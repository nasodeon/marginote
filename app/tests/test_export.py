"""Exporting quotes and notes as a PDF or a Word file: what goes in, in which order, and to whom.
Every text here is invented."""

import io
from datetime import date
from urllib.parse import unquote

import docx
import pytest
from fastapi.testclient import TestClient

from marginote import db, export
from marginote.main import create_app

from conftest import owner
from test_accounts import OWNER_PW, login


def fill(c: TestClient) -> dict:
    """A small invented library: two authors, a video about one of them, a class, words said with no source."""
    def source(**body):
        return c.post("/api/sources", json={"fetch_cover": False, **body}).json()["id"]

    def quote(**body):
        r = c.post("/api/entries", json=body)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    art = source(title="L’Art de lire lentement", publisher="Éditions du Quai", year=2011, people={"author": ["Hélène Marceau"]})
    carnets = source(title="Carnets de marge", subtitle="Essai sur l’annotation", publisher="Éditions du Quai", year=2019,
                     people={"author": ["Hélène Marceau"]})
    memoire = source(title="Petite histoire de la mémoire", publisher="Presses d’exemple", year=1998,
                     people={"author": ["Paul Verdier"]})
    video = source(kind="video", title="Comment prendre des notes qui servent", publisher="Atelier Lecture", year=2024,
                   url="https://example.org/video", people={"speaker": ["Inès Moreau"], "about": ["Hélène Marceau"]})
    cours = source(kind="class", title="Histoire de l’art moderne — séance 4", publisher="Université d’exemple", year=2026,
                   people={"speaker": ["Camille Arnaud"]})
    ids = {"art": art, "carnets": carnets, "memoire": memoire, "video": video, "cours": cours, "q": {}}
    ids["q"]["lent"] = quote(source_id=art, page="12", text="Lire lentement n’est pas lire moins.",
                             topics=["lecture"], note="Pour l’introduction.")
    ids["q"]["marge"] = quote(source_id=art, page="57", text="Une marge vide est une conversation refusée.", topics=["annotation"])
    ids["q"]["souvenir"] = quote(source_id=art, page="143", text="On se souvient de ce qu’on en a fait.", topics=["mémoire", "lecture"])
    ids["q"]["ne"] = quote(source_id=carnets, page="xii", text="Ce livre est né dans les marges des autres.", topics=["annotation"])
    ids["q"]["souligner"] = quote(source_id=carnets, page="34", text="Souligner, c’est déjà choisir ce que l’on oubliera.",
                                  topics=["annotation", "mémoire"])
    ids["q"]["trie"] = quote(source_id=carnets, page="88", words_by="Paul Verdier", text="La mémoire n’archive pas, elle trie.",
                             topics=["mémoire"])
    ids["q"]["perte"] = quote(source_id=memoire, page="9", text="Toute mémoire commence par une perte acceptée.", topics=["mémoire"])
    ids["q"]["liens"] = quote(source_id=memoire, page="71", text="Les anciens apprenaient par lieux ; nous, par liens.",
                              topics=["mémoire", "méthode"])
    ids["q"]["fait"] = quote(source_id=video, text="Elle propose de noter ce que le livre nous fait.", topics=["annotation"])
    ids["q"]["cache"] = quote(source_id=cours, page="séance 4", text="Regardez d’abord ce que le tableau cache.", topics=["attention"])
    ids["q"]["dit"] = quote(words_by="Camille Arnaud", page="en cours, 14 octobre 2026", text="Le cadre fait partie du tableau.",
                            topics=["attention"])
    people = {p["name"]: p["id"] for p in c.get("/api/people").json()}
    c.patch(f"/api/people/{people['Hélène Marceau']}", json={"dates": "née en 1961"})
    ids["people"] = people
    note = lambda **b: c.post("/api/notes", json=b).json()["id"]  # noqa: E731
    ids["n"] = {
        "chapitre": note(title="Pour le chapitre 2", text="Trois gestes : souligner, commenter, relier.\n\nVoir la vidéo.",
                         people=[people["Hélène Marceau"]], topics=["annotation"]),
        "vitesses": note(title="Deux vitesses", text="Deux vitesses, une attention.", sources=[art, memoire], place="p. 60"),
        "lieux": note(text="L’art de la mémoire antique, en deux pages.", sources=[memoire], place="p. 70-72", topics=["mémoire"]),
        "tableau": note(title="Ce que cache le tableau", text="Les zones sombres d’abord.", sources=[cours], topics=["attention"]),
    }
    ids["topics"] = {t["name"]: t["id"] for t in c.get("/api/topics").json()}
    return ids


def text_of(item: dict) -> str:
    return item["text"] if item["type"] == "quote" else item["paras"][0]


def ref(item: dict) -> str:
    return "".join(r[0] for r in item["ref"])


def outline(doc: dict) -> list:
    """Each chapter with its parts, the sources in them and the first words of what each holds."""
    out = []
    for ch in doc["chapters"]:
        parts = []
        for s in ch["sections"]:
            parts.append((s["label"], [((g["head"] or {}).get("title"), [text_of(i)[:12] for i in g["items"]]) for g in s["groups"]]))
        out.append(("".join(r[0] for r in ch["title"]), parts))
    return out


@pytest.fixture()
def library(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        login(c, "", OWNER_PW)
        ids = fill(c)
        yield c, ids, db.connect(owner(settings).db_path)


def test_by_author_follows_the_person_page(library):
    c, ids, conn = library
    p = ids["people"]
    doc = export.build(conn, "author", [p["Paul Verdier"], p["Hélène Marceau"]], account="Dominique", today=date(2026, 11, 8))
    assert doc["subtitle"] == "Par auteur — Hélène Marceau, Paul Verdier"
    assert doc["byline"] == "Dominique · exporté le 8 novembre 2026 · 9 citations · 3 notes"   # each counted once
    assert outline(doc) == [
        ("Marceau, Hélène", [
            ("Notes", [(None, ["Trois gestes"])]),
            ("Œuvres", [("L’Art de lire lentement", ["Lire lenteme", "Une marge vi", "On se souvie", "Deux vitesse"]),
                        ("Carnets de marge", ["Ce livre est", "Souligner, c", "La mémoire n"])]),     # xii before 34
            ("À propos de Marceau", [("Comment prendre des notes qui servent", ["Elle propose"])]),
        ]),
        ("Verdier, Paul", [
            ("Œuvres", [("Petite histoire de la mémoire", ["Toute mémoir", "Les anciens ", "Deux vitesse", "L’art de la "])]),
            ("Cité ailleurs", [("Carnets de marge", ["La mémoire n"])]),          # his words in her book: in both chapters
        ]),
    ]
    assert doc["chapters"][0]["meta"] == "née en 1961"
    items = {text_of(i): i for ch in doc["chapters"] for s in ch["sections"] for g in s["groups"] for i in g["items"]}
    assert ref(items["Lire lentement n’est pas lire moins."]) == "Hélène Marceau, L’Art de lire lentement, p. 12"
    assert ref(items["La mémoire n’archive pas, elle trie."]) == "Paul Verdier, cité dans Hélène Marceau, Carnets de marge, p. 88"
    assert ref(items["Elle propose de noter ce que le livre nous fait."]) == "Inès Moreau, Comment prendre des notes qui servent"
    assert items["Lire lentement n’est pas lire moins."]["comment"] == "Pour l’introduction."
    assert items["Trois gestes : souligner, commenter, relier."]["paras"] == ["Trois gestes : souligner, commenter, relier.", "Voir la vidéo."]
    assert ["".join(r[0] for r in b) for b in doc["bibliography"]] == [
        "Marceau, Hélène, L’Art de lire lentement, Éditions du Quai, 2011.",
        "Marceau, Hélène, Carnets de marge. Essai sur l’annotation, Éditions du Quai, 2019.",
        "Moreau, Inès, Comment prendre des notes qui servent, vidéo, Atelier Lecture, 2024. https://example.org/video",
        "Verdier, Paul, Petite histoire de la mémoire, Presses d’exemple, 1998.",
    ]
    assert export.file_name(doc, "pdf") == "Marginote — Marceau, Verdier — 2026-11-08.pdf"


def test_by_topic_and_by_source(library):
    c, ids, conn = library
    t = ids["topics"]
    doc = export.build(conn, "topic", [t["mémoire"], t["annotation"]], today=date(2026, 11, 8))
    assert [o[0] for o in outline(doc)] == ["Annotation", "Mémoire"]                   # A to Z, with a capital
    annotation = dict(outline(doc)[0][1])
    assert annotation["Notes"] == [(None, ["Trois gestes"])]                           # its notes on no source first
    assert [g[0] for g in annotation["Sources"]] == ["L’Art de lire lentement", "Carnets de marge",
                                                      "Comment prendre des notes qui servent"]   # by author, then year
    memoire = dict(outline(doc)[1][1])["Sources"]
    assert ("Carnets de marge", ["Souligner, c", "La mémoire n"]) in memoire          # in both topics
    assert ("Petite histoire de la mémoire", ["Toute mémoir", "Les anciens ", "L’art de la "]) in memoire

    doc = export.build(conn, "source", None, said=True, include=("quotes", "notes"), today=date(2026, 11, 8))
    assert doc["subtitle"] == "Par source — toutes les sources" and doc["bibliography"] == []
    assert [o[0] for o in outline(doc)] == ["Histoire de l’art moderne — séance 4", "L’Art de lire lentement", "Carnets de marge",
                                            "Comment prendre des notes qui servent", "Petite histoire de la mémoire",
                                            "Paroles sans source"]
    cours = outline(doc)[0][1][0][1][0][1]
    assert cours == ["Les zones so", "Regardez d’a"]                                    # a class: your notes first
    said = doc["chapters"][-1]["sections"][0]["groups"][0]["items"][0]
    assert ref(said) == "Camille Arnaud, en cours, 14 octobre 2026"
    assert doc["chapters"][0]["meta"] == "Camille Arnaud · cours · Université d’exemple · 2026"
    only_notes = export.build(conn, "source", [ids["art"]], include=("notes",))
    assert [text_of(i) for i in only_notes["chapters"][0]["sections"][0]["groups"][0]["items"]] == ["Deux vitesses, une attention."]


def test_files_come_out_and_open(library, tmp_path):
    c, ids, conn = library
    p = ids["people"]
    choices = c.get("/api/export/choices").json()
    assert [a["name"] for a in choices["authors"]] == ["Arnaud, Camille", "Marceau, Hélène", "Moreau, Inès", "Verdier, Paul"]
    marceau = next(a for a in choices["authors"] if a["name"] == "Marceau, Hélène")
    assert marceau["works"] == {"book": 2} and marceau["quotes"] == 7 and marceau["notes"] == 2
    assert [s["title"] for s in choices["sources"]][:2] == ["Histoire de l’art moderne — séance 4", "L’Art de lire lentement"]
    assert choices["said"] == 1 and "mémoire" in [t["name"] for t in choices["topics"]]
    chosen = {"by": "author", "ids": [p["Hélène Marceau"], p["Paul Verdier"]]}
    assert c.post("/api/export/summary", json=chosen).json() == {"chapters": 2, "quotes": 9, "notes": 3}
    assert c.post("/api/export/summary", json={"by": "author"}).json()["chapters"] == 0
    assert c.post("/api/export", json={"by": "author"}).status_code == 422             # nothing chosen
    assert c.post("/api/export", json={**chosen, "quotes": False, "notes": False}).status_code == 422

    made = c.post("/api/export", json={**chosen, "format": "pdf"}).json()
    assert made["name"] == f"Marginote — Marceau, Verdier — {date.today().isoformat()}.pdf"
    cookies = dict(c.cookies)
    c.cookies.clear()                                   # the link works without the login: Safari has its own
    r = c.get(made["url"])
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf"
    assert unquote(r.headers["content-disposition"].split("filename*=UTF-8''")[1]) == made["name"]
    assert r.headers["cache-control"] == "no-store"
    assert c.get("/api/export/files/not-a-real-one").status_code == 404
    assert c.post("/api/export", json=chosen).status_code == 401                       # making one needs the login
    c.cookies.update(cookies)

    made = c.post("/api/export", json={**chosen, "format": "docx"}).json()
    r = c.get(made["url"])
    assert r.headers["content-disposition"].startswith("attachment;")
    word = docx.Document(io.BytesIO(r.content))
    texts = [par.text for par in word.paragraphs]
    assert "« La mémoire n’archive pas, elle trie. »" in texts
    assert "Paul Verdier, cité dans Hélène Marceau, Carnets de marge, p. 88" in texts
    styles = {par.style.name for par in word.paragraphs}
    assert {"Quote", "Référence", "Note", "Heading 1", "Heading 2", "Bibliographie", "toc 1", "toc 2"} <= styles
    body = word.element.body.xml
    links = body.count("<w:hyperlink ")
    assert links == body.count("<w:bookmarkStart ") == 9        # 2 authors, 6 of their parts and works, the bibliography
    assert 'TOC \\o "1-2"' in body


def test_whatever_a_quote_holds_prints(library):
    c, ids, conn = library
    odd = "#let x = 1 $a$ *gras* _souligné_ [crochets] \\ « guillemets » <b>&amp; {accolades} @ref // ✓ 🙂\nDeux lignes\x0b"
    c.post("/api/entries", json={"source_id": ids["art"], "page": "200", "text": odd, "note": "#import \"x\": *"})
    c.post("/api/notes", json={"title": "[Titre] #1", "text": "$$ ` ~ ^", "sources": [ids["art"]]})
    for fmt in ("pdf", "docx"):
        made = c.post("/api/export", json={"by": "source", "ids": [ids["art"]], "format": fmt})
        assert made.status_code == 200, made.text
        content = c.get(made.json()["url"]).content
        assert len(content) > 5000
    word = docx.Document(io.BytesIO(content))
    assert any("[crochets] \\ « guillemets » <b>&amp; {accolades}" in par.text for par in word.paragraphs)


def test_in_english_and_never_from_someone_else(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        login(c, "", OWNER_PW)
        fill(c)
        c.post("/api/accounts", json={"name": "Sam", "password": "sea-shells", "language": "en"})
        login(c, "Sam", "sea-shells")
        assert c.get("/api/export/choices").json() == {"authors": [], "topics": [], "sources": [], "said": 0}
        assert c.post("/api/export", json={"by": "source", "all": True}).status_code == 422   # her library is empty
        src = c.post("/api/sources", json={"title": "Sea Notes", "year": 2020, "people": {"author": ["Ann Lee"]},
                                           "fetch_cover": False}).json()["id"]
        c.post("/api/entries", json={"source_id": src, "page": "3", "text": "Waves keep time.", "words_by": "Bo Tan"})
        # the owner's ids point to nothing of the owner's here: each library has its own ids
        made = c.post("/api/export", json={"by": "source", "ids": list(range(1, 50)), "format": "docx"}).json()
        word = docx.Document(io.BytesIO(c.get(made["url"]).content))
        texts = "\n".join(par.text for par in word.paragraphs)
        assert "Marceau" not in texts and "Verdier" not in texts and "mémoire" not in texts
        assert "“Waves keep time.”" in texts and "Bo Tan, quoted in Ann Lee, Sea Notes, p. 3" in texts
        assert "Quotes and notes" in texts and "By source — Sea Notes" in texts and "Bibliography" in texts
        assert made["name"].startswith("Marginote — Sea Notes — ")
