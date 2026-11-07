import io

from conftest import make_page
from PIL import Image

from marginote import dewarp, lookup, ocr


def cover_png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (400, 600), (47, 72, 88)).save(out, format="PNG")
    return out.getvalue()


def test_health_needs_no_login(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert set(body["ocr_languages"]) == {"fra", "eng"}
    assert body["password_set"] is True
    assert body["straighten_pages"] is dewarp.available()


def test_everything_else_needs_login(client):
    assert client.get("/api/books").status_code == 401
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401
    assert client.get("/api/me").json() == {"logged_in": False}


def test_test_page_and_docs_are_served(client):
    assert "backend test" in client.get("/").text
    assert client.get("/docs").status_code == 200


def test_isbn_checks_and_lookup(logged_in, monkeypatch):
    assert logged_in.get("/api/lookup/isbn/1234567890123").status_code == 422
    monkeypatch.setattr(lookup, "lookup_isbn", lambda isbn: {"title": "Walden", "authors": "Henry David Thoreau",
                                                             "isbn": isbn, "source": "Open Library"})
    r = logged_in.get("/api/lookup/isbn/978-0-14-310624-1")
    assert r.status_code == 200 and r.json()["title"] == "Walden"


def test_book_with_cover_found_online(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda isbn, title, authors: cover_png())
    r = logged_in.post("/api/books", json={"title": "La Science et l’hypothèse", "authors": "Henri Poincaré",
                                           "publisher": "Flammarion", "year": 1902, "language": "fr"})
    assert r.status_code == 201
    book = r.json()
    assert book["cover_pending"] is True  # answered at once; the cover is fetched afterwards
    book = logged_in.get(f"/api/books/{book['id']}").json()
    assert book["has_cover"] is True
    img = logged_in.get(book["cover_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"


def test_bad_isbn_on_book_is_refused(logged_in):
    r = logged_in.post("/api/books", json={"title": "X", "isbn": "123", "fetch_cover": False})
    assert r.status_code == 422


def test_full_capture_flow(logged_in, settings, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/books", json={"title": "La Science et l’hypothèse",
                                              "authors": "Henri Poincaré"}).json()
    assert logged_in.get(f"/api/books/{book['id']}").json()["has_cover"] is False

    # photo of a page -> words, page number
    photo = logged_in.post("/api/photos", files={"file": ("page.jpg", make_page("168"), "image/jpeg")}).json()
    assert photo["detected_page"] == "168"
    words = photo["words"]
    texts = [w["text"] for w in words]
    first = texts.index("On")
    last = next(w["i"] for w in words if w["text"].startswith("maison."))

    # same photo again is not read twice
    again = logged_in.post("/api/photos", files={"file": ("page.jpg", make_page("168"), "image/jpeg")}).json()
    assert again["id"] == photo["id"]

    # preview the selection, then save it without retyping text or page
    preview = logged_in.post(f"/api/photos/{photo['id']}/select", json={"start": last, "end": first}).json()
    assert preview["text"].startswith("On fait la science") and preview["word_start"] == first
    quote = logged_in.post("/api/entries", json={
        "book_id": book["id"], "photo_id": photo["id"], "word_start": first, "word_end": last,
        "note": "Exemple parfait pour une introduction.", "tags": ["#épistémologie", "méthode"],
    })
    assert quote.status_code == 201
    quote = quote.json()
    assert quote["page"] == "168" and quote["text"] == preview["text"]
    assert quote["tags"] == ["méthode", "épistémologie"]
    assert logged_in.get(quote["photo_url"]).status_code == 200
    assert (settings.photos_dir).rglob("*.jpg")

    thought = logged_in.post("/api/entries", json={
        "book_id": book["id"], "kind": "thought", "text": "Comparer avec Duhem et sa mémoire des hypothèses.",
        "page": "158", "tags": ["à creuser"],
    }).json()

    # book page: page order puts p. 158 before p. 168
    entries = logged_in.get(f"/api/books/{book['id']}/entries").json()
    assert [e["id"] for e in entries] == [thought["id"], quote["id"]]
    assert logged_in.get(f"/api/books/{book['id']}/entries", params={"tag": "à creuser"}).json()[0]["kind"] == "thought"

    listed = logged_in.get("/api/books").json()[0]
    assert listed["quote_count"] == 1 and listed["thought_count"] == 1

    tags = {t["name"]: t["count"] for t in logged_in.get("/api/tags").json()}
    assert tags == {"méthode": 1, "épistémologie": 1, "à creuser": 1}

    # search ignores accents and matches word starts and book titles
    assert [h["id"] for h in logged_in.get("/api/search", params={"q": "memoire"}).json()] == [thought["id"]]
    assert len(logged_in.get("/api/search", params={"q": "hypothese"}).json()) == 2
    assert logged_in.get("/api/search", params={"q": "epistemo"}).json()[0]["id"] == quote["id"]

    # edit: new tags and page, reflected in search
    patched = logged_in.patch(f"/api/entries/{quote['id']}", json={"tags": ["maison"], "page": "169"}).json()
    assert patched["tags"] == ["maison"] and patched["page"] == "169"
    assert logged_in.get("/api/search", params={"q": "epistemo"}).json() == []

    # export
    md = logged_in.get(f"/api/books/{book['id']}/export.md")
    assert md.status_code == 200
    assert "> On fait la science" in md.text and "#maison" in md.text and "**Thought (p. 158):**" in md.text

    # delete
    assert logged_in.delete(f"/api/entries/{thought['id']}").status_code == 200
    assert logged_in.get("/api/search", params={"q": "memoire"}).json() == []

    # backup
    name = logged_in.post("/api/backup").json()["file"]
    assert (settings.backups_dir / name).stat().st_size > 0


def test_renaming_a_book_updates_search(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/books", json={"title": "Essais"}).json()
    logged_in.post("/api/entries", json={"book_id": book["id"], "text": "Parce que c’était lui, parce que c’était moi."})
    logged_in.patch(f"/api/books/{book['id']}", json={"title": "Les Essais", "authors": "Montaigne"})
    assert len(logged_in.get("/api/search", params={"q": "montaigne"}).json()) == 1


def test_not_an_image_is_refused(logged_in):
    r = logged_in.post("/api/photos", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_iphone_heic_photo_is_accepted(logged_in):
    from pillow_heif import from_pillow

    img = Image.open(io.BytesIO(make_page("42")))
    out = io.BytesIO()
    from_pillow(img).save(out, quality=90)
    photo = logged_in.post("/api/photos", files={"file": ("IMG_0001.HEIC", out.getvalue(), "image/heic")})
    assert photo.status_code == 200
    assert photo.json()["detected_page"] == "42"


def test_photo_metadata_is_removed_and_rotation_applied(logged_in, settings):
    """A phone photo taken sideways, with camera and GPS tags: stored upright and without any metadata."""
    sideways = Image.open(io.BytesIO(make_page("168"))).rotate(90, expand=True)
    exif = Image.Exif()
    exif[0x0112] = 6                    # orientation: turn 90° clockwise to view
    exif[0x010F] = "PhoneMaker"         # camera make
    exif[0x0110] = "PhoneModel"         # camera model
    exif[0x8825] = {1: "N", 2: (48.0, 51.0, 30.0), 3: "E", 4: (2.0, 20.0, 15.0)}  # GPS position
    out = io.BytesIO()
    sideways.save(out, format="JPEG", exif=exif, quality=92)
    assert Image.open(io.BytesIO(out.getvalue())).getexif().get(0x010F) == "PhoneMaker"

    photo = logged_in.post("/api/photos", files={"file": ("IMG_0002.JPG", out.getvalue(), "image/jpeg")}).json()
    assert photo["height"] > photo["width"]          # upright again
    assert photo["detected_page"] == "168"           # and readable
    stored_path = next(settings.photos_dir.rglob(f"{photo['id']}.jpg"))
    assert len(Image.open(stored_path).getexif()) == 0     # no camera, date or location left
    assert b"PhoneMaker" not in stored_path.read_bytes()


def test_isbn_lookup_merges_both_sources(monkeypatch):
    monkeypatch.setattr(lookup, "_open_library", lambda isbn: {"title": "Walden", "authors": "Henry David Thoreau",
                                                               "publisher": None, "year": 2004})
    monkeypatch.setattr(lookup, "_google_books", lambda isbn: {"title": "Walden (ed.)", "publisher": "Penguin",
                                                               "language": "en"})
    found = lookup.lookup_isbn("9780143106241")
    assert found == {"title": "Walden", "authors": "Henry David Thoreau", "year": 2004, "publisher": "Penguin",
                     "language": "en", "source": "Open Library", "isbn": "9780143106241"}
    monkeypatch.setattr(lookup, "_open_library", lambda isbn: {})
    monkeypatch.setattr(lookup, "_google_books", lambda isbn: {})
    assert lookup.lookup_isbn("9780143106241") is None


def test_changing_the_password_logs_every_device_out(logged_in, settings):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from marginote.main import create_app

    assert logged_in.get("/api/books").status_code == 200
    with TestClient(create_app(replace(settings, password="a new password"))) as restarted:
        restarted.cookies = logged_in.cookies          # the same browser, after the password change
        assert restarted.get("/api/books").status_code == 401
        assert restarted.get("/api/me").json() == {"logged_in": False}


def test_photos_are_cached_and_missing_files_give_404(logged_in, settings, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    photo = logged_in.post("/api/photos", files={"file": ("p.jpg", make_page("9"), "image/jpeg")}).json()
    r = logged_in.get(photo["image_url"])
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    next(settings.photos_dir.rglob(f"{photo['id']}.jpg")).unlink()
    assert logged_in.get(photo["image_url"]).status_code == 404
    book = logged_in.post("/api/books", json={"title": "Sans couverture"}).json()
    assert logged_in.get(f"/api/books/{book['id']}/cover").status_code == 404


def _photo_path(settings, photo_id):
    import sqlite3
    conn = sqlite3.connect(settings.db_path)
    try:
        row = conn.execute("SELECT path FROM photos WHERE id = ?", (photo_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_photos_wait_in_the_inbox_then_move_to_their_book(logged_in, settings, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/books", json={"title": "La Science et l’hypothèse : essai"}).json()
    photo = logged_in.post("/api/photos", files={"file": ("p.jpg", make_page("168"), "image/jpeg")}).json()
    assert _photo_path(settings, photo["id"]) == f"inbox/{photo['id']}.jpg"

    logged_in.post("/api/entries", json={"book_id": book["id"], "photo_id": photo["id"], "text": "On fait la science"})
    filed = _photo_path(settings, photo["id"])
    folder = f"La Science et l’hypothèse essai ({book['id']})"     # ':' removed, Windows-safe
    assert filed == f"{folder}/p168 - {photo['id'][:8]}.jpg"
    assert (settings.photos_dir / filed).is_file()
    assert not (settings.photos_dir / "inbox" / f"{photo['id']}.jpg").exists()
    assert logged_in.get(photo["image_url"]).status_code == 200

    # renaming the book renames its folder
    logged_in.patch(f"/api/books/{book['id']}", json={"title": "La Science et l’hypothèse"})
    renamed = _photo_path(settings, photo["id"])
    assert renamed.startswith(f"La Science et l’hypothèse ({book['id']})/")
    assert (settings.photos_dir / renamed).is_file() and not (settings.photos_dir / folder).exists()
    assert logged_in.get(photo["image_url"]).status_code == 200


def test_unused_photos_are_deleted_after_a_day_used_ones_are_kept(logged_in, settings, monkeypatch):
    import sqlite3
    from fastapi.testclient import TestClient
    from marginote.main import create_app

    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/books", json={"title": "Essais"}).json()
    used = logged_in.post("/api/photos", files={"file": ("a.jpg", make_page("12"), "image/jpeg")}).json()
    unused = logged_in.post("/api/photos", files={"file": ("b.jpg", make_page("13"), "image/jpeg")}).json()
    fresh = logged_in.post("/api/photos", files={"file": ("c.jpg", make_page("14"), "image/jpeg")}).json()
    logged_in.post("/api/entries", json={"book_id": book["id"], "photo_id": used["id"], "text": "Que sais-je ?"})

    conn = sqlite3.connect(settings.db_path)        # make two photos look two days old
    conn.execute("UPDATE photos SET created_at = '2020-01-01T00:00:00Z' WHERE id IN (?, ?)", (used["id"], unused["id"]))
    conn.commit(); conn.close()
    unused_file = settings.photos_dir / _photo_path(settings, unused["id"])

    with TestClient(create_app(settings)):          # cleanup runs at start, then every hour
        pass
    assert _photo_path(settings, unused["id"]) is None and not unused_file.exists()
    assert _photo_path(settings, used["id"]) is not None       # used by a quote: kept
    assert _photo_path(settings, fresh["id"]) is not None      # unused but recent: kept for now


def test_photos_from_the_first_version_are_filed_on_start(logged_in, settings, monkeypatch):
    import sqlite3
    from fastapi.testclient import TestClient
    from marginote.main import create_app

    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/books", json={"title": "Walden"}).json()
    photo = logged_in.post("/api/photos", files={"file": ("w.jpg", make_page("90"), "image/jpeg")}).json()
    logged_in.post("/api/entries", json={"book_id": book["id"], "photo_id": photo["id"], "text": "I went to the woods"})
    # put it back where version 0.1 stored photos: photos/<year>/<month>/<id>.jpg
    filed = settings.photos_dir / _photo_path(settings, photo["id"])
    legacy = settings.photos_dir / "2026" / "11" / f"{photo['id']}.jpg"
    legacy.parent.mkdir(parents=True); filed.replace(legacy)
    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE photos SET path = ? WHERE id = ?", (f"2026/11/{photo['id']}.jpg", photo["id"]))
    conn.commit(); conn.close()

    with TestClient(create_app(settings)):
        pass
    assert _photo_path(settings, photo["id"]) == f"Walden ({book['id']})/p90 - {photo['id'][:8]}.jpg"
    assert not (settings.photos_dir / "2026").exists()        # empty old folders tidied away


def test_curved_page_is_stored_straightened_and_words_match_it(logged_in, settings):
    import dataclasses

    import pytest
    from conftest import as_jpeg, bend_toward_spine, make_full_page, word_recall
    from fastapi.testclient import TestClient

    from marginote.main import create_app

    if not dewarp.available():
        pytest.skip("Leptonica library not found")
    page, written = make_full_page("6")
    upload = as_jpeg(bend_toward_spine(page))
    photo = logged_in.post("/api/photos", files={"file": ("curved.jpg", upload, "image/jpeg")}).json()
    assert photo["detected_page"] == "6"
    assert word_recall([w["text"] for w in photo["words"]], written) > 0.85
    stored = logged_in.get(photo["image_url"]).content
    assert Image.open(io.BytesIO(stored)).size == (photo["width"], photo["height"])
    assert stored != ocr.normalize_photo(upload)[1]          # the straightened copy was kept

    # with STRAIGHTEN_PAGES=false the photo is kept exactly as sent (shrunk, without metadata)
    plain_settings = dataclasses.replace(settings, straighten_pages=False)
    with TestClient(create_app(plain_settings)) as plain:
        plain.post("/api/login", json={"password": "correct horse"})
        other = upload[:-2] + b"\x00" + upload[-2:]          # a different file, so not seen as a duplicate
        photo = plain.post("/api/photos", files={"file": ("curved2.jpg", other, "image/jpeg")}).json()
        assert plain.get(photo["image_url"]).content == ocr.normalize_photo(other)[1]
        assert plain.get("/api/health").json()["straighten_pages"] is False
