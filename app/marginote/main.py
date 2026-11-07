"""Marginote: a small self-hosted app for book quotes and reading notes.

Start it with:  uvicorn --factory marginote.main:create_app
Interactive API documentation is served at /docs.
"""

import hashlib
import hmac
import json
import logging
import mimetypes
import re
import sqlite3
import threading
import time
import unicodedata
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pytesseract
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import backup, db, dewarp, lookup, ocr
from .config import Settings, load_settings

VERSION = "0.2.0"
MAX_UPLOAD = 30 * 1024 * 1024
BAD_IMAGE = (UnidentifiedImageError, OSError, Image.DecompressionBombError)
# One page at a time: keeps memory predictable (about 270 MB at most) even if several photos arrive at once.
OCR_SLOT = threading.Semaphore(1)
PHOTO_CACHE = {"Cache-Control": "private, max-age=31536000, immutable"}  # a photo never changes
COVER_CACHE = {"Cache-Control": "private, no-cache"}  # a cover can be replaced: revalidate
STATIC = Path(__file__).parent / "static"
log = logging.getLogger("marginote")
mimetypes.add_type("application/manifest+json", ".webmanifest")

# The page may load only its own files and talk only to this server: no outside scripts, fonts or trackers.
PAGE_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; "
        "font-src 'self'; connect-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class StaticAssets(StaticFiles):
    """The app's own files (script, styles, fonts, icons). Cached a day; a new version gets a new address."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=86400"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def page_html() -> str:
    """The app page, with its script and styles addressed by a fingerprint of their content."""
    digest = hashlib.sha256()
    for name in ("app.js", "app.css"):
        digest.update((STATIC / name).read_bytes())
    return (STATIC / "index.html").read_text(encoding="utf-8").replace("{{version}}", digest.hexdigest()[:12])


# ---------- request bodies ----------

class LoginIn(BaseModel):
    password: str


class BookIn(BaseModel):
    title: str = Field(min_length=1)
    subtitle: str | None = None
    authors: str | None = Field(None, description="Comma-separated, e.g. 'Henri Poincaré'")
    translator: str | None = None
    publisher: str | None = None
    edition: str | None = None
    year: int | None = None
    isbn: str | None = None
    language: str | None = Field(None, description="e.g. 'fr' or 'en'")
    status: Literal["reading", "paused", "finished"] = "reading"
    fetch_cover: bool = Field(True, description="Look for a cover online, in the background")


class BookPatch(BaseModel):
    title: str | None = Field(None, min_length=1)
    subtitle: str | None = None
    authors: str | None = None
    translator: str | None = None
    publisher: str | None = None
    edition: str | None = None
    year: int | None = None
    isbn: str | None = None
    language: str | None = None
    status: Literal["reading", "paused", "finished"] | None = None


class EntryIn(BaseModel):
    book_id: int
    kind: Literal["quote", "thought"] = "quote"
    text: str | None = Field(None, description="Leave empty to take the words selected on the photo")
    note: str | None = None
    page: str | None = Field(None, description="Leave empty to use the page number found on the photo")
    photo_id: str | None = None
    word_start: int | None = None
    word_end: int | None = None
    tags: list[str] = []


class EntryPatch(BaseModel):
    book_id: int | None = None
    kind: Literal["quote", "thought"] | None = None
    text: str | None = None
    note: str | None = None
    page: str | None = None
    word_start: int | None = None
    word_end: int | None = None
    tags: list[str] | None = None


class SelectIn(BaseModel):
    start: int = Field(description="Index of the first word")
    end: int = Field(description="Index of the last word")


class BoxIn(BaseModel):
    x: int
    y: int
    w: int
    h: int


# ---------- helpers ----------

BOOK_SELECT = """
SELECT b.*,
       COUNT(e.id)                          AS entry_count,
       COALESCE(SUM(e.kind = 'quote'), 0)   AS quote_count,
       COALESCE(SUM(e.kind = 'thought'), 0) AS thought_count,
       MAX(e.created_at)                    AS last_entry_at
FROM books b LEFT JOIN entries e ON e.book_id = b.id
"""

BOOK_FIELDS = ("title", "subtitle", "authors", "translator", "publisher", "edition",
               "year", "isbn", "language", "status")


def book_dict(row: sqlite3.Row) -> dict:
    data = {k: row[k] for k in ("id", *BOOK_FIELDS, "created_at", "updated_at")}
    data.update(
        has_cover=bool(row["cover_path"]),
        cover_url=f"/api/books/{row['id']}/cover" if row["cover_path"] else None,
        entry_count=row["entry_count"],
        quote_count=row["quote_count"],
        thought_count=row["thought_count"],
        last_entry_at=row["last_entry_at"],
    )
    return data


def entry_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "book_id": row["book_id"],
        "book_title": row["book_title"],
        "kind": row["kind"],
        "text": row["text"],
        "note": row["note"],
        "page": row["page"],
        "tags": db.split_tag_list(row["tag_list"]),
        "photo_id": row["photo_id"],
        "photo_url": f"/api/photos/{row['photo_id']}/image" if row["photo_id"] else None,
        "word_start": row["word_start"],
        "word_end": row["word_end"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


ENTRY_SELECT = f"SELECT e.*, b.title AS book_title, {db.TAG_LIST_SQL} FROM entries e JOIN books b ON b.id = e.book_id"


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


INBOX = "inbox"
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def book_folder(book_id: int, title: str) -> str:
    """Readable, Windows-safe folder name for a book's photos: 'La Science et l'hypothèse (12)'."""
    name = unicodedata.normalize("NFC", _UNSAFE.sub(" ", title))
    name = re.sub(r"\s+", " ", name).strip(" .")[:60].strip(" .") or "Book"
    return f"{name} ({book_id})"


def photo_file_name(photo_id: str, page: str | None, suffix: str = ".jpg") -> str:
    page_part = re.sub(r"[^0-9A-Za-z]", "", page or "")[:10]
    return f"p{page_part} - {photo_id[:8]}{suffix}" if page_part else f"{photo_id[:8]}{suffix}"


PHOTO_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg"}


def is_unfiled(path: str) -> bool:
    """Still in the inbox (or stored by the first version, by year and month)."""
    return path.startswith(INBOX + "/") or re.match(r"^\d{4}/\d{2}/", path) is not None


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower() or "book"


# ---------- the app ----------

def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    for folder in (settings.data_dir, settings.photos_dir, settings.covers_dir, settings.backups_dir):
        folder.mkdir(parents=True, exist_ok=True)
    db.migrate(settings.db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logging.basicConfig(level=logging.INFO)
        if not settings.password:
            log.warning("MARGINOTE_PASSWORD is empty: nobody can log in until you set it in the compose file")
        backup.start_maintenance(settings.db_path, settings.backups_dir, settings.backup_hour, settings.backups_kept,
                                 hourly=clean_unused_photos)
        yield

    # The session cookie holds this tag, derived from the password: changing the password logs every device out.
    login_tag = (
        hmac.new(settings.secret_key().encode(), settings.password.encode(), hashlib.sha256).hexdigest()[:32]
        if settings.password else ""
    )

    def logged_in(request: Request) -> bool:
        return bool(login_tag) and hmac.compare_digest(str(request.session.get("ok", "")), login_tag)

    app = FastAPI(
        title="Marginote",
        version=VERSION,
        description=(
            "Book quotes and reading notes, self-hosted.\n\n"
            "**To test here:** open `POST /api/login`, click *Try it out*, type your password, "
            "then *Execute*. Every other call works after that."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key(),
        session_cookie="marginote_session",
        max_age=180 * 24 * 3600,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    def get_db():
        conn = db.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def require_login(request: Request) -> None:
        if not logged_in(request):
            raise HTTPException(401, "Log in first with POST /api/login")

    auth = [Depends(require_login)]

    def load_book(conn: sqlite3.Connection, book_id: int) -> sqlite3.Row:
        row = conn.execute(BOOK_SELECT + " WHERE b.id = ? GROUP BY b.id", (book_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No book with this id")
        return row

    def load_entry(conn: sqlite3.Connection, entry_id: int) -> sqlite3.Row:
        row = conn.execute(ENTRY_SELECT + " WHERE e.id = ?", (entry_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No quote or thought with this id")
        return row

    def load_photo(conn: sqlite3.Connection, photo_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No photo with this id")
        return row

    def photo_words(row: sqlite3.Row) -> list[ocr.Word]:
        return ocr.words_from_dicts(json.loads(row["ocr_json"]))

    def photo_dict(row: sqlite3.Row) -> dict:
        words = photo_words(row)
        return {
            "id": row["id"],
            "width": row["width"],
            "height": row["height"],
            "image_url": f"/api/photos/{row['id']}/image",
            "detected_page": row["detected_page"],
            "text": ocr.full_text(words),
            "words": ocr.words_to_dicts(words),
            "created_at": row["created_at"],
        }

    def save_cover(conn: sqlite3.Connection, book_id: int, image: bytes) -> None:
        path = settings.covers_dir / f"{book_id}.jpg"
        path.write_bytes(ocr.normalize_cover(image))
        conn.execute("UPDATE books SET cover_path = ?, updated_at = ? WHERE id = ?",
                     (path.name, db.now(), book_id))

    def file_photo(conn: sqlite3.Connection, photo_id: str, book_id: int, page: str | None) -> None:
        """Move a photo out of the inbox into its book's folder, named after the page."""
        row = conn.execute("SELECT path FROM photos WHERE id = ?", (photo_id,)).fetchone()
        if not row or not is_unfiled(row["path"]):
            return
        title = conn.execute("SELECT title FROM books WHERE id = ?", (book_id,)).fetchone()["title"]
        new_rel = f"{book_folder(book_id, title)}/{photo_file_name(photo_id, page, Path(row['path']).suffix)}"
        src, dst = settings.photos_dir / row["path"], settings.photos_dir / new_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            src.replace(dst)
        conn.execute("UPDATE photos SET path = ? WHERE id = ?", (new_rel, photo_id))

    def rename_book_folder(conn: sqlite3.Connection, book_id: int, old_title: str, new_title: str) -> None:
        old, new = book_folder(book_id, old_title), book_folder(book_id, new_title)
        if old == new:
            return
        old_dir, new_dir = settings.photos_dir / old, settings.photos_dir / new
        if old_dir.is_dir() and not new_dir.exists():
            old_dir.rename(new_dir)
        prefix = old + "/"
        for row in conn.execute("SELECT id, path FROM photos WHERE substr(path, 1, ?) = ?",
                                (len(prefix), prefix)).fetchall():
            conn.execute("UPDATE photos SET path = ? WHERE id = ?", (new + "/" + row["path"][len(prefix):], row["id"]))

    def refile_photos() -> None:
        """Photos already used by a quote but still unfiled (from older versions): move them now."""
        conn = db.connect(settings.db_path)
        try:
            rows = conn.execute(
                "SELECT p.id, p.path, e.book_id, e.page FROM photos p JOIN entries e ON e.photo_id = p.id GROUP BY p.id"
            ).fetchall()
            for row in rows:
                if is_unfiled(row["path"]):
                    file_photo(conn, row["id"], row["book_id"], row["page"])
            conn.commit()
        finally:
            conn.close()

    def clean_unused_photos() -> int:
        """Delete photos that no quote uses, once they are older than UNUSED_PHOTO_HOURS (24 h by default)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=settings.unused_photo_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = db.connect(settings.db_path)
        try:
            rows = conn.execute(
                "SELECT id, path FROM photos p WHERE created_at < ? "
                "AND NOT EXISTS (SELECT 1 FROM entries e WHERE e.photo_id = p.id)",
                (cutoff,),
            ).fetchall()
            for row in rows:
                (settings.photos_dir / row["path"]).unlink(missing_ok=True)
                conn.execute("DELETE FROM photos WHERE id = ?", (row["id"],))
            conn.commit()
        finally:
            conn.close()
        folders = sorted((d for d in settings.photos_dir.rglob("*") if d.is_dir()), key=lambda d: len(d.parts), reverse=True)
        for folder in folders:
            if folder.name != INBOX and not any(folder.iterdir()):
                folder.rmdir()
        if rows:
            log.info("Removed %d unused photos", len(rows))
        return len(rows)

    refile_photos()
    clean_unused_photos()

    def fetch_cover_in_background(book_id: int, isbn: str | None, title: str, authors: str | None) -> None:
        try:
            image = lookup.find_cover(isbn, title, authors)
            if not image:
                return
            conn = db.connect(settings.db_path)
            try:
                if conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone():
                    save_cover(conn, book_id, image)
                    conn.commit()
            finally:
                conn.close()
        except Exception:
            log.exception("Cover search failed for book %s", book_id)

    # ----- status and login -----

    @lru_cache(maxsize=1)
    def tesseract_info() -> tuple[str | None, frozenset]:
        try:
            return str(pytesseract.get_tesseract_version()), frozenset(pytesseract.get_languages(config=""))
        except Exception:  # Tesseract missing
            return None, frozenset()

    @app.get("/api/health", tags=["status"])
    def health():
        """Is the app running? No login needed."""
        tesseract, installed = tesseract_info()
        wanted = settings.ocr_langs.split("+")
        return {
            "status": "ok",
            "version": VERSION,
            "tesseract": tesseract,
            "ocr_languages": [lang for lang in wanted if lang in installed],
            "missing_ocr_languages": [lang for lang in wanted if lang not in installed],
            "straighten_pages": settings.straighten_pages and dewarp.available(),
            "lookups_enabled": settings.lookups_enabled,
            "password_set": bool(settings.password),
        }

    @app.post("/api/login", tags=["status"])
    def login(body: LoginIn, request: Request):
        if not settings.password:
            raise HTTPException(503, "Set MARGINOTE_PASSWORD in the compose file, then redeploy the app")
        if not hmac.compare_digest(body.password.encode(), settings.password.encode()):
            time.sleep(1)
            raise HTTPException(401, "Wrong password")
        request.session["ok"] = login_tag
        return {"logged_in": True}

    @app.post("/api/logout", tags=["status"])
    def logout(request: Request):
        request.session.clear()
        return {"logged_in": False}

    @app.get("/api/me", tags=["status"])
    def me(request: Request):
        return {"logged_in": logged_in(request)}

    # ----- books -----

    @app.get("/api/books", tags=["books"], dependencies=auth)
    def list_books(
        status: Literal["reading", "paused", "finished"] | None = None,
        sort: Literal["last_entry", "title", "added"] = "last_entry",
        conn: sqlite3.Connection = Depends(get_db),
    ):
        order = {
            "last_entry": "COALESCE(MAX(e.created_at), b.created_at) DESC",
            "title": "b.title COLLATE NOCASE",
            "added": "b.created_at DESC",
        }[sort]
        where, args = ("WHERE b.status = ?", (status,)) if status else ("", ())
        rows = conn.execute(f"{BOOK_SELECT} {where} GROUP BY b.id ORDER BY {order}", args).fetchall()
        return [book_dict(r) for r in rows]

    @app.post("/api/books", tags=["books"], dependencies=auth, status_code=201)
    def create_book(body: BookIn, background: BackgroundTasks, conn: sqlite3.Connection = Depends(get_db)):
        """Saves the book at once; the cover is searched afterwards, so you never wait for it."""
        isbn = None
        if blank_to_none(body.isbn):
            isbn = lookup.clean_isbn(body.isbn)
            if not isbn:
                raise HTTPException(422, "This ISBN looks wrong: check the digits on the back cover")
        stamp = db.now()
        values = body.model_dump(exclude={"fetch_cover"})
        values = {k: blank_to_none(v) if isinstance(v, str) else v for k, v in values.items()}
        values["isbn"] = isbn
        values["title"] = body.title.strip()
        cur = conn.execute(
            f"INSERT INTO books ({', '.join(BOOK_FIELDS)}, created_at, updated_at) "
            f"VALUES ({', '.join('?' * len(BOOK_FIELDS))}, ?, ?)",
            (*[values[k] for k in BOOK_FIELDS], stamp, stamp),
        )
        book_id = cur.lastrowid
        conn.commit()
        cover_pending = body.fetch_cover and settings.lookups_enabled
        if cover_pending:
            background.add_task(fetch_cover_in_background, book_id, isbn, values["title"], values["authors"])
        return {**book_dict(load_book(conn, book_id)), "cover_pending": cover_pending}

    @app.get("/api/books/{book_id}", tags=["books"], dependencies=auth)
    def get_book(book_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return book_dict(load_book(conn, book_id))

    @app.patch("/api/books/{book_id}", tags=["books"], dependencies=auth)
    def update_book(book_id: int, body: BookPatch, conn: sqlite3.Connection = Depends(get_db)):
        old_title = load_book(conn, book_id)["title"]
        changes = body.model_dump(exclude_unset=True)
        if "isbn" in changes and blank_to_none(changes["isbn"]):
            changes["isbn"] = lookup.clean_isbn(changes["isbn"])
            if not changes["isbn"]:
                raise HTTPException(422, "This ISBN looks wrong")
        changes = {k: blank_to_none(v) if isinstance(v, str) else v for k, v in changes.items()}
        if "title" in changes and not changes["title"]:
            raise HTTPException(422, "A book needs a title")
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE books SET {sets}, updated_at = ? WHERE id = ?",
                         (*changes.values(), db.now(), book_id))
            if {"title", "authors"} & changes.keys():
                db.reindex_book(conn, book_id)
            if "title" in changes:
                rename_book_folder(conn, book_id, old_title, changes["title"])
            conn.commit()
        return book_dict(load_book(conn, book_id))

    @app.delete("/api/books/{book_id}", tags=["books"], dependencies=auth)
    def delete_book(book_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """Deletes the book and all its quotes and thoughts. Their photos are removed by the hourly cleanup."""
        row = load_book(conn, book_id)
        conn.execute("DELETE FROM entries_fts WHERE rowid IN (SELECT id FROM entries WHERE book_id = ?)", (book_id,))
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM entry_tags)")
        conn.commit()
        if row["cover_path"]:
            (settings.covers_dir / row["cover_path"]).unlink(missing_ok=True)
        return {"deleted": book_id}

    @app.get("/api/books/{book_id}/cover", tags=["books"], dependencies=auth)
    def get_cover(book_id: int, conn: sqlite3.Connection = Depends(get_db)):
        row = load_book(conn, book_id)
        path = settings.covers_dir / row["cover_path"] if row["cover_path"] else None
        if not path or not path.is_file():
            raise HTTPException(404, "This book has no cover yet")
        return FileResponse(path, media_type="image/jpeg", headers=COVER_CACHE)

    @app.post("/api/books/{book_id}/cover", tags=["books"], dependencies=auth)
    def upload_cover(book_id: int, file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)):
        """Use your own photo of the cover."""
        load_book(conn, book_id)
        data = file.file.read(MAX_UPLOAD + 1)
        try:
            save_cover(conn, book_id, data)
        except BAD_IMAGE:
            raise HTTPException(415, "This file is not an image the app can read")
        conn.commit()
        return book_dict(load_book(conn, book_id))

    @app.post("/api/books/{book_id}/cover/fetch", tags=["books"], dependencies=auth)
    def fetch_cover(book_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """Look for a cover online again (by ISBN, then by title and author)."""
        row = load_book(conn, book_id)
        if not settings.lookups_enabled:
            raise HTTPException(409, "Online lookups are turned off (LOOKUPS_ENABLED=false)")
        image = lookup.find_cover(row["isbn"], row["title"], row["authors"])
        if not image:
            raise HTTPException(404, "No cover found online; you can upload your own photo")
        save_cover(conn, book_id, image)
        conn.commit()
        return book_dict(load_book(conn, book_id))

    @app.get("/api/lookup/isbn/{isbn}", tags=["books"], dependencies=auth)
    def lookup_isbn(isbn: str):
        """Find title, author, publisher and year from an ISBN. Nothing is saved: send the result to POST /api/books."""
        clean = lookup.clean_isbn(isbn)
        if not clean:
            raise HTTPException(422, "This ISBN looks wrong: check the digits on the back cover")
        if not settings.lookups_enabled:
            raise HTTPException(409, "Online lookups are turned off (LOOKUPS_ENABLED=false)")
        found = lookup.lookup_isbn(clean)
        if not found:
            raise HTTPException(404, "No book found for this ISBN; type the details in instead")
        return found

    @app.get("/api/books/{book_id}/export.md", tags=["books"], dependencies=auth)
    def export_book(book_id: int, conn: sqlite3.Connection = Depends(get_db)):
        """Every quote and thought of one book, as a Markdown file."""
        book = load_book(conn, book_id)
        rows = conn.execute(
            ENTRY_SELECT + " WHERE e.book_id = ? ORDER BY e.page_sort IS NULL, e.page_sort, e.created_at",
            (book_id,),
        ).fetchall()
        details = ", ".join(str(v) for v in (book["publisher"], book["year"], book["edition"]) if v)
        lines = [f"# {book['title']}", ""]
        if book["authors"]:
            lines.append(f"*{book['authors']}*" + (f" · {details}" if details else ""))
            lines.append("")
        for row in rows:
            entry = entry_dict(conn, row)
            where = f"p. {entry['page']}" if entry["page"] else ""
            tags = " ".join(f"#{t.replace(' ', '-')}" for t in entry["tags"])
            if entry["kind"] == "quote":
                lines += [f"> {line}" for line in entry["text"].splitlines()]
                meta = " · ".join(x for x in (where, tags) if x)
                if meta:
                    lines += [">", f"> — {meta}"]
            else:
                lines.append(f"**Thought{' (' + where + ')' if where else ''}:** {entry['text']}")
                if tags:
                    lines.append(tags)
            if entry["note"]:
                lines += ["", f"Note: {entry['note']}"]
            lines.append("")
        return PlainTextResponse(
            "\n".join(lines),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{slug(book["title"])}.md"'},
        )

    # ----- photos -----

    @app.post("/api/photos", tags=["photos"], dependencies=auth)
    def upload_photo(file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)):
        """Send a photo of a page. Returns every recognized word (with its position) and the page number if found.

        The photo waits in photos/inbox. Saving a quote from it files it under the book's folder;
        a photo no quote uses is deleted after UNUSED_PHOTO_HOURS (24 h by default).
        """
        data = file.file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Photo larger than 30 MB")
        sha = hashlib.sha256(data).hexdigest()
        existing = conn.execute("SELECT * FROM photos WHERE sha256 = ?", (sha,)).fetchone()
        if existing:
            return photo_dict(existing)
        with OCR_SLOT:
            try:
                img = ocr.normalize_photo(data)
            except BAD_IMAGE:
                raise HTTPException(415, "This file is not an image the app can read")
            try:
                reading = ocr.read_page(img, settings.ocr_langs, straighten=settings.straighten_pages)
            except pytesseract.TesseractError:
                log.exception("Tesseract failed")
                raise HTTPException(500, "Text recognition failed on this photo; try taking it again")
            # keep the straightened photo when there is one: word positions refer to it
            stored = ocr.to_stored(reading.photo)
            words, page = reading.words, reading.page
            width, height = img.width, img.height
            del img, reading
        photo_id = uuid.uuid4().hex
        rel = Path(INBOX) / f"{photo_id}{ocr.PHOTO_SUFFIX}"
        target = settings.photos_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(stored)
        conn.execute(
            "INSERT INTO photos (id, path, width, height, sha256, ocr_json, detected_page, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (photo_id, str(rel), width, height, sha,
             json.dumps(ocr.words_to_dicts(words), ensure_ascii=False), page, db.now()),
        )
        conn.commit()
        return photo_dict(load_photo(conn, photo_id))

    @app.get("/api/photos/{photo_id}", tags=["photos"], dependencies=auth)
    def get_photo(photo_id: str, conn: sqlite3.Connection = Depends(get_db)):
        return photo_dict(load_photo(conn, photo_id))

    @app.get("/api/photos/{photo_id}/image", tags=["photos"], dependencies=auth)
    def photo_image(photo_id: str, conn: sqlite3.Connection = Depends(get_db)):
        path = settings.photos_dir / load_photo(conn, photo_id)["path"]
        if not path.is_file():
            raise HTTPException(404, "The photo file is missing from the photos folder")
        return FileResponse(path, media_type=PHOTO_TYPES.get(path.suffix, "image/jpeg"), headers=PHOTO_CACHE)

    @app.post("/api/photos/{photo_id}/select", tags=["photos"], dependencies=auth)
    def select_words(photo_id: str, body: SelectIn, conn: sqlite3.Connection = Depends(get_db)):
        """Preview the passage between two words (the first and last word you tapped)."""
        words = photo_words(load_photo(conn, photo_id))
        start, end = sorted((body.start, body.end))
        return {"text": ocr.select_range(words, start, end), "word_start": start, "word_end": end}

    @app.post("/api/photos/{photo_id}/select-box", tags=["photos"], dependencies=auth)
    def select_box(photo_id: str, body: BoxIn, conn: sqlite3.Connection = Depends(get_db)):
        """Fallback: preview the passage inside a rectangle drawn on the photo (in photo pixels)."""
        words = photo_words(load_photo(conn, photo_id))
        text, start, end = ocr.select_box(words, body.x, body.y, body.w, body.h)
        return {"text": text, "word_start": start, "word_end": end}

    # ----- quotes and thoughts -----

    @app.post("/api/entries", tags=["quotes and thoughts"], dependencies=auth, status_code=201)
    def create_entry(body: EntryIn, conn: sqlite3.Connection = Depends(get_db)):
        load_book(conn, body.book_id)
        text = blank_to_none(body.text)
        page = blank_to_none(body.page)
        if body.photo_id:
            photo = load_photo(conn, body.photo_id)
            if not text and body.word_start is not None and body.word_end is not None:
                text = ocr.select_range(photo_words(photo), body.word_start, body.word_end) or None
            if not page:
                page = photo["detected_page"]
        if not text:
            raise HTTPException(422, "Give the text, or a photo_id with word_start and word_end")
        stamp = db.now()
        cur = conn.execute(
            "INSERT INTO entries (book_id, kind, text, note, page, page_sort, photo_id, word_start, word_end, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (body.book_id, body.kind, text, blank_to_none(body.note), page, db.page_sort_key(page),
             body.photo_id, body.word_start, body.word_end, stamp, stamp),
        )
        entry_id = cur.lastrowid
        db.set_entry_tags(conn, entry_id, body.tags)
        db.reindex_entry(conn, entry_id)
        if body.photo_id:
            file_photo(conn, body.photo_id, body.book_id, page)
        conn.commit()
        return entry_dict(conn, load_entry(conn, entry_id))

    def list_entry_rows(conn, book_id, tag, kind, order, limit, offset):
        where, args = [], []
        if book_id is not None:
            where.append("e.book_id = ?")
            args.append(book_id)
        if kind:
            where.append("e.kind = ?")
            args.append(kind)
        if tag:
            where.append("e.id IN (SELECT et.entry_id FROM entry_tags et JOIN tags t ON t.id = et.tag_id "
                         "WHERE t.name = ?)")
            args.append(db.clean_tag(tag))
        sql = ENTRY_SELECT + (" WHERE " + " AND ".join(where) if where else "")
        sql += {
            "page": " ORDER BY e.page_sort IS NULL, e.page_sort, e.created_at",
            "date": " ORDER BY e.created_at DESC, e.id DESC",
        }[order]
        sql += " LIMIT ? OFFSET ?"
        rows = conn.execute(sql, (*args, limit, offset)).fetchall()
        return [entry_dict(conn, r) for r in rows]

    @app.get("/api/entries", tags=["quotes and thoughts"], dependencies=auth)
    def list_entries(
        book_id: int | None = None,
        tag: str | None = None,
        kind: Literal["quote", "thought"] | None = None,
        order: Literal["date", "page"] = "date",
        limit: int = Query(200, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        return list_entry_rows(conn, book_id, tag, kind, order, limit, offset)

    @app.get("/api/books/{book_id}/entries", tags=["quotes and thoughts"], dependencies=auth)
    def book_entries(
        book_id: int,
        tag: str | None = None,
        order: Literal["date", "page"] = "page",
        conn: sqlite3.Connection = Depends(get_db),
    ):
        load_book(conn, book_id)
        return list_entry_rows(conn, book_id, tag, None, order, 1000, 0)

    @app.get("/api/entries/{entry_id}", tags=["quotes and thoughts"], dependencies=auth)
    def get_entry(entry_id: int, conn: sqlite3.Connection = Depends(get_db)):
        return entry_dict(conn, load_entry(conn, entry_id))

    @app.patch("/api/entries/{entry_id}", tags=["quotes and thoughts"], dependencies=auth)
    def update_entry(entry_id: int, body: EntryPatch, conn: sqlite3.Connection = Depends(get_db)):
        row = load_entry(conn, entry_id)
        changes = body.model_dump(exclude_unset=True)
        tags = changes.pop("tags", None)
        if "book_id" in changes:
            load_book(conn, changes["book_id"])
        range_changed = {"word_start", "word_end"} & changes.keys()
        if range_changed and "text" not in changes and row["photo_id"]:
            start = changes.get("word_start", row["word_start"])
            end = changes.get("word_end", row["word_end"])
            if start is not None and end is not None:
                changes["text"] = ocr.select_range(photo_words(load_photo(conn, row["photo_id"])), start, end)
        for key in ("text", "note", "page"):
            if key in changes:
                changes[key] = blank_to_none(changes[key])
        if "text" in changes and not changes["text"]:
            raise HTTPException(422, "A quote or thought cannot be empty")
        if "page" in changes:
            changes["page_sort"] = db.page_sort_key(changes["page"])
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE entries SET {sets}, updated_at = ? WHERE id = ?",
                         (*changes.values(), db.now(), entry_id))
        if tags is not None:
            db.set_entry_tags(conn, entry_id, tags)
        db.reindex_entry(conn, entry_id)
        conn.commit()
        return entry_dict(conn, load_entry(conn, entry_id))

    @app.delete("/api/entries/{entry_id}", tags=["quotes and thoughts"], dependencies=auth)
    def delete_entry(entry_id: int, conn: sqlite3.Connection = Depends(get_db)):
        load_entry(conn, entry_id)
        conn.execute("DELETE FROM entries_fts WHERE rowid = ?", (entry_id,))
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM entry_tags)")
        conn.commit()
        return {"deleted": entry_id}

    @app.get("/api/tags", tags=["quotes and thoughts"], dependencies=auth)
    def list_tags(conn: sqlite3.Connection = Depends(get_db)):
        rows = conn.execute(
            "SELECT t.name, COUNT(et.entry_id) AS count FROM tags t JOIN entry_tags et ON et.tag_id = t.id "
            "GROUP BY t.id ORDER BY count DESC, t.name COLLATE NOCASE"
        ).fetchall()
        return [{"name": r["name"], "count": r["count"]} for r in rows]

    @app.get("/api/search", tags=["quotes and thoughts"], dependencies=auth)
    def search(
        q: str = Query(min_length=1, description="Words to find; accents and case are ignored"),
        book_id: int | None = None,
        limit: int = Query(50, ge=1, le=500),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        match = db.fts_query(q)
        if not match:
            return []
        sql = (
            f"SELECT e.*, b.title AS book_title, {db.TAG_LIST_SQL}, "
            "snippet(entries_fts, -1, char(2), char(3), '…', 16) AS snippet "
            "FROM entries_fts JOIN entries e ON e.id = entries_fts.rowid JOIN books b ON b.id = e.book_id "
            "WHERE entries_fts MATCH ?"
        )
        args: list = [match]
        if book_id is not None:
            sql += " AND e.book_id = ?"
            args.append(book_id)
        sql += " ORDER BY rank LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        return [{**entry_dict(conn, r), "snippet": r["snippet"]} for r in rows]

    # ----- maintenance -----

    @app.post("/api/backup", tags=["status"], dependencies=auth)
    def backup_now():
        """Write a database snapshot to data/backups/ right now (one also runs every night)."""
        path = backup.snapshot(settings.db_path, settings.backups_dir, settings.backups_kept)
        return {"file": path.name}

    app.mount("/static", StaticAssets(directory=STATIC), name="static")
    page = page_html()

    @app.get("/", include_in_schema=False)
    def app_page():
        return HTMLResponse(page, headers=PAGE_HEADERS)

    return app
