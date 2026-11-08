"""Export: your quotes and notes as one document, by author, by topic or by source.

This part only gathers and orders, the same for the PDF and the Word file (export_pdf.py, export_docx.py write
them). It reads the library of the account logged in, as every other part of the app does, and keeps nothing.

The order, everywhere:
- chapters: authors by surname, topics A to Z, sources as in a bibliography (author, then year, then title),
  accents ignored;
- in a source: quotes in page order (xii before 9 before 71; then those with no page, by date), then your notes on
  it by place and date; for a class, a video or a podcast your notes come first, as in the app;
- a quote or a note appears once in a chapter, but may appear in two chapters;
- each quote ends with its reference: « Auteur, Titre, p. 42 ».
"""

import re
import sqlite3
import unicodedata
from datetime import date

from . import db
from .views import SOURCE_LIST_SQL, entries_where, note_dicts, source_dicts

BY = ("author", "topic", "source")
NOTES_FIRST = {"video", "podcast", "class"}
MAX_NAMED = 4           # up to this many chosen items are named on page 1; more are counted

WORDS = {
    "fr": {
        "title": "Citations et notes", "contents": "Sommaire", "bibliography": "Bibliographie", "note": "Note",
        "comment": "Commentaire", "notes": "Notes", "works": "Œuvres", "translated": "Traductions", "said": "Paroles",
        "quoted": "Cité ailleurs", "about": "À propos de {}", "sources": "Sources", "quoted_in": "cité dans",
        "and": "et", "page": "p.", "said_chapter": "Paroles sans source", "open": "« ", "close": " »",
        "by": {"author": "Par auteur", "topic": "Par thème", "source": "Par source"},
        "all": {"author": "tous les auteurs", "topic": "tous les thèmes", "source": "toutes les sources"},
        "several": {"author": "{} auteurs", "topic": "{} thèmes", "source": "{} sources"},
        "exported": "exporté le {}", "quote": ("citation", "citations"), "notes_n": ("note", "notes"),
        "months": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(),
        "kinds": {"article": "article", "video": "vidéo", "podcast": "podcast", "class": "cours", "talk": "conférence"},
    },
    "en": {
        "title": "Quotes and notes", "contents": "Contents", "bibliography": "Bibliography", "note": "Note",
        "comment": "Comment", "notes": "Notes", "works": "Works", "translated": "Translations", "said": "Said",
        "quoted": "Quoted elsewhere", "about": "About {}", "sources": "Sources", "quoted_in": "quoted in",
        "and": "and", "page": "p.", "said_chapter": "Said, with no source", "open": "“", "close": "”",
        "by": {"author": "By author", "topic": "By topic", "source": "By source"},
        "all": {"author": "all authors", "topic": "all topics", "source": "all sources"},
        "several": {"author": "{} authors", "topic": "{} topics", "source": "{} sources"},
        "exported": "exported on {}", "quote": ("quote", "quotes"), "notes_n": ("note", "notes"),
        "months": "January February March April May June July August September October November December".split(),
        "kinds": {"article": "article", "video": "video", "podcast": "podcast", "class": "class", "talk": "talk"},
    },
}


def fold(text: str) -> str:
    """'Élise' sorts with 'Elise', 'de Gaulle' with 'De Gaulle'."""
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").casefold()) if not unicodedata.combining(c))


def page_key(page: str | None, created_at: str) -> tuple:
    p = db.page_sort_key((page or "").strip().removeprefix("p.").strip())
    return (p is None, p or 0, created_at)


CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str | None) -> str:
    """Text as it can go in a PDF or a Word file (a stray control character, from a copy, would stop Word)."""
    return CONTROL.sub("", text or "").strip()


PAGE = re.compile(r"^([0-9]+|[ivxlcdm]+)(\s*[-–]\s*([0-9]+|[ivxlcdm]+))?$", re.I)


class Library:
    """One account's library, read once for the export."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.people = {r["id"]: dict(r) for r in conn.execute("SELECT id, name, sort_name, dates FROM people")}
        self.sources = {s["id"]: s for s in source_dicts(conn, conn.execute(SOURCE_LIST_SQL).fetchall())}
        self.entries = entries_where(conn, "1 = 1", order="e.created_at, e.id", limit=10 ** 9)
        self.notes = note_dicts(conn, conn.execute("SELECT * FROM notes ORDER BY created_at, id").fetchall())
        self.topics = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM topics")}

    # ----- who made what -----

    def makers(self, source: dict) -> list[int]:
        out = []
        for role in ("author", "speaker", "editor"):
            out += [p["id"] for p in source["people"][role] if p["id"] not in out]
        return out

    def made_by(self, pid: int) -> tuple[list[int], list[int]]:
        """(works, translations) of a person, as on their page."""
        works, translated = [], []
        for sid, s in self.sources.items():
            if pid in self.makers(s):
                works.append(sid)
            elif any(p["id"] == pid for p in s["people"]["translator"]):
                translated.append(sid)
        return works, translated

    def about(self, pid: int) -> list[int]:
        return [sid for sid, s in self.sources.items() if any(p["id"] == pid for p in s["people"]["about"])]

    def source_key(self, sid: int) -> tuple:
        s = self.sources[sid]
        first = self.makers(s)[:1]
        year = s["year"] or (int(s["date"][:4]) if s["date"] and s["date"][:4].isdigit() else None)
        return (fold(self.people[first[0]]["sort_name"]) if first else "￿", year or 9999, fold(s["title"]))

    def person_key(self, pid: int) -> str:
        return fold(self.people[pid]["sort_name"])

    def year(self, s: dict) -> str:
        return str(s["year"] or (s["date"] or "")[:4] or "")


class Writer:
    """The document, in the account's language."""

    def __init__(self, lib: Library, lang: str, include: set[str]) -> None:
        self.lib, self.w, self.include = lib, WORDS.get(lang, WORDS["fr"]), include
        self.lang = lang if lang in WORDS else "fr"

    # ----- words -----

    def names(self, ids: list[int]) -> str:
        n = [self.lib.people[i]["name"] for i in ids]
        if len(n) > 3:
            return f"{n[0]} et al."
        return n[0] if len(n) == 1 else f"{', '.join(n[:-1])} {self.w['and']} {n[-1]}"

    def surname(self, pid: int) -> str:
        p = self.lib.people[pid]
        return p["sort_name"].split(",")[0].strip() if "," in p["sort_name"] else p["name"].split()[-1]

    def place(self, page: str | None) -> str:
        p = (page or "").strip()
        return f"{self.w['page']} {p}" if PAGE.match(p) else p

    def plural(self, n: int, forms: tuple[str, str]) -> str:
        return f"{n} {forms[n > 1]}"

    # ----- blocks -----

    def reference(self, e: dict) -> list:
        """« Auteur, Titre, p. 42 »; someone else's words in a work: « X, cité dans Auteur, Titre, p. 42 »."""
        where = self.place(e["page"])
        if e["source"] is None:
            who = e["words_by"] or e["by"]
            return [[(who["name"] if who else "") + (f", {where}" if where else ""), False]]
        s = self.lib.sources[e["source"]["id"]]
        makers = self.lib.makers(s)
        runs = []
        if e["words_by"] and e["words_by"]["id"] not in makers:
            runs.append([f"{e['words_by']['name']}, {self.w['quoted_in']} ", False])
        if makers:
            runs.append([self.names(makers) + ", ", False])
        runs.append([s["title"], True])
        if where:
            runs.append([", " + where, False])
        return runs

    def quote(self, e: dict) -> dict:
        return {"type": "quote", "id": e["id"], "text": clean(e["text"]), "ref": self.reference(e),
                "topics": [t["name"] for t in e["topics"]], "comment": clean(e["note"])}

    def note(self, n: dict) -> dict:
        paras = [p.strip() for p in re.split(r"\n\s*\n", clean(n["text"])) if p.strip()]
        return {"type": "note", "id": n["id"], "title": clean(n["title"]), "place": clean(n["place"]),
                "paras": [" ".join(p.splitlines()) for p in paras], "topics": [t["name"] for t in n["topics"]]}

    def source_head(self, sid: int) -> dict:
        s = self.lib.sources[sid]
        meta = [self.names(self.lib.makers(s))] if self.lib.makers(s) else []
        meta += [x for x in (self.w["kinds"].get(s["kind"]), s["publisher"], self.lib.year(s)) if x]
        return {"title": s["title"], "subtitle": s["subtitle"] or "", "meta": " · ".join(meta)}

    def bib_entry(self, sid: int) -> list:
        s = self.lib.sources[sid]
        makers = self.lib.makers(s)
        runs = [["; ".join(self.lib.people[i]["sort_name"] for i in makers) + ", ", False]] if makers else []
        runs.append([s["title"] + (f". {s['subtitle']}" if s["subtitle"] else ""), True])
        rest = [x for x in (self.w["kinds"].get(s["kind"]), s["publisher"], self.lib.year(s)) if x]
        runs.append([(", " + ", ".join(rest) if rest else "") + ".", False])
        if s["url"] and s["kind"] in ("article", "video", "podcast"):
            runs.append([" " + s["url"], False])
        return runs

    def group(self, sid: int | None, entries: list[dict], notes: list[dict], level: int) -> dict:
        """One source in a chapter: its quotes in page order and your notes on it."""
        q = [self.quote(e) for e in sorted(entries, key=lambda e: page_key(e["page"], e["created_at"]))] \
            if "quotes" in self.include else []
        n = [self.note(x) for x in sorted(notes, key=lambda x: page_key(x["place"], x["created_at"]))] \
            if "notes" in self.include else []
        items = n + q if sid is not None and self.lib.sources[sid]["kind"] in NOTES_FIRST else q + n
        return {"sid": sid, "head": self.source_head(sid) if sid is not None else None, "level": level, "items": items}

    # ----- the three ways -----

    def by_author(self, pid: int, cited: set) -> dict:
        lib, w = self.lib, self.w
        shown_e, shown_n = set(), set()

        def take_e(es):
            es = [e for e in es if e["id"] not in shown_e]
            shown_e.update(e["id"] for e in es)
            return es

        def take_n(ns):
            ns = [n for n in ns if n["id"] not in shown_n]
            shown_n.update(n["id"] for n in ns)
            return ns

        def notes_on(sid, only_theirs=False):
            return [n for n in lib.notes if any(s["id"] == sid for s in n["sources"])
                    and (not only_theirs or any(p["id"] == pid for p in n["people"]))]

        works, translated = lib.made_by(pid)
        made = set(works) | set(translated)
        sections = []
        for key, ids in (("works", works), ("translated", translated)):
            groups = []
            for sid in sorted(ids, key=lambda i: (lib.sources[i]["year"] or 9999, fold(lib.sources[i]["title"]))):
                g = self.group(sid, take_e([e for e in lib.entries if e["source"] and e["source"]["id"] == sid]),
                               take_n(notes_on(sid)), 2)
                if g["items"]:
                    groups.append(g)
            if groups:
                sections.append({"label": w[key], "outlined": False, "groups": groups})
        said = take_e([e for e in lib.entries if e["source"] is None and e["words_by"] and e["words_by"]["id"] == pid])
        if said:
            sections.append({"label": w["said"], "outlined": True, "groups": [self.group(None, said, [], 3)]})
        about_sources = set(lib.about(pid))
        for key, fits, extra in (
            ("quoted", lambda e: e["words_by"] and e["words_by"]["id"] == pid and e["source"]["id"] not in made, set()),
            ("about", lambda e: any(p["id"] == pid for p in e["about"]), about_sources - made),
        ):
            es = take_e([e for e in lib.entries if e["source"] is not None and fits(e)])
            sids = {e["source"]["id"] for e in es} | extra
            groups = []
            for sid in sorted(sids, key=lib.source_key):
                g = self.group(sid, [e for e in es if e["source"]["id"] == sid],
                               take_n(notes_on(sid, only_theirs=sid not in about_sources)), 3)
                if g["items"]:
                    groups.append(g)
            if groups:
                label = w["about"].format(self.surname(pid)) if key == "about" else w[key]
                sections.append({"label": label, "outlined": True, "groups": groups})
        own = take_n([n for n in lib.notes if any(p["id"] == pid for p in n["people"])])
        if own and "notes" in self.include:
            sections.insert(0, {"label": w["notes"], "outlined": True,
                                "groups": [{"sid": None, "head": None, "level": 3, "items": [self.note(n) for n in own]}]})
        cited.update(g["sid"] for s in sections for g in s["groups"] if g["sid"] is not None)
        p = lib.people[pid]
        return {"title": [[p["sort_name"], False]], "meta": p["dates"] or "", "sections": sections}

    def by_topic(self, tid: int, cited: set) -> dict:
        lib, w = self.lib, self.w
        es = [e for e in lib.entries if any(t["id"] == tid for t in e["topics"])]
        ns = [n for n in lib.notes if any(t["id"] == tid for t in n["topics"])]
        sections = []
        loose = [n for n in ns if not n["sources"]]
        if loose and "notes" in self.include:
            sections.append({"label": w["notes"], "outlined": True,
                             "groups": [{"sid": None, "head": None, "level": 3, "items": [self.note(n) for n in loose]}]})
        sids = {e["source"]["id"] for e in es if e["source"]} | {s["id"] for n in ns for s in n["sources"]}
        shown_n, groups = set(), []
        for sid in sorted(sids, key=lib.source_key):
            on = [n for n in ns if any(s["id"] == sid for s in n["sources"]) and n["id"] not in shown_n]
            shown_n.update(n["id"] for n in on)
            g = self.group(sid, [e for e in es if e["source"] and e["source"]["id"] == sid], on, 2)
            if g["items"]:
                groups.append(g)
                cited.add(sid)
        if groups:
            sections.append({"label": w["sources"], "outlined": False, "groups": groups})
        said = [e for e in es if e["source"] is None]
        if said and "quotes" in self.include:
            said.sort(key=lambda e: (fold((e["words_by"] or {}).get("name", "")), e["created_at"]))
            sections.append({"label": w["said"], "outlined": True, "groups": [self.group(None, said, [], 3)]})
        name = lib.topics[tid]
        return {"title": [[name[:1].upper() + name[1:], False]], "meta": "", "sections": sections}

    def by_source(self, sid: int, cited: set) -> dict:
        lib = self.lib
        g = self.group(sid, [e for e in lib.entries if e["source"] and e["source"]["id"] == sid],
                       [n for n in lib.notes if any(s["id"] == sid for s in n["sources"])], 2)
        head = g.pop("head")
        g["head"] = None
        if g["items"]:
            cited.add(sid)
        meta = (head["subtitle"] + "\n" if head["subtitle"] else "") + head["meta"]
        return {"title": [[head["title"], True]], "meta": meta, "sections": [{"label": "", "outlined": False, "groups": [g]}]}

    def said_chapter(self) -> dict:
        said = [e for e in self.lib.entries if e["source"] is None]
        said.sort(key=lambda e: (fold((e["words_by"] or e["by"] or {}).get("sort_name", "")), e["created_at"]))
        g = self.group(None, said, [], 2)
        return {"title": [[self.w["said_chapter"], False]], "meta": "", "sections": [{"label": "", "outlined": False, "groups": [g]}]}


def chosen_in_order(lib: Library, by: str, ids: list[int] | None) -> list[int]:
    """The chosen authors, topics or sources (None: all of them), in the order of the document."""
    if by == "author":
        pool = [pid for pid in lib.people if ids is None or pid in ids]
        return sorted(pool, key=lib.person_key)
    if by == "topic":
        pool = [tid for tid in lib.topics if ids is None or tid in ids]
        return sorted(pool, key=lambda t: fold(lib.topics[t]))
    pool = [sid for sid in lib.sources if ids is None or sid in ids]
    return sorted(pool, key=lib.source_key)


def has_items(chapter: dict) -> bool:
    return any(g["items"] for s in chapter["sections"] for g in s["groups"])


def build(conn: sqlite3.Connection, by: str, ids: list[int] | None, *, said: bool = False, include=("quotes", "notes", "bibliography"),
          lang: str = "fr", account: str = "", today: date | None = None) -> dict:
    """The whole document. ids None: every author, topic or source. said: with the words said with no source
    (by source only). Chapters with nothing in them are left out."""
    lib = Library(conn)
    wr = Writer(lib, lang, set(include))
    w = wr.w
    cited: set[int] = set()
    order = chosen_in_order(lib, by, ids)
    make = {"author": wr.by_author, "topic": wr.by_topic, "source": wr.by_source}[by]
    chapters = [c for c in (make(i, cited) for i in order) if has_items(c)]
    if by == "source" and said and "quotes" in include:
        c = wr.said_chapter()
        if has_items(c):
            chapters.append(c)
    # what was chosen, for page 1 and the file's name
    if ids is None:
        chosen = w["all"][by]
        short = chosen
    else:
        names = {"author": lambda i: lib.people[i]["name"], "topic": lambda i: lib.topics[i],
                 "source": lambda i: lib.sources[i]["title"]}[by]
        shorts = {"author": wr.surname, "topic": lambda i: lib.topics[i], "source": lambda i: lib.sources[i]["title"]}[by]
        picked = order + ([None] if said and by == "source" else [])
        count = len(picked)
        named = [names(i) if i is not None else w["said_chapter"] for i in picked]
        chosen = ", ".join(named) if count <= MAX_NAMED else w["several"][by].format(count)
        short = ", ".join(shorts(i) if i is not None else w["said_chapter"] for i in picked) if count <= 3 \
            else w["several"][by].format(count)
    today = today or date.today()
    quotes = {i["id"] for c in chapters for s in c["sections"] for g in s["groups"] for i in g["items"] if i["type"] == "quote"}
    notes = {i["id"] for c in chapters for s in c["sections"] for g in s["groups"] for i in g["items"] if i["type"] == "note"}
    when = f"{today.day} {w['months'][today.month - 1]} {today.year}"
    byline = " · ".join(x for x in (account, w["exported"].format(when), wr.plural(len(quotes), w["quote"]),
                                    wr.plural(len(notes), w["notes_n"])) if x)
    return {
        "lang": wr.lang,
        "title": w["title"],
        "subtitle": f"{w['by'][by]} — {chosen}",
        "byline": byline,
        "account": account,
        "short": short,
        "date": today.isoformat(),
        "labels": {k: w[k] for k in ("contents", "bibliography", "note", "comment", "open", "close")},
        "chapters": chapters,
        "bibliography": [wr.bib_entry(s) for s in sorted(cited, key=lib.source_key)] if "bibliography" in include else [],
        "counts": {"chapters": len(chapters), "quotes": len(quotes), "notes": len(notes)},
    }


def choices(conn: sqlite3.Connection) -> dict:
    """What can be chosen, with what each holds, in the document's order."""
    lib = Library(conn)
    entries_of: dict[int, list] = {}
    for e in lib.entries:
        if e["source"]:
            entries_of.setdefault(e["source"]["id"], []).append(e)
    notes_of: dict[int, list] = {}
    for n in lib.notes:
        for s in n["sources"]:
            notes_of.setdefault(s["id"], []).append(n)
    authors = []
    for pid in chosen_in_order(lib, "author", None):
        works, translated = lib.made_by(pid)
        quotes = {e["id"] for sid in works + translated for e in entries_of.get(sid, [])}
        quotes |= {e["id"] for e in lib.entries if (e["words_by"] and e["words_by"]["id"] == pid)
                   or any(p["id"] == pid for p in e["about"])}
        notes = {n["id"] for sid in works + translated for n in notes_of.get(sid, [])}
        notes |= {n["id"] for n in lib.notes if any(p["id"] == pid for p in n["people"])}
        kinds: dict[str, int] = {}
        for sid in works:
            kinds[lib.sources[sid]["kind"]] = kinds.get(lib.sources[sid]["kind"], 0) + 1
        if quotes or notes:
            authors.append({"id": pid, "name": lib.people[pid]["sort_name"], "works": kinds,
                            "quotes": len(quotes), "notes": len(notes)})
    topics = []
    for tid in chosen_in_order(lib, "topic", None):
        quotes = [e for e in lib.entries if any(t["id"] == tid for t in e["topics"])]
        notes = [n for n in lib.notes if any(t["id"] == tid for t in n["topics"])]
        if quotes or notes:
            topics.append({"id": tid, "name": lib.topics[tid], "quotes": len(quotes), "notes": len(notes),
                           "sources": len({e["source"]["id"] for e in quotes if e["source"]})})
    sources = []
    for sid in chosen_in_order(lib, "source", None):
        s = lib.sources[sid]
        quotes, notes = len(entries_of.get(sid, [])), len(notes_of.get(sid, []))
        if quotes or notes:
            sources.append({"id": sid, "kind": s["kind"], "title": s["title"], "by": [lib.people[i]["name"] for i in lib.makers(s)],
                            "year": lib.year(s), "quotes": quotes, "notes": notes})
    return {"authors": authors, "topics": topics, "sources": sources,
            "said": sum(1 for e in lib.entries if e["source"] is None)}


def file_name(doc: dict, ext: str) -> str:
    """'Marginote — Marceau, Verdier — 2026-11-08.pdf', safe on every system."""
    short = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", doc["short"]).strip()
    if len(short) > 80:
        short = short[:79].rstrip() + "…"
    return f"Marginote — {short} — {doc['date']}.{ext}"
