"""Where files go in the data folder, and keeping it tidy.

    data/
      marginote.db                     everything you typed and every link (one file)
      photos/inbox/                    pages sent to be sorted later
      photos/<Title> (<id>)/           a source's page photos, named after their page: 'p57 - 3f2a9c1b.webp'
      covers/<id>.webp                 covers and video thumbnails
      backups/                         copies of the database (see backup.py)

A source's folder is renamed with it; photos no quote uses are removed after a day; empty folders go.
"""

import logging
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, ocr
from .config import Settings

log = logging.getLogger("marginote")
INBOX = "inbox"
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def source_folder(source_id: int, title: str) -> str:
    """Readable, Windows-safe folder name for a source's photos: 'La Science et l'hypothèse (12)'."""
    name = unicodedata.normalize("NFC", _UNSAFE.sub(" ", title))
    name = re.sub(r"\s+", " ", name).strip(" .")[:60].strip(" .") or "Source"
    return f"{name} ({source_id})"


def photo_file_name(photo_id: str, page: str | None, suffix: str = ".webp") -> str:
    page_part = re.sub(r"[^0-9A-Za-z]", "", page or "")[:10]
    return f"p{page_part} - {photo_id[:8]}{suffix}" if page_part else f"{photo_id[:8]}{suffix}"


def is_unfiled(path: str) -> bool:
    """Still in the inbox (or stored by the first version, by year and month)."""
    return path.startswith(INBOX + "/") or re.match(r"^\d{4}/\d{2}/", path) is not None


class Files:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.photos = settings.photos_dir
        self.covers = settings.covers_dir

    def make_folders(self) -> None:
        for folder in (self.settings.data_dir, self.photos, self.photos / INBOX, self.covers, self.settings.backups_dir):
            folder.mkdir(parents=True, exist_ok=True)

    # ----- photos -----

    def file_photo(self, conn: sqlite3.Connection, photo_id: str, source_id: int, page: str | None) -> None:
        """Move a photo out of the inbox into its source's folder, named after the page."""
        row = conn.execute("SELECT path FROM photos WHERE id = ?", (photo_id,)).fetchone()
        if not row or not is_unfiled(row["path"]):
            return
        title = conn.execute("SELECT title FROM sources WHERE id = ?", (source_id,)).fetchone()["title"]
        new_rel = f"{source_folder(source_id, title)}/{photo_file_name(photo_id, page, Path(row['path']).suffix)}"
        src, dst = self.photos / row["path"], self.photos / new_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            src.replace(dst)
        conn.execute("UPDATE photos SET path = ? WHERE id = ?", (new_rel, photo_id))

    def rename_source_folder(self, conn: sqlite3.Connection, source_id: int, old_title: str, new_title: str) -> None:
        old, new = source_folder(source_id, old_title), source_folder(source_id, new_title)
        if old == new:
            return
        old_dir, new_dir = self.photos / old, self.photos / new
        if old_dir.is_dir() and not new_dir.exists():
            old_dir.rename(new_dir)
        prefix = old + "/"
        for row in conn.execute("SELECT id, path FROM photos WHERE substr(path, 1, ?) = ?",
                                (len(prefix), prefix)).fetchall():
            conn.execute("UPDATE photos SET path = ? WHERE id = ?", (new + "/" + row["path"][len(prefix):], row["id"]))

    def move_photo_to_source(self, conn: sqlite3.Connection, photo_id: str, source_id: int, page: str | None) -> None:
        """A quote moved to another source takes its photo along (when no other quote uses it)."""
        row = conn.execute("SELECT path FROM photos WHERE id = ?", (photo_id,)).fetchone()
        users = conn.execute("SELECT COUNT(DISTINCT source_id) FROM entries WHERE photo_id = ?", (photo_id,)).fetchone()[0]
        if not row or users > 1:
            return
        title = conn.execute("SELECT title FROM sources WHERE id = ?", (source_id,)).fetchone()["title"]
        new_rel = f"{source_folder(source_id, title)}/{Path(row['path']).name}"
        if new_rel == row["path"]:
            return
        src, dst = self.photos / row["path"], self.photos / new_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            src.replace(dst)
        conn.execute("UPDATE photos SET path = ?, source_id = ? WHERE id = ?", (new_rel, source_id, photo_id))

    def refile_photos(self) -> None:
        """Photos already used by a quote but still unfiled (from older versions): move them now."""
        conn = db.connect(self.settings.db_path)
        try:
            rows = conn.execute(
                "SELECT p.id, p.path, e.source_id, e.page FROM photos p JOIN entries e ON e.photo_id = p.id GROUP BY p.id"
            ).fetchall()
            for row in rows:
                if is_unfiled(row["path"]):
                    self.file_photo(conn, row["id"], row["source_id"], row["page"])
            conn.commit()
        finally:
            conn.close()

    def clean_unused_photos(self) -> int:
        """Delete photos that no quote uses, once older than UNUSED_PHOTO_HOURS (24 h by default), then
        remove empty folders."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.settings.unused_photo_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = db.connect(self.settings.db_path)
        try:
            rows = conn.execute(
                "SELECT id, path FROM photos p WHERE created_at < ? AND queued = 0 AND status != 'reading' "
                "AND NOT EXISTS (SELECT 1 FROM entries e WHERE e.photo_id = p.id)",
                (cutoff,),
            ).fetchall()
            for row in rows:
                (self.photos / row["path"]).unlink(missing_ok=True)
                conn.execute("DELETE FROM photos WHERE id = ?", (row["id"],))
            conn.commit()
        finally:
            conn.close()
        folders = sorted((d for d in self.photos.rglob("*") if d.is_dir()), key=lambda d: len(d.parts), reverse=True)
        for folder in folders:
            if folder.name != INBOX and not any(folder.iterdir()):
                folder.rmdir()
        if rows:
            log.info("Removed %d unused photos", len(rows))
        return len(rows)

    # ----- covers -----

    def save_cover(self, conn: sqlite3.Connection, source_id: int, image: bytes) -> None:
        name = f"{source_id}{ocr.COVER_SUFFIX}"
        (self.covers / name).write_bytes(ocr.normalize_cover(image))
        old = conn.execute("SELECT cover FROM sources WHERE id = ?", (source_id,)).fetchone()
        if old and old["cover"] and old["cover"] != name:
            (self.covers / old["cover"]).unlink(missing_ok=True)      # the .jpg of an older version
        conn.execute("UPDATE sources SET cover = ?, updated_at = ? WHERE id = ?", (name, db.now(), source_id))

    def remove_cover(self, name: str | None) -> None:
        if name:
            (self.covers / name).unlink(missing_ok=True)

    def usage(self) -> dict:
        def folder(path: Path) -> dict:
            files = [f for f in path.rglob("*") if f.is_file()] if path.is_dir() else []
            return {"count": len(files), "bytes": sum(f.stat().st_size for f in files)}
        data = self.settings.data_dir
        return {
            "database_bytes": sum(p.stat().st_size for p in data.glob("marginote.db*") if p.is_file()),
            "photos": folder(self.photos),
            "covers": folder(self.covers),
            "backups": folder(self.settings.backups_dir),
        }
