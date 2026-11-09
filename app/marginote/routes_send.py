"""Sending from another device without logging in: a passage copied in a PDF reader (Ctrl+Alt+M on
Windows, the iPhone's Share menu), a PDF or a photo (Windows' Envoyer vers).

Each call carries a sending key (Authorization: Bearer mgk_…), made in Settings. A key can only add to its
own library: these calls answer with where the passage went, never with anything else of the library.
The answer's "say" is one short line for a notification, in the account's language."""

import email.header
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from . import documents, pdfs
from .context import Context, Library
from .routes_passages import PassageIn, receive
from .routes_photos import MAX_UPLOAD, queue_photo

SAY = {
    "fr": {"kept": "Gardé · {title}, p. {page}", "kept_nopage": "Gardé · {title}",
           "maybe": "À trier · peut-être {title}, p. {page}", "pdf_nosource": "À trier · dans {name}, p. {page} : donnez-lui sa source",
           "nowhere": "À trier · pas trouvé dans vos PDF", "link": "À trier · le lien attend sa source",
           "pdf": "PDF reçu · {name} : il est lu, puis attend dans À trier", "pdf_again": "PDF déjà reçu · {name}",
           "photo": "Photo reçue · elle attend dans À trier", "ready": "Marginote est prêt · clé « {name} »"},
    "en": {"kept": "Kept · {title}, p. {page}", "kept_nopage": "Kept · {title}",
           "maybe": "To sort · maybe {title}, p. {page}", "pdf_nosource": "To sort · in {name}, p. {page}: give it its source",
           "nowhere": "To sort · not found in your PDFs", "link": "To sort · the link waits for its source",
           "pdf": "PDF received · {name}: it is read, then waits in To sort", "pdf_again": "PDF already received · {name}",
           "photo": "Photo received · it waits in To sort", "ready": "Marginote is ready · key “{name}”"},
}


class Sent(BaseModel):
    status: str = Field(description="kept, waiting or received")
    say: str = Field(description="One line for a notification")
    entry_id: int | None = None
    waiting_id: int | None = None
    document_id: str | None = None
    source_title: str | None = None
    page: str | None = None


def file_name(raw: str | None) -> str | None:
    """A file name as Windows' .NET sends it: '=?utf-8?B?…?=' when it has accents."""
    if raw and raw.startswith("=?"):
        try:
            return "".join(part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                           for part, enc in email.header.decode_header(raw))
        except (ValueError, LookupError):
            return raw
    return raw


def router(ctx: Context) -> APIRouter:
    api = APIRouter(tags=["sending"])
    session = Depends(ctx.require_library)

    class KeyIn(BaseModel):
        name: str = Field(max_length=60, description="Which device it is for: 'PC du bureau', 'iPhone'")

    @api.get("/api/keys")
    def list_keys(lib: Library = session):
        """Your sending keys (never the keys themselves: they are shown once, when made)."""
        return ctx.accounts.keys(lib.account_id)

    @api.post("/api/keys", status_code=201)
    def make_key(body: KeyIn, lib: Library = session):
        """A new sending key, for one device. The key is in this answer only: copy it now."""
        try:
            entry, full = ctx.accounts.add_key(lib.account_id, body.name)
        except ValueError as err:
            raise HTTPException(422, str(err)) from None
        return {**entry, "key": full}

    @api.delete("/api/keys/{key_id}")
    def delete_key(key_id: str, lib: Library = session):
        """The device with this key can no longer send."""
        try:
            ctx.accounts.remove_key(lib.account_id, key_id)
        except KeyError:
            raise HTTPException(404, "No sending key with this id") from None
        return {"deleted": key_id}

    # ----- with a sending key -----

    def by_key(request: Request) -> tuple[Library, dict, str]:
        auth = request.headers.get("authorization", "")
        found = ctx.accounts.by_key(auth[7:].strip()) if auth.lower().startswith("bearer ") else None
        if found is None:
            raise HTTPException(401, "This sending key is not valid (deleted?): make a new one in Settings",
                                headers={"WWW-Authenticate": "Bearer"})
        account, key = found
        lang = account.get("language", "fr") if account.get("language") in SAY else "fr"
        return ctx.library(account["id"]), key, lang

    def keyed_db(sender=Depends(by_key)):
        conn = sender[0].connect()
        try:
            yield conn
        finally:
            conn.close()

    @api.get("/api/send/check")
    def check(sender=Depends(by_key)) -> Sent:
        """Whether a key works (the installer asks once)."""
        _, key, lang = sender
        return Sent(status="ready", say=SAY[lang]["ready"].format(name=key["name"]))

    @api.post("/api/send/passage", status_code=201)
    def send_passage(body: PassageIn, sender=Depends(by_key), conn: sqlite3.Connection = Depends(keyed_db)) -> Sent:
        """A passage copied while reading: kept at once when found in one of your PDFs, else waiting in À trier."""
        lang = sender[2]
        say = SAY[lang]
        done = receive(conn, body)
        if "kept" in done:
            entry, where = done["kept"], done["where"]
            title = entry["source"]["title"]
            return Sent(status="kept", entry_id=entry["id"], source_title=title, page=entry["page"],
                        say=(say["kept"] if entry["page"] else say["kept_nopage"]).format(title=title, page=entry["page"]),
                        document_id=where["document_id"])
        waiting = done["waiting"]
        guess = waiting["guess"]
        if guess and guess["source_id"]:
            line = say["maybe"].format(title=guess["source_title"], page=guess["page"])
        elif guess:
            line = say["pdf_nosource"].format(name=guess["document_name"], page=guess["page"])
        else:
            line = say["link"] if not body.text.strip() else say["nowhere"]
        return Sent(status="waiting", waiting_id=waiting["id"], say=line,
                    source_title=guess["source_title"] if guess else None, page=guess["page"] if guess else None)

    @api.post("/api/send/pdf", status_code=201)
    def send_pdf(file: UploadFile = File(...), sender=Depends(by_key), conn: sqlite3.Connection = Depends(keyed_db)) -> Sent:
        """A PDF, sent to be read and recognised; it waits in À trier for you to confirm what it is."""
        lib, _, lang = sender
        name = file_name(file.filename) or "document.pdf"
        try:
            doc_id, new = documents.save_upload(lib, conn, file.file, name, None)
        except documents.TooBig as err:
            raise HTTPException(413, str(err)) from None
        except pdfs.NotAPdf:
            raise HTTPException(415, "This file is not a PDF the app can read") from None
        if new:
            ctx.reader_queue.put(("document", lib, doc_id))
        return Sent(status="received", document_id=doc_id, say=SAY[lang]["pdf" if new else "pdf_again"].format(name=name))

    @api.post("/api/send/photo", status_code=201)
    def send_photo(file: UploadFile = File(...), sender=Depends(by_key), conn: sqlite3.Connection = Depends(keyed_db)) -> Sent:
        """A photo of a page or a screenshot: read in the background, it waits in À trier."""
        lib, _, lang = sender
        data = file.file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Photo larger than 30 MB")
        queue_photo(ctx, lib, conn, data, None)
        return Sent(status="received", say=SAY[lang]["photo"])

    return api
