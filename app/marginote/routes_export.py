"""Exporting your quotes and notes as a PDF or a Word file (export.py orders them; export_pdf.py and export_docx.py
write the file).

The file is made when asked, kept in memory for a few minutes under a link nobody can guess, then forgotten: never
written to disk. The link works without the login cookie, so that the iPhone app can hand it to Safari (whose
login is separate) and Safari can show or save the file."""

import secrets
import sqlite3
import threading
import time
import unicodedata
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import export, export_docx, export_pdf
from .context import Context
from .routes_photos import OCR_SLOT

KEEP_SECONDS = 15 * 60
KEEP_FILES = 6
MEDIA = {"pdf": "application/pdf",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_files: dict[str, dict] = {}
_files_lock = threading.Lock()


class ExportIn(BaseModel):
    format: Literal["pdf", "docx"] = "pdf"
    by: Literal["author", "topic", "source"] = "author"
    ids: list[int] = Field(default_factory=list, max_length=100_000)   # the chosen ones, unless all
    all: bool = False
    said: bool = False                  # by source: also what people said, with no source
    quotes: bool = True
    notes: bool = True
    bibliography: bool = True


def _keep(name: str, media: str, body: bytes) -> str:
    token = secrets.token_urlsafe(24)
    now = time.monotonic()
    with _files_lock:
        for t in [t for t, f in _files.items() if f["until"] < now]:
            del _files[t]
        while len(_files) >= KEEP_FILES:
            del _files[min(_files, key=lambda t: _files[t]["until"])]
        _files[token] = {"name": name, "media": media, "body": body, "until": now + KEEP_SECONDS}
    return token


def _disposition(kind: str, name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().replace('"', "")
    return f"{kind}; filename=\"{plain}\"; filename*=UTF-8''{quote(name, safe='')}"


def router(ctx: Context) -> APIRouter:
    api = APIRouter()
    get_db = ctx.get_db

    def account_of(request: Request) -> dict:
        account = ctx.account_for(request)
        if account is None:
            raise HTTPException(401, "Log in first with POST /api/login")
        return account

    def build(body: ExportIn, conn: sqlite3.Connection, account: dict) -> dict:
        include = [k for k in ("quotes", "notes", "bibliography") if getattr(body, k)]
        if not (body.quotes or body.notes):
            raise HTTPException(422, "Choose quotes, notes, or both")
        if not body.all and not body.ids and not (body.by == "source" and body.said):
            raise HTTPException(422, "Choose at least one")
        return export.build(conn, body.by, None if body.all else body.ids, said=body.said and body.by == "source",
                            include=include, lang=account.get("language", "fr"), account=account["name"])

    @api.get("/api/export/choices", tags=["export"])
    def choices(conn: sqlite3.Connection = Depends(get_db)):
        """The authors, topics and sources that can be exported, in the document's order, with what each holds;
        and how many quotes have no source."""
        return export.choices(conn)

    @api.post("/api/export/summary", tags=["export"])
    def summary(body: ExportIn, request: Request, conn: sqlite3.Connection = Depends(get_db)):
        """How many chapters, quotes and notes the export would hold (nothing is made)."""
        if not (body.quotes or body.notes) or (not body.all and not body.ids and not (body.by == "source" and body.said)):
            return {"chapters": 0, "quotes": 0, "notes": 0}
        return build(body, conn, account_of(request))["counts"]

    @api.post("/api/export", tags=["export"])
    def make(body: ExportIn, request: Request, conn: sqlite3.Connection = Depends(get_db)):
        """Make the PDF or Word file. Answers with a link to fetch it (for 15 minutes, without the login cookie)."""
        account = account_of(request)
        with OCR_SLOT:      # a big export uses as much memory as reading a page: one or the other, never both
            doc = build(body, conn, account)
            if not doc["chapters"]:
                raise HTTPException(422, "Nothing to export in what you chose")
            body_bytes = export_pdf.pdf(doc) if body.format == "pdf" else export_docx.docx(doc)
        name = export.file_name(doc, body.format)
        token = _keep(name, MEDIA[body.format], body_bytes)
        return {"url": f"/api/export/files/{token}", "name": name, "size": len(body_bytes), **doc["counts"]}

    @api.get("/api/export/files/{token}", tags=["export"], include_in_schema=False)
    def fetch(token: str):
        with _files_lock:
            f = _files.get(token)
        if f is None or f["until"] < time.monotonic():
            raise HTTPException(404, "This export is no longer here: make it again")
        kind = "inline" if f["media"] == MEDIA["pdf"] else "attachment"
        return Response(f["body"], media_type=f["media"],
                        headers={"Content-Disposition": _disposition(kind, f["name"]), "Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff"})

    return api
