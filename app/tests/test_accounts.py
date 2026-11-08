"""Accounts: each person has a library nobody else can read or change, and a language of their own."""

import base64
import hashlib
import hmac
import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from marginote.main import create_app

from conftest import make_page

OWNER_PW = "correct horse"
MARK = "Zéphyrin-du-propriétaire"     # in every piece of the owner's library: must never reach anyone else


def login(c: TestClient, name: str, password: str) -> dict:
    c.cookies.clear()
    r = c.post("/api/login", json={"name": name, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def fill_owner_library(c: TestClient) -> dict:
    """A bit of everything in the owner's library, each carrying MARK."""
    src = c.post("/api/sources", json={"title": f"Livre {MARK}", "people": {"author": [f"Auteur {MARK}"],
                                       "about": [f"Sujet {MARK}"]}, "topics": [f"thème {MARK}"], "fetch_cover": False}).json()
    c.post(f"/api/sources/{src['id']}/cover", files={"file": ("c.jpg", make_page(), "image/jpeg")})
    quote = c.post("/api/entries", json={"source_id": src["id"], "text": f"Passage {MARK}", "note": f"Commentaire {MARK}"}).json()
    said = c.post("/api/entries", json={"text": f"Parole {MARK}", "words_by": f"Orateur {MARK}"}).json()
    note = c.post("/api/notes", json={"text": f"Note {MARK}", "sources": [src["id"]], "entries": [quote["id"]]}).json()
    photo = c.post("/api/photos?later=true", files={"file": ("p.jpg", make_page(), "image/jpeg")}).json()
    people = {p["name"]: p["id"] for p in c.get("/api/people").json()}
    topic = c.get("/api/topics").json()[0]
    return {"source": src["id"], "quote": quote["id"], "said": said["id"], "note": note["id"], "photo": photo["id"],
            "person": people[f"Auteur {MARK}"], "topic": topic["id"]}


def test_owner_logs_in_as_before_and_old_cookies_still_work(settings):
    with TestClient(create_app(settings)) as c:
        assert c.post("/api/login", json={"password": OWNER_PW}).json()["owner"] is True     # no name: the owner
        me = c.get("/api/me").json()
        assert me["name"] == "admin" and me["owner"] and me["language"] == "fr"
        c.patch("/api/me", json={"name": "Dominique"})
        login(c, "dominique", OWNER_PW)                        # any case, any accents
        assert c.post("/api/login", json={"name": "Dominique", "password": "wrong"}).status_code == 401
        # a phone logged in with an earlier version keeps working: its cookie holds the password's tag
        c.cookies.clear()
        secret = (settings.data_dir / "secret_key").read_text().strip()
        tag = hmac.new(secret.encode(), OWNER_PW.encode(), hashlib.sha256).hexdigest()[:32]
        cookie = TimestampSigner(secret).sign(base64.b64encode(json.dumps({"ok": tag}).encode())).decode()
        c.cookies.set("marginote_session", cookie)
        assert c.get("/api/me").json()["owner"] is True
        assert c.get("/api/sources").status_code == 200
    # every library has its own folder, the owner's too
    assert (settings.data_dir / "users" / "owner" / "marginote.db").exists()
    assert not (settings.data_dir / "marginote.db").exists()


def test_accounts_are_managed_by_the_owner_only(settings):
    with TestClient(create_app(settings)) as c:
        login(c, "", OWNER_PW)
        camille = c.post("/api/accounts", json={"name": "Camille", "password": "lune-de-miel", "language": "en"})
        assert camille.status_code == 201 and camille.json()["language"] == "en" and "password" not in camille.json()
        assert c.post("/api/accounts", json={"name": "camille ", "password": "autre-chose"}).status_code == 422
        assert c.post("/api/accounts", json={"name": "Léa", "password": "court"}).status_code == 422
        stored = (settings.data_dir / "accounts.json").read_text()
        assert "lune-de-miel" not in stored and "scrypt$" in stored
        assert [a["name"] for a in c.get("/api/accounts").json()] == ["admin", "Camille"]
        login(c, "Camille", "lune-de-miel")
        assert c.get("/api/accounts").status_code == 403
        assert c.post("/api/accounts", json={"name": "Intrus", "password": "12345678"}).status_code == 403
        assert c.delete("/api/accounts/owner").status_code == 403


def test_nobody_reaches_anyone_elses_library(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        login(c, "", OWNER_PW)
        owned = fill_owner_library(c)
        cid = c.post("/api/accounts", json={"name": "Camille", "password": "lune-de-miel"}).json()["id"]
        login(c, "Camille", "lune-de-miel")
        # her library starts empty
        for path in ("/api/sources", "/api/entries", "/api/notes", "/api/people", "/api/topics", "/api/photos"):
            assert c.get(path).json() == [], path
        assert c.get("/api/search", params={"q": "zephyrin"}).json() == []
        assert c.get("/api/notes", params={"q": "zephyrin"}).json() == []
        # every call of the API, with the owner's ids put in: nothing of the owner's comes back
        ids = {"source_id": owned["source"], "entry_id": owned["quote"], "note_id": owned["note"],
               "photo_id": owned["photo"], "person_id": owned["person"], "topic_id": owned["topic"]}
        tried = 0
        for route, ops in c.get("/openapi.json").json()["paths"].items():
            if "get" not in ops or not route.startswith("/api/") or route in ("/api/backup/download", "/api/lookup/isbn"):
                continue
            path = route
            for key, value in ids.items():
                path = path.replace("{" + key + "}", str(value))
            if "{" in path:
                continue
            r = c.get(path)
            tried += 1
            assert MARK not in r.content.decode("utf-8", "replace"), path
            assert "zephyrin" not in r.content.decode("utf-8", "replace").lower(), path
        assert tried >= 20
        for path in (f"/api/sources/{owned['source']}", f"/api/entries/{owned['quote']}", f"/api/notes/{owned['note']}",
                     f"/api/photos/{owned['photo']}/image", f"/api/sources/{owned['source']}/cover"):
            assert c.get(path).status_code == 404, path
        # nor can she change or delete it
        assert c.patch(f"/api/entries/{owned['quote']}", json={"text": "x"}).status_code == 404
        assert c.delete(f"/api/notes/{owned['note']}").status_code == 404
        assert c.delete(f"/api/photos/{owned['photo']}").status_code == 404
        # her own things get the same small ids as the owner's, and stay hers
        mine = c.post("/api/sources", json={"title": "Le livre de Camille", "fetch_cover": False}).json()
        assert mine["id"] == owned["source"]
        c.post(f"/api/sources/{mine['id']}/cover", files={"file": ("c.jpg", make_page(), "image/jpeg")})
        cover_url = c.get(f"/api/sources/{mine['id']}").json()["cover_url"]
        assert cover_url.endswith(f"&l={cid}")              # a browser shared by both never mixes the covers
        c.post("/api/entries", json={"source_id": mine["id"], "text": "Une phrase à moi."})
        # her backups and her download hold her library only
        assert c.post("/api/backup").status_code == 200
        status = c.get("/api/backup/status").json()
        assert [x["kind"] for x in status["copies"]] == ["daily"]
        archive = zipfile.ZipFile(io.BytesIO(c.get("/api/backup/download").content))
        db_copy = settings.data_dir / "check.db"
        db_copy.write_bytes(archive.read("marginote.db"))
        titles = [r[0] for r in sqlite3.connect(db_copy).execute("SELECT title FROM sources")]
        assert titles == ["Le livre de Camille"]
        assert not any(MARK in n for n in archive.namelist())
        # and the owner's library is as it was
        login(c, "", OWNER_PW)
        assert c.get(f"/api/sources/{owned['source']}").json()["title"] == f"Livre {MARK}"
        assert [e["text"] for e in c.get(f"/api/sources/{owned['source']}/entries").json()] == [f"Passage {MARK}"]
        assert c.get("/api/search", params={"q": "phrase"}).json() == []
    user_dir = settings.data_dir / "users" / cid
    assert (user_dir / "marginote.db").exists() and list((user_dir / "backups").glob("marginote-*.zip"))
    assert not list((settings.data_dir / "users" / "owner" / "backups").glob("marginote-*.zip"))


def test_passwords_change_and_accounts_go(settings):
    with TestClient(create_app(settings)) as c, TestClient(create_app(settings)) as other:
        login(c, "", OWNER_PW)
        cid = c.post("/api/accounts", json={"name": "Camille", "password": "lune-de-miel"}).json()["id"]
        login(c, "Camille", "lune-de-miel")
        login(other, "Camille", "lune-de-miel")                 # her other device
        bad = {"password": {"current": "pas-le-bon", "new": "soleil-levant"}}
        assert c.patch("/api/me", json=bad).status_code == 403
        assert c.patch("/api/me", json={"password": {"current": "lune-de-miel", "new": "court"}}).status_code == 422
        assert c.patch("/api/me", json={"password": {"current": "lune-de-miel", "new": "soleil-levant"}}).status_code == 200
        assert c.get("/api/me").json()["logged_in"] is True       # this device stays in
        assert other.get("/api/me").json()["logged_in"] is False  # the other one is logged out
        assert other.post("/api/login", json={"name": "Camille", "password": "lune-de-miel"}).status_code == 401
        login(other, "Camille", "soleil-levant")
        # the owner sets a new one for her: she is logged out everywhere
        login(c, "", OWNER_PW)
        assert c.patch(f"/api/accounts/{cid}", json={"password": "nouvelle-lune"}).status_code == 200
        assert other.get("/api/me").json()["logged_in"] is False
        assert c.patch("/api/me", json={"password": {"current": OWNER_PW, "new": "autre-chose"}}).status_code == 422
        # removing her: she cannot log in, her library is set aside on the NAS, not deleted
        assert c.delete(f"/api/accounts/{cid}").status_code == 200
        assert other.post("/api/login", json={"name": "Camille", "password": "nouvelle-lune"}).status_code == 401
        assert not (settings.data_dir / "users" / cid).exists()
        assert [p.name.startswith(cid) for p in (settings.data_dir / "users" / "removed").iterdir()] == [True]
        assert c.delete("/api/accounts/owner").status_code == 422


def test_each_person_reads_the_app_in_their_language(settings):
    with TestClient(create_app(settings)) as c:
        assert "app.fr.js" in c.get("/", headers={"accept-language": "fr-FR,fr;q=0.9"}).text
        c.cookies.clear()
        assert "/static/app.js" in c.get("/", headers={"accept-language": "en-GB"}).text
        c.cookies.set("marginote_lang", "fr")                    # chosen on the login page
        page = c.get("/", headers={"accept-language": "en-GB"}).text
        assert "app.fr.js" in page and '<html lang="fr">' in page
        login(c, "", OWNER_PW)
        c.post("/api/accounts", json={"name": "Camille", "password": "lune-de-miel", "language": "en"})
        login(c, "Camille", "lune-de-miel")
        assert "/static/app.js" in c.get("/").text
        assert c.patch("/api/me", json={"language": "fr"}).json()["language"] == "fr"
        assert "app.fr.js" in c.get("/").text
        assert c.patch("/api/me", json={"language": "de"}).status_code == 422


def test_french_screens_are_made_from_the_english_ones():
    """static/app.fr.js is tools/translate_fr.py applied to static/app.js: every sentence placed, file up to date."""
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "tools"))
    try:
        import translate_fr
    finally:
        sys.path.pop(0)
    static = root / "app" / "marginote" / "static"
    french, missing, _ = translate_fr.translate((static / "app.js").read_text(encoding="utf-8"))
    assert missing == []
    assert french == (static / "app.fr.js").read_text(encoding="utf-8"), "run: python tools/translate_fr.py"


@pytest.fixture(autouse=True)
def _quiet_lookups(monkeypatch):
    from marginote import lookup
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)


def test_the_owners_library_moves_into_its_own_folder_once(settings):
    """A data folder as version 0.6 left it: the owner's library at its top. On start it moves, whole, into
    users/owner/; nothing is lost, logins keep working, and a second start changes nothing."""
    data = settings.data_dir
    with TestClient(create_app(settings)) as c:            # make a library, then put it back where 0.6 kept it
        login(c, "", OWNER_PW)
        src = c.post("/api/sources", json={"title": "Les Essais", "fetch_cover": False}).json()
        c.post(f"/api/sources/{src['id']}/cover", files={"file": ("c.jpg", make_page(), "image/jpeg")})
        photo = c.post("/api/photos", files={"file": ("p.jpg", make_page("12"), "image/jpeg")}).json()
        c.post("/api/entries", json={"source_id": src["id"], "photo_id": photo["id"], "text": "Que sais-je ?"})
        c.post("/api/backup")
    home = data / "users" / "owner"
    for name in ("marginote.db", "photos", "covers", "backups"):
        (home / name).rename(data / name)
    home.rmdir()
    (data / "users").rmdir()
    files_before = sorted(p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file()
                          and p.parts[len(data.parts)] in ("photos", "covers"))
    with TestClient(create_app(settings)) as c:
        login(c, "", OWNER_PW)
        assert [e["text"] for e in c.get(f"/api/sources/{src['id']}/entries").json()] == ["Que sais-je ?"]
        assert c.get(f"/api/photos/{photo['id']}/image").status_code == 200
        assert c.get(f"/api/sources/{src['id']}/cover").status_code == 200
        copies = c.get("/api/backup/status").json()["copies"]
        assert [x["kind"] for x in copies].count("daily") == 1 and any(x["file"].startswith("before-0.7.1-") for x in copies)
    for name in ("marginote.db", "photos", "covers", "backups"):
        assert not (data / name).exists() and (home / name).exists()
    assert sorted("/".join(p.relative_to(home).parts) for p in home.rglob("*") if p.is_file()
                  and p.parts[len(home.parts)] in ("photos", "covers")) == files_before
    with TestClient(create_app(settings)):                  # again: nothing moves, no new copy
        pass
    assert len(list((home / "backups").glob("before-*.zip"))) == 1


def test_the_move_never_mixes_two_libraries(settings):
    data = settings.data_dir
    (data / "users" / "owner" / "photos").mkdir(parents=True)
    (data / "users" / "owner" / "photos" / "a.webp").write_bytes(b"x")
    (data / "photos").mkdir(parents=True)
    (data / "photos" / "b.webp").write_bytes(b"y")
    with pytest.raises(RuntimeError, match="move one of them aside"):
        create_app(settings)
    assert (data / "photos" / "b.webp").exists() and (data / "users" / "owner" / "photos" / "a.webp").exists()
