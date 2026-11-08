"""Looking things up online (an ISBN, a back cover, a link) and the backups."""

import sqlite3
from datetime import datetime, timedelta

import pytesseract
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import backup, linkinfo, lookup, names, ocr
from .context import Context, Library
from .routes_photos import BAD_IMAGE, MAX_UPLOAD, OCR_SLOT


class LinkIn(BaseModel):
    url: str


def router(ctx: Context) -> APIRouter:
    api = APIRouter(dependencies=ctx.auth)
    settings = ctx.settings

    def lookups_on() -> None:
        if not settings.lookups_enabled:
            raise HTTPException(409, "Online lookups are turned off (LOOKUPS_ENABLED=false)")

    def existing(conn: sqlite3.Connection, column: str, value: str | None) -> dict | None:
        row = conn.execute(f"SELECT id, kind, title FROM sources WHERE {column} = ?", (value,)).fetchone() if value else None
        return dict(row) if row else None

    @api.get("/api/lookup/isbn/{isbn}", tags=["lookups"])
    def lookup_isbn(isbn: str, conn: sqlite3.Connection = Depends(ctx.get_db)):
        """Title, authors, publisher and year from an ISBN. Nothing is saved: send the result to POST /api/sources."""
        clean = lookup.clean_isbn(isbn)
        if not clean:
            raise HTTPException(422, "This ISBN looks wrong: check the digits on the back cover")
        lookups_on()
        try:
            found = lookup.lookup_isbn(clean)
        except lookup.LookupUnavailable:
            raise HTTPException(503, "The book services could not be reached from your server; type the details in")
        if not found:
            raise HTTPException(404, "No book found for this ISBN; type the details in instead")
        found["people"] = {"author": names.split_list(found.get("authors")),
                           "translator": names.split_list(found.get("translator"))}
        found["existing"] = existing(conn, "isbn", clean) or existing(conn, "isbn", lookup.isbn13(clean))
        return found

    @api.post("/api/lookup/isbn-photo", tags=["lookups"])
    def isbn_from_photo(file: UploadFile = File(...)):
        """Read the ISBN on a photo of the back cover: the barcode, else the printed number. The photo is not kept."""
        data = file.file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Photo larger than 30 MB")
        with OCR_SLOT:
            try:
                img = ocr.normalize_photo(data)
            except BAD_IMAGE:
                raise HTTPException(415, "This file is not an image the app can read")
            try:
                isbn, found_by = ocr.find_isbn(img, settings.ocr_langs)
            except pytesseract.TesseractError:
                isbn, found_by = None, ""
            finally:
                del img
                ocr.release_memory()
        if not isbn:
            raise HTTPException(404, "No ISBN found on this photo: take the barcode closer, or type the number")
        return {"isbn": isbn, "found_by": found_by}

    @api.post("/api/lookup/link", tags=["lookups"])
    def lookup_link(body: LinkIn, conn: sqlite3.Connection = Depends(ctx.get_db)):
        """What a web page or a video says about itself: title, site or channel, author, date, picture.
        Nothing is saved. `existing` is the source already in your library with this link, if any."""
        try:
            url = linkinfo.clean_url(body.url)
        except linkinfo.LinkError as err:
            raise HTTPException(422, str(err))
        same = existing(conn, "url", url)
        if not settings.lookups_enabled:
            return {"url": url, "kind": "article", "title": None, "site": None, "people": [], "date": None,
                    "language": None, "image_url": None, "existing": same, "note": "Online lookups are turned off"}
        try:
            info = linkinfo.read(url)
        except linkinfo.LinkError as err:
            # the link is still usable: the details are typed in
            return {"url": url, "kind": "article", "title": None, "site": None, "people": [], "date": None,
                    "language": None, "image_url": None, "existing": same, "note": str(err)}
        return {**info, "existing": same or existing(conn, "url", info["url"])}

    # ----- backups -----

    @api.get("/api/backup/status", tags=["status"])
    def backup_status(lib: Library = Depends(ctx.require_library)):
        """Your library's database copies, when the next one is made, and how much space it takes."""
        now = datetime.now().astimezone()
        done_today = (lib.settings.backups_dir / f"marginote-{now:%Y-%m-%d}.zip").exists()
        next_run = now.replace(hour=settings.backup_hour, minute=0, second=0, microsecond=0)
        if done_today or now.hour > settings.backup_hour:
            next_run += timedelta(days=1)
        return {
            "copies": backup.list_backups(lib.settings.backups_dir),
            "kept": settings.backups_kept,
            "monthly": settings.backups_monthly,
            "next": next_run.isoformat(timespec="minutes"),
            **lib.files.usage(),
        }

    @api.get("/api/backup/download", tags=["status"])
    def backup_download(lib: Library = Depends(ctx.require_library)):
        """Your whole library in one zip: a consistent copy of its database, its page photos and covers."""
        name = f"marginote-{datetime.now():%Y-%m-%d}.zip"
        return StreamingResponse(
            backup.archive(lib.settings.db_path, lib.settings.data_dir, ("photos", "covers")),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @api.post("/api/backup", tags=["status"])
    def backup_now(lib: Library = Depends(ctx.require_library)):
        """Make a copy of your library's database now (one is also made every night)."""
        path = backup.snapshot(lib.settings.db_path, lib.settings.backups_dir, settings.backups_kept, settings.backups_monthly)
        return {"file": path.name}

    return api
