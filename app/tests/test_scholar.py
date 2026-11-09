"""Scientific articles: recognising a DOI, an arXiv number or an ISBN in what was pasted, their details from
Crossref, DataCite and arXiv, the article fields of a source, and how an article is cited. All invented."""

import json
from datetime import date

import httpx
import pytest

from marginote import db, export, ids, linkinfo, lookup, scholar
from test_library import fake_web
from conftest import owner

CROSSREF = {"message": {
    "DOI": "10.5555/Exemple.2021.045", "type": "journal-article",
    "title": ["Une revue d’exemple sur la <i>mémoire</i>"], "subtitle": [],
    "author": [{"given": "Hélène", "family": "Marceau"}, {"given": "Paul", "family": "Verdier"},
               {"given": "Inès", "family": "Moreau"}, {"given": "Lucie", "family": "Brunet"}],
    "container-title": ["Revue d’exemple"], "volume": "12", "issue": "3", "page": "45-56",
    "publisher": "Éditions d’exemple", "published-print": {"date-parts": [[2021, 3, 4]]},
}}
DATACITE = {"data": {"attributes": {
    "doi": "10.5281/zenodo.0000001", "titles": [{"title": "Un jeu de données inventé"}],
    "creators": [{"name": "Arnaud, Camille", "givenName": "Camille", "familyName": "Arnaud"}],
    "publisher": "Zenodo", "publicationYear": 2023, "types": {"resourceTypeGeneral": "Dataset"},
}}}
ARXIV = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v2</id>
    <published>2024-01-03T18:00:00Z</published>
    <title>Une prépublication
      inventée</title>
    <author><name>Émile Dubois</name></author>
    <author><name>Lucie Brunet</name></author>
  </entry>
</feed>"""


def registry(monkeypatch, routes):
    def handler(request):
        for key, answer in routes.items():
            if key in str(request.url):
                return answer() if callable(answer) else answer
        return httpx.Response(404)
    monkeypatch.setattr(scholar, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("text, kind, value", [
    ("10.1103/PhysRevA.104.012345", "doi", "10.1103/physreva.104.012345"),
    ("https://doi.org/10.1016/S0140-6736(20)30183-5.", "doi", "10.1016/s0140-6736(20)30183-5"),
    ("doi: 10.5555/exemple.2021.045", "doi", "10.5555/exemple.2021.045"),
    ("https://arxiv.org/pdf/2401.01234v3", "arxiv", "2401.01234"),
    ("arXiv:hep-th/9901001", "arxiv", "hep-th/9901001"),
    ("2401.01234", "arxiv", "2401.01234"),
    ("ISBN 978-2-07-036002-4", "isbn", "9782070360024"),
    ("2-07-036002-4", "isbn", "9782070360024"),
    ("https://onlinelibrary.wiley.com/doi/10.1002/abc.123", "url", "https://onlinelibrary.wiley.com/doi/10.1002/abc.123"),
    ("2413.00001", "text", "2413.00001"),            # no 13th month: not an arXiv number
])
def test_what_was_pasted_is_recognised(text, kind, value):
    found = ids.classify(text)
    assert (found["kind"], found["value"]) == (kind, value)


def test_identifiers_are_found_inside_a_passage():
    passage = ("Une phrase assez longue pour être un passage, citée d’après https://doi.org/10.5555/X.2021.045. "
               "Voir aussi arXiv:2312.04567v1 et l’ISBN 978-2-07-036002-4.")
    found = ids.classify(passage)
    assert found["kind"] == "text"
    assert found["ids"] == [{"kind": "doi", "value": "10.5555/x.2021.045"}, {"kind": "arxiv", "value": "2312.04567"},
                            {"kind": "isbn", "value": "9782070360024"}]


def test_registries_are_read_and_asked_in_turn(monkeypatch):
    article = scholar.parse_crossref(CROSSREF["message"])
    assert article["title"] == "Une revue d’exemple sur la mémoire"            # markup removed
    assert article["people"]["author"] == ["Hélène Marceau", "Paul Verdier", "Inès Moreau", "Lucie Brunet"]
    assert (article["journal"], article["volume"], article["issue"], article["pages"]) == ("Revue d’exemple", "12", "3", "45–56")
    assert (article["year"], article["date"], article["doi"]) == (2021, "2021-03-04", "10.5555/exemple.2021.045")
    preprint = scholar.parse_arxiv(ARXIV)
    assert preprint["title"] == "Une prépublication inventée" and preprint["arxiv"] == "2401.01234"
    assert preprint["people"]["author"] == ["Émile Dubois", "Lucie Brunet"] and preprint["year"] == 2024

    # Crossref does not know it: DataCite does
    registry(monkeypatch, {"api.crossref.org": httpx.Response(404), "api.datacite.org": httpx.Response(200, json=DATACITE)})
    found = scholar.lookup_doi("10.5281/zenodo.0000001")
    assert found["title"] == "Un jeu de données inventé" and found["people"]["author"] == ["Camille Arnaud"]

    def down():
        raise httpx.ConnectError("no network")
    registry(monkeypatch, {"api.crossref.org": down, "api.datacite.org": down})
    with pytest.raises(lookup.LookupUnavailable):
        scholar.lookup_doi("10.5555/x")


def test_a_doi_becomes_an_article_once(logged_in, monkeypatch):
    c = logged_in
    registry(monkeypatch, {"api.crossref.org/works/10.5555/exemple.2021.045": httpx.Response(200, json=CROSSREF),
                           "export.arxiv.org": httpx.Response(200, text=ARXIV)})
    found = c.post("/api/recognize", json={"text": "https://doi.org/10.5555/Exemple.2021.045"}).json()
    assert found["kind"] == "doi" and found["existing"] is None
    src = found["source"]
    assert src["kind"] == "article" and src["journal"] == "Revue d’exemple" and len(src["people"]["author"]) == 4

    body = {k: src[k] for k in ("kind", "title", "journal", "volume", "issue", "pages", "year", "publisher", "url")}
    made = c.post("/api/sources", json={**body, "doi": "https://doi.org/10.5555/EXEMPLE.2021.045",
                                        "people": src["people"], "fetch_cover": False})
    assert made.status_code == 201 and made.json()["doi"] == "10.5555/exemple.2021.045"
    assert len(made.json()["people"]["author"]) == 4                     # every author is kept
    again = c.post("/api/recognize", json={"text": "doi:10.5555/exemple.2021.045"}).json()
    assert again["existing"]["id"] == made.json()["id"] and again["source"] is None   # nothing asked online
    twice = c.post("/api/sources", json={"title": "Autre", "doi": "10.5555/exemple.2021.045", "fetch_cover": False})
    assert twice.status_code == 409
    assert c.post("/api/sources", json={"title": "Autre", "doi": "pas un doi", "fetch_cover": False}).status_code == 422

    pre = c.post("/api/recognize", json={"text": "arXiv:2401.01234v2"}).json()
    assert pre["kind"] == "arxiv" and pre["source"]["arxiv"] == "2401.01234"
    made = c.post("/api/sources", json={"kind": "article", "title": pre["source"]["title"], "arxiv": "arxiv.org/abs/2401.01234",
                                        "fetch_cover": False}).json()
    assert made["arxiv"] == "2401.01234"
    assert c.patch(f"/api/sources/{made['id']}", json={"arxiv": "2401.01234v3"}).json()["arxiv"] == "2401.01234"

    passage = c.post("/api/recognize", json={"text": "Un passage assez long pour ne pas être un identifiant, voilà."}).json()
    assert passage["kind"] == "text" and passage["source"] is None and passage["ids"] == []


def test_a_journal_page_gives_its_doi_and_every_author(logged_in, monkeypatch):
    page = """<html><head><title>x</title>
    <meta name="citation_title" content="Une revue d’exemple sur la mémoire">
    <meta name="citation_author" content="Marceau, Hélène"><meta name="citation_author" content="Verdier, Paul">
    <meta name="citation_doi" content="10.5555/exemple.2021.045"><meta name="citation_journal_title" content="Revue d’exemple">
    <meta name="citation_firstpage" content="45"><meta name="citation_lastpage" content="56">
    <meta name="citation_publication_date" content="2021/03/04"></head></html>"""
    fake_web(monkeypatch, {"revue.example/article": httpx.Response(200, text=page, headers={"content-type": "text/html"})})
    registry(monkeypatch, {"api.crossref.org": httpx.Response(200, json=CROSSREF)})
    info = logged_in.post("/api/lookup/link", json={"url": "https://revue.example/article"}).json()
    assert info["doi"] == "10.5555/exemple.2021.045" and info["date"] == "2021-03-04" and info["pages"] == "45–56"
    assert info["people"] == ["Hélène Marceau", "Paul Verdier", "Inès Moreau", "Lucie Brunet"]   # Crossref knows all four
    assert info["journal"] == "Revue d’exemple" and info["volume"] == "12"


def test_an_article_in_the_bibliography(logged_in, settings):
    c = logged_in
    sid = c.post("/api/sources", json={"kind": "article", "title": "Une revue d’exemple sur la mémoire", "year": 2021,
                                       "journal": "Revue d’exemple", "volume": "12", "issue": "3", "pages": "45–56",
                                       "doi": "10.5555/exemple.2021.045", "fetch_cover": False,
                                       "people": {"author": ["Hélène Marceau", "Paul Verdier"]}}).json()["id"]
    c.post("/api/entries", json={"source_id": sid, "page": "48", "text": "Annoter, c’est déjà relire."})
    doc = export.build(db.connect(owner(settings).db_path), "source", [sid], today=date(2026, 11, 9))
    assert "".join(r[0] for r in doc["bibliography"][0]) == (
        "Marceau, Hélène; Verdier, Paul, Une revue d’exemple sur la mémoire, Revue d’exemple 12 (3), p. 45–56, 2021. "
        "doi:10.5555/exemple.2021.045")
    assert doc["chapters"][0]["meta"] == "Hélène Marceau et Paul Verdier · Revue d’exemple 12 (3), p. 45–56 · 2021"
