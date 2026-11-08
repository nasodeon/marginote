"""Quotes (from a source, or words someone said), and searching them."""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import db, ocr
from .context import Context, Library
from .views import ENTRY_SQL, entry_dict, entry_dicts, entries_where, load_photo, load_source

Medium = Literal["book", "ebook", "article", "video", "podcast", "class", "talk", "other", "said"]
PersonRef = int | str


class EntryIn(BaseModel):
    source_id: int | None = Field(None, description="Left out: words someone said, from no source (give words_by)")
    text: str | None = Field(None, description="Leave empty to take the words selected on the photo")
    note: str | None = Field(None, description="Your comment on the quote")
    page: str | None = Field(None, description="Where in the source: '57', 'III, 9 sc.', 'ch. 2'. "
                                               "Left empty, the page number found on the photo. "
                                               "With no source: where and when it was said")
    photo_id: str | None = None
    word_start: int | None = None
    word_end: int | None = None
    words_by: PersonRef | None = Field(None, description="Whose words, when not the source's author's; "
                                                        "with no source, who said it")
    about: list[PersonRef] | None = Field(None, description="Whom it is about. Left out: whom its source is about")
    topics: list[str] | None = Field(None, description="Left out: its source's topics")


class EntryPatch(BaseModel):
    source_id: int | None = Field(None, description="null: from no source any more (it stays its author's words)")
    text: str | None = None
    note: str | None = None
    page: str | None = None
    word_start: int | None = None
    word_end: int | None = None
    words_by: PersonRef | None = None
    about: list[PersonRef] | None = None
    topics: list[str] | None = None


class DeleteIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000, description="Ids of the quotes to delete")


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def router(ctx: Context) -> APIRouter:
    api = APIRouter(dependencies=ctx.auth, tags=["quotes"])
    get_db = ctx.get_db

    def person(conn, ref):
        try:
            return db.person_id(conn, ref)
        except KeyError:
            raise HTTPException(422, f"No person with id {ref}")
        except ValueError:
            raise HTTPException(422, "A person's name cannot be empty")

    def refs(items):
        return [r for r in items or [] if not (isinstance(r, str) and not r.strip())]

    def words_by_id(conn, source_id: int | None, ref) -> int | None:
        """A quote within a quote. The source's own author is no exception, so nothing is stored then.
        With no source, the person who said it."""
        if ref is None or (isinstance(ref, str) and not ref.strip()):
            if source_id is None:
                raise HTTPException(422, "Say who said it: a quote with no source needs a person")
            return None
        pid = person(conn, ref)
        if source_id is None:
            return pid
        makers = {r[0] for r in conn.execute("SELECT person_id FROM source_people WHERE source_id = ? AND role IN "
                                             "('author', 'speaker', 'editor')", (source_id,))}
        return None if pid in makers else pid

    @api.post("/api/entries", status_code=201)
    def create_entry(body: EntryIn, conn: sqlite3.Connection = Depends(get_db), lib: Library = Depends(ctx.require_library)):
        if body.source_id is not None:
            load_source(conn, body.source_id)
        elif body.photo_id:
            raise HTTPException(422, "A quote taken from a photo needs its source")
        text = blank_to_none(body.text)
        page = blank_to_none(body.page)
        if body.photo_id:
            photo = load_photo(conn, body.photo_id)
            if photo["status"] != "ready":
                raise HTTPException(409, "This photo is still being read; try again in a few seconds")
            if not text and body.word_start is not None and body.word_end is not None:
                words = ocr.words_from_dicts(db.unpack_words(photo["words"]))
                text = ocr.select_range(words, body.word_start, body.word_end) or None
            if not page:
                page = photo["detected_page"]
        if not text:
            raise HTTPException(422, "Give the text, or a photo_id with word_start and word_end")
        stamp = db.now()
        entry_id = conn.execute(
            "INSERT INTO entries (source_id, text, note, page, page_sort, words_by, photo_id, word_start, word_end, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (body.source_id, text, blank_to_none(body.note), page, db.page_sort_key(page) if body.source_id else None,
             words_by_id(conn, body.source_id, body.words_by), body.photo_id, body.word_start, body.word_end, stamp, stamp),
        ).lastrowid
        if body.about is not None:
            db.set_entry_about(conn, entry_id, [person(conn, r) for r in refs(body.about)])
        if body.topics is not None:
            db.set_entry_topics(conn, entry_id, body.topics)
        db.reindex_entry(conn, entry_id)
        if body.photo_id:
            lib.files.file_photo(conn, body.photo_id, body.source_id, page)
        conn.commit()
        return entry_dict(conn, entry_id)

    @api.get("/api/entries")
    def list_entries(
        source_id: int | None = None,
        topic_id: int | None = None,
        person_id: int | None = Query(None, description="Quotes on this person's page"),
        medium: Medium | None = Query(None, description="Only from books, videos…; 'said': from no source"),
        order: Literal["date", "page"] = "date",
        limit: int = Query(200, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        where, args = ["1"], []
        if source_id is not None:
            where.append("e.source_id = ?")
            args.append(source_id)
        if topic_id is not None:
            where.append("e.id IN (SELECT entry_id FROM entry_topic WHERE topic_id = ?)")
            args.append(topic_id)
        if person_id is not None:
            where.append("(e.words_by = ? OR e.source_id IN (SELECT source_id FROM source_people WHERE person_id = ? "
                         "AND role != 'about') OR e.id IN (SELECT entry_id FROM entry_about WHERE person_id = ?))")
            args += [person_id] * 3
        if medium == "said":
            where.append("e.source_id IS NULL")
        elif medium:
            where.append("s.kind = ?")
            args.append(medium)
        order_sql = "e.page_sort IS NULL, e.page_sort, e.created_at" if order == "page" else "e.created_at DESC, e.id DESC"
        return entries_where(conn, " AND ".join(where), args, order=order_sql, limit=limit, offset=offset)

    @api.get("/api/entries/{entry_id}")
    def get_entry(entry_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """One quote, with the notes of yours that refer to it."""
        notes = conn.execute("SELECT n.id, n.title, n.text FROM notes n JOIN note_entries ne ON ne.note_id = n.id "
                             "WHERE ne.entry_id = ? ORDER BY n.updated_at DESC", (entry_id,)).fetchall()
        return {**entry_dict(conn, entry_id),
                "notes": [{"id": n["id"], "title": n["title"] or n["text"][:60]} for n in notes]}

    @api.patch("/api/entries/{entry_id}")
    def update_entry(entry_id: int, body: EntryPatch, conn: sqlite3.Connection = Depends(get_db),
                     lib: Library = Depends(ctx.require_library)):
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No quote with this id")
        changes = body.model_dump(exclude_unset=True)
        about = changes.pop("about", None)
        topics = changes.pop("topics", None)
        source_id = row["source_id"]
        if "source_id" in changes:
            new_source = changes.pop("source_id")
            if new_source is None and row["source_id"] is not None:
                # from no source any more: it stays the words of whoever they were
                if row["photo_id"]:
                    raise HTTPException(422, "A quote taken from a photo keeps its source")
                if "words_by" not in changes or not changes["words_by"]:
                    by = conn.execute(f"SELECT {db.BY_SQL} FROM entries e WHERE e.id = ?", (entry_id,)).fetchone()[0]
                    if by is None:
                        raise HTTPException(422, "Say who said it: a quote with no source needs a person")
                    changes["words_by"] = by
                conn.execute("UPDATE entries SET words_by = ? WHERE id = ?", (person(conn, changes["words_by"]), entry_id))
                db.keep_entry_links(conn, entry_id, None)
                source_id = None
            elif new_source is not None and new_source != row["source_id"]:
                load_source(conn, new_source)
                db.keep_entry_links(conn, entry_id, new_source)
                if row["photo_id"]:
                    lib.files.move_photo_to_source(conn, row["photo_id"], new_source, changes.get("page", row["page"]))
                source_id = new_source
        range_changed = {"word_start", "word_end"} & changes.keys()
        if range_changed and "text" not in changes and row["photo_id"]:
            start = changes.get("word_start", row["word_start"])
            end = changes.get("word_end", row["word_end"])
            if start is not None and end is not None:
                words = ocr.words_from_dicts(db.unpack_words(load_photo(conn, row["photo_id"])["words"]))
                changes["text"] = ocr.select_range(words, start, end)
        for key in ("text", "note", "page"):
            if key in changes:
                changes[key] = blank_to_none(changes[key])
        if "text" in changes and not changes["text"]:
            raise HTTPException(422, "A quote cannot be empty")
        if "page" in changes:
            changes["page_sort"] = db.page_sort_key(changes["page"]) if source_id else None
        if "words_by" in changes:
            changes["words_by"] = words_by_id(conn, source_id, changes["words_by"])
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE entries SET {sets}, updated_at = ? WHERE id = ?", (*changes.values(), db.now(), entry_id))
        else:
            conn.execute("UPDATE entries SET updated_at = ? WHERE id = ?", (db.now(), entry_id))
        if about is not None:
            db.set_entry_about(conn, entry_id, [person(conn, r) for r in refs(about)])
        if topics is not None:
            db.set_entry_topics(conn, entry_id, topics)
        db.forget_unused_people(conn)
        db.forget_unused_topics(conn)
        db.reindex_entry(conn, entry_id)
        conn.commit()
        return entry_dict(conn, entry_id)

    def delete_ids(conn, ids: list[int]) -> list[int]:
        found = []
        for part in db.chunks(sorted(set(ids))):
            marks = ", ".join("?" * len(part))
            found += [r["id"] for r in conn.execute(f"SELECT id FROM entries WHERE id IN ({marks})", part)]
            conn.execute(f"DELETE FROM entries_fts WHERE rowid IN ({marks})", part)
            conn.execute(f"DELETE FROM entries WHERE id IN ({marks})", part)
        db.forget_unused_people(conn)
        db.forget_unused_topics(conn)
        conn.commit()
        return found

    @api.delete("/api/entries/{entry_id}")
    def delete_entry(entry_id: int, conn: sqlite3.Connection = Depends(get_db)):
        entry_dict(conn, entry_id)
        delete_ids(conn, [entry_id])
        return {"deleted": entry_id}

    @api.post("/api/entries/delete")
    def delete_entries(body: DeleteIn, conn: sqlite3.Connection = Depends(get_db)):
        """Delete several quotes at once (for example all of a source's, keeping the source)."""
        return {"deleted": delete_ids(conn, body.ids)}

    @api.get("/api/search")
    def search(
        q: str = Query(min_length=1, description="Words to find; accents and case are ignored"),
        source_id: int | None = None,
        limit: int = Query(50, ge=1, le=500),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        """Search quotes: their text, your comments on them, their source, people and topics."""
        match = db.fts_query(q)
        if not match:
            return []
        sql = (f"SELECT x.*, snippet(entries_fts, -1, char(2), char(3), '…', 16) AS snippet "
               f"FROM entries_fts JOIN ({ENTRY_SQL}) x ON x.id = entries_fts.rowid WHERE entries_fts MATCH ?")
        args: list = [match]
        if source_id is not None:
            sql += " AND x.source_id = ?"
            args.append(source_id)
        sql += " ORDER BY rank LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        return [{**d, "snippet": r["snippet"]} for d, r in zip(entry_dicts(conn, rows), rows)]

    return api
