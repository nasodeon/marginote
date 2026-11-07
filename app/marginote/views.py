"""How sources, people, topics, entries and notes are sent to the app (JSON), built with few queries."""

import sqlite3
from urllib.parse import quote

from fastapi import HTTPException

from . import db

# ---------- loading one thing, or a 404 ----------


def load(conn: sqlite3.Connection, table: str, row_id, what: str) -> sqlite3.Row:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"No {what} with this id")
    return row


def load_source(conn, source_id: int) -> sqlite3.Row:
    return load(conn, "sources", source_id, "source")


def load_person(conn, person_id: int) -> sqlite3.Row:
    return load(conn, "people", person_id, "person")


def load_topic(conn, topic_id: int) -> sqlite3.Row:
    return load(conn, "topics", topic_id, "topic")


def load_note(conn, note_id: int) -> sqlite3.Row:
    return load(conn, "notes", note_id, "note")


def load_photo(conn, photo_id: str) -> sqlite3.Row:
    return load(conn, "photos", photo_id, "photo")


# ---------- people ----------

def person_brief(row) -> dict:
    return {"id": row["id"], "name": row["name"], "sort_name": row["sort_name"]}


def people_by_id(conn, ids) -> dict[int, dict]:
    ids = [i for i in set(ids) if i is not None]
    out: dict[int, dict] = {}
    for part in db.chunks(ids):
        marks = ",".join("?" * len(part))
        for r in conn.execute(f"SELECT id, name, sort_name FROM people WHERE id IN ({marks})", part):
            out[r["id"]] = person_brief(r)
    return out


# ---------- sources ----------

SOURCE_FIELDS = ("kind", "title", "subtitle", "publisher", "edition", "year", "date", "isbn", "url", "language", "field")

SOURCE_LIST_SQL = """
SELECT s.*,
       (SELECT COUNT(*) FROM entries e WHERE e.source_id = s.id)                       AS quote_count,
       (SELECT COUNT(*) FROM note_sources ns WHERE ns.source_id = s.id)                AS note_count,
       NULLIF(MAX(COALESCE((SELECT MAX(e.created_at) FROM entries e WHERE e.source_id = s.id), ''),
                  COALESCE((SELECT MAX(n.updated_at) FROM notes n JOIN note_sources ns ON ns.note_id = n.id
                            WHERE ns.source_id = s.id), '')), '')                      AS last_entry_at
FROM sources s
"""


def _source_links(conn, source_ids: list[int]) -> tuple[dict, dict]:
    people: dict[int, dict[str, list]] = {}
    topics: dict[int, list[str]] = {}
    for part in db.chunks(source_ids):
        marks = ",".join("?" * len(part))
        for r in conn.execute(
            f"SELECT sp.source_id, sp.role, p.id, p.name, p.sort_name FROM source_people sp "
            f"JOIN people p ON p.id = sp.person_id WHERE sp.source_id IN ({marks}) ORDER BY sp.position", part
        ):
            people.setdefault(r["source_id"], {}).setdefault(r["role"], []).append(person_brief(r))
        for r in conn.execute(
            f"SELECT st.source_id, t.id, t.name FROM source_topics st JOIN topics t ON t.id = st.topic_id "
            f"WHERE st.source_id IN ({marks}) ORDER BY t.name COLLATE NOCASE", part
        ):
            topics.setdefault(r["source_id"], []).append({"id": r["id"], "name": r["name"]})
    return people, topics


def source_dicts(conn, rows) -> list[dict]:
    people, topics = _source_links(conn, [r["id"] for r in rows])
    out = []
    for r in rows:
        roles = people.get(r["id"], {})
        out.append({
            "id": r["id"],
            **{k: r[k] for k in SOURCE_FIELDS},
            "people": {role: roles.get(role, []) for role in db.ROLES},
            "topics": topics.get(r["id"], []),
            "has_cover": bool(r["cover"]),
            "cover_url": f"/api/sources/{r['id']}/cover?v={quote(r['updated_at'])}" if r["cover"] else None,
            "quote_count": r["quote_count"],
            "note_count": r["note_count"],
            "last_entry_at": r["last_entry_at"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return out


def source_dict(conn, source_id: int) -> dict:
    row = conn.execute(SOURCE_LIST_SQL + " WHERE s.id = ?", (source_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No source with this id")
    return source_dicts(conn, [row])[0]


def source_brief(row) -> dict:
    return {"id": row["id"], "kind": row["kind"], "title": row["title"]}


# ---------- entries ----------

ENTRY_SQL = f"""
SELECT e.*, s.title AS source_title, s.kind AS source_kind, s.url AS source_url, {db.BY_SQL} AS by_id
FROM entries e LEFT JOIN sources s ON s.id = e.source_id
"""


def passage_link(url: str | None, kind: str, text: str) -> str | None:
    """For a web article: a link that opens the page scrolled to the passage, highlighted (a 'text fragment',
    understood by Safari, Chrome and Edge; other browsers just open the page)."""
    if not url:
        return None
    if kind != "article":
        return url
    words = text.split()
    enc = lambda s: quote(s, safe="").replace("-", "%2D")  # noqa: E731
    if len(words) > 10:
        fragment = f"{enc(' '.join(words[:5]))},{enc(' '.join(words[-5:]))}"
    else:
        fragment = enc(" ".join(words))
    return f"{url.split('#')[0]}#:~:text={fragment}"


def entry_dicts(conn, rows) -> list[dict]:
    ids = [r["id"] for r in rows]
    about: dict[int, list] = {}
    topics: dict[int, list] = {}
    inherited_about: dict[int, set] = {}
    inherited_topics: dict[int, set] = {}
    for part in db.chunks(ids):
        marks = ",".join("?" * len(part))
        for r in conn.execute(
            f"SELECT ea.entry_id, p.id, p.name, p.sort_name FROM entry_about ea JOIN people p ON p.id = ea.person_id "
            f"WHERE ea.entry_id IN ({marks}) ORDER BY p.sort_name COLLATE NOCASE", part
        ):
            about.setdefault(r["entry_id"], []).append(person_brief(r))
        for r in conn.execute(
            f"SELECT et.entry_id, t.id, t.name FROM entry_topic et JOIN topics t ON t.id = et.topic_id "
            f"WHERE et.entry_id IN ({marks}) ORDER BY t.name COLLATE NOCASE", part
        ):
            topics.setdefault(r["entry_id"], []).append({"id": r["id"], "name": r["name"]})
        for r in conn.execute(
            f"SELECT e.id, sp.person_id FROM entries e JOIN source_people sp ON sp.source_id = e.source_id "
            f"AND sp.role = 'about' WHERE e.id IN ({marks})", part
        ):
            inherited_about.setdefault(r["id"], set()).add(r["person_id"])
        for r in conn.execute(
            f"SELECT e.id, st.topic_id FROM entries e JOIN source_topics st ON st.source_id = e.source_id "
            f"WHERE e.id IN ({marks})", part
        ):
            inherited_topics.setdefault(r["id"], set()).add(r["topic_id"])
    people = people_by_id(conn, [r["by_id"] for r in rows] + [r["words_by"] for r in rows])
    out = []
    for r in rows:
        by = people.get(r["by_id"])
        out.append({
            "id": r["id"],
            "text": r["text"],
            "note": r["note"],                                           # your comment on it
            "page": r["page"],                                           # with no source: where and when it was said
            "source": {"id": r["source_id"], "kind": r["source_kind"], "title": r["source_title"]}
            if r["source_id"] else None,
            "by": by,                                                    # whose words
            "words_by": people.get(r["words_by"]),                       # set only for a quote within a quote
            "about": [{**p, "from_source": p["id"] in inherited_about.get(r["id"], set())}
                      for p in about.get(r["id"], [])],
            "topics": [{**t, "from_source": t["id"] in inherited_topics.get(r["id"], set())}
                       for t in topics.get(r["id"], [])],
            "link": passage_link(r["source_url"], r["source_kind"], r["text"]) if r["source_id"] else None,
            "photo_id": r["photo_id"],
            "photo_url": f"/api/photos/{r['photo_id']}/image" if r["photo_id"] else None,
            "word_start": r["word_start"],
            "word_end": r["word_end"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return out


def entry_dict(conn, entry_id: int) -> dict:
    row = conn.execute(ENTRY_SQL + " WHERE e.id = ?", (entry_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No quote with this id")
    return entry_dicts(conn, [row])[0]


def entries_where(conn, where: str, args: tuple | list = (), order: str = "e.created_at DESC, e.id DESC",
                  limit: int = 5000, offset: int = 0) -> list[dict]:
    rows = conn.execute(f"{ENTRY_SQL} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                        (*args, limit, offset)).fetchall()
    return entry_dicts(conn, rows)


# ---------- notes ----------

def note_dicts(conn, rows, with_entries: bool = False) -> list[dict]:
    ids = [r["id"] for r in rows]
    people: dict[int, list] = {}
    topics: dict[int, list] = {}
    sources: dict[int, list] = {}
    entries: dict[int, list] = {}
    for part in db.chunks(ids):
        marks = ",".join("?" * len(part))
        for r in conn.execute(
            f"SELECT ns.note_id, s.id, s.kind, s.title FROM note_sources ns JOIN sources s ON s.id = ns.source_id "
            f"WHERE ns.note_id IN ({marks}) ORDER BY ns.position", part
        ):
            sources.setdefault(r["note_id"], []).append(source_brief(r))
        for r in conn.execute(
            f"SELECT np.note_id, p.id, p.name, p.sort_name FROM note_people np JOIN people p ON p.id = np.person_id "
            f"WHERE np.note_id IN ({marks}) ORDER BY p.sort_name COLLATE NOCASE", part
        ):
            people.setdefault(r["note_id"], []).append(person_brief(r))
        for r in conn.execute(
            f"SELECT nt.note_id, t.id, t.name FROM note_topics nt JOIN topics t ON t.id = nt.topic_id "
            f"WHERE nt.note_id IN ({marks}) ORDER BY t.name COLLATE NOCASE", part
        ):
            topics.setdefault(r["note_id"], []).append({"id": r["id"], "name": r["name"]})
        if with_entries:
            links = conn.execute(f"SELECT note_id, entry_id FROM note_entries WHERE note_id IN ({marks}) "
                                 f"ORDER BY position", part).fetchall()
            found = {e["id"]: e for e in entries_where(
                conn, f"e.id IN ({','.join('?' * len(links))})", [link["entry_id"] for link in links])} if links else {}
            for link in links:
                if link["entry_id"] in found:
                    entries.setdefault(link["note_id"], []).append(found[link["entry_id"]])
    return [{
        "id": r["id"], "title": r["title"], "text": r["text"], "place": r["place"],
        "sources": sources.get(r["id"], []), "people": people.get(r["id"], []), "topics": topics.get(r["id"], []),
        **({"entries": entries.get(r["id"], [])} if with_entries else {}),
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    } for r in rows]


def note_dict(conn, note_id: int) -> dict:
    return note_dicts(conn, [load_note(conn, note_id)], with_entries=True)[0]
