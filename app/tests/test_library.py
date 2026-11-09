"""Sources of every kind, people, topics, notes, links, the upgrade from version 0.4, and backups."""

import io
import json
import sqlite3
import zipfile
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from marginote import backup, db, linkinfo, lookup, names
from marginote.main import create_app

from conftest import owner


@pytest.fixture(autouse=True)
def no_cover_search(monkeypatch):
    monkeypatch.setattr(lookup, "find_cover", lambda *a: None)


def new(client, **body):
    r = client.post("/api/sources", json={"fetch_cover": False, **body})
    assert r.status_code == 201, r.text
    return r.json()


def add(client, **body):
    r = client.post("/api/entries", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def section(page, key):
    found = next((s for s in page["sections"] if s["key"] == key), None)
    return {(g["source"]["title"] if g["source"] else None): [e["text"] for e in g["entries"]]
            for g in found["groups"]} if found else None


# ---------- names ----------

def test_names_are_written_and_sorted_as_in_an_index():
    assert names.display_and_sort("Baruch Spinoza") == ("Baruch Spinoza", "Spinoza, Baruch")
    assert names.display_and_sort("Lordon, Frédéric") == ("Frédéric Lordon", "Lordon, Frédéric")
    assert names.display_and_sort("Charles de Gaulle") == ("Charles de Gaulle", "Gaulle, Charles de")
    assert names.display_and_sort("Spinoza") == ("Spinoza", "Spinoza")
    assert names.match_key("Spinoza, Baruch (1632-1677)") == names.match_key("baruch SPINOZA")
    assert names.match_key("Frédéric Lordon") == names.match_key("Frederic Lordon")
    assert names.split_dates("Camus, Albert (1913-1960)") == ("Camus, Albert", "1913–1960")
    assert names.split_list("Gilles Deleuze, Félix Guattari") == ["Gilles Deleuze", "Félix Guattari"]
    assert names.split_list("Lordon, Frédéric") == ["Lordon, Frédéric"]
    assert names.split_list("Deleuze; Guattari") == ["Deleuze", "Guattari"]
    assert names.split_list("Marx et Engels") == ["Marx", "Engels"]
    assert names.split_list("") == []


# ---------- people and what appears on their page ----------

def test_lordon_on_spinoza_appears_on_both_pages(logged_in):
    """The example of the design: an entry is stored once and shown wherever it belongs."""
    book = new(logged_in, title="Capitalisme, désir et servitude", subtitle="Marx et Spinoza", publisher="La Fabrique",
               year=2010, people={"author": ["Frédéric Lordon"], "about": ["Baruch Spinoza", "Karl Marx"]},
               topics=["salariat"])
    ethique = new(logged_in, title="Éthique", people={"author": ["Spinoza, Baruch"], "translator": ["Charles Appuhn"]})
    review = new(logged_in, kind="article", title="Lire Lordon", url="https://revue.example/lire-lordon?utm_source=x#top",
                 publisher="revue.example", date="2026-10-02", people={"author": ["C. Martin"], "about": ["Frédéric Lordon"]})
    assert review["url"] == "https://revue.example/lire-lordon"          # without tracking or fragment

    people = {p["name"]: p for p in logged_in.get("/api/people").json()}
    assert set(people) == {"Frédéric Lordon", "Baruch Spinoza", "Karl Marx", "Charles Appuhn", "C. Martin"}
    spinoza, lordon, marx = people["Baruch Spinoza"]["id"], people["Frédéric Lordon"]["id"], people["Karl Marx"]["id"]

    on_conatus = add(logged_in, source_id=book["id"], text="Le conatus que le salariat enrôle.", page="57",
                     topics=["salariat", "désir"])
    assert {p["name"] for p in on_conatus["about"]} == {"Baruch Spinoza", "Karl Marx"}      # from its book
    assert all(p["from_source"] for p in on_conatus["about"])
    assert {t["name"] for t in on_conatus["topics"]} == {"salariat", "désir"}
    assert on_conatus["by"]["name"] == "Frédéric Lordon" and on_conatus["words_by"] is None

    quoted = add(logged_in, source_id=book["id"], text="Le désir est l'essence même de l'homme.", page="18",
                 words_by=spinoza, about=[])                                      # Spinoza's words, about nobody
    assert quoted["words_by"]["id"] == spinoza and quoted["about"] == []
    own = add(logged_in, source_id=ethique["id"], text="Chaque chose s'efforce de persévérer dans son être.", page="III, 6")
    assert add(logged_in, source_id=ethique["id"], text="x", words_by=spinoza)["words_by"] is None   # his own book

    lordon_page = logged_in.get(f"/api/people/{lordon}").json()
    assert section(lordon_page, "works") == {book["title"]: [quoted["text"], on_conatus["text"]]}   # page order
    assert section(lordon_page, "about") == {"Lire Lordon": []}             # the review, nothing captured yet

    spinoza_page = logged_in.get(f"/api/people/{spinoza}").json()
    assert section(spinoza_page, "works") == {"Éthique": [own["text"], "x"]}
    assert section(spinoza_page, "quoted") == {book["title"]: [quoted["text"]]}
    assert section(spinoza_page, "about") == {book["title"]: [on_conatus["text"]]}   # shown once, not twice

    appuhn = people["Charles Appuhn"]["id"]
    assert section(logged_in.get(f"/api/people/{appuhn}").json(), "translated") == {"Éthique": [own["text"], "x"]}

    # this passage is not about Marx: an exception for this entry only
    edited = logged_in.patch(f"/api/entries/{on_conatus['id']}", json={"about": [spinoza]}).json()
    assert [p["name"] for p in edited["about"]] == ["Baruch Spinoza"]
    assert section(logged_in.get(f"/api/people/{marx}").json(), "about") == {book["title"]: []}

    # what the source is about changes later: its entries follow, the exception stays
    logged_in.patch(f"/api/sources/{book['id']}", json={"people": {"about": [spinoza, marx, "Gilles Deleuze"]}})
    names_now = {p["name"] for p in logged_in.get(f"/api/entries/{on_conatus['id']}").json()["about"]}
    assert names_now == {"Baruch Spinoza", "Gilles Deleuze"}

    listed = {p["name"]: p for p in logged_in.get("/api/people").json()}
    assert listed["Baruch Spinoza"]["works"] == 1 and listed["Baruch Spinoza"]["quoted_in"] == 1
    assert listed["Baruch Spinoza"]["about_in"] == 1 and listed["Baruch Spinoza"]["entries"] == 4
    assert listed["Frédéric Lordon"]["works"] == 1 and listed["Frédéric Lordon"]["about_in"] == 1

    # the person filter of all entries gives what their page shows
    shown = logged_in.get("/api/entries", params={"person_id": spinoza}).json()
    assert {e["id"] for e in shown} == {on_conatus["id"], quoted["id"], own["id"]} | {e["id"] for e in shown if e["text"] == "x"}


def test_the_same_person_typed_twice_is_one_person(logged_in):
    a = new(logged_in, title="Éthique", people={"author": ["Baruch Spinoza"]})
    b = new(logged_in, title="Traité théologico-politique", people={"author": ["Spinoza, Baruch"]})
    assert a["people"]["author"][0]["id"] == b["people"]["author"][0]["id"]
    pid = a["people"]["author"][0]["id"]
    # another spelling, recorded on the person, is recognised too
    logged_in.patch(f"/api/people/{pid}", json={"aliases": ["Benedictus de Spinoza"], "dates": "1632–1677"})
    c = new(logged_in, title="Lettres", people={"author": ["Benedictus de Spinoza"]})
    assert c["people"]["author"][0]["id"] == pid
    # two entries for one person can still be merged; the name left becomes another spelling
    d = new(logged_in, title="Court traité", people={"author": ["B. Spinoza"]})
    other = d["people"]["author"][0]["id"]
    assert other != pid
    merged = logged_in.post(f"/api/people/{other}/merge", json={"into": pid}).json()
    assert merged["works"] == 4 and "B. Spinoza" in merged["aliases"] and merged["dates"] == "1632–1677"
    assert logged_in.get(f"/api/people/{other}").status_code == 404
    assert logged_in.post(f"/api/people/{pid}/merge", json={"into": pid}).status_code == 422
    # renamed: search follows
    add(logged_in, source_id=a["id"], text="Omnis determinatio est negatio.")
    logged_in.patch(f"/api/people/{pid}", json={"name": "Baruch de Spinoza"})
    person = logged_in.get(f"/api/people/{pid}").json()["person"]
    assert person["sort_name"] == "Spinoza, Baruch de"
    assert len(logged_in.get("/api/search", params={"q": "benedictus"}).json()) == 1


def test_people_nobody_points_to_are_forgotten(logged_in):
    s = new(logged_in, title="Essai", people={"author": ["Typo Nmae"]})
    logged_in.patch(f"/api/sources/{s['id']}", json={"people": {"author": ["Typo Name"]}})
    assert [p["name"] for p in logged_in.get("/api/people").json()] == ["Typo Name"]
    assert logged_in.post("/api/sources", json={"title": "x", "people": {"author": [9999]}}).status_code == 422
    assert logged_in.post("/api/sources", json={"title": "x", "people": {"author": ["   "]}}).status_code == 201


def test_deleting_a_person_keeps_their_sources_and_quotes(logged_in):
    s = new(logged_in, title="Essai", people={"author": ["Montaigne"], "about": ["La Boétie"]})
    e = add(logged_in, source_id=s["id"], text="Parce que c'était lui.")
    boetie = next(p["id"] for p in logged_in.get("/api/people").json() if p["name"] == "La Boétie")
    assert logged_in.delete(f"/api/people/{boetie}").status_code == 200
    assert logged_in.get(f"/api/entries/{e['id']}").json()["about"] == []
    assert logged_in.get(f"/api/sources/{s['id']}").json()["people"]["about"] == []
    assert logged_in.get("/api/search", params={"q": "boetie"}).json() == []


# ---------- topics ----------

def test_topics_follow_the_source_rename_merge_and_delete(logged_in):
    s = new(logged_in, title="Le Capital", people={"author": ["Karl Marx"]}, topics=["salariat"])
    e1 = add(logged_in, source_id=s["id"], text="La force de travail est une marchandise.", topics=["salariat", "travail"])
    e2 = add(logged_in, source_id=s["id"], text="Le capital est du travail mort.", topics=[])     # not about wages
    assert [t["name"] for t in e2["topics"]] == []
    topics = {t["name"]: t for t in logged_in.get("/api/topics").json()}
    assert topics["salariat"]["entries"] == 1 and topics["travail"]["entries"] == 1

    page = logged_in.get(f"/api/topics/{topics['salariat']['id']}").json()
    assert [e["id"] for e in page["entries"]] == [e1["id"]]
    assert [p["name"] for p in page["people"]] == ["Karl Marx"]
    assert [r["name"] for r in page["related"]] == ["travail"]

    # renamed into an existing name: the two become one
    merged = logged_in.patch(f"/api/topics/{topics['travail']['id']}", json={"name": "Salariat"}).json()
    assert merged["id"] == topics["salariat"]["id"] and merged["entries"] == 1
    assert [t["name"] for t in logged_in.get("/api/topics").json()] == ["salariat"]
    renamed = logged_in.patch(f"/api/topics/{merged['id']}", json={"name": "travail salarié"}).json()
    assert renamed["name"] == "travail salarié"
    assert logged_in.get("/api/search", params={"q": "salarie"}).json()[0]["id"] == e1["id"]
    assert logged_in.delete(f"/api/topics/{renamed['id']}").status_code == 200
    assert logged_in.get(f"/api/entries/{e1['id']}").json()["topics"] == []
    assert logged_in.get("/api/topics").json() == []


# ---------- notes ----------

def test_notes_on_people_and_topics(logged_in):
    s = new(logged_in, title="Éthique", people={"author": ["Baruch Spinoza"]})
    e = add(logged_in, source_id=s["id"], text="Le désir est l'essence même de l'homme.", topics=["désir"])
    spinoza = s["people"]["author"][0]["id"]
    n = logged_in.post("/api/notes", json={"title": "Le désir d'abord", "text": "On juge bonne une chose parce qu'on la désire.",
                                           "people": [spinoza, "Frédéric Lordon"], "topics": ["désir"], "entries": [e["id"]]})
    assert n.status_code == 201
    n = n.json()
    assert {p["name"] for p in n["people"]} == {"Baruch Spinoza", "Frédéric Lordon"}
    assert [x["id"] for x in n["entries"]] == [e["id"]]
    assert [x["title"] for x in logged_in.get(f"/api/people/{spinoza}").json()["notes"]] == ["Le désir d'abord"]
    desir = logged_in.get("/api/topics").json()[0]
    assert desir["notes"] == 1 and logged_in.get(f"/api/topics/{desir['id']}").json()["notes"][0]["id"] == n["id"]
    assert logged_in.get(f"/api/entries/{e['id']}").json()["notes"] == [{"id": n["id"], "title": "Le désir d'abord"}]
    lordon = next(p for p in logged_in.get("/api/people").json() if p["name"] == "Frédéric Lordon")
    assert lordon["notes"] == 1 and lordon["works"] == 0     # known only from the note

    assert [x["id"] for x in logged_in.get("/api/notes", params={"q": "desire"}).json()] == [n["id"]]
    assert [x["id"] for x in logged_in.get("/api/notes", params={"q": "lordon"}).json()] == [n["id"]]
    assert logged_in.get("/api/notes", params={"person_id": spinoza}).json()[0]["id"] == n["id"]
    changed = logged_in.patch(f"/api/notes/{n['id']}", json={"people": [spinoza], "text": "Plus court."}).json()
    assert changed["text"] == "Plus court." and len(changed["people"]) == 1
    assert all(p["name"] != "Frédéric Lordon" for p in logged_in.get("/api/people").json())   # forgotten
    assert logged_in.patch(f"/api/notes/{n['id']}", json={"text": "  "}).status_code == 422
    assert logged_in.post("/api/notes", json={"text": "x", "entries": [999]}).status_code == 422
    assert logged_in.delete(f"/api/notes/{n['id']}").status_code == 200
    assert logged_in.get("/api/notes", params={"q": "court"}).json() == []


# ---------- sources of any kind ----------

def test_a_video_its_notes_and_an_article_quote_link(logged_in):
    v = new(logged_in, kind="video", title="Spinoza : le conatus expliqué", url="https://youtu.be/abc?si=x",
            publisher="Philosophie à voix haute", date="2024-03", people={"about": ["Baruch Spinoza"]})
    assert v["url"] == "https://www.youtube.com/watch?v=abc" and v["date"] == "2024-03" and v["year"] is None
    c = logged_in.post("/api/notes", json={"sources": [v["id"]], "text": "Exposé clair."}).json()
    assert c["sources"][0]["id"] == v["id"]
    assert logged_in.post("/api/sources", json={"kind": "video", "title": "Doublon", "url": "youtube.com/watch?v=abc"}).status_code == 409
    assert logged_in.post("/api/sources", json={"title": "x", "date": "2 octobre"}).status_code == 422
    assert logged_in.post("/api/sources", json={"title": "x", "kind": "film"}).status_code == 422

    a = new(logged_in, kind="article", title="Un article", url="https://revue.example/a-b")
    q = add(logged_in, source_id=a["id"], text="Une phrase courte - avec un tiret, et une virgule.")
    assert q["link"] == "https://revue.example/a-b#:~:text=Une%20phrase%20courte%20%2D%20avec%20un%20tiret%2C%20et%20une%20virgule."
    long = add(logged_in, source_id=a["id"], text="un deux trois quatre cinq six sept huit neuf dix onze douze")
    assert long["link"].endswith("#:~:text=un%20deux%20trois%20quatre%20cinq,huit%20neuf%20dix%20onze%20douze")
    kinds = {s["kind"] for s in logged_in.get("/api/sources").json()}
    assert kinds == {"video", "article"}
    assert [s["title"] for s in logged_in.get("/api/sources", params={"kind": "video"}).json()] == [v["title"]]
    assert [e["id"] for e in logged_in.get("/api/entries", params={"medium": "article"}).json()] == [long["id"], q["id"]]


def test_words_someone_said_with_no_source(logged_in):
    said = add(logged_in, text="Le capitalisme est un régime de désir.", words_by="Frédéric Lordon",
               page="France Inter, 2024", about=["Baruch Spinoza"], topics=["désir"], note="À vérifier.")
    assert said["source"] is None and said["by"]["name"] == "Frédéric Lordon" and said["page"] == "France Inter, 2024"
    assert said["link"] is None and [p["name"] for p in said["about"]] == ["Baruch Spinoza"]
    assert not said["about"][0]["from_source"]
    assert logged_in.post("/api/entries", json={"text": "Personne ne l'a dit."}).status_code == 422
    people = {p["name"]: p for p in logged_in.get("/api/people").json()}
    lordon, spinoza = people["Frédéric Lordon"], people["Baruch Spinoza"]
    assert lordon["said"] == 1 and lordon["entries"] == 1 and spinoza["about_in"] == 0

    page = logged_in.get(f"/api/people/{lordon['id']}").json()
    assert section(page, "said") == {None: [said["text"]]}
    assert section(logged_in.get(f"/api/people/{spinoza['id']}").json(), "about") == {None: [said["text"]]}
    assert [e["id"] for e in logged_in.get("/api/entries", params={"medium": "said"}).json()] == [said["id"]]
    assert logged_in.get("/api/search", params={"q": "france inter"}).json()[0]["id"] == said["id"]
    topic = next(t for t in logged_in.get("/api/topics").json() if t["name"] == "désir")
    assert topic["entries"] == 1 and topic["sources"] == 0
    # its author cannot be deleted while it is theirs, only merged
    assert logged_in.delete(f"/api/people/{lordon['id']}").status_code == 409

    # a quote from a book, then from no source: it stays its author's words
    book = new(logged_in, title="Imperium", people={"author": ["Frédéric Lordon"]}, topics=["État"])
    q = add(logged_in, source_id=book["id"], text="Les corps politiques.")
    loose = logged_in.patch(f"/api/entries/{q['id']}", json={"source_id": None}).json()
    assert loose["source"] is None and loose["by"]["name"] == "Frédéric Lordon"
    assert [t["name"] for t in loose["topics"]] == ["État"]          # what it was about stays
    back = logged_in.patch(f"/api/entries/{q['id']}", json={"source_id": book["id"]}).json()
    assert back["source"]["id"] == book["id"] and back["by"]["name"] == "Frédéric Lordon"


def test_classes_and_notes_on_a_persons_works(logged_in):
    course = new(logged_in, kind="class", title="Histoire de l'art moderne", publisher="Université d'exemple",
                 year=2026, people={"speaker": ["Jeanne Dupont"]}, topics=["information"])
    assert course["kind"] == "class"
    n1 = logged_in.post("/api/notes", json={"sources": [course["id"]], "place": "Séance 3", "text": "Les fauves."}).json()
    n2 = logged_in.post("/api/notes", json={"sources": [course["id"]], "place": "Séance 1", "text": "Manet et Monet."}).json()
    assert [n["id"] for n in logged_in.get("/api/notes", params={"source_id": course["id"], "order": "place"}).json()] \
        == [n2["id"], n1["id"]]
    q = add(logged_in, source_id=course["id"], text="La couleur avant le dessin.")
    assert q["by"]["name"] == "Jeanne Dupont"
    dupont = next(p for p in logged_in.get("/api/people").json() if p["name"] == "Jeanne Dupont")
    page = logged_in.get(f"/api/people/{dupont['id']}").json()
    works = next(s for s in page["sections"] if s["key"] == "works")
    group = works["groups"][0]
    assert group["source"]["id"] == course["id"] and [e["id"] for e in group["entries"]] == [q["id"]]
    assert {n["id"] for n in group["notes"]} == {n1["id"], n2["id"]}
    # a note on her and on her class is shown once, with the class
    on_both = logged_in.post("/api/notes", json={"sources": [course["id"]], "people": [dupont["id"]], "text": "Très claire."}).json()
    page = logged_in.get(f"/api/people/{dupont['id']}").json()
    assert on_both["id"] in {n["id"] for n in page["sections"][0]["groups"][0]["notes"]}
    assert on_both["id"] not in {n["id"] for n in page["notes"]}
    listed = next(s for s in logged_in.get("/api/sources").json() if s["id"] == course["id"])
    assert listed["note_count"] == 3 and listed["quote_count"] == 1


def test_moving_an_entry_keeps_whom_it_is_about_and_takes_its_photo(logged_in, settings):
    from conftest import make_page
    a = new(logged_in, title="Tome un", people={"about": ["Napoléon"]}, topics=["empire"])
    b = new(logged_in, title="Tome deux")
    photo = logged_in.post("/api/photos", files={"file": ("p.jpg", make_page("12"), "image/jpeg")}).json()
    e = add(logged_in, source_id=a["id"], photo_id=photo["id"], text="Une page.")
    moved = logged_in.patch(f"/api/entries/{e['id']}", json={"source_id": b["id"]}).json()
    assert moved["source"]["id"] == b["id"]
    assert [p["name"] for p in moved["about"]] == ["Napoléon"] and [t["name"] for t in moved["topics"]] == ["empire"]
    conn = sqlite3.connect(owner(settings).db_path)
    path = conn.execute("SELECT path FROM photos WHERE id = ?", (photo["id"],)).fetchone()[0]
    conn.close()
    assert path.startswith(f"Tome deux ({b['id']})/") and (owner(settings).photos_dir / path).is_file()


def test_deleting_a_source_removes_its_entries_people_and_cover(logged_in, settings):
    s = new(logged_in, title="Essai", people={"author": ["Personne Seule"]}, topics=["seul"])
    logged_in.post(f"/api/sources/{s['id']}/cover", files={"file": ("c.png", _png(), "image/png")})
    add(logged_in, source_id=s["id"], text="Un mot.")
    assert (owner(settings).covers_dir / f"{s['id']}.webp").is_file()
    assert logged_in.delete(f"/api/sources/{s['id']}").status_code == 200
    assert logged_in.get("/api/entries").json() == [] and logged_in.get("/api/people").json() == []
    assert logged_in.get("/api/topics").json() == [] and not list(owner(settings).covers_dir.iterdir())
    assert logged_in.get("/api/search", params={"q": "mot"}).json() == []


def _png(size=(400, 600)) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", size, (47, 72, 88)).save(out, format="PNG")
    return out.getvalue()


# ---------- links: reading a page's details ----------

PAGE = """<!doctype html><html lang="fr-FR"><head><title>Lire Lordon - La Revue</title>
<meta property="og:site_name" content="La Revue">
<meta property="og:title" content="Lire Lordon : un structuralisme des passions ?">
<meta property="og:image" content="/img/une.jpg">
<meta property="article:published_time" content="2026-10-02T08:00:00+02:00">
<script type="application/ld+json">{"@graph": [{"@type": "NewsArticle", "author": [{"@type": "Person", "name": "Claire Martin"}]}]}</script>
</head><body><p>…</p></body></html>"""


def fake_web(monkeypatch, routes):
    def handler(request):
        for key, answer in routes.items():
            if key in str(request.url):
                return answer() if callable(answer) else answer
        return httpx.Response(404)
    monkeypatch.setattr(linkinfo, "check_public", lambda url: None)
    monkeypatch.setattr(linkinfo, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_a_link_is_read_and_becomes_a_source_with_its_picture(logged_in, settings, monkeypatch):
    fake_web(monkeypatch, {
        "revue.example/old": httpx.Response(301, headers={"location": "https://revue.example/lire-lordon"}),
        "revue.example/lire-lordon": httpx.Response(200, text=PAGE, headers={"content-type": "text/html; charset=utf-8"}),
        "revue.example/img/une.jpg": lambda: httpx.Response(200, content=_png((1200, 630)), headers={"content-type": "image/png"}),
    })
    info = logged_in.post("/api/lookup/link", json={"url": "revue.example/old?utm_campaign=x"}).json()
    assert info["title"] == "Lire Lordon : un structuralisme des passions ?" and info["site"] == "La Revue"
    assert info["people"] == ["Claire Martin"] and info["date"] == "2026-10-02" and info["language"] == "fr"
    assert info["kind"] == "article" and info["image_url"] == "https://revue.example/img/une.jpg"
    assert info["existing"] is None

    s = logged_in.post("/api/sources", json={"kind": info["kind"], "title": info["title"], "url": info["url"],
                                             "publisher": info["site"], "date": info["date"], "cover_url": info["image_url"],
                                             "people": {"author": info["people"]}}).json()
    assert s["cover_pending"] is True
    assert logged_in.get(f"/api/sources/{s['id']}").json()["has_cover"] is True     # fetched after the answer
    again = logged_in.post("/api/lookup/link", json={"url": "https://revue.example/old"}).json()
    assert again["existing"]["id"] == s["id"] or info["url"] != s["url"]


def test_videos_are_read_from_their_platform(logged_in, monkeypatch):
    fake_web(monkeypatch, {"youtube.com/oembed": httpx.Response(200, json={
        "title": "Spinoza : le conatus expliqué", "author_name": "Philosophie à voix haute", "provider_name": "YouTube",
        "thumbnail_url": "https://i.ytimg.com/vi/abc/hqdefault.jpg"})})
    info = logged_in.post("/api/lookup/link", json={"url": "https://youtu.be/abc"}).json()
    assert info["kind"] == "video" and info["site"] == "Philosophie à voix haute" and info["url"] == "https://www.youtube.com/watch?v=abc"


def test_a_link_that_cannot_be_read_is_still_usable(logged_in, monkeypatch):
    fake_web(monkeypatch, {"revue.example": httpx.Response(503)})
    info = logged_in.post("/api/lookup/link", json={"url": "https://revue.example/x"}).json()
    assert info["title"] is None and "503" in info["note"] and info["url"] == "https://revue.example/x"
    assert logged_in.post("/api/lookup/link", json={"url": "pas une adresse"}).status_code == 422


def test_addresses_inside_your_network_are_never_read():
    for url in ("http://192.168.1.10/admin", "http://localhost:8000/", "http://127.0.0.1/", "https://100.100.1.2/",
                "http://[::1]/", "http://10.0.0.1/", "ftp://example.org/file"):
        with pytest.raises(linkinfo.LinkError):
            linkinfo.check_public(url)


# ---------- ISBN lookup gives people ----------

def test_isbn_lookup_splits_authors_and_finds_the_book_already_there(logged_in, monkeypatch):
    monkeypatch.setattr(lookup, "lookup_isbn", lambda isbn: {"title": "Mille plateaux", "authors": "Gilles Deleuze, Félix Guattari",
                                                             "translator": None, "isbn": isbn, "source": "BnF"})
    found = logged_in.get("/api/lookup/isbn/9782707302076").json()
    assert found["people"] == {"author": ["Gilles Deleuze", "Félix Guattari"], "translator": []} and found["existing"] is None
    s = new(logged_in, title="Mille plateaux", isbn="9782707302076")
    assert logged_in.get("/api/lookup/isbn/9782707302076").json()["existing"]["id"] == s["id"]


# ---------- the upgrade from version 0.4 ----------

def make_v4_database(path):
    """A database as version 0.4 left it: books with author names in a field, tags, 'thought' entries."""
    conn = sqlite3.connect(path)
    for script in (db.SCHEMA_V1, db.SCHEMA_V2, db.SCHEMA_V3, db.SCHEMA_V4):
        conn.executescript(script)
    conn.execute("PRAGMA user_version = 4")
    t = "2026-11-01T10:00:00Z"
    conn.execute("INSERT INTO books (id, title, authors, translator, subject, cover_path, created_at, updated_at) VALUES "
                 "(3, 'Mille plateaux', 'Gilles Deleuze, Félix Guattari', NULL, 'Philosophie', '3.jpg', ?, ?)", (t, t))
    conn.execute("INSERT INTO books (id, title, authors, translator, created_at, updated_at) VALUES "
                 "(7, 'Éthique', 'Spinoza, Baruch', 'Charles Appuhn', ?, ?)", (t, t))
    words = [{"i": k, "text": w, "conf": 91.5, "x": 10 * k, "y": 20, "w": 9, "h": 12, "line": 0}
             for k, w in enumerate("Chaque chose s'efforce de persévérer".split())]
    conn.execute("INSERT INTO photos (id, path, width, height, sha256, ocr_json, detected_page, created_at, book_id, queued, status) "
                 "VALUES ('ph1', 'Éthique (7)/pIII - ph1.webp', 800, 1200, 'abc', ?, '57', ?, 7, 0, 'ready')",
                 (json.dumps(words), t))
    conn.execute("INSERT INTO entries (id, book_id, kind, text, note, page, page_sort, photo_id, word_start, word_end, created_at, updated_at) "
                 "VALUES (11, 7, 'quote', 'Chaque chose s''efforce', 'à relire', '57', 57, 'ph1', 0, 2, ?, ?)", (t, t))
    conn.execute("INSERT INTO entries (id, book_id, kind, text, created_at, updated_at) VALUES (12, 3, 'thought', 'Rhizome.', ?, ?)", (t, t))
    conn.execute("INSERT INTO tags (id, name) VALUES (5, 'conatus')")
    conn.execute("INSERT INTO entry_tags (entry_id, tag_id) VALUES (11, 5)")
    conn.execute("INSERT INTO entries_fts (rowid, text, note, book_title, authors, tags) VALUES (11, 'Chaque chose', '', 'Éthique', 'Spinoza', 'conatus')")
    conn.commit()
    conn.close()


def test_upgrade_from_version_0_4_keeps_everything(settings):
    settings.data_dir.mkdir(parents=True)
    make_v4_database(settings.db_path)
    with TestClient(create_app(settings)) as c:
        c.post("/api/login", json={"password": "correct horse"})
        sources = {s["id"]: s for s in c.get("/api/sources").json()}
        assert sources[3]["kind"] == "book" and sources[3]["field"] == "Philosophie"
        assert [p["name"] for p in sources[3]["people"]["author"]] == ["Gilles Deleuze", "Félix Guattari"]
        assert [p["name"] for p in sources[7]["people"]["author"]] == ["Baruch Spinoza"]
        assert [p["name"] for p in sources[7]["people"]["translator"]] == ["Charles Appuhn"]
        quote = c.get("/api/entries/11").json()
        assert quote["note"] == "à relire" and quote["page"] == "57" and [t["name"] for t in quote["topics"]] == ["conatus"]
        assert c.get("/api/entries/12").status_code == 404     # a comment: now a note on its source
        assert [n["text"] for n in c.get("/api/notes", params={"source_id": 3}).json()] == ["Rhizome."]
        photo = c.get("/api/photos/ph1").json()
        assert [w["text"] for w in photo["words"]][:2] == ["Chaque", "chose"] and photo["source_id"] == 7
        assert c.post("/api/photos/ph1/select", json={"start": 0, "end": 2}).json()["text"] == "Chaque chose s'efforce"
        assert c.get("/api/search", params={"q": "efforce"}).json()[0]["id"] == 11
        assert c.get("/api/search", params={"q": "appuhn"}).json()[0]["id"] == 11
        status = c.get("/api/backup/status").json()
        before = sorted(x["file"][:13] for x in status["copies"] if x["kind"] == "before upgrade")
        assert before == ["before-0.7.1-", "before-0.9.0-"]       # the move to users/owner, and the new shape
    # the copy made before the upgrade is the old database, ready to go back to version 0.4
    copy = next(owner(settings).backups_dir.glob("before-0.9.0-*.zip"))
    old = settings.data_dir / "old.db"
    old.write_bytes(zipfile.ZipFile(copy).read("marginote.db"))
    conn = sqlite3.connect(old)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 2
    conn.close()
    # starting again changes nothing and makes no new copy
    with TestClient(create_app(settings)):
        pass
    assert len(list(owner(settings).backups_dir.glob("before-*.zip"))) == 2
    conn = sqlite3.connect(owner(settings).db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.LATEST
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_upgrade_from_version_0_5_turns_comments_into_notes(settings, monkeypatch):
    settings.data_dir.mkdir(parents=True)
    make_v4_database(settings.db_path)
    with monkeypatch.context() as m:          # a database as version 0.5 left it
        m.setattr(db, "LATEST", 5)
        m.setattr(db, "_to_v6", lambda conn: None)
        db.migrate(settings.db_path)
    conn = db.connect(settings.db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    t = "2026-11-02T10:00:00Z"
    bergson = db.person_id(conn, "Henri Bergson")
    conn.execute("INSERT INTO entry_people (entry_id, person_id, included) VALUES (12, ?, 1)", (bergson,))
    conn.execute("INSERT INTO notes (id, title, text, created_at, updated_at) VALUES (4, 'Lien', 'Voir le rhizome.', ?, ?)", (t, t))
    conn.execute("INSERT INTO note_entries (note_id, entry_id, position) VALUES (4, 12, 0), (4, 11, 1)")
    conn.execute("UPDATE entries SET note = 'Chapitre 1.', page = '9' WHERE id = 12")
    conn.commit()
    conn.close()
    with TestClient(create_app(settings)) as c:
        c.post("/api/login", json={"password": "correct horse"})
        assert c.get("/api/entries/12").status_code == 404
        quote = c.get("/api/entries/11").json()
        assert quote["note"] == "à relire" and quote["source"]["id"] == 7
        rhizome = next(n for n in c.get("/api/notes", params={"source_id": 3}).json() if n["text"].startswith("Rhizome."))
        assert rhizome["text"] == "Rhizome.\n\nChapitre 1." and rhizome["place"] == "9"
        assert [p["name"] for p in rhizome["people"]] == ["Henri Bergson"] and rhizome["created_at"] == "2026-11-01T10:00:00Z"
        lien = c.get("/api/notes/4").json()
        assert [s["id"] for s in lien["sources"]] == [3] and [e["id"] for e in lien["entries"]] == [11]
        assert {s["id"]: s["note_count"] for s in c.get("/api/sources").json()}[3] == 2
        assert {n["id"] for n in c.get("/api/notes", params={"q": "mille plateaux"}).json()} == {4, rhizome["id"]}
        before = sorted(x["file"][:13] for x in c.get("/api/backup/status").json()["copies"] if x["kind"] == "before upgrade")
        assert before == ["before-0.7.1-", "before-0.9.0-"]
        assert c.post("/api/sources", json={"kind": "class", "title": "Un cours", "fetch_cover": False}).status_code == 201
    conn = sqlite3.connect(owner(settings).db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.LATEST
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_words_are_stored_compactly():
    words = [{"i": k, "text": f"mot{k}", "conf": 95.25, "x": 100 + k, "y": 200, "w": 40, "h": 18, "line": k // 10}
             for k in range(400)]
    packed = db.pack_words(words)
    assert len(packed) < len(json.dumps(words)) / 8
    back = db.unpack_words(packed)
    assert [w["text"] for w in back] == [w["text"] for w in words] and back[5]["conf"] == 95
    assert db.unpack_words(None) == []


# ---------- backups ----------

def test_backup_copies_are_zipped_and_kept_daily_then_monthly(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    dbfile = data / "marginote.db"
    sqlite3.connect(dbfile).execute("CREATE TABLE t (x)").connection.commit()
    copies = tmp_path / "backups"
    copies.mkdir()
    day = datetime(2026, 3, 1)
    for n in range(200):           # 200 nightly copies
        (copies / f"marginote-{day + timedelta(days=n):%Y-%m-%d}.zip").write_bytes(b"x")
    (copies / "before-0.5.0-2026-01-01-1200.zip").write_bytes(b"x")
    backup.prune(copies, keep=14, monthly=6)
    left = sorted(p.name for p in copies.iterdir())
    daily = [n for n in left if n.startswith("marginote-")]
    assert len(daily) == 14 + 6         # the last 14 days (3 to 16 September), and 1 April to 1 September
    assert "marginote-2026-09-16.zip" in daily and "marginote-2026-09-01.zip" in daily
    assert "marginote-2026-04-01.zip" in daily and "marginote-2026-03-01.zip" not in daily
    assert "before-0.5.0-2026-01-01-1200.zip" in left        # never removed

    old = copies / "marginote-2026-02-01.db"                  # a plain copy left by version 0.4
    sqlite3.connect(old).execute("CREATE TABLE t (x)").connection.commit()
    backup.compress_old_copies(copies)
    assert not old.exists() and zipfile.ZipFile(copies / "marginote-2026-02-01.zip").namelist() == ["marginote.db"]
    made = backup.snapshot(dbfile, copies, keep=14, monthly=6)
    assert made.suffix == ".zip" and not list(copies.glob(".*"))
