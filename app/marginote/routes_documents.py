"""PDFs: sending one, following its reading, giving it its source, opening it.

The PDF itself opens from a link signed for one account and a few hours, so the iPhone app can hand it to
Safari (whose login is separate); the link names no library, and opens only the one it was made for."""

import hashlib
import hmac
import json
import sqlite3
import time

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import documents, pdfs
from .context import Context, Library
from .routes_export import _disposition
from .views import load_source

LINK_SECONDS = 12 * 3600


class DocumentPatch(BaseModel):
    source_id: int | None = Field(None, description="The source it is; it then leaves À trier")
    queued: bool | None = Field(None, description="false: out of À trier")


def router(ctx: Context) -> APIRouter:
    api = APIRouter(tags=["pdfs"])
    get_db = ctx.get_db
    current = Depends(ctx.require_library)
    secret = ctx.settings.secret_key().encode()

    def signature(account_id: str, doc_id: str, until: int) -> str:
        return hmac.new(secret, f"pdf:{account_id}:{doc_id}:{until}".encode(), hashlib.sha256).hexdigest()[:32]

    def file_url(lib: Library, doc_id: str) -> str:
        until = int(time.time()) + LINK_SECONDS
        until -= until % 3600            # the same link for an hour: the browser keeps the PDF it opened
        return f"/api/documents/{doc_id}/file?a={lib.account_id}&e={until}&s={signature(lib.account_id, doc_id, until)}"

    def load(conn: sqlite3.Connection, doc_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No PDF with this id")
        return row

    def doc_dict(conn: sqlite3.Connection, lib: Library, row: sqlite3.Row, pages: bool = False) -> dict:
        found = json.loads(row["found"] or "{}")
        source = conn.execute("SELECT id, kind, title, pages FROM sources WHERE id = ?", (row["source_id"],)).fetchone() \
            if row["source_id"] else None
        out = {
            "id": row["id"], "name": row["name"], "pages": row["pages"], "read_pages": row["read_pages"],
            "status": row["status"], "queued": bool(row["queued"]), "created_at": row["created_at"],
            "source": {k: source[k] for k in ("id", "kind", "title")} if source else None,
            "found": {k: found.get(k) for k in ("by", "value", "page", "title", "source", "note")},
            "existing": documents.existing_source(conn, found) if row["status"] == "ready" else None,
            "file_url": file_url(lib, row["id"]),
            "entry_count": conn.execute("SELECT COUNT(*) FROM entries e JOIN photos p ON p.id = e.photo_id "
                                        "WHERE p.document_id = ?", (row["id"],)).fetchone()[0],
        }
        if pages:
            counts = dict(conn.execute("SELECT p.page_index, COUNT(e.id) FROM photos p JOIN entries e ON e.photo_id = p.id "
                                       "WHERE p.document_id = ? GROUP BY p.page_index", (row["id"],)).fetchall())
            out["page_list"] = [
                {"photo_id": r["id"], "index": r["page_index"], "entry_count": counts.get(r["page_index"], 0),
                 "page": documents.page_label(r["page_index"], r["detected_page"], source["pages"] if source else None)}
                for r in conn.execute("SELECT id, page_index, detected_page FROM photos WHERE document_id = ? "
                                      "ORDER BY page_index", (row["id"],))]
        return out

    @api.post("/api/documents", status_code=201, dependencies=ctx.auth)
    def upload(file: UploadFile = File(...), source_id: int | None = Query(None, description="The source it is, if known"),
               conn: sqlite3.Connection = Depends(get_db), lib: Library = current):
        """Send a PDF (an article, a book). It is kept, read page by page in the background (pages with no text,
        from a scan, are read like photos), and recognised from the DOI, arXiv number or ISBN printed in it.
        Sent twice, it is kept once. Follow the reading with GET /api/documents/{id}."""
        if source_id is not None:
            load_source(conn, source_id)
        try:
            doc_id, new = documents.save_upload(lib, conn, file.file, file.filename, source_id)
        except documents.TooBig as err:
            raise HTTPException(413, str(err)) from None
        except pdfs.NotAPdf:
            raise HTTPException(415, "This file is not a PDF the app can read") from None
        if new:
            ctx.reader_queue.put(("document", lib, doc_id))
        elif source_id is not None:
            row = load(conn, doc_id)
            if row["source_id"] is None:
                lib.files.file_document(conn, doc_id, source_id)
                conn.execute("UPDATE documents SET queued = 0 WHERE id = ?", (doc_id,))
                conn.commit()
        return doc_dict(conn, lib, load(conn, doc_id))

    @api.get("/api/documents", dependencies=ctx.auth)
    def list_documents(source_id: int | None = Query(None, description="A source's PDFs"),
                       queued: bool | None = Query(None, description="true: those in À trier"),
                       conn: sqlite3.Connection = Depends(get_db), lib: Library = current):
        where, args = [], []
        if source_id is not None:
            where.append("source_id = ?")
            args.append(source_id)
        if queued is not None:
            where.append("queued = ?")
            args.append(int(queued))
        rows = conn.execute("SELECT * FROM documents" + (" WHERE " + " AND ".join(where) if where else "")
                            + " ORDER BY created_at DESC", args).fetchall()
        return [doc_dict(conn, lib, r) for r in rows]

    @api.get("/api/documents/{doc_id}", dependencies=ctx.auth)
    def get_document(doc_id: str, conn: sqlite3.Connection = Depends(get_db), lib: Library = current):
        """The PDF, how far its reading has gone, what it was recognised as, and its pages (with the number
        printed on each, and how many quotes were kept from it)."""
        return doc_dict(conn, lib, load(conn, doc_id), pages=True)

    @api.patch("/api/documents/{doc_id}", dependencies=ctx.auth)
    def update_document(doc_id: str, body: DocumentPatch, conn: sqlite3.Connection = Depends(get_db),
                        lib: Library = current):
        """Give the PDF its source (it moves to the source's folder and leaves À trier), or take it out of
        À trier."""
        load(conn, doc_id)
        changes = body.model_dump(exclude_unset=True)
        if "source_id" in changes:
            if body.source_id is not None:
                load_source(conn, body.source_id)
            lib.files.file_document(conn, doc_id, body.source_id)
            if body.source_id is not None and "queued" not in changes:
                changes["queued"] = False
        if changes.get("queued") is not None:
            conn.execute("UPDATE documents SET queued = ? WHERE id = ?", (int(changes["queued"]), doc_id))
        conn.commit()
        return doc_dict(conn, lib, load(conn, doc_id), pages=True)

    @api.post("/api/documents/{doc_id}/recognize", dependencies=ctx.auth)
    def recognize_again(doc_id: str, conn: sqlite3.Connection = Depends(get_db), lib: Library = current):
        """Look again for what the PDF is (when the online services could not be reached the first time)."""
        row = load(conn, doc_id)
        if row["status"] != "ready":
            raise HTTPException(409, "This PDF is still being read")
        found = json.loads(row["found"] or "{}")
        found.update(documents.recognise(lib, conn, doc_id, row["name"], ctx.settings.lookups_enabled))
        conn.execute("UPDATE documents SET found = ? WHERE id = ?", (json.dumps(found, ensure_ascii=False), doc_id))
        conn.commit()
        return doc_dict(conn, lib, load(conn, doc_id), pages=True)

    @api.delete("/api/documents/{doc_id}", dependencies=ctx.auth)
    def delete_document(doc_id: str, conn: sqlite3.Connection = Depends(get_db), lib: Library = current):
        """Delete the PDF and its pages. Quotes kept from it stay, with their text and page number."""
        load(conn, doc_id)
        lib.files.remove_documents(conn, "id = ?", (doc_id,))
        return {"deleted": doc_id}

    @api.get("/api/documents/{doc_id}/file", include_in_schema=False)
    def open_file(doc_id: str, request: Request, a: str = "", e: int = 0, s: str = ""):
        """The PDF itself, shown by the browser. From the app (logged in), or from a signed link."""
        lib = None
        if a and s and e >= time.time() and hmac.compare_digest(s, signature(a, doc_id, e)) and ctx.accounts.get(a):
            lib = ctx.library(a)
        if lib is None:
            lib = ctx.require_library(request)
        conn = lib.connect()
        try:
            row = load(conn, doc_id)
        finally:
            conn.close()
        path = lib.files.pdfs / row["path"]
        if not path.is_file():
            raise HTTPException(404, "The PDF file is missing from the pdfs folder")
        return FileResponse(path, media_type="application/pdf",
                            headers={"Content-Disposition": _disposition("inline", row["name"] or "document.pdf"),
                                     "Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})

    return api

