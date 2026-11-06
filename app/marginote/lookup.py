"""Book details and covers from Open Library, with Google Books as a fallback.

Only an ISBN, or a title and author, leaves the NAS. Turn lookups off with LOOKUPS_ENABLED=false.
"""

import re

import httpx

HEADERS = {"User-Agent": "Marginote/0.1 (self-hosted personal reading notes)"}
TIMEOUT = httpx.Timeout(8.0, connect=5.0)
MIN_COVER_BYTES = 2000  # Open Library sometimes answers with a 1x1 placeholder


def clean_isbn(raw: str) -> str | None:
    """Keep digits (and a final X), check the length and the checksum."""
    isbn = re.sub(r"[^0-9Xx]", "", raw).upper()
    if len(isbn) == 13 and isbn.isdigit():
        total = sum(int(d) * (1 if k % 2 == 0 else 3) for k, d in enumerate(isbn[:12]))
        return isbn if (10 - total % 10) % 10 == int(isbn[12]) else None
    if len(isbn) == 10 and isbn[:9].isdigit() and (isbn[9].isdigit() or isbn[9] == "X"):
        total = sum((10 - k) * int(d) for k, d in enumerate(isbn[:9]))
        check = 10 if isbn[9] == "X" else int(isbn[9])
        return isbn if (total + check) % 11 == 0 else None
    return None


def _year(text: str | None) -> int | None:
    m = re.search(r"(1[4-9]\d\d|20\d\d)", text or "")
    return int(m.group(1)) if m else None


def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)


def lookup_isbn(isbn: str) -> dict | None:
    """Return title, authors, publisher, year, language for an ISBN, or None if nobody knows it."""
    result: dict = {}
    with _client() as client:
        try:
            r = client.get(
                "https://openlibrary.org/api/books",
                params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
            )
            data = r.json().get(f"ISBN:{isbn}") if r.status_code == 200 else None
            if data:
                result = {
                    "title": data.get("title"),
                    "subtitle": data.get("subtitle"),
                    "authors": ", ".join(a.get("name", "") for a in data.get("authors", [])) or None,
                    "publisher": ", ".join(p.get("name", "") for p in data.get("publishers", [])) or None,
                    "year": _year(data.get("publish_date")),
                    "source": "Open Library",
                }
        except (httpx.HTTPError, ValueError):
            pass

        try:
            r = client.get("https://www.googleapis.com/books/v1/volumes", params={"q": f"isbn:{isbn}"})
            items = r.json().get("items") if r.status_code == 200 else None
            if items:
                info = items[0].get("volumeInfo", {})
                google = {
                    "title": info.get("title"),
                    "subtitle": info.get("subtitle"),
                    "authors": ", ".join(info.get("authors", [])) or None,
                    "publisher": info.get("publisher"),
                    "year": _year(info.get("publishedDate")),
                    "language": info.get("language"),
                }
                for key, value in google.items():
                    if value and not result.get(key):
                        result[key] = value
                result.setdefault("source", "Google Books")
        except (httpx.HTTPError, ValueError):
            pass

    if not result.get("title"):
        return None
    result["isbn"] = isbn
    return result


def _get_image(client: httpx.Client, url: str) -> bytes | None:
    try:
        r = client.get(url)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        return None
    return r.content if len(r.content) >= MIN_COVER_BYTES else None


def find_cover(isbn: str | None, title: str | None, authors: str | None) -> bytes | None:
    """Try the ISBN first, then a title + author search. Returns image bytes or None."""
    with _client() as client:
        if isbn:
            img = _get_image(client, f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false")
            if img:
                return img
        if title:
            params = {"title": title, "fields": "cover_i", "limit": 5}
            if authors:
                params["author"] = authors.split(",")[0].strip()
            try:
                r = client.get("https://openlibrary.org/search.json", params=params)
                docs = r.json().get("docs", []) if r.status_code == 200 else []
            except (httpx.HTTPError, ValueError):
                docs = []
            for doc in docs:
                if doc.get("cover_i"):
                    img = _get_image(client, f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg")
                    if img:
                        return img
        query = f"isbn:{isbn}" if isbn else None
        if not query and title:
            query = f'intitle:"{title}"' + (f' inauthor:"{authors.split(",")[0].strip()}"' if authors else "")
        if query:
            try:
                r = client.get("https://www.googleapis.com/books/v1/volumes", params={"q": query})
                items = r.json().get("items", []) if r.status_code == 200 else []
            except (httpx.HTTPError, ValueError):
                items = []
            for item in items[:3]:
                links = item.get("volumeInfo", {}).get("imageLinks", {})
                url = links.get("thumbnail") or links.get("smallThumbnail")
                if url:
                    img = _get_image(client, url.replace("http://", "https://"))
                    if img:
                        return img
    return None
