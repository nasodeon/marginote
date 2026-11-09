"""PDFs: kept once, read page by page in the background, recognised from the DOI printed on their first page,
their pages then used like page photos. Every PDF here is made by the test, from invented text."""

import io
import time
import zipfile

import httpx
import typst
from fastapi.testclient import TestClient
from PIL import Image

from conftest import owner
from marginote import pdfs
from marginote.main import create_app
from test_scholar import CROSSREF, registry

TEMPLATE = """#set page(paper: "a5", margin: 1.6cm, numbering: "1")
#counter(page).update({first})
#set text(lang: "fr", size: 10pt, hyphenate: false)
#set par(justify: true)
{header}
{body}
"""
HEADER = """#text(size: 15pt, weight: "bold")[Une revue d’exemple sur la mémoire] \\
Hélène Marceau, Paul Verdier, Inès Moreau et Lucie Brunet \\
#text(size: 8pt)[Revue d’exemple 12 (3), 2021 · https://doi.org/10.5555/exemple.2021.045]

"""
PASSAGE = "Annoter, c’est déjà relire : le geste fixe moins le texte que la question qu’on lui posait."
FILLER = ("Les lecteurs qui annotent en marge retrouvent un passage bien plus vite que ceux qui surlignent, "
          "et le tri commence dès la première lecture. ")


def make_pdf(first: int = 45, header: str = HEADER, pages: int = 3) -> bytes:
    body = "\n\n#pagebreak()\n".join(
        (f"{PASSAGE}\n\n" if k == 1 else "") + FILLER * 6 for k in range(pages))
    return typst.compile(TEMPLATE.format(first=first, header=header, body=body).encode())


def scanned_pdf(tmp_path) -> bytes:
    """A PDF with only a picture of a page in it, as a scanner makes."""
    made = tmp_path / "made.pdf"
    made.write_bytes(make_pdf(pages=1))
    out = io.BytesIO()
    pdfs.render(made, 0, 1240).save(out, format="PDF", resolution=150)
    return out.getvalue()


def send(c: TestClient, data: bytes, name: str = "memoire-2021.pdf", **params) -> dict:
    r = c.post("/api/documents", params=params, files={"file": (name, data, "application/pdf")})
    assert r.status_code in (200, 201), r.text
    return r.json()


def read(c: TestClient, doc_id: str, timeout: float = 90) -> dict:
    """Wait for the background reading to finish."""
    until = time.time() + timeout
    while time.time() < until:
        doc = c.get(f"/api/documents/{doc_id}").json()
        if doc["status"] != "reading":
            return doc
        time.sleep(0.2)
    raise AssertionError("the PDF was not read in time")


def test_a_pdf_is_read_recognised_and_its_pages_work_like_photos(logged_in, settings, monkeypatch):
    c = logged_in
    registry(monkeypatch, {"api.crossref.org/works/10.5555/exemple.2021.045": httpx.Response(200, json=CROSSREF)})
    data = make_pdf()
    sent = send(c, data)
    assert sent["status"] == "reading" and sent["queued"] is True and sent["pages"] == 3
    doc = read(c, sent["id"])
    assert doc["status"] == "ready" and doc["read_pages"] == 3
    # recognised from the DOI printed on its first page, then Crossref: every author, the journal
    assert (doc["found"]["by"], doc["found"]["value"], doc["found"]["page"]) == ("doi", "10.5555/exemple.2021.045", 0)
    draft = doc["found"]["source"]
    assert draft["journal"] == "Revue d’exemple" and len(draft["people"]["author"]) == 4 and doc["existing"] is None
    assert [p["page"] for p in doc["page_list"]] == ["45", "46", "47"]         # the numbers printed on the pages
    # sent again: the same PDF
    assert send(c, data, name="copie.pdf")["id"] == doc["id"]

    # its source is made from what was found, and the PDF given to it
    body = {k: draft[k] for k in ("kind", "title", "journal", "volume", "issue", "pages", "year", "doi")}
    src = c.post("/api/sources", json={**body, "people": draft["people"], "fetch_cover": False}).json()
    linked = c.patch(f"/api/documents/{doc['id']}", json={"source_id": src["id"]}).json()
    assert linked["source"]["id"] == src["id"] and linked["queued"] is False
    lib = owner(settings)
    kept = list((lib.pdfs_dir).rglob("*.pdf"))
    assert [p.relative_to(lib.pdfs_dir).as_posix() for p in kept] == [
        f"Une revue d’exemple sur la mémoire ({src['id']})/memoire-2021.pdf"]
    assert c.get(f"/api/documents/{doc['id']}").json()["existing"]["id"] == src["id"]

    # a page: its words, placed like a photo's, drawn from the PDF when looked at
    page = c.get(f"/api/photos/{linked['page_list'][1]['photo_id']}").json()
    assert page["document"]["index"] == 1 and page["document"]["previous"] and page["document"]["next"]
    assert page["detected_page"] == "46" and page["source_id"] == src["id"]
    assert PASSAGE.split()[0] in page["text"]
    image = c.get(page["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
    assert Image.open(io.BytesIO(image.content)).size == (page["width"], page["height"])
    small = Image.open(io.BytesIO(c.get(page["image_url"], params={"width": 320}).content))
    assert small.width == 320

    # a passage chosen on it, kept as a quote with its page
    words = [w["text"] for w in page["words"]]
    start = words.index("Annoter,")
    end = start + len(PASSAGE.split()) - 1
    chosen = c.post(f"/api/photos/{page['id']}/select", json={"start": start, "end": end}).json()
    assert chosen["text"] == PASSAGE
    entry = c.post("/api/entries", json={"source_id": src["id"], "photo_id": page["id"], "word_start": start,
                                         "word_end": end, "page": page["detected_page"], "text": chosen["text"]}).json()
    assert entry["page"] == "46" and entry["photo_id"] == page["id"]
    assert c.get(f"/api/documents/{doc['id']}").json()["page_list"][1]["entry_count"] == 1
    assert c.delete(f"/api/photos/{page['id']}").status_code == 409          # a page goes with its PDF only

    # the hourly cleaning never takes a PDF's pages, even unused
    from marginote.files import Files
    import dataclasses
    Files(dataclasses.replace(lib, unused_photo_hours=0)).clean_unused_photos()
    assert len(c.get(f"/api/documents/{doc['id']}").json()["page_list"]) == 3

    # renamed, the source takes its PDF's folder along
    c.patch(f"/api/sources/{src['id']}", json={"title": "La mémoire trie"})
    assert (lib.pdfs_dir / f"La mémoire trie ({src['id']})" / "memoire-2021.pdf").is_file()
    assert c.get(page["image_url"] + "?width=200").status_code == 200

    # the download of the whole library holds the PDF
    with zipfile.ZipFile(io.BytesIO(c.get("/api/backup/download").content)) as z:
        assert f"pdfs/La mémoire trie ({src['id']})/memoire-2021.pdf" in z.namelist()

    # deleted, the PDF takes its pages; the quote stays, with its text and page
    assert c.delete(f"/api/documents/{doc['id']}").status_code == 200
    kept_entry = c.get(f"/api/entries/{entry['id']}").json()
    assert kept_entry["text"] == PASSAGE and kept_entry["page"] == "46" and kept_entry["photo_id"] is None
    assert c.get(f"/api/photos/{page['id']}").status_code == 404
    assert not list(lib.pdfs_dir.rglob("*.pdf"))


def test_the_pdf_opens_from_a_signed_link_for_one_library_only(settings, monkeypatch):
    registry(monkeypatch, {})
    with TestClient(create_app(settings)) as c:
        c.post("/api/login", json={"password": "correct horse"})
        doc = read(c, send(c, make_pdf(pages=1), name="Carnet secret.pdf")["id"])
        url = doc["file_url"]
        assert c.get(url).headers["content-type"] == "application/pdf"
        c.post("/api/accounts", json={"name": "Camille", "password": "lune-de-miel"})
        c.cookies.clear()
        r = c.get(url)                                  # Safari, without the app's login: the signed link works
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        assert "Carnet" in r.headers["content-disposition"]
        assert c.get(url.replace("&s=", "&s=0")).status_code == 401         # altered: refused
        assert c.get(url.replace("a=owner", "a=nobody")).status_code == 401
        c.post("/api/login", json={"name": "Camille", "password": "lune-de-miel"})
        for path in (f"/api/documents/{doc['id']}", f"/api/documents/{doc['id']}/file",
                     f"/api/photos/{doc['page_list'][0]['photo_id']}"):
            assert c.get(path).status_code == 404, path          # someone else's PDF does not exist for her
        assert c.get("/api/documents").json() == []
        assert c.delete(f"/api/documents/{doc['id']}").status_code == 404


def test_a_scanned_page_is_read_like_a_photo_and_a_bad_file_is_refused(logged_in, monkeypatch, tmp_path):
    c = logged_in
    registry(monkeypatch, {"api.crossref.org": httpx.Response(404), "api.datacite.org": httpx.Response(404)})
    doc = read(c, send(c, scanned_pdf(tmp_path), name="scan.pdf")["id"])
    page = c.get(f"/api/photos/{doc['page_list'][0]['photo_id']}").json()
    assert "Une revue" in page["text"] and "Marceau" in page["text"]        # read with Tesseract
    assert doc["page_list"][0]["page"] == "45"
    assert doc["found"]["by"] == "doi" and doc["found"]["note"] == "No article found for this DOI"
    # a passage copied from a reader's own reading of the scan is found in Tesseract's
    found = c.post("/api/passages/find", json={"text": FILLER[:120].replace("surlignent", "sur-\nlignent")}).json()
    assert found["match"]["document_id"] == doc["id"] and found["match"]["score"] > 0.9 and found["sure"]
    assert c.post("/api/documents", files={"file": ("x.pdf", b"not a pdf at all", "application/pdf")}).status_code == 415


def test_a_preprint_and_unnumbered_pages(logged_in, monkeypatch):
    """No page number printed: pages count from the article's first page in its journal, or from 1."""
    c = logged_in
    registry(monkeypatch, {})
    plain = TEMPLATE.replace('numbering: "1"', "numbering: none")
    body = "\n\n#pagebreak()\n".join(FILLER * 6 for _ in range(2))
    data = typst.compile(plain.format(first=1, header="#text(size: 15pt)[Une prépublication inventée] \\\n"
                                      "Émile Dubois \\\n\n", body=body).encode())
    doc = read(c, send(c, data, name="2401.01234v2.pdf")["id"])
    assert (doc["found"]["by"], doc["found"]["value"]) == ("arxiv", "2401.01234")        # from its file name
    assert doc["found"]["title"] == "Une prépublication inventée"
    assert [p["page"] for p in doc["page_list"]] == ["1", "2"]
    src = c.post("/api/sources", json={"kind": "article", "title": "Une prépublication inventée", "pages": "112–113",
                                       "fetch_cover": False}).json()
    linked = c.patch(f"/api/documents/{doc['id']}", json={"source_id": src["id"]}).json()
    assert [p["page"] for p in linked["page_list"]] == ["112", "113"]
    # deleting the source deletes its PDF
    c.delete(f"/api/sources/{src['id']}")
    assert c.get(f"/api/documents/{doc['id']}").status_code == 404
