"""Looking things up online (an ISBN, a back cover, a link, a DOI, an arXiv number) and the backups."""

import sqlite3
from datetime import datetime, timedelta

import pytesseract
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import backup, ids, linkinfo, lookup, names, ocr, scholar
from .context import Context, Library
from .routes_photos import BAD_IMAGE, MAX_UPLOAD, OCR_SLOT


class LinkIn(BaseModel):
    url: str


class RecognizeIn(BaseModel):
    text: str = Field(max_length=200_000, description="Whatever was pasted or shared")


ARTICLE_FIELDS = ("doi", "arxiv", "journal", "volume", "issue", "pages")


def merge_article(info: dict, found: dict | None) -> dict:
    """A page's own details, completed by the registry's (which knows every author and the journal)."""
    if not found:
        return info
    out = dict(info)
    for key in ("title", "journal", "volume", "issue", "pages", "doi", "arxiv", "date", "language"):
        if found.get(key) and not out.get(key):
            out[key] = found[key]
    if found.get("title"):
        out["title"] = found["title"]
    authors = found.get("people", {}).get("author") or []
    if len(authors) >= len(out.get("people") or []):
        out["people"] = authors
    if found.get("year") and not out.get("date"):
        out["date"] = str(found["year"])
    if not out.get("site") and found.get("journal"):
        out["site"] = found["journal"]
    return out


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
        if info.get("doi") or info.get("arxiv"):        # a scientific article: every author, the journal
            try:
                found = scholar.lookup_doi(info["doi"]) if info.get("doi") else scholar.lookup_arxiv(info["arxiv"])
            except lookup.LookupUnavailable:
                found = None
            info = merge_article(info, found)
        return {**info, "existing": same or existing(conn, "url", info["url"])
                or existing(conn, "doi", info.get("doi")) or existing(conn, "arxiv", info.get("arxiv"))}

    @api.post("/api/recognize", tags=["lookups"])
    def recognize(body: RecognizeIn, conn: sqlite3.Connection = Depends(ctx.get_db)):
        """What was pasted or shared: a DOI, an arXiv number, an ISBN, a link, or a passage. For an identifier,
        the source it names (looked up online, nothing saved) and the one already in your library, if any.
        For a passage, the identifiers written in it."""
        what = ids.classify(body.text)
        kind, value = what["kind"], what["value"]
        out = {**what, "existing": None, "source": None, "note": None}
        if kind == "doi":
            out["existing"] = existing(conn, "doi", value)
        elif kind == "arxiv":
            out["existing"] = existing(conn, "arxiv", value)
        elif kind == "isbn":
            out["existing"] = existing(conn, "isbn", value) or existing(conn, "isbn", lookup.isbn10(value))
        if kind not in ("doi", "arxiv", "isbn") or out["existing"]:
            return out
        if not settings.lookups_enabled:
            out["note"] = "Online lookups are turned off"
            return out
        try:
            out["source"] = scholar.identify(kind, value)
        except lookup.LookupUnavailable:
            out["note"] = "The online services could not be reached from your server"
            return out
        if not out["source"]:
            out["note"] = scholar.NOT_FOUND[kind]
        else:
            src = out["source"]
            out["existing"] = (existing(conn, "doi", src.get("doi")) or existing(conn, "arxiv", src.get("arxiv"))
                               or existing(conn, "isbn", src.get("isbn")))
        return out

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
        """Your whole library in one zip: a consistent copy of its database, its page photos, covers and PDFs."""
        name = f"marginote-{datetime.now():%Y-%m-%d}.zip"
        return StreamingResponse(
            backup.archive(lib.settings.db_path, lib.settings.data_dir, ("photos", "covers", "pdfs")),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @api.post("/api/backup", tags=["status"])
    def backup_now(lib: Library = Depends(ctx.require_library)):
        """Make a copy of your library's database now (one is also made every night)."""
        path = backup.snapshot(lib.settings.db_path, lib.settings.backups_dir, settings.backups_kept, settings.backups_monthly)
        return {"file": path.name}

    return api
