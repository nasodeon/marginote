"""Page photos: reading them (now, or later from the inbox), showing them, choosing a passage on them."""

import hashlib
import io
import logging
import sqlite3
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

import pytesseract
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from . import db, documents, ocr, pdfs
from .context import Context, Library
from .files import INBOX
from .views import load_photo, load_source

log = logging.getLogger("marginote")
MAX_UPLOAD = 30 * 1024 * 1024
BAD_IMAGE = (UnidentifiedImageError, OSError, Image.DecompressionBombError)
OCR_SLOT = ocr.OCR_SLOT      # one page read at a time (see ocr.py)
# Small copies are made one at a time too, and the last few kept: the inbox asks for them again and again.
THUMB_SLOT = threading.Lock()
THUMBS: OrderedDict = OrderedDict()
PAGES: OrderedDict = OrderedDict()      # PDF pages drawn at full size, the last few looked at
PHOTO_CACHE = {"Cache-Control": "private, max-age=31536000, immutable"}  # a photo never changes
PHOTO_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg"}


class PhotoPatch(BaseModel):
    queued: bool | None = Field(None, description="false: take it out of the inbox")
    source_id: int | None = None


class SelectIn(BaseModel):
    start: int = Field(description="Index of the first word")
    end: int = Field(description="Index of the last word")


class BoxIn(BaseModel):
    x: int
    y: int
    w: int
    h: int


def read_photo(ctx: Context, data: bytes) -> tuple[bytes, int, int, list, str | None]:
    """Open, straighten and read a photo, one at a time. Returns (file to keep, width, height, words, page)."""
    with OCR_SLOT:
        try:
            img = ocr.normalize_photo(data)
            size = img.size
            reading = ocr.read_page(img, ctx.settings.ocr_langs, straighten=ctx.settings.straighten_pages)
            del img
            # keep the straightened photo when there is one: word positions refer to it
            result = (ocr.to_stored(reading.photo), size[0], size[1], reading.words, reading.page)
            del reading
        finally:
            ocr.release_memory()
    return result


def queue_photo(ctx: Context, lib: Library, conn: sqlite3.Connection, data: bytes, source_id: int | None) -> str:
    """Keep a photo in the inbox, to be read in the background. The same photo twice is kept once."""
    sha = hashlib.sha256(data).hexdigest()
    existing = conn.execute("SELECT id FROM photos WHERE sha256 = ?", (sha,)).fetchone()
    if existing:
        conn.execute("UPDATE photos SET queued = 1, source_id = COALESCE(?, source_id) WHERE id = ?",
                     (source_id, existing["id"]))
        conn.commit()
        return existing["id"]
    try:
        ocr.open_image(data)   # reads only the header: refuse what is not an image now
    except BAD_IMAGE:
        raise HTTPException(415, "This file is not an image the app can read") from None
    photo_id = uuid.uuid4().hex
    rel = Path(INBOX) / f"{photo_id}.upload"
    (lib.files.photos / rel).write_bytes(data)
    conn.execute(
        "INSERT INTO photos (id, path, width, height, sha256, words, created_at, source_id, queued, status) "
        "VALUES (?, ?, 0, 0, ?, NULL, ?, ?, 1, 'reading')",
        (photo_id, rel.as_posix(), sha, db.now(), source_id),
    )
    conn.commit()
    ctx.reader_queue.put(("photo", lib, photo_id))
    return photo_id


def start_reader(ctx: Context) -> None:
    """Photos sent to the inbox, and PDFs, are read here, in the background, so the phone can send several and
    close. One at a time, whoever sent it; each is written back to its own library."""
    def read_queued(lib: Library, photo_id: str) -> None:
        conn = lib.connect()
        try:
            row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
            if not row or row["status"] != "reading":
                return
            source = lib.files.photos / row["path"]
            try:
                stored, width, height, words, page = read_photo(ctx, source.read_bytes())
            except (*BAD_IMAGE, pytesseract.TesseractError):
                log.exception("Could not read a photo from the inbox")
                conn.execute("UPDATE photos SET status = 'failed' WHERE id = ?", (photo_id,))
                conn.commit()
                return
            rel = Path(INBOX) / f"{photo_id}{ocr.PHOTO_SUFFIX}"
            (lib.files.photos / rel).write_bytes(stored)
            conn.execute(
                "UPDATE photos SET path = ?, width = ?, height = ?, words = ?, detected_page = ?, status = 'ready' "
                "WHERE id = ?",
                (rel.as_posix(), width, height, db.pack_words(ocr.words_to_dicts(words)), page, photo_id),
            )
            conn.commit()
            if source != lib.files.photos / rel:
                source.unlink(missing_ok=True)
        finally:
            conn.close()

    def loop() -> None:
        while True:
            item = ctx.reader_queue.get()
            if item is None:
                return
            kind, lib, item_id = item
            try:
                if kind == "document":
                    documents.read_document(lib, item_id, ctx.settings.ocr_langs, ctx.settings.lookups_enabled)
                else:
                    read_queued(lib, item_id)
            except Exception:
                log.exception("Reading in the background failed")

    threading.Thread(target=loop, name="photo-reader", daemon=True).start()
    for lib in ctx.libraries():   # photos sent before a restart and not read yet
        conn = lib.connect()
        try:
            for row in conn.execute("SELECT id FROM photos WHERE status = 'reading' ORDER BY created_at"):
                ctx.reader_queue.put(("photo", lib, row["id"]))
            for row in conn.execute("SELECT id FROM documents WHERE status = 'reading' ORDER BY created_at"):
                ctx.reader_queue.put(("document", lib, row["id"]))
        finally:
            conn.close()


def router(ctx: Context) -> APIRouter:
    api = APIRouter(dependencies=ctx.auth, tags=["photos"])
    get_db = ctx.get_db
    current = Depends(ctx.require_library)

    def photo_dict(row: sqlite3.Row, conn: sqlite3.Connection | None = None) -> dict:
        words = ocr.words_from_dicts(db.unpack_words(row["words"]))
        detected = row["detected_page"]
        document = None
        if row["document_id"] and conn is not None:      # a PDF's page
            doc = conn.execute("SELECT d.id, d.name, d.pages, s.pages AS journal_pages FROM documents d "
                               "LEFT JOIN sources s ON s.id = d.source_id WHERE d.id = ?", (row["document_id"],)).fetchone()
            near = {r["page_index"]: r["id"] for r in conn.execute(
                "SELECT id, page_index FROM photos WHERE document_id = ? AND page_index IN (?, ?)",
                (row["document_id"], row["page_index"] - 1, row["page_index"] + 1))}
            detected = documents.page_label(row["page_index"], detected, doc["journal_pages"])
            document = {"id": doc["id"], "name": doc["name"], "pages": doc["pages"], "index": row["page_index"],
                        "previous": near.get(row["page_index"] - 1), "next": near.get(row["page_index"] + 1)}
        return {
            "id": row["id"],
            "width": row["width"],
            "height": row["height"],
            "image_url": f"/api/photos/{row['id']}/image",
            "detected_page": detected,
            "document": document,
            "source_id": row["source_id"],
            "queued": bool(row["queued"]),
            "status": row["status"],
            "text": ocr.full_text(words),
            "words": ocr.words_for_browser(words),
            "created_at": row["created_at"],
        }

    @api.post("/api/photos")
    def upload_photo(
        file: UploadFile = File(...),
        later: bool = Query(False, description="Put it in the inbox, read it in the background, sort it later"),
        source_id: int | None = Query(None, description="The source it comes from"),
        conn: sqlite3.Connection = Depends(get_db),
        lib: Library = current,
    ):
        """Send a photo of a page (or a screenshot). Returns every word read, with its position, and the page
        number if found.

        With later=true the answer comes at once (status "reading") and the photo waits in the inbox until you
        sort it. Saving a quote from a photo files it in its source's folder; a photo no quote uses, and not in
        the inbox, is deleted after UNUSED_PHOTO_HOURS (24 h by default).
        """
        data = file.file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Photo larger than 30 MB")
        if source_id is not None:
            load_source(conn, source_id)
        if later:
            return photo_dict(load_photo(conn, queue_photo(ctx, lib, conn, data, source_id)), conn)
        sha = hashlib.sha256(data).hexdigest()
        existing = conn.execute("SELECT * FROM photos WHERE sha256 = ?", (sha,)).fetchone()
        if existing:
            return photo_dict(load_photo(conn, existing["id"]), conn)
        photo_id = uuid.uuid4().hex
        try:
            stored, width, height, words, page = read_photo(ctx, data)
        except BAD_IMAGE:
            raise HTTPException(415, "This file is not an image the app can read")
        except pytesseract.TesseractError:
            log.exception("Tesseract failed")
            raise HTTPException(500, "Text recognition failed on this photo; try taking it again")
        rel = Path(INBOX) / f"{photo_id}{ocr.PHOTO_SUFFIX}"
        (lib.files.photos / rel).write_bytes(stored)
        conn.execute(
            "INSERT INTO photos (id, path, width, height, sha256, words, detected_page, created_at, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (photo_id, rel.as_posix(), width, height, sha, db.pack_words(ocr.words_to_dicts(words)), page,
             db.now(), source_id),
        )
        conn.commit()
        return photo_dict(load_photo(conn, photo_id), conn)

    @api.get("/api/photos")
    def list_inbox(conn: sqlite3.Connection = Depends(get_db)):
        """The inbox: photos waiting to be sorted, oldest first (without their words)."""
        rows = conn.execute(
            "SELECT p.id, p.source_id, p.status, p.detected_page, p.created_at, p.width, p.height, "
            "s.title AS source_title, (SELECT COUNT(*) FROM entries e WHERE e.photo_id = p.id) AS entry_count "
            "FROM photos p LEFT JOIN sources s ON s.id = p.source_id WHERE p.queued = 1 ORDER BY p.created_at, p.id"
        ).fetchall()
        return [{**dict(r), "image_url": f"/api/photos/{r['id']}/image",
                 "thumb_url": f"/api/photos/{r['id']}/image?width=320"} for r in rows]

    @api.patch("/api/photos/{photo_id}")
    def update_photo(photo_id: str, body: PhotoPatch, conn: sqlite3.Connection = Depends(get_db)):
        """Take a photo out of the inbox (queued=false), or change the source it comes from."""
        load_photo(conn, photo_id)
        if body.source_id is not None:
            load_source(conn, body.source_id)
            conn.execute("UPDATE photos SET source_id = ? WHERE id = ?", (body.source_id, photo_id))
        if body.queued is not None:
            conn.execute("UPDATE photos SET queued = ? WHERE id = ?", (int(body.queued), photo_id))
        conn.commit()
        return photo_dict(load_photo(conn, photo_id), conn)

    @api.delete("/api/photos/{photo_id}")
    def delete_photo(photo_id: str, conn: sqlite3.Connection = Depends(get_db), lib: Library = current):
        """Delete a photo no quote uses (from the inbox, for example)."""
        row = load_photo(conn, photo_id)
        if row["document_id"]:
            raise HTTPException(409, "This is a page of a PDF: delete the PDF instead")
        used = conn.execute("SELECT COUNT(*) FROM entries WHERE photo_id = ?", (photo_id,)).fetchone()[0]
        if used:
            raise HTTPException(409, f"This photo is used by {used} saved quote(s); delete them first")
        conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        conn.commit()
        (lib.files.photos / row["path"]).unlink(missing_ok=True)
        return {"deleted": photo_id}

    @api.get("/api/photos/{photo_id}")
    def get_photo(photo_id: str, conn: sqlite3.Connection = Depends(get_db)):
        return photo_dict(load_photo(conn, photo_id), conn)

    @api.get("/api/photos/{photo_id}/image")
    def photo_image(photo_id: str, width: int | None = Query(None, ge=64, le=1200, description="A smaller copy"),
                    conn: sqlite3.Connection = Depends(get_db), lib: Library = current):
        row = load_photo(conn, photo_id)
        if row["document_id"]:
            return pdf_page(lib, conn, row, width)
        path = lib.files.photos / row["path"]
        if not path.is_file():
            raise HTTPException(404, "The photo file is missing from the photos folder")
        ready = row["status"] == "ready"
        headers = PHOTO_CACHE if ready else {"Cache-Control": "no-store"}
        if width is None and path.suffix in PHOTO_TYPES:
            return FileResponse(path, media_type=PHOTO_TYPES[path.suffix], headers=headers)
        key = (lib.account_id, photo_id, width, row["status"])   # never one library's picture for another
        with THUMB_SLOT:
            if key in THUMBS:
                THUMBS.move_to_end(key)
                return Response(THUMBS[key], media_type="image/webp", headers=headers)
            try:
                with Image.open(path) as img:
                    if img.format == "JPEG":
                        img.draft("RGB", ((width or 1600), (width or 1600) * 2))
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    img.thumbnail((width or 1600, (width or 1600) * 2))
                    out = io.BytesIO()
                    img.save(out, format="WEBP", quality=72, method=2)
            except BAD_IMAGE:
                raise HTTPException(415, "This photo cannot be shown")
            data = out.getvalue()
            if ready and width and width <= 400:
                THUMBS[key] = data
                while len(THUMBS) > 60:          # about 1 MB at most
                    THUMBS.popitem(last=False)
        return Response(data, media_type="image/webp", headers=headers)

    def pdf_page(lib: Library, conn: sqlite3.Connection, row: sqlite3.Row, width: int | None) -> Response:
        """A PDF's page, drawn now from the PDF, at the size its words are placed in (or smaller)."""
        doc = conn.execute("SELECT path FROM documents WHERE id = ?", (row["document_id"],)).fetchone()
        path = lib.files.pdfs / doc["path"]
        if not path.is_file():
            raise HTTPException(404, "The PDF file is missing from the pdfs folder")
        size = min(width or row["width"], row["width"])
        key = (lib.account_id, row["id"], size)        # never one library's page for another
        cache = THUMBS if width and width <= 400 else PAGES
        with THUMB_SLOT:
            data = cache.get(key)
            if data is not None:
                cache.move_to_end(key)
        if data is None:
            try:
                data = pdfs.page_image(path, row["page_index"], size, round(row["height"] * size / row["width"]))
            except pdfs.NotAPdf:
                raise HTTPException(415, "This PDF page cannot be shown") from None
            with THUMB_SLOT:
                cache[key] = data
                while len(cache) > (60 if cache is THUMBS else 8):    # about 1 MB and 2 MB at most
                    cache.popitem(last=False)
        return Response(data, media_type="image/webp", headers=PHOTO_CACHE)

    @api.post("/api/photos/{photo_id}/select")
    def select_words(photo_id: str, body: SelectIn, conn: sqlite3.Connection = Depends(get_db)):
        """Preview the passage between two words (the first and last word you tapped)."""
        words = ocr.words_from_dicts(db.unpack_words(load_photo(conn, photo_id)["words"]))
        start, end = sorted((body.start, body.end))
        return {"text": ocr.select_range(words, start, end), "word_start": start, "word_end": end}

    @api.post("/api/photos/{photo_id}/select-box")
    def select_box(photo_id: str, body: BoxIn, conn: sqlite3.Connection = Depends(get_db)):
        """Fallback: preview the passage inside a rectangle drawn on the photo (in photo pixels)."""
        words = ocr.words_from_dicts(db.unpack_words(load_photo(conn, photo_id)["words"]))
        text, start, end = ocr.select_box(words, body.x, body.y, body.w, body.h)
        return {"text": text, "word_start": start, "word_end": end}

    return api
