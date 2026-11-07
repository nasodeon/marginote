"""Sources (books, articles, videos…), the people linked to them, topics, and your own notes."""

import logging
import re
import sqlite3
import unicodedata
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import db, linkinfo, lookup, names
from .context import Context
from .views import (SOURCE_LIST_SQL, entries_where, load_note, load_person, load_source, load_topic, note_dict,
                    note_dicts, people_by_id, person_brief, source_dict, source_dicts)

log = logging.getLogger("marginote")
MAX_UPLOAD = 30 * 1024 * 1024
Kind = Literal["book", "ebook", "article", "video", "podcast", "class", "talk", "other"]
Role = Literal["author", "translator", "editor", "speaker", "about"]
PersonRef = int | str
COVER_CACHE = {"Cache-Control": "private, max-age=31536000, immutable"}   # its address changes with the source
PAGE_ORDER = "e.page_sort IS NULL, e.page_sort, e.created_at"


class SourceIn(BaseModel):
    kind: Kind = "book"
    title: str = Field(min_length=1)
    subtitle: str | None = None
    publisher: str | None = Field(None, description="Publisher; for a web page the site, for a video the channel")
    edition: str | None = None
    year: int | None = None
    date: str | None = Field(None, description="'2026-10-02', '2026-10' or '2026'")
    isbn: str | None = None
    url: str | None = None
    language: str | None = None
    field: str | None = Field(None, description="What kind of work: 'Philosophie', 'Roman'…")
    people: dict[Role, list[PersonRef]] = Field({}, description="{'author': ['Frédéric Lordon'], 'about': [12]}")
    topics: list[str] = []
    fetch_cover: bool = Field(True, description="Look for a cover online (books), in the background")
    cover_url: str | None = Field(None, description="A picture found with the link (articles, videos)")


class SourcePatch(BaseModel):
    kind: Kind | None = None
    title: str | None = Field(None, min_length=1)
    subtitle: str | None = None
    publisher: str | None = None
    edition: str | None = None
    year: int | None = None
    date: str | None = None
    isbn: str | None = None
    url: str | None = None
    language: str | None = None
    field: str | None = None
    people: dict[Role, list[PersonRef]] | None = Field(None, description="Only the roles given are replaced")
    topics: list[str] | None = None


class PersonPatch(BaseModel):
    name: str | None = Field(None, min_length=1)
    sort_name: str | None = None
    dates: str | None = None
    aliases: list[str] | None = None


class MergeIn(BaseModel):
    into: int = Field(description="The person who stays; this one's links move to them")


class TopicPatch(BaseModel):
    name: str = Field(min_length=1, description="A new name; if another topic has it, the two are merged")


class NoteIn(BaseModel):
    title: str | None = None
    text: str = Field(min_length=1)
    sources: list[int] = Field([], description="The books, videos, classes… it is on")
    place: str | None = Field(None, description="Where in its source: a page, a chapter, a session")
    people: list[PersonRef] = []
    topics: list[str] = []
    entries: list[int] = Field([], description="Quotes the note refers to")


class NotePatch(BaseModel):
    title: str | None = None
    text: str | None = None
    sources: list[int] | None = None
    place: str | None = None
    people: list[PersonRef] | None = None
    topics: list[str] | None = None
    entries: list[int] | None = None


def blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower() or "source"


def check_date(value: str | None) -> str | None:
    value = blank_to_none(value)
    if value and not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", value):
        raise HTTPException(422, "Write the date as 2026-10-02, 2026-10 or 2026")
    return value


def router(ctx: Context) -> APIRouter:
    api = APIRouter(dependencies=ctx.auth)
    get_db = ctx.get_db
    files = ctx.files
    settings = ctx.settings

    def person_or_422(conn, ref):
        try:
            return db.person_id(conn, ref)
        except KeyError:
            raise HTTPException(422, f"No person with id {ref}")
        except ValueError:
            raise HTTPException(422, "A person's name cannot be empty")

    def set_people(conn, source_id: int, roles: dict) -> None:
        clean = {role: [r for r in refs if not (isinstance(r, str) and not r.strip())] for role, refs in roles.items()}
        for refs in clean.values():
            for ref in refs:
                person_or_422(conn, ref)
        db.set_source_people(conn, source_id, clean)

    def fetch_cover_in_background(source_id: int, row: dict, cover_url: str | None) -> None:
        try:
            image = None
            if cover_url:
                image = _download_picture(cover_url)
            elif row["kind"] in ("book", "ebook"):
                image = lookup.find_cover(row.get("isbn"), row["title"], row.get("first_author"))
            if not image:
                return
            conn = ctx.connect()
            try:
                if conn.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone():
                    files.save_cover(conn, source_id, image)
                    conn.commit()
            finally:
                conn.close()
        except Exception:
            log.exception("Cover search failed for source %s", source_id)

    def first_author(conn, source_id: int) -> str | None:
        row = conn.execute("SELECT p.name FROM source_people sp JOIN people p ON p.id = sp.person_id "
                           "WHERE sp.source_id = ? AND sp.role = 'author' ORDER BY sp.position LIMIT 1",
                           (source_id,)).fetchone()
        return row["name"] if row else None

    # ----- sources -----

    @api.get("/api/sources", tags=["sources"])
    def list_sources(kind: Kind | None = None, conn: sqlite3.Connection = Depends(get_db)):
        """Everything in the library, the most recently used first."""
        where, args = ("WHERE s.kind = ?", (kind,)) if kind else ("", ())
        rows = conn.execute(f"{SOURCE_LIST_SQL} {where} ORDER BY COALESCE(last_entry_at, s.created_at) DESC", args).fetchall()
        return source_dicts(conn, rows)

    @api.post("/api/sources", tags=["sources"], status_code=201)
    def create_source(body: SourceIn, background: BackgroundTasks, conn: sqlite3.Connection = Depends(get_db)):
        """Saved at once; a cover is looked for afterwards, so you never wait for it."""
        values = {k: blank_to_none(getattr(body, k)) for k in ("kind", "title", "subtitle", "publisher", "edition",
                                                              "year", "isbn", "url", "language", "field")}
        values["date"] = check_date(body.date)
        if values["isbn"]:
            values["isbn"] = lookup.clean_isbn(values["isbn"])
            if not values["isbn"]:
                raise HTTPException(422, "This ISBN looks wrong: check the digits on the back cover")
        if values["url"]:
            try:
                values["url"] = linkinfo.clean_url(values["url"])
            except linkinfo.LinkError as err:
                raise HTTPException(422, str(err))
            same = conn.execute("SELECT id, title FROM sources WHERE url = ?", (values["url"],)).fetchone()
            if same:
                raise HTTPException(409, f"Already in your library: {same['title']} (source {same['id']})")
        stamp = db.now()
        keys = list(values)
        source_id = conn.execute(
            f"INSERT INTO sources ({', '.join(keys)}, created_at, updated_at) VALUES ({', '.join('?' * len(keys))}, ?, ?)",
            (*values.values(), stamp, stamp),
        ).lastrowid
        set_people(conn, source_id, body.people)
        db.set_source_topics(conn, source_id, body.topics)
        conn.commit()
        cover_pending = settings.lookups_enabled and (
            bool(body.cover_url) or (body.fetch_cover and values["kind"] in ("book", "ebook")))
        if cover_pending:
            background.add_task(fetch_cover_in_background, source_id,
                                {**values, "first_author": first_author(conn, source_id)}, body.cover_url)
        return {**source_dict(conn, source_id), "cover_pending": cover_pending}

    @api.get("/api/sources/{source_id}", tags=["sources"])
    def get_source(source_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return source_dict(conn, source_id)

    @api.patch("/api/sources/{source_id}", tags=["sources"])
    def update_source(source_id: int, body: SourcePatch, conn: sqlite3.Connection = Depends(get_db)):
        old = load_source(conn, source_id)
        changes = body.model_dump(exclude_unset=True)
        people = changes.pop("people", None)
        topics = changes.pop("topics", None)
        changes = {k: blank_to_none(v) for k, v in changes.items()}
        if "kind" in changes and not changes["kind"]:
            del changes["kind"]
        if "title" in changes and not changes["title"]:
            raise HTTPException(422, "A source needs a title")
        if "date" in changes:
            changes["date"] = check_date(changes["date"])
        if changes.get("isbn"):
            changes["isbn"] = lookup.clean_isbn(changes["isbn"])
            if not changes["isbn"]:
                raise HTTPException(422, "This ISBN looks wrong")
        if changes.get("url"):
            try:
                changes["url"] = linkinfo.clean_url(changes["url"])
            except linkinfo.LinkError as err:
                raise HTTPException(422, str(err))
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE sources SET {sets}, updated_at = ? WHERE id = ?", (*changes.values(), db.now(), source_id))
            if "title" in changes:
                files.rename_source_folder(conn, source_id, old["title"], changes["title"])
        if people is not None:
            set_people(conn, source_id, people)
        if topics is not None:
            db.set_source_topics(conn, source_id, topics)
        if people is not None or topics is not None:
            conn.execute("UPDATE sources SET updated_at = ? WHERE id = ?", (db.now(), source_id))
            db.forget_unused_people(conn)
            db.forget_unused_topics(conn)
        db.reindex_source(conn, source_id)
        conn.commit()
        return source_dict(conn, source_id)

    @api.delete("/api/sources/{source_id}", tags=["sources"])
    def delete_source(source_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """Deletes the source with all its quotes (their photos go with the hourly cleanup). Your notes on it
        are kept."""
        row = load_source(conn, source_id)
        conn.execute("DELETE FROM entries_fts WHERE rowid IN (SELECT id FROM entries WHERE source_id = ?)", (source_id,))
        notes = [r[0] for r in conn.execute("SELECT note_id FROM note_sources WHERE source_id = ?", (source_id,))]
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        for note_id in notes:
            db.reindex_note(conn, note_id)
        db.forget_unused_people(conn)
        db.forget_unused_topics(conn)
        conn.commit()
        files.remove_cover(row["cover"])
        return {"deleted": source_id}

    @api.get("/api/sources/{source_id}/entries", tags=["sources"])
    def source_entries(source_id: int, order: Literal["page", "date"] = "page", conn: sqlite3.Connection = Depends(get_db)):
        load_source(conn, source_id)
        return entries_where(conn, "e.source_id = ?", (source_id,),
                             order=PAGE_ORDER if order == "page" else "e.created_at DESC, e.id DESC")

    @api.get("/api/sources/{source_id}/cover", tags=["sources"])
    def get_cover(source_id: int, conn: sqlite3.Connection = Depends(get_db)):
        row = load_source(conn, source_id)
        path = files.covers / row["cover"] if row["cover"] else None
        if not path or not path.is_file():
            raise HTTPException(404, "No cover yet")
        media = "image/webp" if path.suffix == ".webp" else "image/jpeg"
        return FileResponse(path, media_type=media, headers=COVER_CACHE)

    @api.post("/api/sources/{source_id}/cover", tags=["sources"])
    def upload_cover(source_id: int, file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)):
        """Use your own photo of the cover."""
        load_source(conn, source_id)
        data = file.file.read(MAX_UPLOAD + 1)
        try:
            files.save_cover(conn, source_id, data)
        except (OSError, ValueError):
            raise HTTPException(415, "This file is not an image the app can read")
        conn.commit()
        return source_dict(conn, source_id)

    @api.post("/api/sources/{source_id}/cover/fetch", tags=["sources"])
    def fetch_cover(source_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """Look for a cover online again: by ISBN, then by title and author; for a link, its picture."""
        row = load_source(conn, source_id)
        if not settings.lookups_enabled:
            raise HTTPException(409, "Online lookups are turned off (LOOKUPS_ENABLED=false)")
        image = None
        if row["url"] and row["kind"] not in ("book", "ebook"):
            try:
                found = linkinfo.read(row["url"])
                image = _download_picture(found["image_url"]) if found.get("image_url") else None
            except linkinfo.LinkError:
                image = None
        else:
            image = lookup.find_cover(row["isbn"], row["title"], first_author(conn, source_id))
        if not image:
            raise HTTPException(404, "No picture found online; you can use your own photo")
        files.save_cover(conn, source_id, image)
        conn.commit()
        return source_dict(conn, source_id)

    @api.get("/api/sources/{source_id}/export.md", tags=["sources"])
    def export_source(source_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """Every quote of one source, and your notes on it, as a Markdown file."""
        source = source_dict(conn, source_id)
        entries = entries_where(conn, "e.source_id = ?", (source_id,), order=PAGE_ORDER)
        notes = note_dicts(conn, conn.execute(
            "SELECT n.* FROM notes n JOIN note_sources ns ON ns.note_id = n.id WHERE ns.source_id = ? "
            "ORDER BY n.created_at", (source_id,)).fetchall())
        authors = ", ".join(p["name"] for p in source["people"]["author"] + source["people"]["speaker"])
        details = ", ".join(str(v) for v in (source["publisher"], source["year"] or source["date"], source["edition"]) if v)
        lines = [f"# {source['title']}", ""]
        if authors or details:
            lines += [" · ".join(x for x in (f"*{authors}*" if authors else "", details) if x), ""]
        if source["url"]:
            lines += [f"<{source['url']}>", ""]
        for e in entries:
            where = f"p. {e['page']}" if e["page"] and e["page"][0].isdigit() else (e["page"] or "")
            tags = " ".join(f"#{t['name'].replace(' ', '-')}" for t in e["topics"])
            quoted = f"{e['words_by']['name']}, quoted" if e["words_by"] else ""
            lines += [f"> {line}" for line in e["text"].splitlines()]
            meta = " · ".join(x for x in (quoted, where, tags) if x)
            if meta:
                lines += [">", f"> — {meta}"]
            if e["note"]:
                lines += ["", f"Comment: {e['note']}"]
            lines.append("")
        if notes:
            lines += ["## Notes", ""]
            for n in notes:
                head = " · ".join(x for x in (n["title"], n["place"]) if x)
                if head:
                    lines += [f"**{head}**", ""]
                lines += [n["text"], ""]
                tags = " ".join(f"#{t['name'].replace(' ', '-')}" for t in n["topics"])
                if tags:
                    lines += [tags, ""]
        return PlainTextResponse("\n".join(lines), media_type="text/markdown; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{slug(source["title"])}.md"'})

    def _download_picture(url: str) -> bytes | None:
        """A picture given by a page (a video's thumbnail, an article's image), checked like the page itself."""
        import httpx
        try:
            linkinfo.check_public(url)
            with linkinfo._client() as client:
                final, body, ctype = linkinfo._get(client, url, accept="image/*", limit=8 * 1024 * 1024)
            return body if ctype.startswith("image/") and len(body) > 2000 else None
        except (linkinfo.LinkError, httpx.HTTPError):
            return None

    # ----- people -----

    PEOPLE_SQL = """
    SELECT p.*,
      (SELECT COUNT(DISTINCT source_id) FROM source_people WHERE person_id = p.id AND role IN ('author', 'editor', 'speaker')) AS works,
      (SELECT COUNT(DISTINCT source_id) FROM source_people WHERE person_id = p.id AND role = 'translator') AS translated,
      (SELECT COUNT(DISTINCT e.source_id) FROM entries e WHERE e.words_by = p.id AND e.source_id NOT IN
          (SELECT source_id FROM source_people WHERE person_id = p.id AND role != 'about')) AS quoted_in,
      (SELECT COUNT(*) FROM entries e WHERE e.words_by = p.id AND e.source_id IS NULL) AS said,
      (SELECT COUNT(*) FROM (SELECT source_id FROM source_people WHERE person_id = p.id AND role = 'about'
          UNION SELECT e.source_id FROM entry_about ea JOIN entries e ON e.id = ea.entry_id WHERE ea.person_id = p.id
          AND e.source_id IS NOT NULL)) AS about_in,
      (SELECT COUNT(*) FROM (SELECT e.id FROM entries e JOIN source_people sp ON sp.source_id = e.source_id
          AND sp.person_id = p.id AND sp.role != 'about' UNION SELECT id FROM entries WHERE words_by = p.id
          UNION SELECT entry_id FROM entry_about WHERE person_id = p.id)) AS entries,
      (SELECT COUNT(*) FROM note_people WHERE person_id = p.id) AS notes
    FROM people p
    """

    def person_dict(row) -> dict:
        return {**person_brief(row), "dates": row["dates"],
                "aliases": row["aliases"].splitlines() if row["aliases"] else [],
                **{k: row[k] for k in ("works", "translated", "quoted_in", "said", "about_in", "entries", "notes")}}

    @api.get("/api/people", tags=["people"])
    def list_people(conn: sqlite3.Connection = Depends(get_db)):
        """Everyone in the library, as in an index: 'Spinoza, Baruch'."""
        rows = conn.execute(PEOPLE_SQL + " ORDER BY p.sort_name COLLATE NOCASE").fetchall()
        return [person_dict(r) for r in rows]

    @api.get("/api/people/{person_id}", tags=["people"])
    def get_person(person_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """A person's page: your notes on them, their works, what they said (no source), their words quoted
        elsewhere, what is about them. Each section groups by source, with its quotes and your notes on it.
        A quote or a note appears once, in the first place that fits."""
        load_person(conn, person_id)
        person = person_dict(conn.execute(PEOPLE_SQL + " WHERE p.id = ?", (person_id,)).fetchone())
        made = {r[0]: r[1] for r in conn.execute(
            "SELECT source_id, MIN(CASE WHEN role = 'translator' THEN 1 ELSE 0 END) FROM source_people "
            "WHERE person_id = ? AND role != 'about' GROUP BY source_id", (person_id,))}
        works = [s for s, t in made.items() if t == 0]
        translated = [s for s, t in made.items() if t == 1]
        shown: set[int] = set()
        sections = []

        def take(entries: list[dict]) -> list[dict]:
            fresh = [e for e in entries if e["id"] not in shown]
            shown.update(e["id"] for e in fresh)
            return fresh

        def in_list(ids):
            return ",".join(str(int(i)) for i in ids if i is not None) or "-1"   # never an id

        def sid(e):
            return e["source"]["id"] if e["source"] else None

        for key, ids in (("works", works), ("translated", translated)):
            if ids:
                entries = take(entries_where(conn, f"e.source_id IN ({in_list(ids)})", order=PAGE_ORDER))
                sections.append({"key": key, "source_ids": ids, "entries": entries})
        said = take(entries_where(conn, "e.words_by = ? AND e.source_id IS NULL", (person_id,)))
        if said:
            sections.append({"key": "said", "source_ids": [None], "entries": said})
        quoted = take(entries_where(conn, f"e.words_by = ? AND e.source_id NOT IN ({in_list(made)})", (person_id,),
                                    order=PAGE_ORDER))
        if quoted:
            sections.append({"key": "quoted", "source_ids": list(dict.fromkeys(sid(e) for e in quoted)), "entries": quoted})
        about = take(entries_where(conn, "e.id IN (SELECT entry_id FROM entry_about WHERE person_id = ?)",
                                   (person_id,), order=PAGE_ORDER))
        about_sources = list(dict.fromkeys(
            [sid(e) for e in about]
            + [r[0] for r in conn.execute("SELECT source_id FROM source_people WHERE person_id = ? AND role = 'about'",
                                          (person_id,)) if r[0] not in made]))
        if about_sources:
            sections.append({"key": "about", "source_ids": about_sources, "entries": about})
        all_sources = {s for sec in sections for s in sec["source_ids"] if s is not None}
        rows = conn.execute(f"{SOURCE_LIST_SQL} WHERE s.id IN ({in_list(all_sources)})").fetchall()
        sources = {s["id"]: s for s in source_dicts(conn, rows)}
        notes_of: dict[int, list] = {}
        for n in note_dicts(conn, conn.execute(
                f"SELECT DISTINCT n.* FROM notes n JOIN note_sources ns ON ns.note_id = n.id "
                f"WHERE ns.source_id IN ({in_list(all_sources)}) ORDER BY n.created_at").fetchall()):
            for src in n["sources"]:
                notes_of.setdefault(src["id"], []).append(n)
        shown_notes: set[int] = set()
        for sec in sections:
            groups = []
            for source_id in sec.pop("source_ids"):
                if source_id is None:
                    groups.append({"source": None, "entries": [e for e in sec["entries"] if e["source"] is None],
                                   "notes": []})
                elif source_id in sources:
                    notes = [n for n in notes_of.get(source_id, []) if n["id"] not in shown_notes]
                    shown_notes.update(n["id"] for n in notes)
                    groups.append({"source": sources[source_id], "notes": notes,
                                   "entries": [e for e in sec["entries"] if sid(e) == source_id]})
            # works by date of the work, the rest by the most recent quote or note
            if sec["key"] in ("works", "translated"):
                groups.sort(key=lambda g: (g["source"]["year"] or 9999, g["source"]["title"].lower()))
            else:
                groups.sort(key=lambda g: max([e["created_at"] for e in g["entries"]] + [n["created_at"] for n in g["notes"]]
                                              or [g["source"]["created_at"] if g["source"] else ""]), reverse=True)
            sec["groups"] = groups
            del sec["entries"]
        notes = [n for n in note_dicts(conn, conn.execute(
            "SELECT n.* FROM notes n JOIN note_people np ON np.note_id = n.id WHERE np.person_id = ? "
            "ORDER BY n.updated_at DESC", (person_id,)).fetchall()) if n["id"] not in shown_notes]
        return {"person": person, "notes": notes, "sections": sections}

    @api.patch("/api/people/{person_id}", tags=["people"])
    def update_person(person_id: int, body: PersonPatch, conn: sqlite3.Connection = Depends(get_db)):
        row = load_person(conn, person_id)
        changes = body.model_dump(exclude_unset=True)
        sets: dict = {}
        if changes.get("name"):
            bare, dates = names.split_dates(changes["name"])
            display, sort = names.display_and_sort(bare)
            sets.update(name=display, match_key=names.match_key(display))
            if not changes.get("sort_name") and names.match_key(row["sort_name"]) != names.match_key(sort):
                sets["sort_name"] = sort
            if dates and "dates" not in changes:
                sets["dates"] = dates
        if changes.get("sort_name"):
            sets["sort_name"] = names.clean(changes["sort_name"])
        if "dates" in changes:
            sets["dates"] = blank_to_none(changes["dates"])
        if "aliases" in changes:
            aliases = [names.clean(a) for a in changes["aliases"] or [] if names.clean(a)]
            sets["aliases"] = "\n".join(dict.fromkeys(aliases)) or None
        if sets:
            conn.execute(f"UPDATE people SET {', '.join(f'{k} = ?' for k in sets)}, updated_at = ? WHERE id = ?",
                         (*sets.values(), db.now(), person_id))
            db.reindex_person(conn, person_id)
            conn.commit()
        return person_dict(conn.execute(PEOPLE_SQL + " WHERE p.id = ?", (person_id,)).fetchone())

    @api.post("/api/people/{person_id}/merge", tags=["people"])
    def merge_person(person_id: int, body: MergeIn, conn: sqlite3.Connection = Depends(get_db)):
        """The same person entered twice ('Spinoza' and 'Baruch Spinoza'): everything moves to `into`,
        and this one's name is kept as another spelling."""
        gone, stays = load_person(conn, person_id), load_person(conn, body.into)
        if gone["id"] == stays["id"]:
            raise HTTPException(422, "A person cannot be merged with themselves")
        for table in ("source_people", "entry_people", "note_people"):
            conn.execute(f"UPDATE OR IGNORE {table} SET person_id = ? WHERE person_id = ?", (stays["id"], gone["id"]))
            conn.execute(f"DELETE FROM {table} WHERE person_id = ?", (gone["id"],))
        conn.execute("UPDATE entries SET words_by = ? WHERE words_by = ?", (stays["id"], gone["id"]))
        aliases = (stays["aliases"] or "").splitlines() + (gone["aliases"] or "").splitlines()
        if names.match_key(gone["name"]) != names.match_key(stays["name"]):
            aliases.append(gone["name"])
        conn.execute("UPDATE people SET aliases = ?, dates = COALESCE(dates, ?), updated_at = ? WHERE id = ?",
                     ("\n".join(dict.fromkeys(a for a in aliases if a)) or None, gone["dates"], db.now(), stays["id"]))
        conn.execute("DELETE FROM people WHERE id = ?", (gone["id"],))
        db.reindex_person(conn, stays["id"])
        conn.commit()
        return person_dict(conn.execute(PEOPLE_SQL + " WHERE p.id = ?", (stays["id"],)).fetchone())

    @api.delete("/api/people/{person_id}", tags=["people"])
    def delete_person(person_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """Removes the person from every source, quote and note (these are kept). Not possible while quotes
        with no source are theirs: delete those first, or merge the person into another."""
        load_person(conn, person_id)
        said = conn.execute("SELECT COUNT(*) FROM entries WHERE words_by = ? AND source_id IS NULL",
                            (person_id,)).fetchone()[0]
        if said:
            raise HTTPException(409, f"{said} quote{'s' if said > 1 else ''} with no source are theirs: delete "
                                     f"{'them' if said > 1 else 'it'} first, or merge this person into another")
        affected = [r[0] for r in conn.execute(
            "SELECT id FROM entries WHERE words_by = ? OR source_id IN (SELECT source_id FROM source_people WHERE person_id = ?) "
            "UNION SELECT entry_id FROM entry_people WHERE person_id = ?", (person_id,) * 3)]
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
        for entry_id in affected:
            db.reindex_entry(conn, entry_id)
        conn.commit()
        return {"deleted": person_id}

    # ----- topics -----

    TOPICS_SQL = """
    SELECT t.id, t.name,
      (SELECT COUNT(*) FROM entry_topic et WHERE et.topic_id = t.id) AS entries,
      (SELECT COUNT(DISTINCT e.source_id) FROM entry_topic et JOIN entries e ON e.id = et.entry_id
          WHERE et.topic_id = t.id AND e.source_id IS NOT NULL) AS sources,
      (SELECT COUNT(*) FROM note_topics nt WHERE nt.topic_id = t.id) AS notes
    FROM topics t
    """

    @api.get("/api/topics", tags=["topics"])
    def list_topics(conn: sqlite3.Connection = Depends(get_db)):
        rows = conn.execute(TOPICS_SQL + " ORDER BY t.name COLLATE NOCASE").fetchall()
        return [dict(r) for r in rows]

    @api.get("/api/topics/{topic_id}", tags=["topics"])
    def get_topic(topic_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """A topic's page: your notes, the people who appear in it, topics often found with it, its entries."""
        load_topic(conn, topic_id)
        topic = dict(conn.execute(TOPICS_SQL + " WHERE t.id = ?", (topic_id,)).fetchone())
        entries = entries_where(conn, "e.id IN (SELECT entry_id FROM entry_topic WHERE topic_id = ?)", (topic_id,))
        counts: dict[int, int] = {}
        for e in entries:
            involved = {p["id"] for p in e["about"]} | ({e["by"]["id"]} if e["by"] else set())
            for pid in involved:
                counts[pid] = counts.get(pid, 0) + 1
        people = people_by_id(conn, counts)
        related = conn.execute(
            "SELECT t.id, t.name, COUNT(*) AS count FROM entry_topic a JOIN entry_topic b ON b.entry_id = a.entry_id "
            "AND b.topic_id != a.topic_id JOIN topics t ON t.id = b.topic_id WHERE a.topic_id = ? "
            "GROUP BY t.id ORDER BY count DESC, t.name COLLATE NOCASE LIMIT 8", (topic_id,)).fetchall()
        notes = note_dicts(conn, conn.execute(
            "SELECT n.* FROM notes n JOIN note_topics nt ON nt.note_id = n.id WHERE nt.topic_id = ? "
            "ORDER BY n.updated_at DESC", (topic_id,)).fetchall())
        return {
            "topic": topic,
            "notes": notes,
            "people": sorted(({**people[pid], "count": n} for pid, n in counts.items() if pid in people),
                             key=lambda p: (-p["count"], p["sort_name"].lower())),
            "related": [dict(r) for r in related],
            "entries": entries,
        }

    @api.patch("/api/topics/{topic_id}", tags=["topics"])
    def rename_topic(topic_id: int, body: TopicPatch, conn: sqlite3.Connection = Depends(get_db)):
        """Rename a topic. If another topic already has the new name, the two become one."""
        load_topic(conn, topic_id)
        name = db.clean_topic(body.name)
        if not name:
            raise HTTPException(422, "A topic needs a name")
        other = conn.execute("SELECT id FROM topics WHERE name = ? AND id != ?", (name, topic_id)).fetchone()
        if other:
            for table in ("entry_topics", "source_topics", "note_topics"):
                conn.execute(f"UPDATE OR IGNORE {table} SET topic_id = ? WHERE topic_id = ?", (other["id"], topic_id))
                conn.execute(f"DELETE FROM {table} WHERE topic_id = ?", (topic_id,))
            conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
            topic_id = other["id"]
        else:
            conn.execute("UPDATE topics SET name = ? WHERE id = ?", (name, topic_id))
        for (entry_id,) in conn.execute("SELECT entry_id FROM entry_topic WHERE topic_id = ?", (topic_id,)).fetchall():
            db.reindex_entry(conn, entry_id)
        for (note_id,) in conn.execute("SELECT note_id FROM note_topics WHERE topic_id = ?", (topic_id,)).fetchall():
            db.reindex_note(conn, note_id)
        conn.commit()
        return dict(conn.execute(TOPICS_SQL + " WHERE t.id = ?", (topic_id,)).fetchone())

    @api.delete("/api/topics/{topic_id}", tags=["topics"])
    def delete_topic(topic_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """Removes the topic from every entry, source and note (these are kept)."""
        load_topic(conn, topic_id)
        affected = [r[0] for r in conn.execute("SELECT entry_id FROM entry_topic WHERE topic_id = ?", (topic_id,))]
        notes = [r[0] for r in conn.execute("SELECT note_id FROM note_topics WHERE topic_id = ?", (topic_id,))]
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        for entry_id in affected:
            db.reindex_entry(conn, entry_id)
        for note_id in notes:
            db.reindex_note(conn, note_id)
        conn.commit()
        return {"deleted": topic_id}

    # ----- notes -----

    def set_note_links(conn, note_id: int, people, topics, entries, sources=None) -> None:
        if sources is not None:
            conn.execute("DELETE FROM note_sources WHERE note_id = ?", (note_id,))
            for position, source_id in enumerate(dict.fromkeys(sources)):
                load_source(conn, source_id)
                conn.execute("INSERT INTO note_sources (note_id, source_id, position) VALUES (?, ?, ?)",
                             (note_id, source_id, position))
        if people is not None:
            conn.execute("DELETE FROM note_people WHERE note_id = ?", (note_id,))
            for pid in dict.fromkeys(person_or_422(conn, r) for r in people if not (isinstance(r, str) and not r.strip())):
                conn.execute("INSERT INTO note_people (note_id, person_id) VALUES (?, ?)", (note_id, pid))
        if topics is not None:
            conn.execute("DELETE FROM note_topics WHERE note_id = ?", (note_id,))
            for tid in db.topic_ids(conn, topics):
                conn.execute("INSERT INTO note_topics (note_id, topic_id) VALUES (?, ?)", (note_id, tid))
        if entries is not None:
            conn.execute("DELETE FROM note_entries WHERE note_id = ?", (note_id,))
            for position, entry_id in enumerate(dict.fromkeys(entries)):
                if not conn.execute("SELECT 1 FROM entries WHERE id = ?", (entry_id,)).fetchone():
                    raise HTTPException(422, f"No quote with id {entry_id}")
                conn.execute("INSERT INTO note_entries (note_id, entry_id, position) VALUES (?, ?, ?)",
                             (note_id, entry_id, position))

    @api.get("/api/notes", tags=["notes"])
    def list_notes(person_id: int | None = None, topic_id: int | None = None, source_id: int | None = None,
                   q: str | None = None, order: Literal["changed", "created", "place"] = "changed",
                   conn: sqlite3.Connection = Depends(get_db)):
        """Your notes, the most recently changed first; filtered by person, topic, source, or words.
        order=place: in the order of their place in the source (pages, sessions), then oldest first."""
        where, args = [], []
        if source_id is not None:
            where.append("n.id IN (SELECT note_id FROM note_sources WHERE source_id = ?)")
            args.append(source_id)
        if person_id is not None:
            where.append("n.id IN (SELECT note_id FROM note_people WHERE person_id = ?)")
            args.append(person_id)
        if topic_id is not None:
            where.append("n.id IN (SELECT note_id FROM note_topics WHERE topic_id = ?)")
            args.append(topic_id)
        if q and db.fts_query(q):
            where.append("n.id IN (SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?)")
            args.append(db.fts_query(q))
        order_sql = {"changed": "n.updated_at DESC", "created": "n.created_at DESC",
                     "place": "n.place IS NULL, n.place, n.created_at"}[order]
        sql = "SELECT n.* FROM notes n" + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {order_sql}"
        rows = conn.execute(sql, args).fetchall()
        if order == "place":
            rows = sorted(rows, key=lambda r: (r["place"] is None, db.page_sort_key(r["place"]) or 0, r["created_at"]))
        return note_dicts(conn, rows)

    @api.post("/api/notes", tags=["notes"], status_code=201)
    def create_note(body: NoteIn, conn: sqlite3.Connection = Depends(get_db)):
        stamp = db.now()
        note_id = conn.execute("INSERT INTO notes (title, text, place, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                               (blank_to_none(body.title), body.text.strip(), blank_to_none(body.place), stamp, stamp)).lastrowid
        set_note_links(conn, note_id, body.people, body.topics, body.entries, body.sources)
        db.reindex_note(conn, note_id)
        conn.commit()
        return note_dict(conn, note_id)

    @api.get("/api/notes/{note_id}", tags=["notes"])
    def get_note(note_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return note_dict(conn, note_id)

    @api.patch("/api/notes/{note_id}", tags=["notes"])
    def update_note(note_id: int, body: NotePatch, conn: sqlite3.Connection = Depends(get_db)):
        load_note(conn, note_id)
        changes = body.model_dump(exclude_unset=True)
        if "text" in changes and not blank_to_none(changes["text"]):
            raise HTTPException(422, "A note cannot be empty")
        sets = {k: blank_to_none(changes[k]) for k in ("title", "text", "place") if k in changes}
        conn.execute(f"UPDATE notes SET {''.join(f'{k} = ?, ' for k in sets)}updated_at = ? WHERE id = ?",
                     (*sets.values(), db.now(), note_id))
        set_note_links(conn, note_id, changes.get("people"), changes.get("topics"), changes.get("entries"),
                       changes.get("sources"))
        db.forget_unused_people(conn)
        db.forget_unused_topics(conn)
        db.reindex_note(conn, note_id)
        conn.commit()
        return note_dict(conn, note_id)

    @api.delete("/api/notes/{note_id}", tags=["notes"])
    def delete_note(note_id: int, conn: sqlite3.Connection = Depends(get_db)):
        load_note(conn, note_id)
        conn.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        db.forget_unused_people(conn)
        db.forget_unused_topics(conn)
        conn.commit()
        return {"deleted": note_id}

    return api
