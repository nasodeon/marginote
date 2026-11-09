"""What was pasted, shared or found in a page: a DOI, an arXiv number, an ISBN, a link, or a passage.

  classify("10.1103/PhysRevA.104.012345")          -> {"kind": "doi", "value": "10.1103/physreva.104.012345"}
  classify("https://arxiv.org/abs/2401.01234v2")    -> {"kind": "arxiv", "value": "2401.01234"}
  classify("Une phrase … doi:10.5555/x.2021.045")   -> {"kind": "text", "ids": [{"kind": "doi", …}]}

DOIs are compared in lower case (they are case-insensitive); arXiv numbers without their version (v2).
"""

import re
from urllib.parse import unquote, urlsplit

from .lookup import clean_isbn, isbn13

# 10.<registrant>/<anything without spaces>; the end is trimmed of punctuation that belongs to the sentence
_DOI = re.compile(r"(?<![\w.])(10\.\d{4,9}/[^\s\"<>{}|\\^`]+)", re.I)
_DOI_TAIL = ".,;:!?)]}'’»”  "
_ARXIV_NEW = re.compile(r"(?<![\w.])(\d{4}\.\d{4,5})(?:v\d+)?(?![\w.])")
_ARXIV_OLD = re.compile(r"(?<![\w.])([a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?(?![\w.])", re.I)
_ARXIV_LABEL = re.compile(r"arxiv\s*[:.]?\s*(?:abs/)?", re.I)
_URL = re.compile(r"^(https?://|www\.)\S+$", re.I)


def clean_doi(raw: str) -> str | None:
    """'https://doi.org/10.1103/PhysRevA.104.012345.' -> '10.1103/physreva.104.012345'."""
    text = unquote((raw or "").strip())
    m = _DOI.search(text)
    if not m:
        return None
    doi = m.group(1)
    while doi and doi[-1] in _DOI_TAIL:
        if doi[-1] == ")" and doi.count("(") >= doi.count(")"):
            break              # a DOI may hold brackets: 10.1016/s0140-6736(20)30183-5
        doi = doi[:-1]
    for suffix in (".pdf", "/full", "/abstract", "/pdf", "/epdf"):
        if doi.lower().endswith(suffix) and len(doi) > len(suffix) + 8:
            doi = doi[: -len(suffix)]
    return doi.lower() if "/" in doi and len(doi) > 7 else None


def clean_arxiv(raw: str, labelled_only: bool = False) -> str | None:
    """'arXiv:2401.01234v2', 'https://arxiv.org/pdf/2401.01234' or '2401.01234' -> '2401.01234'.
    With labelled_only, a bare number counts only after 'arXiv' or in an arxiv.org link."""
    text = (raw or "").strip()
    host = urlsplit(text).hostname or "" if text.lower().startswith("http") else ""
    labelled = host.endswith("arxiv.org") or bool(_ARXIV_LABEL.search(text))
    if labelled_only and not labelled:
        return None
    if host.endswith("arxiv.org"):
        text = urlsplit(text).path
    for pattern in (_ARXIV_NEW, _ARXIV_OLD):
        m = pattern.search(text)
        if m:
            value = m.group(1)
            if pattern is _ARXIV_NEW and not 1 <= int(value[2:4]) <= 12:
                continue           # 2413.00001 is no month
            return value
    return None


def ids_in_text(text: str) -> list[dict]:
    """Every DOI, arXiv number and ISBN written in a text (a page read from a photo, a PDF's first page)."""
    out: list[dict] = []
    seen = set()

    def add(kind: str, value: str | None) -> None:
        if value and (kind, value) not in seen:
            seen.add((kind, value))
            out.append({"kind": kind, "value": value})

    for m in _DOI.finditer(text or ""):
        add("doi", clean_doi(m.group(1)))
    for m in re.finditer(r"arxiv\s*[:.]?\s*(?:abs/)?\s*(\S+)|arxiv\.org/(?:abs|pdf)/(\S+)", text or "", re.I):
        add("arxiv", clean_arxiv("arXiv:" + (m.group(1) or m.group(2))))
    from .ocr import isbns_in_text            # the page reader's own finder (labels, hyphens, checksums)
    for isbn in isbns_in_text(text or ""):
        add("isbn", isbn)
    return out


def classify(text: str) -> dict:
    """What a pasted or shared text is. A single DOI, arXiv number, ISBN or link is recognised as such;
    anything longer is a passage, with the identifiers found in it."""
    raw = (text or "").strip()
    single = raw and not re.search(r"\s", raw)
    if single and _URL.match(raw):
        url = raw if raw.lower().startswith("http") else "https://" + raw
        host = (urlsplit(url).hostname or "").lower()
        if host in ("doi.org", "dx.doi.org", "www.doi.org") and clean_doi(url):
            return {"kind": "doi", "value": clean_doi(url)}
        if host.endswith("arxiv.org") and clean_arxiv(url):
            return {"kind": "arxiv", "value": clean_arxiv(url)}
        return {"kind": "url", "value": url.rstrip(".,;")}
    if single or len(raw) <= 40:
        doi = clean_doi(raw)
        if doi and (single or raw.lower().startswith(("doi", "10."))):
            return {"kind": "doi", "value": doi}
        arxiv = clean_arxiv(raw, labelled_only=not single)
        if arxiv and (single or raw.lower().startswith("arxiv")):
            return {"kind": "arxiv", "value": arxiv}
        digits = re.sub(r"[\s-]", "", raw.lower().removeprefix("isbn").strip(" :"))
        isbn = clean_isbn(digits) if re.fullmatch(r"[0-9xX]{10,13}", digits) else None
        if isbn:
            return {"kind": "isbn", "value": isbn13(isbn)}
    return {"kind": "text", "value": raw, "ids": ids_in_text(raw)}
