"""SQLite storage: schema, migrations, links between sources, people and topics, and the search index."""

import json
import re
import sqlite3
import zlib
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

from . import names

# ---------- schema ----------
# Versions 1-4 are kept exactly as they were, so a database of any age is brought up to date step by step.

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

CREATE VIRTUAL TABLE entries_fts USING fts5 (
    text, note, book_title, authors, tags,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

SCHEMA_V2 = "CREATE INDEX entries_photo ON entries (photo_id);"

SCHEMA_V3 = "ALTER TABLE books ADD COLUMN subject TEXT;"

SCHEMA_V4 = """
ALTER TABLE photos ADD COLUMN book_id INTEGER REFERENCES books(id) ON DELETE SET NULL;
ALTER TABLE photos ADD COLUMN queued  INTEGER NOT NULL DEFAULT 0;
ALTER TABLE photos ADD COLUMN status  TEXT NOT NULL DEFAULT 'ready';
CREATE INDEX photos_queued ON photos (queued);
"""

# Version 5: books become sources of any kind; authors become people; tags become topics; notes.
SCHEMA_V5 = """
CREATE TABLE sources (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL DEFAULT 'book'
                CHECK (kind IN ('book', 'ebook', 'article', 'video', 'podcast', 'talk', 'other')),
    title       TEXT NOT NULL,
    subtitle    TEXT,
    publisher   TEXT,              -- the publisher; for a web page the site, for a video the channel
    edition     TEXT,
    year        INTEGER,
    date        TEXT,              -- '2026-10-02' when known (articles, videos, talks)
    isbn        TEXT,
    url         TEXT,
    language    TEXT,
    field       TEXT,              -- what kind of work: 'Philosophie', 'Roman'
    cover       TEXT,              -- file name in covers/
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX sources_isbn ON sources (isbn);
CREATE INDEX sources_url ON sources (url);

CREATE TABLE people (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,     -- as usually written: 'Baruch Spinoza'
    sort_name   TEXT NOT NULL,     -- as in an index: 'Spinoza, Baruch'
    match_key   TEXT NOT NULL,     -- to recognise the same person typed again: 'baruch spinoza'
    dates       TEXT,              -- '1632–1677'
    aliases     TEXT,              -- other spellings, one per line
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX people_key ON people (match_key);

-- who made a source, and who it is about
CREATE TABLE source_people (
    source_id   INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('author', 'translator', 'editor', 'speaker', 'about')),
    position    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source_id, role, person_id)
);
CREATE INDEX source_people_person ON source_people (person_id);

CREATE TABLE topics (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE source_topics (
    source_id  INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    topic_id   INTEGER NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    PRIMARY KEY (source_id, topic_id)
);
CREATE INDEX source_topics_topic ON source_topics (topic_id);

CREATE TABLE photos_v5 (
    id            TEXT PRIMARY KEY,
    path          TEXT NOT NULL,           -- inside photos/
    width         INTEGER NOT NULL,
    height        INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    words         BLOB,                    -- the words read on it, compact and compressed (see pack_words)
    detected_page TEXT,
    source_id     INTEGER REFERENCES sources (id) ON DELETE SET NULL,
    queued        INTEGER NOT NULL DEFAULT 0,          -- 1: waiting in the inbox
    status        TEXT NOT NULL DEFAULT 'ready',       -- 'reading', 'ready' or 'failed'
    created_at    TEXT NOT NULL
);

CREATE TABLE entries_v5 (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('quote', 'comment')),
    text        TEXT NOT NULL,
    note        TEXT,
    page        TEXT,                      -- where in the source: '57', 'xii', 'III, 9 sc.', 'ch. 2'
    page_sort   INTEGER,
    words_by    INTEGER REFERENCES people (id) ON DELETE SET NULL,   -- a quote within a quote: whose words
    photo_id    TEXT REFERENCES photos (id) ON DELETE SET NULL,
    word_start  INTEGER,
    word_end    INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- An entry is about the people and topics of its source, plus these rows; included = 0 removes one
-- the source would give it ('this passage is not about Marx').
CREATE TABLE entry_people (
    entry_id   INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    included   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (entry_id, person_id)
);
CREATE INDEX entry_people_person ON entry_people (person_id);

CREATE TABLE entry_topics (
    entry_id   INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    topic_id   INTEGER NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    included   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (entry_id, topic_id)
);
CREATE INDEX entry_topics_topic ON entry_topics (topic_id);

CREATE TABLE notes (
    id          INTEGER PRIMARY KEY,
    title       TEXT,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE note_people (
    note_id    INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, person_id)
);
CREATE INDEX note_people_person ON note_people (person_id);
CREATE TABLE note_topics (
    note_id   INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    topic_id  INTEGER NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, topic_id)
);
CREATE INDEX note_topics_topic ON note_topics (topic_id);
CREATE TABLE note_entries (
    note_id   INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    entry_id  INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    position  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (note_id, entry_id)
);
CREATE INDEX note_entries_entry ON note_entries (entry_id);
"""

# created after the old tables are replaced
SCHEMA_V5_AFTER = """
CREATE INDEX photos_sha256 ON photos (sha256);
CREATE INDEX photos_queued ON photos (queued);
CREATE INDEX photos_source ON photos (source_id);
CREATE INDEX entries_source ON entries (source_id);
CREATE INDEX entries_photo ON entries (photo_id);
CREATE INDEX entries_words_by ON entries (words_by);
CREATE INDEX entries_created ON entries (created_at);

-- whom and what each entry is about, once its source's links and its own exceptions are combined
CREATE VIEW entry_about (entry_id, person_id) AS
    SELECT e.id, sp.person_id FROM entries e
    JOIN source_people sp ON sp.source_id = e.source_id AND sp.role = 'about'
    WHERE NOT EXISTS (SELECT 1 FROM entry_people x WHERE x.entry_id = e.id AND x.person_id = sp.person_id AND x.included = 0)
    UNION
    SELECT entry_id, person_id FROM entry_people WHERE included = 1;

CREATE VIEW entry_topic (entry_id, topic_id) AS
    SELECT e.id, st.topic_id FROM entries e
    JOIN source_topics st ON st.source_id = e.source_id
    WHERE NOT EXISTS (SELECT 1 FROM entry_topics x WHERE x.entry_id = e.id AND x.topic_id = st.topic_id AND x.included = 0)
    UNION
    SELECT entry_id, topic_id FROM entry_topics WHERE included = 1;

-- Search: accents and case are ignored ('memoire' finds 'mémoire').
CREATE VIRTUAL TABLE entries_fts USING fts5 (
    text, note, source, people, topics,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE VIRTUAL TABLE notes_fts USING fts5 (
    title, text, links,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

# 0.6: a quote can come from a person with no source; comments become notes, which can be on sources; classes.
# The old sources and entries tables are rebuilt (their CHECK constraints change); ids stay the same.
SCHEMA_V6 = """
CREATE TABLE sources_v6 (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL DEFAULT 'book'
                CHECK (kind IN ('book', 'ebook', 'article', 'video', 'podcast', 'class', 'talk', 'other')),
    title       TEXT NOT NULL,
    subtitle    TEXT,
    publisher   TEXT,              -- the publisher; for a web page the site, for a video the channel, for a class the school
    edition     TEXT,
    year        INTEGER,
    date        TEXT,              -- '2026-10-02' when known (articles, videos, talks)
    isbn        TEXT,
    url         TEXT,
    language    TEXT,
    field       TEXT,              -- what kind of work: 'Philosophie', 'Roman'
    cover       TEXT,              -- file name in covers/
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE entries_v6 (
    id          INTEGER PRIMARY KEY,
    source_id   INTEGER REFERENCES sources (id) ON DELETE CASCADE,   -- none: words someone said, from no source
    text        TEXT NOT NULL,
    note        TEXT,                      -- your comment on the quote
    page        TEXT,                      -- where in the source: '57', 'III, 9 sc.'; with no source, where and when
    page_sort   INTEGER,
    words_by    INTEGER REFERENCES people (id) ON DELETE SET NULL,   -- whose words, when not the source's author's
    photo_id    TEXT REFERENCES photos (id) ON DELETE SET NULL,
    word_start  INTEGER,
    word_end    INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    CHECK (source_id IS NOT NULL OR words_by IS NOT NULL)
);

CREATE TABLE note_sources (
    note_id    INTEGER NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    source_id  INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (note_id, source_id)
);
"""

SCHEMA_V6_AFTER = """
CREATE INDEX sources_isbn ON sources (isbn);
CREATE INDEX sources_url ON sources (url);
CREATE INDEX entries_source ON entries (source_id);
CREATE INDEX entries_photo ON entries (photo_id);
CREATE INDEX entries_words_by ON entries (words_by);
CREATE INDEX entries_created ON entries (created_at);
CREATE INDEX note_sources_source ON note_sources (source_id);

-- whom and what each quote is about, once its source's links and its own exceptions are combined
CREATE VIEW entry_about (entry_id, person_id) AS
    SELECT e.id, sp.person_id FROM entries e
    JOIN source_people sp ON sp.source_id = e.source_id AND sp.role = 'about'
    WHERE NOT EXISTS (SELECT 1 FROM entry_people x WHERE x.entry_id = e.id AND x.person_id = sp.person_id AND x.included = 0)
    UNION
    SELECT entry_id, person_id FROM entry_people WHERE included = 1;

CREATE VIEW entry_topic (entry_id, topic_id) AS
    SELECT e.id, st.topic_id FROM entries e
    JOIN source_topics st ON st.source_id = e.source_id
    WHERE NOT EXISTS (SELECT 1 FROM entry_topics x WHERE x.entry_id = e.id AND x.topic_id = st.topic_id AND x.included = 0)
    UNION
    SELECT entry_id, topic_id FROM entry_topics WHERE included = 1;
"""

# Version 7: scientific articles (DOI, arXiv, journal…), PDFs kept with their source (each page stored like a
# photo, its words read from the PDF), the text of those pages for finding a passage sent from another app,
# passages waiting for a source, and what is being read now.
SCHEMA_V7 = """
ALTER TABLE sources ADD COLUMN doi TEXT;
ALTER TABLE sources ADD COLUMN arxiv TEXT;
ALTER TABLE sources ADD COLUMN journal TEXT;         -- the journal or the collection an article is in
ALTER TABLE sources ADD COLUMN volume TEXT;
ALTER TABLE sources ADD COLUMN issue TEXT;
ALTER TABLE sources ADD COLUMN pages TEXT;           -- an article's pages in its journal: '45-56', 'e1043'
CREATE INDEX sources_doi ON sources (doi);
CREATE INDEX sources_arxiv ON sources (arxiv);

CREATE TABLE documents (
    id          TEXT PRIMARY KEY,
    source_id   INTEGER REFERENCES sources (id) ON DELETE SET NULL,
    path        TEXT NOT NULL,                       -- inside pdfs/
    name        TEXT,                                -- the file's name when it was sent
    sha256      TEXT NOT NULL,
    pages       INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'reading',     -- 'reading', 'ready' or 'failed'
    read_pages  INTEGER NOT NULL DEFAULT 0,          -- how far the reading has gone
    queued      INTEGER NOT NULL DEFAULT 1,          -- 1: in À trier
    found       TEXT,                                -- what was recognised in it (JSON)
    created_at  TEXT NOT NULL
);
CREATE INDEX documents_source ON documents (source_id);
CREATE INDEX documents_sha256 ON documents (sha256);
ALTER TABLE photos ADD COLUMN document_id TEXT REFERENCES documents (id) ON DELETE CASCADE;
ALTER TABLE photos ADD COLUMN page_index INTEGER;    -- 0 for a PDF's first page
CREATE INDEX photos_document ON photos (document_id, page_index);
-- the text of every PDF page, to find in which one a passage sent from a reader is
CREATE VIRTUAL TABLE page_fts USING fts5 (photo_id UNINDEXED, text, tokenize = 'unicode61 remove_diacritics 2');

CREATE TABLE waiting (
    id          INTEGER PRIMARY KEY,
    text        TEXT,
    note        TEXT,                                -- a comment sent with it
    url         TEXT,
    title       TEXT,
    origin      TEXT,                                -- 'windows', 'iphone', 'android', 'web', 'app'
    source_id   INTEGER REFERENCES sources (id) ON DELETE SET NULL,   -- a guess, to confirm
    guess       TEXT,                                -- where in a PDF it may be (JSON), to confirm
    reason      TEXT,                                -- why it waits: 'source', 'place'
    created_at  TEXT NOT NULL
);

CREATE TABLE library_state (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
"""

LATEST = 7
MAKER_ROLES = ("author", "editor", "speaker")      # roles that make a person's "works"
ROLES = ("author", "translator", "editor", "speaker", "about")
KINDS = ("book", "ebook", "article", "video", "podcast", "class", "talk", "other")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Connection(sqlite3.Connection):
    """A connection that knows whose library it opened: image addresses carry it, so a browser shared by two
    people never shows one the other's cached cover."""
    library = ""


def connect(db_path: Path, library: str = "") -> Connection:
    # Each request gets its own connection, but the web framework may open it in one worker thread and
    # close it in another: allowed here, since a connection is never used by two requests at once.
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False, factory=Connection)
    conn.library = library
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -4000")   # 4 MB of page cache per connection is plenty here
    return conn


def version(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def migrate(db_path: Path, before_upgrade: Callable[[int], None] | None = None) -> bool:
    """Bring the database up to date. Calls before_upgrade(old_version) first when an existing database
    is about to change shape (to keep a copy). Returns True when anything was changed."""
    old = version(db_path)
    if old >= LATEST:
        return False
    if old > 0 and before_upgrade:
        before_upgrade(old)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")   # stored in the file: set once, applies to every connection
        for number, script in enumerate([SCHEMA_V1, SCHEMA_V2, SCHEMA_V3, SCHEMA_V4], start=1):
            if old < number:
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {number}")
        conn.commit()
        if old < 5:
            _to_v5(conn)
        if old < 6:
            _to_v6(conn)
        if old < 7 <= LATEST:
            conn.execute("BEGIN")
            for statement in _statements(SCHEMA_V7):
                conn.execute(statement)
            conn.execute("PRAGMA user_version = 7")
            conn.commit()
        if old > 0:
            conn.execute("VACUUM")   # give back the space the old tables took
    finally:
        conn.close()
    return True


def _to_v5(conn: sqlite3.Connection) -> None:
    """Books -> sources, author strings -> people, tags -> topics, OCR words compressed. Nothing is lost:
    the ids of books, entries, tags and photos stay the same."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        for statement in _statements(SCHEMA_V5):
            conn.execute(statement)
        stamp = now()
        books = conn.execute("SELECT * FROM books ORDER BY id").fetchall()
        for b in books:
            conn.execute(
                "INSERT INTO sources (id, kind, title, subtitle, publisher, edition, year, isbn, language, field, cover, "
                "created_at, updated_at) VALUES (?, 'book', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (b["id"], b["title"], b["subtitle"], b["publisher"], b["edition"], b["year"], b["isbn"], b["language"],
                 b["subject"], b["cover_path"], b["created_at"], b["updated_at"]),
            )
            for role, text in (("author", b["authors"]), ("translator", b["translator"])):
                for position, name in enumerate(names.split_list(text)):
                    person = person_id(conn, name, stamp)
                    conn.execute("INSERT OR IGNORE INTO source_people (source_id, person_id, role, position) VALUES (?, ?, ?, ?)",
                                 (b["id"], person, role, position))
        conn.execute("INSERT INTO topics (id, name) SELECT id, name FROM tags")
        conn.execute("INSERT INTO entry_topics (entry_id, topic_id, included) SELECT entry_id, tag_id, 1 FROM entry_tags")
        conn.execute(
            "INSERT INTO entries_v5 (id, source_id, kind, text, note, page, page_sort, photo_id, word_start, word_end, "
            "created_at, updated_at) SELECT id, book_id, CASE kind WHEN 'quote' THEN 'quote' ELSE 'comment' END, text, note, "
            "page, page_sort, photo_id, word_start, word_end, created_at, updated_at FROM entries"
        )
        for p in conn.execute("SELECT * FROM photos").fetchall():
            try:
                words = json.loads(p["ocr_json"] or "[]")
            except ValueError:
                words = []
            conn.execute(
                "INSERT INTO photos_v5 (id, path, width, height, sha256, words, detected_page, source_id, queued, status, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p["id"], p["path"], p["width"], p["height"], p["sha256"], pack_words(words), p["detected_page"],
                 p["book_id"], p["queued"], p["status"], p["created_at"]),
            )
        for table in ("entries_fts", "entry_tags", "tags", "entries", "photos", "books"):
            conn.execute(f"DROP TABLE {table}")
        conn.execute("ALTER TABLE entries_v5 RENAME TO entries")
        conn.execute("ALTER TABLE photos_v5 RENAME TO photos")
        for statement in _statements(SCHEMA_V5_AFTER):
            conn.execute(statement)
        for (entry_id,) in conn.execute("SELECT id FROM entries").fetchall():
            reindex_entry(conn, entry_id)
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise RuntimeError(f"Database upgrade stopped: {len(problems)} broken links")
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _to_v6(conn: sqlite3.Connection) -> None:
    """Comments become notes on their source, about the same people and topics; a note that pointed to a
    comment now points to its source. Quotes keep their ids; nothing else changes."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        # what each comment is about, read while the views still exist
        comments = conn.execute(
            "SELECT * FROM entries WHERE kind = 'comment' AND photo_id IS NULL ORDER BY id").fetchall()
        links = {}
        for c in comments:
            people = [r[0] for r in conn.execute("SELECT person_id FROM entry_about WHERE entry_id = ?", (c["id"],))]
            if c["words_by"]:
                people.append(c["words_by"])
            topics = [r[0] for r in conn.execute("SELECT topic_id FROM entry_topic WHERE entry_id = ?", (c["id"],))]
            refs = [r[0] for r in conn.execute("SELECT note_id FROM note_entries WHERE entry_id = ?", (c["id"],))]
            links[c["id"]] = (list(dict.fromkeys(people)), list(dict.fromkeys(topics)), refs)
        conn.execute("DROP VIEW entry_about")
        conn.execute("DROP VIEW entry_topic")
        for statement in _statements(SCHEMA_V6):
            conn.execute(statement)
        conn.execute("ALTER TABLE notes ADD COLUMN place TEXT")    # where in its source: page, chapter, session
        conn.execute("INSERT INTO sources_v6 SELECT id, kind, title, subtitle, publisher, edition, year, date, isbn, "
                     "url, language, field, cover, created_at, updated_at FROM sources")
        conn.execute("DROP TABLE sources")
        conn.execute("ALTER TABLE sources_v6 RENAME TO sources")
        comment_ids = [c["id"] for c in comments]
        conn.execute("INSERT INTO entries_v6 SELECT id, source_id, text, note, page, page_sort, words_by, photo_id, "
                     "word_start, word_end, created_at, updated_at FROM entries WHERE id NOT IN "
                     f"({','.join(str(int(i)) for i in comment_ids) or '-1'})")
        for c in comments:
            people, topics, refs = links[c["id"]]
            text = c["text"] + (f"\n\n{c['note']}" if c["note"] else "")
            note_id = conn.execute(
                "INSERT INTO notes (title, text, place, created_at, updated_at) VALUES (NULL, ?, ?, ?, ?)",
                (text, c["page"], c["created_at"], c["updated_at"])).lastrowid
            conn.execute("INSERT INTO note_sources (note_id, source_id, position) VALUES (?, ?, 0)", (note_id, c["source_id"]))
            for pid in people:
                conn.execute("INSERT OR IGNORE INTO note_people (note_id, person_id) VALUES (?, ?)", (note_id, pid))
            for tid in topics:
                conn.execute("INSERT OR IGNORE INTO note_topics (note_id, topic_id) VALUES (?, ?)", (note_id, tid))
            for ref in refs:
                conn.execute("INSERT OR IGNORE INTO note_sources (note_id, source_id, position) VALUES (?, ?, "
                             "(SELECT COUNT(*) FROM note_sources WHERE note_id = ?))", (ref, c["source_id"], ref))
            for table in ("entry_people", "entry_topics", "note_entries"):
                conn.execute(f"DELETE FROM {table} WHERE entry_id = ?", (c["id"],))
            conn.execute("DELETE FROM entries_fts WHERE rowid = ?", (c["id"],))
        conn.execute("DROP TABLE entries")
        conn.execute("ALTER TABLE entries_v6 RENAME TO entries")
        for statement in _statements(SCHEMA_V6_AFTER):
            conn.execute(statement)
        for (note_id,) in conn.execute("SELECT id FROM notes").fetchall():
            reindex_note(conn, note_id)
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise RuntimeError(f"Database upgrade stopped: {len(problems)} broken links")
        conn.execute("PRAGMA user_version = 6")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _statements(script: str) -> list[str]:
    """Split a schema script into statements (none of ours has a ';' inside a string or a trigger)."""
    return [part.strip() for part in re.sub(r"--[^\n]*", "", script).split(";") if part.strip()]


# ---------- recognised words, stored compactly ----------
# [[text, conf, x, y, w, h, line], ...] in reading order, compressed: about a tenth of the plain JSON.

def pack_words(words: list[dict]) -> bytes:
    ordered = sorted(words, key=lambda w: w["i"])
    rows = []
    for k, w in enumerate(ordered):
        row = [w["text"], round(float(w["conf"])), w["x"], w["y"], w["w"], w["h"], w["line"]]
        if w["i"] != k:
            row.append(w["i"])        # never happens with words read by this app; kept so nothing shifts
        rows.append(row)
    return zlib.compress(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode(), 9)


def unpack_words(blob: bytes | None) -> list[dict]:
    if not blob:
        return []
    rows = json.loads(zlib.decompress(blob))
    return [{"i": row[7] if len(row) > 7 else k, "text": row[0], "conf": row[1], "x": row[2], "y": row[3],
             "w": row[4], "h": row[5], "line": row[6]} for k, row in enumerate(rows)]


# ---------- pages ----------

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


# ---------- people ----------

PersonRef = int | str     # an existing person's id, or a name to find or create


def person_id(conn: sqlite3.Connection, ref: PersonRef, stamp: str | None = None) -> int:
    """The id of a person given by id, or by name: an existing person with the same name (or one of their
    other spellings) is reused, otherwise one is created."""
    if isinstance(ref, int):
        if not conn.execute("SELECT 1 FROM people WHERE id = ?", (ref,)).fetchone():
            raise KeyError(ref)
        return ref
    bare, dates = names.split_dates(ref)
    key = names.match_key(bare)
    if not key:
        raise ValueError("empty name")
    row = conn.execute("SELECT id, dates FROM people WHERE match_key = ? ORDER BY id LIMIT 1", (key,)).fetchone()
    if row is None:   # one of someone's other spellings?
        for cand in conn.execute("SELECT id, aliases FROM people WHERE aliases IS NOT NULL"):
            if any(names.match_key(a) == key for a in cand["aliases"].splitlines()):
                row = cand
                break
    if row is not None:
        if dates and not row["dates"]:
            conn.execute("UPDATE people SET dates = ? WHERE id = ?", (dates, row["id"]))
        return row["id"]
    name, sort = names.display_and_sort(bare)
    stamp = stamp or now()
    return conn.execute(
        "INSERT INTO people (name, sort_name, match_key, dates, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, sort, key, dates, stamp, stamp),
    ).lastrowid


def set_source_people(conn: sqlite3.Connection, source_id: int, roles: dict[str, list[PersonRef]]) -> None:
    """Replace the people of the given roles ({'author': ['Frédéric Lordon'], 'about': [12]})."""
    for role, refs in roles.items():
        conn.execute("DELETE FROM source_people WHERE source_id = ? AND role = ?", (source_id, role))
        for position, ref in enumerate(refs):
            conn.execute("INSERT OR IGNORE INTO source_people (source_id, person_id, role, position) VALUES (?, ?, ?, ?)",
                         (source_id, person_id(conn, ref), role, position))


def forget_unused_people(conn: sqlite3.Connection) -> None:
    """People nothing points to any more (a typo replaced, a source deleted) are removed."""
    conn.execute(
        "DELETE FROM people WHERE id NOT IN (SELECT person_id FROM source_people) "
        "AND id NOT IN (SELECT person_id FROM entry_people) "
        "AND id NOT IN (SELECT words_by FROM entries WHERE words_by IS NOT NULL) "
        "AND id NOT IN (SELECT person_id FROM note_people)"
    )


# ---------- topics ----------

def clean_topic(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lstrip("#")).strip()


def topic_id(conn: sqlite3.Connection, name: str) -> int | None:
    name = clean_topic(name)
    if not name:
        return None
    row = conn.execute("SELECT id FROM topics WHERE name = ?", (name,)).fetchone()
    return row["id"] if row else conn.execute("INSERT INTO topics (name) VALUES (?)", (name,)).lastrowid


def topic_ids(conn: sqlite3.Connection, topic_names: Iterable[str]) -> list[int]:
    out: list[int] = []
    for name in topic_names:
        tid = topic_id(conn, name)
        if tid is not None and tid not in out:
            out.append(tid)
    return out


def set_source_topics(conn: sqlite3.Connection, source_id: int, topic_names: list[str]) -> None:
    conn.execute("DELETE FROM source_topics WHERE source_id = ?", (source_id,))
    for tid in topic_ids(conn, topic_names):
        conn.execute("INSERT INTO source_topics (source_id, topic_id) VALUES (?, ?)", (source_id, tid))


def forget_unused_topics(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM topics WHERE id NOT IN (SELECT topic_id FROM entry_topics WHERE included = 1) "
        "AND id NOT IN (SELECT topic_id FROM source_topics) AND id NOT IN (SELECT topic_id FROM note_topics)"
    )


# ---------- an entry's people and topics ----------

def set_entry_about(conn: sqlite3.Connection, entry_id: int, refs: list[PersonRef]) -> None:
    """Make the entry about exactly these people: stores only what differs from its source."""
    source_id = conn.execute("SELECT source_id FROM entries WHERE id = ?", (entry_id,)).fetchone()[0]
    wanted = [person_id(conn, r) for r in refs]
    inherited = {r[0] for r in conn.execute(
        "SELECT person_id FROM source_people WHERE source_id = ? AND role = 'about'", (source_id,))}
    conn.execute("DELETE FROM entry_people WHERE entry_id = ?", (entry_id,))
    for pid in dict.fromkeys(wanted):
        if pid not in inherited:
            conn.execute("INSERT INTO entry_people (entry_id, person_id, included) VALUES (?, ?, 1)", (entry_id, pid))
    for pid in inherited - set(wanted):
        conn.execute("INSERT INTO entry_people (entry_id, person_id, included) VALUES (?, ?, 0)", (entry_id, pid))


def set_entry_topics(conn: sqlite3.Connection, entry_id: int, topic_names: list[str]) -> None:
    source_id = conn.execute("SELECT source_id FROM entries WHERE id = ?", (entry_id,)).fetchone()[0]
    wanted = topic_ids(conn, topic_names)
    inherited = {r[0] for r in conn.execute("SELECT topic_id FROM source_topics WHERE source_id = ?", (source_id,))}
    conn.execute("DELETE FROM entry_topics WHERE entry_id = ?", (entry_id,))
    for tid in wanted:
        if tid not in inherited:
            conn.execute("INSERT INTO entry_topics (entry_id, topic_id, included) VALUES (?, ?, 1)", (entry_id, tid))
    for tid in inherited - set(wanted):
        conn.execute("INSERT INTO entry_topics (entry_id, topic_id, included) VALUES (?, ?, 0)", (entry_id, tid))


def keep_entry_links(conn: sqlite3.Connection, entry_id: int, new_source_id: int) -> None:
    """Before moving an entry to another source: keep it about the same people and topics."""
    about = [r[0] for r in conn.execute("SELECT person_id FROM entry_about WHERE entry_id = ?", (entry_id,))]
    topics = [r[0] for r in conn.execute(
        "SELECT t.name FROM entry_topic et JOIN topics t ON t.id = et.topic_id WHERE et.entry_id = ?", (entry_id,))]
    conn.execute("UPDATE entries SET source_id = ? WHERE id = ?", (new_source_id, entry_id))
    set_entry_about(conn, entry_id, about)
    set_entry_topics(conn, entry_id, topics)


# whose words an entry holds: the person named, else the source's first author (or speaker, or editor)
BY_SQL = (
    "COALESCE(e.words_by, (SELECT sp.person_id FROM source_people sp WHERE sp.source_id = e.source_id "
    "AND sp.role IN ('author', 'speaker', 'editor') "
    "ORDER BY CASE sp.role WHEN 'author' THEN 0 WHEN 'speaker' THEN 1 ELSE 2 END, sp.position LIMIT 1))"
)


# ---------- search index ----------

def reindex_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    conn.execute("DELETE FROM entries_fts WHERE rowid = ?", (entry_id,))
    row = conn.execute(
        "SELECT e.id, e.text, e.note, e.page, e.words_by, e.source_id, s.title, s.subtitle, s.publisher "
        "FROM entries e LEFT JOIN sources s ON s.id = e.source_id WHERE e.id = ?", (entry_id,)
    ).fetchone()
    if row is None:
        return
    people = [r[0] for r in conn.execute(
        "SELECT p.name || ' ' || COALESCE(p.aliases, '') FROM people p WHERE p.id IN ("
        "SELECT person_id FROM source_people WHERE source_id = ? UNION SELECT person_id FROM entry_about WHERE entry_id = ? "
        "UNION SELECT ?)", (row["source_id"], entry_id, row["words_by"]))]
    topics = [r[0] for r in conn.execute(
        "SELECT t.name FROM entry_topic et JOIN topics t ON t.id = et.topic_id WHERE et.entry_id = ?", (entry_id,))]
    conn.execute(
        "INSERT INTO entries_fts (rowid, text, note, source, people, topics) VALUES (?, ?, ?, ?, ?, ?)",
        (row["id"], row["text"], row["note"] or "",
         " ".join(filter(None, (row["title"], row["subtitle"], row["publisher"]) if row["source_id"] else (row["page"],))),
         " ".join(people), " ".join(topics)),
    )


def reindex_source(conn: sqlite3.Connection, source_id: int) -> None:
    for (entry_id,) in conn.execute("SELECT id FROM entries WHERE source_id = ?", (source_id,)).fetchall():
        reindex_entry(conn, entry_id)
    for (note_id,) in conn.execute("SELECT note_id FROM note_sources WHERE source_id = ?", (source_id,)).fetchall():
        reindex_note(conn, note_id)


def reindex_person(conn: sqlite3.Connection, pid: int) -> None:
    """After a person is renamed: every entry and note that mentions them."""
    ids = {r[0] for r in conn.execute(
        "SELECT e.id FROM entries e WHERE e.words_by = ? OR e.source_id IN (SELECT source_id FROM source_people "
        "WHERE person_id = ?) UNION SELECT entry_id FROM entry_people WHERE person_id = ?", (pid, pid, pid))}
    for entry_id in ids:
        reindex_entry(conn, entry_id)
    for (note_id,) in conn.execute("SELECT note_id FROM note_people WHERE person_id = ?", (pid,)).fetchall():
        reindex_note(conn, note_id)


def reindex_note(conn: sqlite3.Connection, note_id: int) -> None:
    conn.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
    row = conn.execute("SELECT id, title, text, place FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        return
    links = [r[0] for r in conn.execute(
        "SELECT p.name FROM note_people np JOIN people p ON p.id = np.person_id WHERE np.note_id = ? "
        "UNION ALL SELECT t.name FROM note_topics nt JOIN topics t ON t.id = nt.topic_id WHERE nt.note_id = ? "
        "UNION ALL SELECT s.title || ' ' || COALESCE(s.subtitle, '') FROM note_sources ns "
        "JOIN sources s ON s.id = ns.source_id WHERE ns.note_id = ?",
        (note_id, note_id, note_id))]
    conn.execute("INSERT INTO notes_fts (rowid, title, text, links) VALUES (?, ?, ?, ?)",
                 (note_id, row["title"] or "", row["text"], " ".join(filter(None, [*links, row["place"]]))))


def fts_query(user_text: str) -> str | None:
    """Make a safe FTS5 query: every word must match, as a prefix ("hypoth" finds "hypothèse")."""
    words = re.findall(r"[\w’']+", user_text, flags=re.UNICODE)
    words = [w.replace("'", " ").replace("’", " ") for w in words]
    tokens = [t for w in words for t in w.split() if t]
    if not tokens:
        return None
    return " ".join(f'"{t}"*' for t in tokens)


def chunks(items: list, size: int = 500) -> Iterable[list]:
    for k in range(0, len(items), size):
        yield items[k:k + size]
