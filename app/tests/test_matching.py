"""A passage copied from a PDF reader is found in the PDFs a library keeps, however the reader copied it:
lines broken, words cut with a hyphen, ligatures as one sign or lost, a footnote or a running head caught
with it, from one page to the next. All text is invented."""

import random
import time

import httpx
import pytest
import typst

from conftest import owner
from marginote import db, matching
from test_documents import read, send
from test_scholar import registry

WORDS = ("lecture mémoire marge carnet relire geste trace page oubli souvenir question réponse lecteur livre "
         "passage phrase idée image chapitre retour silence regard main encre papier fil temps semaine "
         "pensée travail note ligne mot sens forme ordre écart détail fragment hypothèse lent vif clair "
         "sombre long bref ancien nouveau proche lointain simple double ouvert fermé premier dernier").split()
VERBS = "trie garde efface relie déplace éclaire reprend suit précède retient prolonge interrompt".split()


def prose(seed: int, sentences: int) -> str:
    rng = random.Random(seed)
    out = []
    for _ in range(sentences):
        words = [rng.choice(WORDS) for _ in range(rng.randint(5, 9))]
        words.insert(rng.randint(1, 3), rng.choice(VERBS))
        out.append(" ".join(words).capitalize() + ".")
    return " ".join(out)


FOOTNOTE = "Voir aussi les travaux de Dubois sur la lecture lente, qui défendent une thèse voisine."
OPENING = ("La mémoire n’archive pas, elle trie, et ce tri commence dès la lecture#footnote[" + FOOTNOTE + "]. "
           "Les difficultés de la classification fine des souvenirs, efficaces ou non, montrent que l’affaire "
           "est délicate et qu’elle demande des définitions officielles.")
COPIED = ("La mémoire n’archive pas, elle trie, et ce tri commence dès la lecture¹. Les difficultés de la "
          "classification fine des souvenirs, efficaces ou non, montrent que l’affaire est délicate et qu’elle "
          "demande des définitions officielles.")
SHARED = "Annoter, c’est déjà relire : le geste fixe moins le texte que la question qu’on lui posait."
DOC = """#set page(paper: "a4", margin: (x: 2cm, y: 2.4cm), numbering: "1", columns: 2,
  header: context {{ if counter(page).get().first() > {first} [#text(size: 8pt)[Revue d’exemple · Marceau] #h(1fr) #text(size: 8pt)[#counter(page).display()]] }})
#counter(page).update({first})
#set text(lang: "fr", size: 10pt, hyphenate: true)
#set par(justify: true)
{body}
"""


def article(seed: int, first: int, opening: str = "") -> bytes:
    body = f"{opening}\n\n{prose(seed, 40)}\n\n{SHARED}\n\n{prose(seed + 1, 160)}"
    return typst.compile(DOC.format(first=first, body=body).encode())


@pytest.fixture()
def library(logged_in, settings, monkeypatch):
    """Two articles: one opening on a footnote, the other not; one sentence is in both."""
    registry(monkeypatch, {})
    c = logged_in
    a = read(c, send(c, article(1, 45, OPENING), name="marceau.pdf")["id"])
    b = read(c, send(c, article(7, 112), name="dubois.pdf")["id"])
    sa = c.post("/api/sources", json={"kind": "article", "title": "La mémoire trie", "fetch_cover": False}).json()
    sb = c.post("/api/sources", json={"kind": "article", "title": "La lecture lente", "fetch_cover": False}).json()
    c.patch(f"/api/documents/{a['id']}", json={"source_id": sa["id"]})
    c.patch(f"/api/documents/{b['id']}", json={"source_id": sb["id"]})
    conn = db.connect(owner(settings).db_path)
    yield {"c": c, "conn": conn, "a": a, "b": b, "sa": sa, "sb": sb}
    conn.close()


def page_lines(c, doc: dict, index: int) -> list[str]:
    page = c.get(f"/api/photos/{doc['page_list'][index]['photo_id']}").json()
    return page["text"].split("\n")


MESSY = {
    "lines broken, a word cut": "La mémoire n’archive pas, elle trie, et ce tri com-\r\nmence dès la lecture1. Les\r\ndifficultés de la classification fine",
    "cut word, space left": "et ce tri com- mence dès la lecture. Les difficultés de la classifi- cation fine des souvenirs, efficaces ou non",
    "soft hyphen": "et ce tri com­mence dès la lecture1. Les difficultés de la classification fine des souvenirs, efficaces ou non",
    "ligatures as one sign": "Les difficultés de la classiﬁcation ﬁne des souvenirs, eﬃcaces ou non, montrent que l’aﬀaire est délicate",
    "ligatures lost": "Les difficultés de la classi cation ne des souvenirs, e caces ou non, montrent que l’a aire est délicate",
    "no accents, straight quotes": "La memoire n'archive pas, elle trie, et ce tri commence des la lecture. Les difficultes de la classification",
    "odd spaces": "La mémoire n’archive  pas,\telle trie, et ce tri commence dès la lecture ¹. Les difficultés",
    "footnote caught": ("La mémoire n’archive pas, elle trie, et ce tri commence dès la lecture1. Les difficultés de la "
                        "classification fine des souvenirs, efficaces ou non, montrent que l’affaire est délicate\n"
                        f"1 {FOOTNOTE}\net qu’elle demande des définitions officielles."),
}


@pytest.mark.parametrize("how", MESSY)
def test_a_passage_is_found_however_the_reader_copied_it(library, how):
    best, others = matching.find(library["conn"], MESSY[how])
    assert best is not None and matching.is_sure(best, others), how
    assert best.document_id == library["a"]["id"] and best.page == "45"
    assert "Dubois" not in best.text                    # a footnote caught with the passage is left out
    want = matching.letters(COPIED)
    got = matching.letters(best.text)
    assert got in want or want.startswith(got[:40]), (how, best.text)
    assert best.text.startswith(("La mémoire", "et ce tri", "Les difficultés")) and "  " not in best.text


def test_a_passage_from_one_page_to_the_next_without_its_running_head(library):
    c = library["c"]
    end = [line for line in page_lines(c, library["a"], 0)[:-1] if line.strip()][-3:]     # the last line is "45"
    top = page_lines(c, library["a"], 1)[1:4]                                               # the first is the running head
    copied = "\n".join(end) + "\n45\nRevue d’exemple · Marceau 46\n" + "\n".join(top)
    best, others = matching.find(library["conn"], copied)
    assert matching.is_sure(best, others) and best.page == "45–46"
    assert "Revue d’exemple" not in best.text and " 45 " not in f" {best.text} "
    assert matching.letters(best.text) == matching.letters(" ".join(end + top))
    start, stop = best.word_range                       # highlighted on the first page, to its end
    assert best.photo_id == library["a"]["page_list"][0]["photo_id"] and start < stop


def test_what_is_not_there_is_not_found(library):
    conn = library["conn"]
    assert matching.find(conn, "Une phrase qui n’est dans aucun des PDF de cette bibliothèque, écrite pour l’essai.")[0] is None
    assert matching.find(conn, "la mémoire")[0] is None                       # too short to say where
    # in both PDFs: not sure, unless one of them is the one being read
    best, others = matching.find(conn, SHARED)
    assert best and others and not matching.is_sure(best, others)
    best, others = matching.find(conn, SHARED, reading=library["b"]["id"])
    assert best.document_id == library["b"]["id"] and matching.is_sure(best, others, library["b"]["id"])


def test_a_sent_passage_is_kept_at_once_or_waits(library):
    c, a, b = library["c"], library["a"], library["b"]
    # found in one place: kept, with its source, page and place, in the PDF's own words
    sent = c.post("/api/passages", json={"text": MESSY["lines broken, a word cut"], "note": "À relire.", "origin": "windows"})
    assert sent.status_code == 201
    kept = sent.json()["kept"]
    assert kept["source"]["id"] == library["sa"]["id"] and kept["page"] == "45" and kept["note"] == "À relire."
    assert kept["text"].startswith("La mémoire n’archive pas, elle trie, et ce tri commence dès la lecture¹. Les")
    assert kept["photo_id"] == a["page_list"][0]["photo_id"] and kept["word_start"] is not None
    # in both PDFs: the one being read now (the last kept from) wins
    assert c.post("/api/passages", json={"text": SHARED}).json()["kept"]["source"]["id"] == library["sa"]["id"]
    # nowhere: it waits, to be given its source
    lost = c.post("/api/passages", json={"text": "Une phrase lue ailleurs, sur papier, et recopiée à la main ce matin.",
                                         "origin": "iphone"}).json()["waiting"]
    assert lost["reason"] == "source" and lost["guess"] is None
    waiting = c.get("/api/waiting").json()
    assert [w["id"] for w in waiting] == [lost["id"]]
    entry = c.post(f"/api/waiting/{lost['id']}/keep", json={"source_id": library["sb"]["id"], "page": "120"}).json()
    assert entry["source"]["id"] == library["sb"]["id"] and entry["page"] == "120" and entry["photo_id"] is None
    assert c.get("/api/waiting").json() == []
    # a link alone waits too; it can be dropped
    link = c.post("/api/passages", json={"url": "https://revue.example/article", "title": "Un article"}).json()["waiting"]
    assert c.delete(f"/api/waiting/{link['id']}").json() == {"deleted": link["id"]}
    assert c.post("/api/passages", json={"text": " "}).status_code == 422


def test_a_passage_in_a_pdf_with_no_source_yet_waits_with_its_place(logged_in, monkeypatch):
    c = logged_in
    registry(monkeypatch, {"api.crossref.org": httpx.Response(404), "api.datacite.org": httpx.Response(404)})
    doc = read(c, send(c, article(3, 9, OPENING), name="sans-source.pdf")["id"])
    waiting = c.post("/api/passages", json={"text": COPIED}).json()["waiting"]
    assert waiting["reason"] == "source" and waiting["guess"]["document_id"] == doc["id"]
    assert waiting["guess"]["page"] == "9" and waiting["guess"]["source_id"] is None
    src = c.post("/api/sources", json={"kind": "article", "title": "Sans source", "fetch_cover": False}).json()
    c.patch(f"/api/documents/{doc['id']}", json={"source_id": src["id"]})
    entry = c.post(f"/api/waiting/{waiting['id']}/keep", json={}).json()       # its PDF now has a source: kept there
    assert entry["source"]["id"] == src["id"] and entry["page"] == "9"
    assert entry["photo_id"] == doc["page_list"][0]["photo_id"] and entry["text"].startswith("La mémoire n’archive")


def test_finding_stays_quick_in_a_long_pdf(library):
    c = library["c"]
    long_doc = read(c, send(c, typst.compile(DOC.format(first=1, body=prose(11, 2400)).encode()), name="livre.pdf")["id"])
    assert long_doc["pages"] >= 15
    middle = page_lines(c, long_doc, long_doc["pages"] // 2)
    passage = "\n".join(middle[5:9])
    started = time.perf_counter()
    best, others = matching.find(library["conn"], passage)
    assert time.perf_counter() - started < 2
    assert best.document_id == long_doc["id"] and best.pages[best.start[0]].index == long_doc["pages"] // 2


def test_what_you_are_reading_comes_first_with_where_you_were(library):
    c, a, b = library["c"], library["a"], library["b"]
    c.post("/api/passages", json={"text": COPIED})                      # kept from the first PDF, p. 45
    reading = c.get("/api/reading").json()
    assert reading[0]["source"]["id"] == library["sa"]["id"] and reading[0]["last_page"] == "45"
    assert reading[0]["document"]["id"] == a["id"] and reading[0]["document"]["page_index"] == 0
    c.patch(f"/api/documents/{b['id']}", json={"source_id": library["sb"]["id"]})    # given its source: read now
    assert c.get("/api/reading").json()[0]["source"]["id"] == library["sb"]["id"]
