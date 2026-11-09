"""PDFs kept in a library. Sent once, read page by page in the background, recognised from what is printed
in their first pages (a DOI, an arXiv number, an ISBN), then used like page photos: each page is a row of
the photos table with its words, drawn as a picture only when someone looks at it.

    documents   one row per PDF: its file in pdfs/, its source once known, how far it has been read
    photos      one row per page (document_id, page_index); path is empty, the picture comes from the PDF
    page_fts    the text of every page, to find the page a passage sent from a reader is on
"""

import hashlib
import json
import logging
import re
import sqlite3
import statistics
import uuid
from collections import Counter
from pathlib import Path
from typing import BinaryIO

from . import db, ids, lookup, ocr, pdfs, scholar
from .files import INBOX

log = logging.getLogger("marginote")
MAX_PDF = 300 * 1024 * 1024
FIRST_PAGES = 3          # where an article's DOI or arXiv number is printed
BOOK_PAGES = 8           # where a book's ISBN is (the copyright page)


class TooBig(ValueError):
    pass


def page_text(words: list[ocr.Word]) -> str:
    """A page's text in one piece, words cut at the end of a line glued back: what passages are looked for in."""
    return ocr.join_words(words)


def save_upload(lib, conn: sqlite3.Connection, stream: BinaryIO, name: str | None,
                source_id: int | None) -> tuple[str, bool]:
    """Keep a sent PDF in pdfs/inbox/ (or its source's folder). Returns (document id, whether it is new);
    the same file sent twice is kept once. Raises TooBig, or pdfs.NotAPdf."""
    doc_id = uuid.uuid4().hex
    tmp = lib.files.pdfs / INBOX / f".{doc_id}.part"
    digest = hashlib.sha256()
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_PDF:
                    raise TooBig("PDF larger than 300 MB")
                digest.update(chunk)
                out.write(chunk)
        sha = digest.hexdigest()
        same = conn.execute("SELECT id FROM documents WHERE sha256 = ?", (sha,)).fetchone()
        if same:
            return same["id"], False
        pages, meta = pdfs.count_pages(tmp)
        if pages == 0:
            raise pdfs.NotAPdf("This PDF has no pages")
        rel = f"{INBOX}/{doc_id}.pdf"
        tmp.replace(lib.files.pdfs / rel)
        conn.execute(
            "INSERT INTO documents (id, source_id, path, name, sha256, pages, status, queued, found, created_at) "
            "VALUES (?, NULL, ?, ?, ?, ?, 'reading', ?, ?, ?)",
            (doc_id, rel, (name or "document.pdf")[:200], sha, pages, 0 if source_id else 1,
             json.dumps({"meta": meta}, ensure_ascii=False), db.now()))
        if source_id:
            lib.files.file_document(conn, doc_id, source_id)
        conn.commit()
        return doc_id, True
    finally:
        tmp.unlink(missing_ok=True)


def read_document(lib, doc_id: str, langs: str, lookups: bool) -> None:
    """Read every page not read yet (a restart picks up where it stopped), then recognise the PDF."""
    conn = lib.connect()
    try:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row or row["status"] != "reading":
            return
        with pdfs.PDFIUM:
            doc = pdfs.open_pdf(lib.files.pdfs / row["path"])   # stays readable if the file is moved meanwhile
        try:
            for index in range(row["read_pages"], row["pages"]):
                if not conn.execute("SELECT 1 FROM documents WHERE id = ?", (doc_id,)).fetchone():
                    return                                       # deleted while being read
                with pdfs.PDFIUM:
                    page = pdfs.read_page(doc, index)
                words, printed = page.words, None
                if page.scanned:
                    path = lib.files.pdfs / conn.execute("SELECT path FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
                    with ocr.OCR_SLOT:
                        try:
                            words, printed = pdfs.read_scanned_page(path, index, page.width, page.height, langs)
                        finally:
                            ocr.release_memory()
                number = pdfs.page_number(page.label, words, page.width, page.height) if not printed else printed
                add_page(conn, row, index, page.width, page.height, words, number)
                conn.execute("UPDATE documents SET read_pages = ? WHERE id = ?", (index + 1, doc_id))
                conn.commit()
        finally:
            with pdfs.PDFIUM:
                doc.close()
        fill_page_numbers(conn, doc_id)
        found = json.loads(row["found"] or "{}")
        found.update(recognise(lib, conn, doc_id, row["name"], lookups))
        conn.execute("UPDATE documents SET status = 'ready', found = ? WHERE id = ?",
                     (json.dumps(found, ensure_ascii=False), doc_id))
        conn.commit()
    except Exception:
        log.exception("Reading a PDF failed")
        conn.execute("UPDATE documents SET status = 'failed' WHERE id = ?", (doc_id,))
        conn.commit()
    finally:
        conn.close()


def add_page(conn: sqlite3.Connection, doc: sqlite3.Row, index: int, width: int, height: int,
             words: list[ocr.Word], number: str | None) -> str:
    photo_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO photos (id, path, width, height, sha256, words, detected_page, source_id, queued, status, created_at, "
        "document_id, page_index) VALUES (?, '', ?, ?, ?, ?, ?, (SELECT source_id FROM documents WHERE id = ?), 0, 'ready', ?, ?, ?)",
        (photo_id, width, height, f"{doc['sha256']}:{index}", db.pack_words(ocr.words_to_dicts(words)), number,
         doc["id"], db.now(), doc["id"], index))
    conn.execute("INSERT INTO page_fts (photo_id, text) VALUES (?, ?)", (photo_id, page_text(words)))
    return photo_id


def fill_page_numbers(conn: sqlite3.Connection, doc_id: str) -> None:
    """A page with no number printed on it (an article's first page, a chapter's opening) takes the number
    its neighbours give it, when most numbered pages agree: page 4 of the PDF is p. 48 if page 5 is p. 49."""
    rows = conn.execute("SELECT id, page_index, detected_page FROM photos WHERE document_id = ? ORDER BY page_index",
                        (doc_id,)).fetchall()
    offsets = [int(r["detected_page"]) - r["page_index"] for r in rows if (r["detected_page"] or "").isdigit()]
    if not offsets:
        return
    offset, count = Counter(offsets).most_common(1)[0]
    if count < max(2, len(offsets) / 2):
        return
    for r in rows:
        if not r["detected_page"] and r["page_index"] + offset >= 1:
            conn.execute("UPDATE photos SET detected_page = ? WHERE id = ?", (str(r["page_index"] + offset), r["id"]))
    conn.commit()


def _guess_title(words: list[ocr.Word], height: int) -> str | None:
    """The largest writing near the top of the first page, a line or two: most often the title."""
    lines: dict[int, list[ocr.Word]] = {}
    for w in words:
        if w.y < 0.5 * height:
            lines.setdefault(w.line, []).append(w)
    if not lines or len(words) < 20:
        return None
    usual = statistics.median(w.h for w in words)
    sizes = {n: statistics.median(w.h for w in ws) for n, ws in lines.items()}
    biggest = max(sizes.values())
    if biggest < 1.3 * usual:
        return None
    chosen = [n for n in sorted(lines) if sizes[n] >= 0.85 * biggest]
    run = [chosen[0]] + [n for k, n in enumerate(chosen[1:], 1) if n == chosen[k - 1] + 1]
    title = " ".join(ocr.join_words(sorted(lines[n], key=lambda w: w.i)) for n in run[:3])
    return title if 6 <= len(title) <= 300 else None


def _sensible(title: str | None) -> str | None:
    if not title or len(title) < 6 or re.search(r"\.(docx?|tex|pdf|indd)\b|^microsoft|^untitled|^document\d*$", title, re.I):
        return None
    return title.strip()


def recognise(lib, conn: sqlite3.Connection, doc_id: str, name: str | None, lookups: bool) -> dict:
    """What the PDF is: the first DOI or arXiv number printed in its first pages (its own, on an article),
    else an ISBN on a book's first pages, else its file name; then what the registries say of it."""
    row = conn.execute("SELECT path FROM documents WHERE id = ?", (doc_id,)).fetchone()
    pages = conn.execute("SELECT page_index, words, width, height FROM photos WHERE document_id = ? AND page_index < ? "
                         "ORDER BY page_index", (doc_id, BOOK_PAGES)).fetchall()
    words = {r["page_index"]: ocr.words_from_dicts(db.unpack_words(r["words"])) for r in pages}
    try:
        layer = pdfs.first_text(lib.files.pdfs / row["path"], FIRST_PAGES)   # PDFium's own reading: sideways stamps too
    except pdfs.NotAPdf:
        layer = []
    texts = [(layer[i] if i < len(layer) else "") + "\n" + page_text(words.get(i, [])) for i in range(len(words))]
    found: dict = {"by": None, "value": None, "page": None}

    def first(kinds: tuple[str, ...], upto: int) -> bool:
        for i, text in enumerate(texts[:upto]):
            for item in ids.ids_in_text(text):
                if item["kind"] in kinds:
                    found.update(by=item["kind"], value=item["value"], page=i)
                    return True
        return False

    named = ids.clean_arxiv(Path(name or "").stem) if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", Path(name or "").stem) else None
    if not (first(("doi",), 1) or first(("arxiv",), 1) or first(("doi", "arxiv"), FIRST_PAGES)
            or first(("isbn",), BOOK_PAGES)) and named:
        found.update(by="arxiv", value=named, page=None)
    first_words = words.get(0, [])
    found["title"] = _guess_title(first_words, pages[0]["height"]) if first_words and pages else None
    meta = json.loads(conn.execute("SELECT found FROM documents WHERE id = ?", (doc_id,)).fetchone()[0] or "{}").get("meta", {})
    found["title"] = found["title"] or _sensible(meta.get("title"))
    found.update(source=None, note=None)
    if found["by"]:
        if not lookups:
            found["note"] = "Online lookups are turned off"
        else:
            try:
                found["source"] = scholar.identify(found["by"], found["value"])
                if not found["source"]:
                    found["note"] = scholar.NOT_FOUND[found["by"]]
            except lookup.LookupUnavailable:
                found["note"] = "The online services could not be reached from your server"
    return found


def existing_source(conn: sqlite3.Connection, found: dict) -> dict | None:
    """The source of your library the PDF is, by its DOI, arXiv number or ISBN."""
    src = found.get("source") or {}
    for column, value in (("doi", src.get("doi")), ("arxiv", src.get("arxiv")), ("isbn", src.get("isbn")),
                          (found.get("by"), found.get("value"))):
        if column in ("doi", "arxiv", "isbn") and value:
            hit = conn.execute(f"SELECT id, kind, title FROM sources WHERE {column} = ?", (value,)).fetchone()
            if not hit and column == "isbn":
                hit = conn.execute("SELECT id, kind, title FROM sources WHERE isbn = ?", (lookup.isbn10(value),)).fetchone()
            if hit:
                return dict(hit)
    return None


def page_label(index: int, detected: str | None, journal_pages: str | None) -> str:
    """The page as cited: its printed number, else counted from the article's first page in its journal,
    else its place in the PDF."""
    if detected:
        return detected
    start = re.match(r"\d+", journal_pages or "")
    return str(int(start.group()) + index) if start else str(index + 1)
