"""Finding a passage copied from a PDF reader in the PDFs a library keeps: which PDF, which page, which words.

What a reader puts on the clipboard is rarely the page's text as printed: lines broken in the middle of a
sentence, words cut with a hyphen (com-↵mence, com- mence), ligatures as one sign (ﬁ) or lost (classi cation),
curly or straight quotes, footnote calls glued to a word (lecture1), a footnote or a running head caught in
the middle when the selection crosses the foot of a column or a page.

So both sides are compared as letters only: accents, case, spaces, punctuation and line breaks taken away.
"com-↵mence", "com- mence" and "commence" are then the same; a lost ligature or a footnote call is a
difference of two letters, a running head one stretch of letters too many, and the rest still lines up.

    1. candidate pages: the passage's rarest words, looked up in page_fts (every PDF of the library at once;
       the one being read first)
    2. on each candidate and the pages around it: runs of ten letters shared by the passage and the pages
       vote for where the passage starts; the best place is then aligned letter by letter (difflib)
    3. the share of the passage's letters found there, in order, says how sure the match is
    4. the text kept is the PDF's own words, without what the passage did not have (a footnote, a running
       head between two pages)
"""

import difflib
import re
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from . import db, ocr

SEED = 10              # letters in a run that votes
SURE = 0.9             # share of the passage's letters found in order: kept at once
LIKELY = 0.6           # below: not this place
MAX_LETTERS = 20_000


def fold(text: str) -> str:
    """Compatibility forms (ﬁ, 𝑥, ¹) as plain letters, lower case, no accents."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text or "").casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def letters(text: str) -> str:
    return "".join(ch for ch in fold(text) if ch.isalnum())


def index_text(words: list[ocr.Word]) -> str:
    """A page's text as page_fts keeps it: words cut at a line's end glued back, folded, punctuation out."""
    return re.sub(r"[^\w]+", " ", fold(ocr.join_words(words)).replace("_", " ")).strip()


@dataclass
class PageWords:
    photo_id: str
    document_id: str
    index: int
    page: str
    height: int
    words: list[ocr.Word]


@dataclass
class Match:
    document_id: str
    pages: list[PageWords]                       # the pages the passage is on (one, or two when it crosses)
    start: tuple[int, int]                       # (position in pages, word index)
    end: tuple[int, int]
    score: float                                 # share of the passage's letters found, in order
    text: str                                    # the PDF's own words
    words_kept: list[tuple[int, int]] = field(default_factory=list)

    @property
    def page(self) -> str:
        first, last = self.pages[self.start[0]].page, self.pages[self.end[0]].page
        return first if first == last else f"{first}–{last}"

    @property
    def photo_id(self) -> str:
        return self.pages[self.start[0]].photo_id

    @property
    def word_range(self) -> tuple[int, int]:
        """On the first page: the words to highlight (to its end, when the passage goes on to the next)."""
        first = self.pages[self.start[0]]
        end = self.end[1] if self.end[0] == self.start[0] else max(w.i for w in first.words)
        return self.start[1], end

    def place(self) -> tuple:
        return (self.document_id, self.pages[self.start[0]].index, self.start[1])


def _query(passage: str) -> str | None:
    """The passage's longest words, any of which a page may hold (bm25 then ranks the pages holding most)."""
    tokens = [t for t in re.sub(r"[^\w]+", " ", fold(passage)).split() if len(t) >= 4 and not t.isdigit()]
    if not tokens:
        tokens = [t for t in re.sub(r"[^\w]+", " ", fold(passage)).split() if len(t) >= 2]
    chosen = sorted(set(tokens), key=lambda t: (-len(t), t))[:12]
    return " OR ".join(f'"{t}"' for t in chosen) if chosen else None


def candidate_pages(conn: sqlite3.Connection, passage: str, document_id: str | None = None, limit: int = 6) -> list[sqlite3.Row]:
    query = _query(passage)
    if not query:
        return []
    sql = ("SELECT p.id, p.document_id, p.page_index FROM page_fts f JOIN photos p ON p.id = f.photo_id "
           "JOIN documents d ON d.id = p.document_id WHERE page_fts MATCH ? AND d.status != 'failed'")
    args: list = [query]
    if document_id:
        sql += " AND p.document_id = ?"
        args.append(document_id)
    return conn.execute(sql + " ORDER BY bm25(page_fts) LIMIT ?", (*args, limit)).fetchall()


def load_pages(conn: sqlite3.Connection, document_id: str, first: int, last: int) -> list[PageWords]:
    rows = conn.execute(
        "SELECT p.id, p.page_index, p.detected_page, p.height, p.words, s.pages AS journal_pages FROM photos p "
        "JOIN documents d ON d.id = p.document_id LEFT JOIN sources s ON s.id = d.source_id "
        "WHERE p.document_id = ? AND p.page_index BETWEEN ? AND ? ORDER BY p.page_index",
        (document_id, first, last)).fetchall()
    from .documents import page_label
    return [PageWords(r["id"], document_id, r["page_index"], page_label(r["page_index"], r["detected_page"], r["journal_pages"]),
                      r["height"], ocr.words_from_dicts(db.unpack_words(r["words"]))) for r in rows]


def _stream(pages: list[PageWords]) -> tuple[str, list[tuple[int, int]]]:
    """The pages' letters in reading order, and for each letter the (page, word) it belongs to."""
    chars: list[str] = []
    owner: list[tuple[int, int]] = []
    for k, page in enumerate(pages):
        for w in page.words:
            for ch in letters(w.text):
                chars.append(ch)
                owner.append((k, w.i))
    return "".join(chars), owner


def align(passage: str, pages: list[PageWords]) -> Match | None:
    """Where the passage is on these pages (consecutive pages of one PDF), if it is there."""
    p = letters(passage)[:MAX_LETTERS]
    s, owner = _stream(pages)
    if len(p) < 12 or len(s) < len(p) * 0.5:
        return None
    seeds: dict[str, list[int]] = {}
    for i in range(len(s) - SEED + 1):
        seeds.setdefault(s[i:i + SEED], []).append(i)
    votes: Counter = Counter()
    step = max(1, len(p) // 400)
    for j in range(0, len(p) - SEED + 1, step):
        for i in seeds.get(p[j:j + SEED], ())[:20]:
            votes[(i - j) // 8] += 1                 # where the passage would start, in bins of 8 letters
    if not votes:
        return None
    # the places most voted for (a text may repeat itself: the best few are each aligned)
    ranked = sorted(votes, key=lambda b: -(votes[b - 1] + votes[b] + votes[b + 1]))
    starts: list[int] = []
    for b in ranked:
        if all(abs(b - x) * 8 > len(p) // 2 for x in starts):
            starts.append(b)
        if len(starts) == 3:
            break
    best: Match | None = None
    for b in starts:
        found = _at(p, s, owner, pages, b * 8)
        if found and (best is None or found.score > best.score):
            best = found
    return best


def _at(p: str, s: str, owner, pages: list[PageWords], start: int) -> "Match | None":
    slack = 40 + len(p) // 5
    lo = max(0, start - slack)
    hi = min(len(s), start + len(p) + slack)
    blocks = [b for b in difflib.SequenceMatcher(None, p, s[lo:hi], autojunk=False).get_matching_blocks() if b.size >= 3]
    if not blocks:
        return None
    score = sum(b.size for b in blocks) / len(p)
    if score < SURE:
        # a passage with a stretch the pages do not have (a footnote, a running head copied with it):
        # judged on what lies around that stretch
        score = max(score, _around_inserts(p, blocks))
    if score < LIKELY:
        return None
    first, last = lo + blocks[0].b, lo + blocks[-1].b + blocks[-1].size - 1
    matched = set()
    for b in blocks:
        matched.update(range(lo + b.b, lo + b.b + b.size))
    return _match(pages, owner, first, last, matched, score)


def _around_inserts(p: str, blocks) -> float:
    """The share found when at most two stretches of the passage that the pages do not have at all, right
    there, are set aside: a footnote or a running head the selection caught, in the middle of the passage."""
    inserts = []
    for b1, b2 in zip(blocks, blocks[1:]):
        extra = b2.a - (b1.a + b1.size)          # letters of the passage between two found stretches
        skipped = b2.b - (b1.b + b1.size)        # letters of the page between them
        if extra >= 25 and skipped <= 8:
            inserts.append(extra)
    aside = sum(sorted(inserts, reverse=True)[:2])
    found = sum(b.size for b in blocks)
    rest = len(p) - aside
    return found / rest if aside and found >= 100 and rest > 0 else 0.0


def _match(pages: list[PageWords], owner, first: int, last: int, matched: set[int], score: float) -> Match:
    start, end = owner[first], owner[last]
    # every word between the two ends, in reading order, with how much of it the passage had
    inside: list[tuple[int, int]] = []
    seen = set()
    hit: Counter = Counter()
    total: Counter = Counter()
    for pos in range(first, last + 1):
        key = owner[pos]
        total[key] += 1
        if pos in matched:
            hit[key] += 1
        if key not in seen:
            seen.add(key)
            inside.append(key)
    for k in range(start[0], end[0] + 1):            # words with no letters (a dash, a quote mark) between the two ends
        for w in pages[k].words:
            key = (k, w.i)
            if key not in seen and (k, w.i) > start and (k, w.i) < end and not letters(w.text):
                seen.add(key)
                inside.append(key)
    inside.sort()
    # words the passage did not have, in a stretch of 12 letters or more: a footnote, a running head, left out
    kept: list[tuple[int, int]] = []
    run: list[tuple[int, int]] = []
    run_letters = 0

    def flush() -> None:
        nonlocal run, run_letters
        if run_letters < 12:
            kept.extend(run)
        run, run_letters = [], 0

    for key in inside:
        if total[key] and hit[key] < 0.5 * total[key]:
            run.append(key)
            run_letters += total[key]
        else:
            flush()
            kept.append(key)
    flush()
    kept = [key for key in kept if not _furniture(pages, key, start, end)]
    by_index = [{w.i: w for w in page.words} for page in pages]
    words = []
    for k, i in kept:
        w = by_index[k][i]
        words.append(ocr.Word(w.i, w.text, w.conf, w.x, w.y, w.w, w.h, w.line + 100_000 * k))   # lines of two pages never mix
    return Match(pages[0].document_id, pages, start, end, score, ocr.join_words(words), kept)


def _furniture(pages: list[PageWords], key: tuple[int, int], start, end) -> bool:
    """A running head or a page number, where the passage goes from one page to the next."""
    k, i = key
    if start[0] == end[0]:
        return False
    page = pages[k]
    w = next((x for x in page.words if x.i == i), None)
    if w is None:
        return False
    same_line = [x for x in page.words if x.line == w.line]
    near_edge = (k > start[0] and w.y < 0.08 * page.height) or (k < end[0] and w.y + w.h > 0.92 * page.height)
    return near_edge and len(same_line) <= 12


def find(conn: sqlite3.Connection, passage: str, reading: str | None = None) -> tuple[Match | None, list[Match]]:
    """The place of a passage in the library's PDFs: the best match, and the other places it might be.
    The PDF being read (reading) is looked in first, and wins a tie."""
    tried: set = set()
    matches: list[Match] = []

    def around(rows) -> None:
        for row in rows:
            key = (row["document_id"], row["page_index"])
            if key in tried:
                continue
            tried.update({(row["document_id"], row["page_index"] + d) for d in (-1, 0, 1)})
            pages = load_pages(conn, row["document_id"], row["page_index"] - 1, row["page_index"] + 1)
            found = align(passage, pages)
            if found and all(m.place() != found.place() for m in matches):
                matches.append(found)

    if reading:
        around(candidate_pages(conn, passage, reading, limit=4))
    if not any(m.score >= SURE for m in matches):
        around(candidate_pages(conn, passage))
    if not matches:
        return None, []
    matches.sort(key=lambda m: (-round(m.score, 2), m.document_id != reading))
    return matches[0], matches[1:]


def is_sure(best: Match | None, others: list[Match], reading: str | None = None) -> bool:
    """Kept at once only when the passage is found, and found in one place (or the same text twice, once in
    the PDF being read)."""
    if not best or best.score < SURE or len(letters(best.text)) < 20:
        return False
    rivals = [m for m in others if m.score >= SURE]
    return not rivals or (best.document_id == reading and all(m.document_id != reading for m in rivals))
