"""Sending from another device with a sending key: a passage, a PDF, a photo. A key adds to its own library
and can do nothing else."""

import json

import typst
from fastapi.testclient import TestClient

from conftest import make_page, owner
from marginote.main import create_app
from test_documents import read, send
from test_matching import COPIED, OPENING, article
from test_scholar import registry


def test_a_key_is_shown_once_kept_hashed_and_can_be_deleted(logged_in, settings):
    c = logged_in
    made = c.post("/api/keys", json={"name": "PC du bureau"}).json()
    assert made["key"].startswith("mgk_") and made["name"] == "PC du bureau"
    assert c.get("/api/keys").json() == [{k: made[k] for k in ("id", "name", "created_at", "last_used")}]
    stored = (settings.data_dir / "accounts.json").read_text()
    assert made["key"] not in stored and json.loads(stored)["accounts"][0]["keys"][0]["hash"]
    headers = {"Authorization": f"Bearer {made['key']}"}
    c.cookies.clear()                                         # another device: no login at all
    assert c.get("/api/send/check", headers=headers).json()["say"] == "Marginote est prêt · clé « PC du bureau »"
    assert c.get("/api/sources", headers=headers).status_code == 401           # it cannot read anything
    assert c.get("/api/send/check", headers={"Authorization": "Bearer mgk_x_y"}).status_code == 401
    c.post("/api/login", json={"password": "correct horse"})
    assert c.get("/api/keys").json()[0]["last_used"]
    assert c.delete(f"/api/keys/{made['id']}").json() == {"deleted": made["id"]}
    assert c.get("/api/send/check", headers=headers).status_code == 401        # deleted: stops at once


def test_a_passage_sent_from_a_pdf_reader_is_kept_with_its_page(logged_in, monkeypatch):
    c = logged_in
    registry(monkeypatch, {})
    doc = read(c, send(c, article(1, 45, OPENING), name="marceau.pdf")["id"])
    src = c.post("/api/sources", json={"kind": "article", "title": "La mémoire trie", "fetch_cover": False}).json()
    c.patch(f"/api/documents/{doc['id']}", json={"source_id": src["id"]})
    key = c.post("/api/keys", json={"name": "PC"}).json()["key"]
    c.cookies.clear()
    h = {"Authorization": f"Bearer {key}"}
    copied = COPIED.replace("commence", "com-\r\nmence").replace("¹", "1")
    sent = c.post("/api/send/passage", headers=h, json={"text": copied, "note": "Voir chapitre 3.", "origin": "windows"}).json()
    assert sent["status"] == "kept" and sent["say"] == "Gardé · La mémoire trie, p. 45" and sent["page"] == "45"
    nowhere = c.post("/api/send/passage", headers=h, json={"text": "Une phrase lue sur papier, ailleurs, ce matin même.",
                                                           "origin": "iphone"}).json()
    assert nowhere["status"] == "waiting" and nowhere["say"] == "À trier · pas trouvé dans vos PDF"
    c.post("/api/login", json={"password": "correct horse"})
    entry = c.get(f"/api/entries/{sent['entry_id']}").json()
    assert entry["note"] == "Voir chapitre 3." and entry["text"].startswith("La mémoire n’archive pas")
    assert [w["origin"] for w in c.get("/api/waiting").json()] == ["iphone"]


def test_pdfs_and_photos_sent_wait_in_the_inbox_of_the_keys_library_only(settings, monkeypatch):
    registry(monkeypatch, {})
    with TestClient(create_app(settings)) as c:
        c.post("/api/login", json={"password": "correct horse"})
        c.post("/api/accounts", json={"name": "Camille", "password": "lune-de-miel", "language": "en"})
        c.cookies.clear()
        c.post("/api/login", json={"name": "Camille", "password": "lune-de-miel"})
        key = c.post("/api/keys", json={"name": "Laptop"}).json()["key"]
        c.cookies.clear()
        h = {"Authorization": f"Bearer {key}"}
        pdf = typst.compile("Un court texte, assez long pour être lu comme une page véritable de quelques mots.".encode())
        # Windows' .NET writes a name with accents this way
        sent = c.post("/api/send/pdf", headers=h, files={"file": ("=?utf-8?B?TcOpbW9pcmUucGRm?=", pdf, "application/pdf")}).json()
        assert sent["status"] == "received" and sent["say"] == "PDF received · Mémoire.pdf: it is read, then waits in To sort"
        assert c.post("/api/send/photo", headers=h, files={"file": ("p.jpg", make_page(), "image/jpeg")}).json()["status"] == "received"
        assert c.post("/api/send/pdf", headers=h, files={"file": ("x.pdf", b"nope", "application/pdf")}).status_code == 415
        c.post("/api/login", json={"name": "Camille", "password": "lune-de-miel"})
        doc = read(c, sent["document_id"])
        assert doc["name"] == "Mémoire.pdf" and doc["queued"] is True
        assert len(c.get("/api/photos").json()) == 1
        c.cookies.clear()
        c.post("/api/login", json={"password": "correct horse"})
        assert c.get("/api/documents").json() == [] and c.get("/api/photos").json() == []     # the owner's: untouched
        assert c.get("/api/keys").json() == []
        assert not list(owner(settings).pdfs_dir.rglob("*.pdf"))


def test_the_windows_installer_is_whole():
    """The installer is a template filled in by Settings (the address, the key); its sending script is one
    block, written to %LOCALAPPDATA%\\Marginote on the PC."""
    from marginote.main import STATIC
    text = (STATIC / "marginote-windows.ps1").read_text(encoding="utf-8")
    assert text.count("'__SERVER__'") == 1 and text.count("'__KEY__'") == 1
    lines = text.splitlines()
    assert lines.count("$SendScript = @'") == 1 and lines.count("'@") == 1          # one here-string, closed once
    assert "CTRL+ALT+M" in text and "CTRL+ALT+N" in text and "GetFolderPath('SendTo')" in text
    for path in ("/api/send/passage", "/api/send/pdf", "/api/send/photo", "/api/send/check"):
        assert path in text
