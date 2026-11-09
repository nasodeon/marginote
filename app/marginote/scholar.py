"""A scientific article's details from its DOI (Crossref, then DataCite) or its arXiv number (arXiv).

Only the DOI or the arXiv number leaves the server, never a passage. Turned off with LOOKUPS_ENABLED=false,
like the book lookups. The answer has the shape of a new source (POST /api/sources).
"""

import html
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

from . import lookup, names
from .lookup import HEADERS, LookupUnavailable, httpx

log = logging.getLogger("marginote")
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
NOT_FOUND = {"doi": "No article found for this DOI", "arxiv": "No article found for this arXiv number",
             "isbn": "No book found for this ISBN"}
BOOK_TYPES = {"book", "monograph", "edited-book", "reference-book", "book-set"}


def _client():
    return httpx.Client(headers=HEADERS, timeout=httpx.Timeout(8.0, connect=5.0), follow_redirects=True)


def _plain(text: str | None) -> str | None:
    """Titles come with markup at times: '<i>In vivo</i> imaging of H<sub>2</sub>O'."""
    if not text:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\s+", " ", text).strip() or None


def _first(value) -> str | None:
    if isinstance(value, list):
        return _plain(value[0]) if value else None
    return _plain(value) if isinstance(value, str) else None


def _date(parts: dict | None) -> tuple[int | None, str | None]:
    try:
        p = parts["date-parts"][0]
    except (KeyError, IndexError, TypeError):
        return None, None
    if not p or p[0] is None:
        return None, None
    year = int(p[0])
    return year, "-".join(f"{int(x):02d}" if k else str(int(x)) for k, x in enumerate(p[:3]))


def _pages(value) -> str | None:
    """'45-56' -> '45–56', as the pages read from a journal's page are written."""
    return re.sub(r"(?<=\w)\s*-+\s*(?=\w)", "\u2013", str(value)).strip() if value else None


def _person(p: dict) -> str | None:
    name = " ".join(x for x in (p.get("given"), p.get("family")) if x) or p.get("name")
    return re.sub(r"\s+", " ", name).strip() if name else None


def parse_crossref(message: dict) -> dict:
    kind = message.get("type", "")
    year, date = None, None
    for key in ("published-print", "published-online", "issued", "published", "created"):
        year, date = _date(message.get(key))
        if year:
            break
    isbns = message.get("ISBN") or []
    book = kind in BOOK_TYPES
    return {
        "kind": "book" if book else "article",
        "title": _first(message.get("title")),
        "subtitle": _first(message.get("subtitle")),
        "people": {"author": [n for n in (_person(p) for p in message.get("author", [])) if n],
                   "editor": [n for n in (_person(p) for p in message.get("editor", [])) if n]},
        "journal": None if book else _first(message.get("container-title")),
        "volume": message.get("volume"),
        "issue": message.get("issue"),
        "pages": _pages(message.get("page") or message.get("article-number")),
        "publisher": message.get("publisher"),
        "year": year,
        "date": date if date and len(date) == 10 else None,
        "isbn": re.sub(r"[^0-9X]", "", isbns[0].upper()) if book and isbns else None,
        "arxiv": None,
        "doi": (message.get("DOI") or "").lower() or None,
        "url": f"https://doi.org/{message['DOI']}" if message.get("DOI") else message.get("URL"),
        "language": (message.get("language") or "")[:2].lower() or None,
        "found_by": "Crossref",
    }


def parse_datacite(data: dict) -> dict:
    a = data.get("attributes", {})
    people = [c.get("name") if not c.get("givenName") else f"{c['givenName']} {c.get('familyName', '')}".strip()
              for c in a.get("creators", [])]
    year = a.get("publicationYear")
    general = (a.get("types") or {}).get("resourceTypeGeneral", "")
    container = (a.get("container") or {}).get("title")
    return {
        "kind": "book" if general == "Book" else "article",
        "title": _plain((a.get("titles") or [{}])[0].get("title")),
        "subtitle": None,
        "people": {"author": [p for p in people if p], "editor": []},
        "journal": _plain(container),
        "volume": (a.get("container") or {}).get("volume"),
        "issue": (a.get("container") or {}).get("issue"),
        "pages": None,
        "publisher": a.get("publisher") if isinstance(a.get("publisher"), str) else (a.get("publisher") or {}).get("name"),
        "year": int(year) if str(year or "").isdigit() else None,
        "date": None,
        "isbn": None,
        "arxiv": None,
        "doi": (a.get("doi") or "").lower() or None,
        "url": f"https://doi.org/{a['doi']}" if a.get("doi") else a.get("url"),
        "language": (a.get("language") or "")[:2].lower() or None,
        "found_by": "DataCite",
    }


def parse_arxiv(xml_text: str) -> dict | None:
    root = ET.fromstring(xml_text)
    entry = root.find("a:entry", ATOM)
    if entry is None or entry.find("a:title", ATOM) is None:
        return None
    ident = (entry.findtext("a:id", "", ATOM) or "").rsplit("/abs/", 1)[-1]
    number = re.sub(r"v\d+$", "", ident)
    published = entry.findtext("a:published", "", ATOM)
    journal_ref = _plain(entry.findtext("arxiv:journal_ref", "", ATOM))
    doi = (entry.findtext("arxiv:doi", "", ATOM) or "").strip().lower() or None
    return {
        "kind": "article",
        "title": _plain(entry.findtext("a:title", "", ATOM)),
        "subtitle": None,
        "people": {"author": [_plain(a.findtext("a:name", "", ATOM)) for a in entry.findall("a:author", ATOM)
                              if a.findtext("a:name", "", ATOM)], "editor": []},
        "journal": journal_ref,          # 'Phys. Rev. A 104, 012345 (2021)' once published, else nothing
        "volume": None,
        "issue": None,
        "pages": None,
        "publisher": "arXiv",
        "year": int(published[:4]) if published[:4].isdigit() else None,
        "date": published[:10] or None,
        "isbn": None,
        "doi": doi,
        "arxiv": number or None,
        "url": f"https://arxiv.org/abs/{number}" if number else None,
        "language": None,
        "found_by": "arXiv",
    }


def lookup_doi(doi: str, client_factory=None) -> dict | None:
    """The article (or book) a DOI names, or None if no registry knows it. Raises LookupUnavailable when
    neither Crossref nor DataCite could be reached."""
    reached = False
    with (client_factory or _client)() as client:
        for url, parse in ((f"https://api.crossref.org/works/{quote(doi, safe='/')}", lambda d: parse_crossref(d["message"])),
                           (f"https://api.datacite.org/dois/{quote(doi, safe='')}", lambda d: parse_datacite(d["data"]))):
            try:
                r = client.get(url, headers={"Accept": "application/json"})
            except httpx.HTTPError as err:
                log.info("DOI lookup could not reach %s (%s)", url.split("/")[2], type(err).__name__)
                continue
            reached = True
            if r.status_code == 200:
                try:
                    found = parse(r.json())
                except (ValueError, KeyError, TypeError):
                    continue
                if found.get("title"):
                    found["doi"] = found.get("doi") or doi
                    return found
    if not reached:
        raise LookupUnavailable("Crossref and DataCite could not be reached")
    return None


def lookup_arxiv(number: str, client_factory=None) -> dict | None:
    with (client_factory or _client)() as client:
        try:
            r = client.get("https://export.arxiv.org/api/query", params={"id_list": number, "max_results": 1})
        except httpx.HTTPError as err:
            raise LookupUnavailable(f"arXiv could not be reached ({type(err).__name__})") from None
    if r.status_code != 200:
        return None
    try:
        return parse_arxiv(r.text)
    except ET.ParseError:
        return None


def identify(kind: str, value: str) -> dict | None:
    """The source a DOI, an arXiv number or an ISBN names, in the shape of a new source; None if nobody knows
    it. Raises LookupUnavailable when the services could not be reached."""
    if kind == "doi":
        return lookup_doi(value)
    if kind == "arxiv":
        found = lookup_arxiv(value)
        if found and found.get("doi"):          # published since: the journal's details too
            try:
                found = {**found, **{k: v for k, v in (lookup_doi(found["doi"]) or {}).items() if v}, "arxiv": value}
            except LookupUnavailable:
                pass
        return found
    if kind == "isbn":
        book = lookup.lookup_isbn(value)
        if not book:
            return None
        return {"kind": "book", **{k: book.get(k) for k in ("title", "subtitle", "publisher", "year", "language")},
                "isbn": value, "people": {"author": names.split_list(book.get("authors")),
                                          "translator": names.split_list(book.get("translator"))},
                "found_by": book.get("source")}
    raise ValueError(f"Not an identifier: {kind}")
