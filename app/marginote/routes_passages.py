"""Passages sent from elsewhere (a PDF reader, a web page, another app), and what waits to be sorted.

A passage found in one of your PDFs, in one place, is kept at once: as a quote of that PDF's source, with
its page and its place on the page, in the PDF's own words. Anything else waits in À trier with what was
guessed (the place it may be, the source it may be from), to confirm with one tap.
"""

import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, documents, matching
from .context import Context
from .views import entry_dict, load_source

Origin = Literal["windows", "iphone", "android", "web", "app"]


class PassageIn(BaseModel):
    text: str = Field("", max_length=200_000, description="The passage, as copied")
    note: str | None = Field(None, max_length=50_000, description="A comment written with it")
    url: str | None = Field(None, max_length=4000, description="The page it was copied from, if a web page")
    title: str | None = Field(None, max_length=1000, description="That page's title")
    origin: Origin = "app"


class FindIn(BaseModel):
    text: str = Field(max_length=200_000)


class KeepIn(BaseModel):
    source_id: int | None = Field(None, description="The source it is from, when not where it was guessed to be")
    page: str | None = None
    text: str | None = Field(None, description="The passage as corrected; else as guessed, or as sent")


def match_dict(conn: sqlite3.Connection, m: matching.Match) -> dict:
    doc = conn.execute("SELECT d.name, d.source_id, s.title FROM documents d LEFT JOIN sources s ON s.id = d.source_id "
                       "WHERE d.id = ?", (m.document_id,)).fetchone()
    start, end = m.word_range
    return {"document_id": m.document_id, "document_name": doc["name"], "source_id": doc["source_id"],
            "source_title": doc["title"], "photo_id": m.photo_id, "page_index": m.pages[m.start[0]].index,
            "page": m.page, "word_start": start, "word_end": end, "text": m.text, "score": round(m.score, 3)}


def add_entry(conn: sqlite3.Connection, source_id: int, text: str, page: str | None, note: str | None,
              photo_id: str | None = None, word_start: int | None = None, word_end: int | None = None) -> int:
    stamp = db.now()
    entry_id = conn.execute(
        "INSERT INTO entries (source_id, text, note, page, page_sort, photo_id, word_start, word_end, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, text, (note or "").strip() or None, page, db.page_sort_key(page), photo_id, word_start, word_end,
         stamp, stamp)).lastrowid
    db.reindex_entry(conn, entry_id)
    return entry_id


def waiting_dict(row: sqlite3.Row) -> dict:
    return {**{k: row[k] for k in ("id", "text", "note", "url", "title", "origin", "source_id", "reason", "created_at")},
            "guess": json.loads(row["guess"]) if row["guess"] else None}


def router(ctx: Context) -> APIRouter:
    api = APIRouter(dependencies=ctx.auth, tags=["passages"])
    get_db = ctx.get_db

    def place(conn: sqlite3.Connection, text: str) -> tuple[matching.Match | None, list[matching.Match], bool]:
        reading = documents.reading(conn)
        best, others = matching.find(conn, text, reading)
        return best, others, matching.is_sure(best, others, reading)

    @api.post("/api/passages/find")
    def find_passage(body: FindIn, conn: sqlite3.Connection = Depends(get_db)):
        """Where a passage is in your PDFs, without keeping anything: the best place (PDF, page, words, the
        PDF's own text and how much of the passage was found there), whether it is sure, and other places."""
        best, others, sure = place(conn, body.text)
        return {"match": match_dict(conn, best) if best else None, "sure": sure,
                "others": [match_dict(conn, m) for m in others[:4]]}

    def wait(conn: sqlite3.Connection, body: PassageIn, reason: str, source_id: int | None = None,
             guess: dict | None = None) -> dict:
        wid = conn.execute(
            "INSERT INTO waiting (text, note, url, title, origin, source_id, guess, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (body.text.strip() or None, (body.note or "").strip() or None, body.url, body.title, body.origin, source_id,
             json.dumps(guess, ensure_ascii=False) if guess else None, reason, db.now())).lastrowid
        conn.commit()
        return {"waiting": waiting_dict(conn.execute("SELECT * FROM waiting WHERE id = ?", (wid,)).fetchone())}

    @api.post("/api/passages", status_code=201)
    def send_passage(body: PassageIn, conn: sqlite3.Connection = Depends(get_db)):
        """A passage copied while reading. Found in one of your PDFs, in one place: kept at once as a quote
        (answer: kept, and where). Otherwise it waits in À trier (answer: waiting), with where it may be."""
        if not body.text.strip() and not body.url:
            raise HTTPException(422, "Send a passage, a link, or both")
        if not body.text.strip():
            return wait(conn, body, "source")
        best, others, sure = place(conn, body.text)
        if best and sure:
            guess = match_dict(conn, best)
            if guess["source_id"] is None:              # its PDF has not been given its source yet
                return wait(conn, body, "source", guess=guess)
            entry_id = add_entry(conn, guess["source_id"], best.text, best.page, body.note, best.photo_id,
                                 guess["word_start"], guess["word_end"])
            documents.set_reading(conn, best.document_id)
            conn.commit()
            return {"kept": entry_dict(conn, entry_id), "where": guess}
        guess = match_dict(conn, best) if best else None
        return wait(conn, body, "place" if best else "source", source_id=guess["source_id"] if guess else None, guess=guess)

    @api.get("/api/waiting")
    def list_waiting(conn: sqlite3.Connection = Depends(get_db)):
        """What waits in À trier: passages and links sent, with what was guessed. Newest first."""
        return [waiting_dict(r) for r in conn.execute("SELECT * FROM waiting ORDER BY created_at DESC, id DESC")]

    @api.post("/api/waiting/{waiting_id}/keep", status_code=201)
    def keep_waiting(waiting_id: int, body: KeepIn, conn: sqlite3.Connection = Depends(get_db)):
        """Keep a waiting passage: where it was guessed to be, or in the source you say (with its page)."""
        row = conn.execute("SELECT * FROM waiting WHERE id = ?", (waiting_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Nothing waiting with this id")
        guess = json.loads(row["guess"]) if row["guess"] else None
        if guess:          # its PDF may have been given its source since
            now = conn.execute("SELECT source_id FROM documents WHERE id = ?", (guess["document_id"],)).fetchone()
            guess["source_id"] = now["source_id"] if now else None
        source_id = body.source_id or row["source_id"] or (guess or {}).get("source_id")
        if source_id is None:
            raise HTTPException(422, "Say which source it is from")
        load_source(conn, source_id)
        on_guess = bool(guess and guess.get("source_id") == source_id
                        and conn.execute("SELECT 1 FROM photos WHERE id = ?", (guess["photo_id"],)).fetchone())
        text = (body.text or (guess["text"] if on_guess else None) or row["text"] or "").strip()
        if not text:
            raise HTTPException(422, "There is no passage to keep: write it, or keep the link as a source")
        page = body.page if body.page is not None else (guess["page"] if on_guess else None)
        entry_id = add_entry(conn, source_id, text, page or None, row["note"],
                             guess["photo_id"] if on_guess else None, guess["word_start"] if on_guess else None,
                             guess["word_end"] if on_guess else None)
        conn.execute("DELETE FROM waiting WHERE id = ?", (waiting_id,))
        if on_guess:
            documents.set_reading(conn, guess["document_id"])
        conn.commit()
        return entry_dict(conn, entry_id)

    @api.delete("/api/waiting/{waiting_id}")
    def drop_waiting(waiting_id: int, conn: sqlite3.Connection = Depends(get_db)):
        if not conn.execute("DELETE FROM waiting WHERE id = ?", (waiting_id,)).rowcount:
            raise HTTPException(404, "Nothing waiting with this id")
        conn.commit()
        return {"deleted": waiting_id}

    return api
