import io
import re

from conftest import make_page
from fastapi.testclient import TestClient
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
    assert client.get("/api/sources").status_code == 401
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401
    assert client.get("/api/me").json() == {"logged_in": False}


def test_app_page_files_and_docs_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "<title>Marginote</title>" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]   # nothing loaded from outside
    assert "{{version}}" not in page.text
    for path in re.findall(r'(?:href|src)="(/static/[^"?]+)', page.text):
        assert client.get(path).status_code == 200, path                      # every file the page names exists
    assert client.get("/static/app.js").headers["content-type"].startswith(("text/javascript", "application/javascript"))
    assert client.get("/static/fonts/cmu-serif-regular.woff2").status_code == 200
    assert client.get("/static/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")
    assert client.get("/docs").status_code == 200


def test_isbn_checks_and_lookup(logged_in, monkeypatch):
    assert logged_in.get("/api/lookup/isbn/1234567890123").status_code == 422
    monkeypatch.setattr(lookup, "lookup_isbn", lambda isbn: {"title": "Walden", "authors": "Henry David Thoreau",
                                                             "isbn": isbn, "source": "Open Library"})
    r = logged_in.get("/api/lookup/isbn/978-0-14-310624-1")
    assert r.status_code == 200 and r.json()["title"] == "Walden"


def test_book_with_cover_found_online(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda isbn, title, authors: cover_png())
    r = logged_in.post("/api/sources", json={"title": "La Science et l’hypothèse", "people": {"author": ["Henri Poincaré"]},
                                           "publisher": "Flammarion", "year": 1902, "language": "fr"})
    assert r.status_code == 201
    book = r.json()
    assert book["cover_pending"] is True  # answered at once; the cover is fetched afterwards
    book = logged_in.get(f"/api/sources/{book['id']}").json()
    assert book["has_cover"] is True
    img = logged_in.get(book["cover_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"


def test_bad_isbn_on_book_is_refused(logged_in):
    r = logged_in.post("/api/sources", json={"title": "X", "isbn": "123", "fetch_cover": False})
    assert r.status_code == 422


def test_full_capture_flow(logged_in, settings, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "La Science et l’hypothèse",
                                              "people": {"author": ["Henri Poincaré"]}}).json()
    assert logged_in.get(f"/api/sources/{book['id']}").json()["has_cover"] is False

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
        "source_id": book["id"], "photo_id": photo["id"], "word_start": first, "word_end": last,
        "note": "Exemple parfait pour une introduction.", "topics": ["#épistémologie", "méthode"],
    })
    assert quote.status_code == 201
    quote = quote.json()
    assert quote["page"] == "168" and quote["text"] == preview["text"]
    assert [t["name"] for t in quote["topics"]] == ["méthode", "épistémologie"]
    assert logged_in.get(quote["photo_url"]).status_code == 200
    assert next(settings.photos_dir.rglob("*.webp"))
    assert logged_in.get(quote["photo_url"]).headers["content-type"] == "image/webp"

    thought = logged_in.post("/api/entries", json={
        "source_id": book["id"], "kind": "thought", "text": "Comparer avec Duhem et sa mémoire des hypothèses.",
        "page": "158", "topics": ["à creuser"],
    }).json()

    # book page: page order puts p. 158 before p. 168
    entries = logged_in.get(f"/api/sources/{book['id']}/entries").json()
    assert [e["id"] for e in entries] == [thought["id"], quote["id"]]
    creuser = next(t for t in logged_in.get("/api/topics").json() if t["name"] == "à creuser")
    assert logged_in.get("/api/entries", params={"topic_id": creuser["id"]}).json()[0]["kind"] == "comment"

    listed = logged_in.get("/api/sources").json()[0]
    assert listed["quote_count"] == 1 and listed["comment_count"] == 1

    topics = {t["name"]: t["entries"] for t in logged_in.get("/api/topics").json()}
    assert topics == {"méthode": 1, "épistémologie": 1, "à creuser": 1}

    # search ignores accents and matches word starts and book titles
    assert [h["id"] for h in logged_in.get("/api/search", params={"q": "memoire"}).json()] == [thought["id"]]
    assert len(logged_in.get("/api/search", params={"q": "hypothese"}).json()) == 2
    assert logged_in.get("/api/search", params={"q": "epistemo"}).json()[0]["id"] == quote["id"]

    # edit: new tags and page, reflected in search
    patched = logged_in.patch(f"/api/entries/{quote['id']}", json={"topics": ["maison"], "page": "169"}).json()
    assert [t["name"] for t in patched["topics"]] == ["maison"] and patched["page"] == "169"
    assert logged_in.get("/api/search", params={"q": "epistemo"}).json() == []

    # export
    md = logged_in.get(f"/api/sources/{book['id']}/export.md")
    assert md.status_code == 200
    assert "> On fait la science" in md.text and "#maison" in md.text and "**Comment (p. 158):**" in md.text
    assert "*Henri Poincaré*" in md.text

    # delete
    assert logged_in.delete(f"/api/entries/{thought['id']}").status_code == 200
    assert logged_in.get("/api/search", params={"q": "memoire"}).json() == []

    # backup
    name = logged_in.post("/api/backup").json()["file"]
    assert name.endswith(".zip") and (settings.backups_dir / name).stat().st_size > 0


def test_renaming_a_book_updates_search(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "Essais"}).json()
    logged_in.post("/api/entries", json={"source_id": book["id"], "text": "Parce que c’était lui, parce que c’était moi."})
    logged_in.patch(f"/api/sources/{book['id']}", json={"title": "Les Essais", "people": {"author": ["Montaigne"]}})
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
    stored_path = next(settings.photos_dir.rglob(f"{photo['id']}.webp"))
    assert len(Image.open(stored_path).getexif()) == 0     # no camera, date or location left
    assert b"PhoneMaker" not in stored_path.read_bytes()


def test_isbn_lookup_merges_both_sources(monkeypatch):
    monkeypatch.setattr(lookup, "_bnf", lambda isbn: {"_note": "not known"})
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

    assert logged_in.get("/api/sources").status_code == 200
    with TestClient(create_app(replace(settings, password="a new password"))) as restarted:
        restarted.cookies = logged_in.cookies          # the same browser, after the password change
        assert restarted.get("/api/sources").status_code == 401
        assert restarted.get("/api/me").json() == {"logged_in": False}


def test_photos_are_cached_and_missing_files_give_404(logged_in, settings, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    photo = logged_in.post("/api/photos", files={"file": ("p.jpg", make_page("9"), "image/jpeg")}).json()
    r = logged_in.get(photo["image_url"])
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    next(settings.photos_dir.rglob(f"{photo['id']}.webp")).unlink()
    assert logged_in.get(photo["image_url"]).status_code == 404
    book = logged_in.post("/api/sources", json={"title": "Sans couverture"}).json()
    assert logged_in.get(f"/api/sources/{book['id']}/cover").status_code == 404


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
    book = logged_in.post("/api/sources", json={"title": "La Science et l’hypothèse : essai"}).json()
    photo = logged_in.post("/api/photos", files={"file": ("p.jpg", make_page("168"), "image/jpeg")}).json()
    assert _photo_path(settings, photo["id"]) == f"inbox/{photo['id']}.webp"

    logged_in.post("/api/entries", json={"source_id": book["id"], "photo_id": photo["id"], "text": "On fait la science"})
    filed = _photo_path(settings, photo["id"])
    folder = f"La Science et l’hypothèse essai ({book['id']})"     # ':' removed, Windows-safe
    assert filed == f"{folder}/p168 - {photo['id'][:8]}.webp"
    assert (settings.photos_dir / filed).is_file()
    assert not (settings.photos_dir / "inbox" / f"{photo['id']}.webp").exists()
    assert logged_in.get(photo["image_url"]).status_code == 200

    # renaming the book renames its folder
    logged_in.patch(f"/api/sources/{book['id']}", json={"title": "La Science et l’hypothèse"})
    renamed = _photo_path(settings, photo["id"])
    assert renamed.startswith(f"La Science et l’hypothèse ({book['id']})/")
    assert (settings.photos_dir / renamed).is_file() and not (settings.photos_dir / folder).exists()
    assert logged_in.get(photo["image_url"]).status_code == 200


def test_unused_photos_are_deleted_after_a_day_used_ones_are_kept(logged_in, settings, monkeypatch):
    import sqlite3
    from fastapi.testclient import TestClient
    from marginote.main import create_app

    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "Essais"}).json()
    used = logged_in.post("/api/photos", files={"file": ("a.jpg", make_page("12"), "image/jpeg")}).json()
    unused = logged_in.post("/api/photos", files={"file": ("b.jpg", make_page("13"), "image/jpeg")}).json()
    fresh = logged_in.post("/api/photos", files={"file": ("c.jpg", make_page("14"), "image/jpeg")}).json()
    logged_in.post("/api/entries", json={"source_id": book["id"], "photo_id": used["id"], "text": "Que sais-je ?"})

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
    book = logged_in.post("/api/sources", json={"title": "Walden"}).json()
    photo = logged_in.post("/api/photos", files={"file": ("w.jpg", make_page("90"), "image/jpeg")}).json()
    logged_in.post("/api/entries", json={"source_id": book["id"], "photo_id": photo["id"], "text": "I went to the woods"})
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
    assert stored != ocr.to_stored(ocr.normalize_photo(upload))          # the straightened copy was kept

    # with STRAIGHTEN_PAGES=false the photo is kept exactly as sent (shrunk, without metadata)
    plain_settings = dataclasses.replace(settings, straighten_pages=False)
    with TestClient(create_app(plain_settings)) as plain:
        plain.post("/api/login", json={"password": "correct horse"})
        other = upload[:-2] + b"\x00" + upload[-2:]          # a different file, so not seen as a duplicate
        photo = plain.post("/api/photos", files={"file": ("curved2.jpg", other, "image/jpeg")}).json()
        assert plain.get(photo["image_url"]).content == ocr.to_stored(ocr.normalize_photo(other))
        assert plain.get("/api/health").json()["straighten_pages"] is False


def test_search_marks_matches_without_clashing_with_brackets(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "Essai", "fetch_cover": False}).json()
    logged_in.post("/api/entries", json={"source_id": book["id"], "text": "Une [comparaison] devient une image."})
    hit = logged_in.get("/api/search", params={"q": "image"}).json()[0]
    assert "\u0002image\u0003" in hit["snippet"] and "[comparaison]" in hit["snippet"]


def test_many_requests_at_once_all_succeed(logged_in, monkeypatch):
    """The database connection of a request may be closed by another worker thread."""
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "Pensées", "fetch_cover": False}).json()
    def add(n):
        return logged_in.post("/api/entries", json={"source_id": book["id"], "text": f"Pensée {n}"}).status_code
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(add, range(40)))
    assert codes == [201] * 40
    assert len(logged_in.get(f"/api/sources/{book['id']}/entries").json()) == 40


def test_sources_have_a_kind_of_work(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "Walden", "field": "Nature writing"}).json()
    assert book["field"] == "Nature writing" and book["kind"] == "book"
    assert logged_in.patch(f"/api/sources/{book['id']}", json={"field": "Philosophy"}).json()["field"] == "Philosophy"
    assert logged_in.patch(f"/api/sources/{book['id']}", json={"field": ""}).json()["field"] is None


def test_comments_are_called_comments(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "Essais", "fetch_cover": False}).json()
    c = logged_in.post("/api/entries", json={"source_id": book["id"], "kind": "comment", "text": "À relire.", "page": "12"}).json()
    q = logged_in.post("/api/entries", json={"source_id": book["id"], "text": "Que philosopher, c'est apprendre à mourir."}).json()
    assert c["kind"] == "comment" and q["kind"] == "quote"
    assert [e["id"] for e in logged_in.get("/api/entries", params={"kind": "comment"}).json()] == [c["id"]]
    assert logged_in.get(f"/api/sources/{book['id']}").json()["comment_count"] == 1
    assert logged_in.patch(f"/api/entries/{q['id']}", json={"kind": "comment"}).json()["kind"] == "comment"
    assert logged_in.patch(f"/api/entries/{q['id']}", json={"kind": None, "note": "x"}).json()["kind"] == "comment"
    assert "**Comment (p. 12):** À relire." in logged_in.get(f"/api/sources/{book['id']}/export.md").text


def test_several_entries_deleted_at_once_and_book_kept(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "Pensées", "fetch_cover": False}).json()
    ids = [logged_in.post("/api/entries", json={"source_id": book["id"], "text": f"Pensée {n}", "topics": [f"t{n}"]}).json()["id"]
           for n in range(3)]
    r = logged_in.post("/api/entries/delete", json={"ids": ids[:2] + [999999]})
    assert r.status_code == 200 and r.json()["deleted"] == ids[:2]
    assert [e["id"] for e in logged_in.get(f"/api/sources/{book['id']}/entries").json()] == [ids[2]]
    assert [t["name"] for t in logged_in.get("/api/topics").json()] == ["t2"]       # topics left unused are removed
    assert logged_in.get("/api/search", params={"q": "Pensée"}).json()[0]["id"] == ids[2]
    assert logged_in.get(f"/api/sources/{book['id']}").status_code == 200
    assert logged_in.post("/api/entries/delete", json={"ids": []}).status_code == 422


# ---------- ISBN from a photo of the back cover ----------

def back_cover(isbn=None, printed=None) -> bytes:
    import zxingcpp
    from conftest import _font
    from PIL import ImageDraw, ImageOps

    page = Image.new("RGB", (1200, 1700), (236, 230, 220))
    draw = ImageDraw.Draw(page)
    draw.text((100, 200), "Un roman sur la lecture lente et les marges.", font=_font(40), fill=(40, 40, 40))
    if isbn:
        code = zxingcpp.create_barcode(isbn, zxingcpp.BarcodeFormat.EAN13).to_image(scale=4)
        bars = Image.frombuffer("L", (code.shape[1], code.shape[0]), bytes(code), "raw", "L", 0, 1)
        page.paste(ImageOps.expand(bars, 24, fill=255).convert("RGB"), (640, 1250))
    if printed:
        draw.text((100, 1350), printed, font=_font(42), fill=(20, 20, 20))
    out = io.BytesIO()
    page.save(out, format="JPEG", quality=90)
    return out.getvalue()


def test_isbn_read_from_the_barcode_or_the_printed_number(logged_in):
    r = logged_in.post("/api/lookup/isbn-photo", files={"file": ("back.jpg", back_cover(isbn="9782070360024"), "image/jpeg")})
    assert r.status_code == 200 and r.json() == {"isbn": "9782070360024", "found_by": "barcode"}
    r = logged_in.post("/api/lookup/isbn-photo", files={"file": ("back.jpg", back_cover(printed="ISBN 2-07-036002-4"), "image/jpeg")})
    assert r.status_code == 200 and r.json() == {"isbn": "9782070360024", "found_by": "text"}
    r = logged_in.post("/api/lookup/isbn-photo", files={"file": ("back.jpg", back_cover(), "image/jpeg")})
    assert r.status_code == 404
    assert logged_in.get("/api/health").json()["barcode_reader"] is True


def test_lookup_says_when_the_book_services_cannot_be_reached(logged_in, monkeypatch):
    def down(isbn):
        raise lookup.LookupUnavailable("all down")
    monkeypatch.setattr(lookup, "lookup_isbn", down)
    r = logged_in.get("/api/lookup/isbn/9782070360024")
    assert r.status_code == 503 and "could not be reached" in r.json()["detail"]


# ---------- inbox: photos to sort later ----------

from marginote.main import create_app  # noqa: E402

def wait_until_read(client, photo_id, seconds=90):
    import time
    for _ in range(seconds * 4):
        photo = client.get(f"/api/photos/{photo_id}").json()
        if photo["status"] != "reading":
            return photo
        time.sleep(0.25)
    raise AssertionError("photo still being read")


def test_inbox_photos_are_read_in_the_background_and_kept_until_sorted(logged_in, settings, monkeypatch):
    import sqlite3

    from marginote import routes_photos
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "La Science et l’hypothèse", "fetch_cover": False}).json()

    with routes_photos.OCR_SLOT:   # the reader waits: the photo stays "reading"
        sent = logged_in.post("/api/photos", params={"later": "true", "source_id": book["id"]},
                              files={"file": ("p.jpg", make_page("168"), "image/jpeg")}).json()
        assert sent["status"] == "reading" and sent["queued"] and sent["words"] == []
        r = logged_in.post("/api/entries", json={"source_id": book["id"], "photo_id": sent["id"], "text": "x"})
        assert r.status_code == 409                       # cannot be used before it is read
    photo = wait_until_read(logged_in, sent["id"])
    assert photo["status"] == "ready" and photo["detected_page"] == "168" and len(photo["words"]) > 40

    inbox = logged_in.get("/api/photos").json()
    assert [(p["id"], p["source_title"], p["entry_count"]) for p in inbox] == [(sent["id"], book["title"], 0)]
    thumb = logged_in.get(inbox[0]["thumb_url"])
    assert thumb.headers["content-type"] == "image/webp" and Image.open(io.BytesIO(thumb.content)).width <= 320

    # a day later it is still there: the inbox is never cleaned up
    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE photos SET created_at = '2020-01-01T00:00:00Z'")
    conn.commit(); conn.close()
    with TestClient(create_app(settings)):
        pass
    assert logged_in.get(f"/api/photos/{sent['id']}").status_code == 200

    # sorting: a quote from it, then out of the inbox; it stays because a quote uses it
    first = next(w["i"] for w in photo["words"] if w["text"] == "On")
    q = logged_in.post("/api/entries", json={"source_id": book["id"], "photo_id": sent["id"], "word_start": first, "word_end": first + 4})
    assert q.status_code == 201
    assert logged_in.get("/api/photos").json()[0]["entry_count"] == 1
    assert logged_in.delete(f"/api/photos/{sent['id']}").status_code == 409
    assert logged_in.patch(f"/api/photos/{sent['id']}", json={"queued": False}).json()["queued"] is False
    assert logged_in.get("/api/photos").json() == []

    # a photo nobody needs is deleted, file included
    other = logged_in.post("/api/photos", params={"later": "true"}, files={"file": ("o.jpg", make_page("9"), "image/jpeg")}).json()
    wait_until_read(logged_in, other["id"])
    assert logged_in.delete(f"/api/photos/{other['id']}").status_code == 200
    assert not list(settings.photos_dir.rglob(f"{other['id']}*"))


def test_photos_left_unread_by_a_restart_are_read_on_start(logged_in, settings):
    import sqlite3

    from marginote import routes_photos
    with routes_photos.OCR_SLOT:
        sent = logged_in.post("/api/photos", params={"later": "true"}, files={"file": ("p.jpg", make_page("27"), "image/jpeg")}).json()
        # simulate a restart: a new app finds the photo still "reading" and queues it again
        conn = sqlite3.connect(settings.db_path)
        assert conn.execute("SELECT status FROM photos WHERE id = ?", (sent["id"],)).fetchone()[0] == "reading"
        conn.close()
        restarted = TestClient(create_app(settings))
        restarted.__enter__()
    try:
        restarted.post("/api/login", json={"password": "correct horse"})
        assert wait_until_read(restarted, sent["id"])["detected_page"] == "27"
    finally:
        restarted.__exit__(None, None, None)


# ---------- backup status and download ----------

def test_backup_status_and_everything_as_a_zip(logged_in, settings, monkeypatch):
    import sqlite3
    import zipfile

    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/sources", json={"title": "Walden", "fetch_cover": False}).json()
    logged_in.post(f"/api/sources/{book['id']}/cover", files={"file": ("c.png", cover_png(), "image/png")})
    photo = logged_in.post("/api/photos", files={"file": ("p.jpg", make_page("90"), "image/jpeg")}).json()
    logged_in.post("/api/entries", json={"source_id": book["id"], "photo_id": photo["id"], "text": "I went to the woods"})

    assert logged_in.get("/api/backup/status").json()["copies"] == []
    logged_in.post("/api/backup")
    status = logged_in.get("/api/backup/status").json()
    assert len(status["copies"]) == 1 and status["copies"][0]["bytes"] > 0 and status["kept"] == 14
    assert status["copies"][0]["file"].endswith(".zip") and status["copies"][0]["kind"] == "daily"
    assert status["photos"]["count"] == 1 and status["covers"]["count"] == 1 and status["database_bytes"] > 0
    assert status["next"] > status["copies"][0]["written_at"][:10]

    r = logged_in.get("/api/backup/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert names[0] == "marginote.db" and any(n.startswith("photos/Walden") for n in names) and "covers/1.webp" in names
    restored = settings.data_dir / "restored.db"
    restored.write_bytes(z.read("marginote.db"))
    assert sqlite3.connect(restored).execute("SELECT title FROM sources").fetchall() == [("Walden",)]
    assert not list(settings.data_dir.glob(".download-*"))     # the temporary copy is gone
