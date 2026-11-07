"""Book details and covers from Open Library and Google Books (covers also from Amazon's image server).

Only an ISBN, or a title and author, leaves the server. Turn lookups off with LOOKUPS_ENABLED=false.
"""

import io
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import httpx
from PIL import Image

log = logging.getLogger("marginote")

HEADERS = {"User-Agent": "Marginote/0.1 (self-hosted personal reading notes)"}
TIMEOUT = httpx.Timeout(8.0, connect=5.0)
MIN_COVER_BYTES = 2000  # Open Library sometimes answers with a 1x1 placeholder
MAX_COVER_BYTES = 10 * 1024 * 1024


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


def _open_library(isbn: str) -> dict:
    try:
        with _client() as client:
            r = client.get(
                "https://openlibrary.org/api/books",
                params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
            )
            data = r.json().get(f"ISBN:{isbn}") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return {}
    if not data:
        return {}
    return {
        "title": data.get("title"),
        "subtitle": data.get("subtitle"),
        "authors": ", ".join(a.get("name", "") for a in data.get("authors", [])) or None,
        "publisher": ", ".join(p.get("name", "") for p in data.get("publishers", [])) or None,
        "year": _year(data.get("publish_date")),
    }


def _google_books(isbn: str) -> dict:
    try:
        with _client() as client:
            r = client.get("https://www.googleapis.com/books/v1/volumes", params={"q": f"isbn:{isbn}"})
            items = r.json().get("items") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return {}
    if not items:
        return {}
    info = items[0].get("volumeInfo", {})
    return {
        "title": info.get("title"),
        "subtitle": info.get("subtitle"),
        "authors": ", ".join(info.get("authors", [])) or None,
        "publisher": info.get("publisher"),
        "year": _year(info.get("publishedDate")),
        "language": info.get("language"),
    }


def lookup_isbn(isbn: str) -> dict | None:
    """Return title, authors, publisher, year, language for an ISBN, or None if nobody knows it.

    Both sources are asked at the same time, so the wait is the slower of the two, not their sum.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        ol_future = pool.submit(_open_library, isbn)
        google_future = pool.submit(_google_books, isbn)
        ol, google = ol_future.result(), google_future.result()
    result = {k: v for k, v in ol.items() if v}
    for key, value in google.items():
        if value and not result.get(key):
            result[key] = value
    if not result.get("title"):
        return None
    result["source"] = "Open Library" if ol.get("title") else "Google Books"
    result["isbn"] = isbn
    return result


def isbn10(isbn: str | None) -> str | None:
    """The 10-digit form of an ISBN (only books whose ISBN-13 starts with 978 have one)."""
    if not isbn:
        return None
    if len(isbn) == 10:
        return isbn
    if len(isbn) != 13 or not isbn.startswith("978"):
        return None
    core = isbn[3:12]
    check = (11 - sum((10 - k) * int(d) for k, d in enumerate(core)) % 11) % 11
    return core + ("X" if check == 10 else str(check))


def plausible_cover(data: bytes) -> bool:
    """A real cover: an image at least 80 x 100 px, taller than wide or nearly square.

    Rejects the 1x1 or blank placeholders some services send instead of a "not found".
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
    except Exception:
        return False
    return width >= 80 and height >= 100 and 0.4 <= width / height <= 1.15


def _get_image(client: httpx.Client, url: str) -> tuple[bytes | None, str]:
    """Download an image. Returns (image or None, what happened, for the log)."""
    try:
        with client.stream("GET", url) as r:
            if r.status_code != 200:
                return None, str(r.status_code)
            if not r.headers.get("content-type", "").startswith("image/"):
                return None, "not an image"
            chunks, size = [], 0
            for chunk in r.iter_bytes():
                size += len(chunk)
                if size > MAX_COVER_BYTES:
                    return None, "too large"
                chunks.append(chunk)
    except httpx.HTTPError as err:
        return None, type(err).__name__
    content = b"".join(chunks)
    if len(content) < MIN_COVER_BYTES or not plausible_cover(content):
        return None, "placeholder"
    return content, "found"


def _plain_title(title: str) -> str:
    """Title without its subtitle and with straight apostrophes, for searching."""
    title = unicodedata.normalize("NFC", title).replace("’", "'").replace("‘", "'")
    return re.split(r"\s[:;—–-]\s|\s?:\s", title)[0].strip() or title


def find_cover(isbn: str | None, title: str | None, authors: str | None) -> bytes | None:
    """Look for a cover, from the most exact source to the loosest. Returns image bytes or None.

    1. Open Library, by ISBN          2. Google Books, by ISBN        3. Amazon's image server, by ISBN-10
    4. Open Library, by title+author  5. Google Books, by title+author
    """
    first_author = authors.split(",")[0].strip() if authors else None
    plain = _plain_title(title) if title else None
    tried: list[str] = []

    def google(client: httpx.Client, query: str, label: str) -> bytes | None:
        try:
            r = client.get("https://www.googleapis.com/books/v1/volumes",
                           params={"q": query, "maxResults": 5, "printType": "books"})
            items = r.json().get("items", []) if r.status_code == 200 else []
            if r.status_code != 200:
                tried.append(f"{label}: {r.status_code}")
                return None
        except (httpx.HTTPError, ValueError) as err:
            tried.append(f"{label}: {type(err).__name__}")
            return None
        for item in items:
            links = item.get("volumeInfo", {}).get("imageLinks", {})
            url = links.get("thumbnail") or links.get("smallThumbnail")
            if not url:
                continue
            url = url.replace("http://", "https://").replace("&edge=curl", "")
            img, what = _get_image(client, url)
            if img:
                return img
            tried.append(f"{label} image: {what}")
        tried.append(f"{label}: {len(items)} result(s), no cover")
        return None

    with _client() as client:
        if isbn:
            img, what = _get_image(client, f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false")
            if img:
                return img
            tried.append(f"open library isbn: {what}")
            img = google(client, f"isbn:{isbn}", "google isbn")
            if img:
                return img
            short = isbn10(isbn)
            if short:
                img, what = _get_image(client, f"https://images-na.ssl-images-amazon.com/images/P/{short}.01.LZZZZZZZ.jpg")
                if img:
                    return img
                tried.append(f"amazon: {what}")
        if plain:
            params = {"title": plain, "fields": "cover_i", "limit": 5}
            if first_author:
                params["author"] = first_author
            try:
                r = client.get("https://openlibrary.org/search.json", params=params)
                docs = r.json().get("docs", []) if r.status_code == 200 else []
                tried.append(f"open library search: {r.status_code}, {len(docs)} result(s)")
            except (httpx.HTTPError, ValueError) as err:
                docs = []
                tried.append(f"open library search: {type(err).__name__}")
            for doc in docs:
                if doc.get("cover_i"):
                    img, what = _get_image(client, f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg")
                    if img:
                        return img
            query = f"intitle:{plain}" + (f" inauthor:{first_author}" if first_author else "")
            img = google(client, query, "google title")
            if img:
                return img
    # what each source answered, without the book: helps tell "not known" from "not reachable"
    log.info("No cover found. Tried: %s", "; ".join(tried) or "nothing (no ISBN or title)")
    return None
