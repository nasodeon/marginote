import io

from conftest import make_page
from PIL import Image

from marginote import lookup


def cover_png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (400, 600), (47, 72, 88)).save(out, format="PNG")
    return out.getvalue()


def test_health_needs_no_login(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert set(body["ocr_languages"]) == {"fra", "eng"}
    assert body["password_set"] is True


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
    assert book["cover_found"] is True and book["cover_url"]
    img = logged_in.get(book["cover_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"


def test_bad_isbn_on_book_is_refused(logged_in):
    r = logged_in.post("/api/books", json={"title": "X", "isbn": "123", "fetch_cover": False})
    assert r.status_code == 422


def test_full_capture_flow(logged_in, settings, monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)
    book = logged_in.post("/api/books", json={"title": "La Science et l’hypothèse",
                                              "authors": "Henri Poincaré"}).json()
    assert book["cover_found"] is False

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
