"""Cover search: sources tried in order, placeholders rejected. No network: every answer is simulated."""
import io

import httpx
from PIL import Image

from marginote import lookup


def jpeg(w, h):
    out = io.BytesIO()
    Image.new("RGB", (w, h), (90, 60, 40)).save(out, format="JPEG")
    return out.getvalue()


def fake_internet(monkeypatch, routes):
    """routes: function(request) -> httpx.Response. Records every address asked."""
    asked = []

    def handler(request):
        asked.append(f"{request.url.host}{request.url.path}")
        return routes(request)

    monkeypatch.setattr(lookup, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    return asked


def test_isbn10_and_cover_shape():
    assert lookup.isbn10("9782070360024") == "2070360024"
    assert lookup.isbn10("9791032305096") is None          # 979 ISBNs have no 10-digit form
    assert lookup.plausible_cover(jpeg(300, 450))
    assert not lookup.plausible_cover(jpeg(1, 1)) and not lookup.plausible_cover(jpeg(600, 120))


def test_cover_found_at_amazon_when_open_library_and_google_have_none(monkeypatch):
    cover = jpeg(300, 460)

    def routes(request):
        host = request.url.host
        if host == "covers.openlibrary.org":
            return httpx.Response(404)
        if host == "www.googleapis.com":
            return httpx.Response(200, json={"items": [{"volumeInfo": {"title": "x"}}]})   # known, but no image
        if host == "images-na.ssl-images-amazon.com":
            return httpx.Response(200, content=cover, headers={"content-type": "image/jpeg"})
        return httpx.Response(500)

    asked = fake_internet(monkeypatch, routes)
    assert lookup.find_cover("9782070360024", "L'Étranger", "Albert Camus") == cover
    assert asked[-1].endswith("/images/P/2070360024.01.LZZZZZZZ.jpg")


def test_placeholder_images_are_skipped_and_title_search_is_used(monkeypatch, caplog):
    tiny = jpeg(1, 1)
    real = jpeg(320, 480)

    def routes(request):
        host, path = request.url.host, request.url.path
        if host == "covers.openlibrary.org" and "/b/id/" in path:
            return httpx.Response(200, content=real, headers={"content-type": "image/jpeg"})
        if host == "openlibrary.org" and path == "/search.json":
            assert request.url.params["title"] == "La Science et l'hypothèse"          # subtitle and curly quote removed
            return httpx.Response(200, json={"docs": [{"cover_i": 42}]})
        if host == "www.googleapis.com":
            return httpx.Response(429)
        return httpx.Response(200, content=tiny, headers={"content-type": "image/gif"})  # 1x1 "no cover" answers

    fake_internet(monkeypatch, routes)
    assert lookup.find_cover("9782081205232", "La Science et l’hypothèse : essai", "Henri Poincaré") == real


def test_nothing_found_is_logged_without_the_book(monkeypatch, caplog):
    fake_internet(monkeypatch, lambda request: httpx.Response(404))
    with caplog.at_level("INFO", logger="marginote"):
        assert lookup.find_cover("9782070360024", "L'Étranger", "Albert Camus") is None
    message = caplog.records[-1].getMessage()
    assert message.startswith("No cover found. Tried: open library isbn: 404; google isbn: 404")
    assert "Camus" not in message and "2070360024" not in message
