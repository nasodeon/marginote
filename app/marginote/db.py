"""SQLite storage: schema, connections and the full-text search index."""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_V1 = """
CREATE TABLE books (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    subtitle    TEXT,
    authors     TEXT,
    translator  TEXT,
    publisher   TEXT,
    edition     TEXT,
    year        INTEGER,
    isbn        TEXT,
    language    TEXT,
    status      TEXT NOT NULL DEFAULT 'reading'
                CHECK (status IN ('reading', 'paused', 'finished')),
    cover_path  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE photos (
    id            TEXT PRIMARY KEY,
    path          TEXT NOT NULL,
    width         INTEGER NOT NULL,
    height        INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    ocr_json      TEXT NOT NULL,
    detected_page TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX photos_sha256 ON photos (sha256);

CREATE TABLE entries (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER NOT NULL REFERENCES books (id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('quote', 'thought')),
    text        TEXT NOT NULL,
    note        TEXT,
    page        TEXT,
    page_sort   INTEGER,
    photo_id    TEXT REFERENCES photos (id) ON DELETE SET NULL,
    word_start  INTEGER,
    word_end    INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX entries_book ON entries (book_id);

CREATE TABLE tags (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE entry_tags (
    entry_id  INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (entry_id, tag_id)
);

-- Search index: accents and case are ignored ("memoire" finds "mémoire").
CREATE VIRTUAL TABLE entries_fts USING fts5 (
    text, note, book_title, authors, tags,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

MIGRATIONS = [SCHEMA_V1]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def migrate(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS, start=1):
            if version < number:
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {number}")
        conn.commit()
    finally:
        conn.close()


ROMAN = re.compile(r"^(?=[mdclxvi])m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.I)


def page_sort_key(page: str | None) -> int | None:
    """Turn '168' into 168 and roman numerals like 'xii' into negative numbers (front matter first)."""
    if not page:
        return None
    page = page.strip()
    if page.isdigit():
        return int(page)
    if ROMAN.match(page):
        values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
        total, prev = 0, 0
        for ch in reversed(page.lower()):
            val = values[ch]
            total = total - val if val < prev else total + val
            prev = max(prev, val)
        return -10000 + total
    digits = re.search(r"\d+", page)
    return int(digits.group()) if digits else None


# ---------- tags ----------

def clean_tag(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lstrip("#")).strip()


def set_entry_tags(conn: sqlite3.Connection, entry_id: int, names: list[str]) -> None:
    conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (entry_id,))
    seen: set[str] = set()
    for raw in names:
        name = clean_tag(raw)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        tag_id = row["id"] if row else conn.execute("INSERT INTO tags (name) VALUES (?)", (name,)).lastrowid
        conn.execute("INSERT OR IGNORE INTO entry_tags (entry_id, tag_id) VALUES (?, ?)", (entry_id, tag_id))
    conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM entry_tags)")


def entry_tags(conn: sqlite3.Connection, entry_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT t.name FROM tags t JOIN entry_tags et ON et.tag_id = t.id WHERE et.entry_id = ? ORDER BY t.name",
        (entry_id,),
    ).fetchall()
    return [r["name"] for r in rows]


# ---------- search index ----------

def reindex_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    conn.execute("DELETE FROM entries_fts WHERE rowid = ?", (entry_id,))
    row = conn.execute(
        """SELECT e.id, e.text, e.note, b.title, b.authors
           FROM entries e JOIN books b ON b.id = e.book_id WHERE e.id = ?""",
        (entry_id,),
    ).fetchone()
    if row is None:
        return
    conn.execute(
        "INSERT INTO entries_fts (rowid, text, note, book_title, authors, tags) VALUES (?, ?, ?, ?, ?, ?)",
        (row["id"], row["text"], row["note"] or "", row["title"], row["authors"] or "",
         " ".join(entry_tags(conn, entry_id))),
    )


def reindex_book(conn: sqlite3.Connection, book_id: int) -> None:
    for row in conn.execute("SELECT id FROM entries WHERE book_id = ?", (book_id,)).fetchall():
        reindex_entry(conn, row["id"])


def fts_query(user_text: str) -> str | None:
    """Make a safe FTS5 query: every word must match, as a prefix ("hypoth" finds "hypothèse")."""
    words = re.findall(r"[\w’']+", user_text, flags=re.UNICODE)
    words = [w.replace("'", " ").replace("’", " ") for w in words]
    tokens = [t for w in words for t in w.split() if t]
    if not tokens:
        return None
    return " ".join(f'"{t}"*' for t in tokens)
