"""Copies of the database in data/backups/: one a night, kept 14 days, plus the first of each month for
6 months, and one before every upgrade that changes the database. Each copy is a zip holding
marginote.db: about a third of the size, and opened by any file manager.

Restoring a copy: stop the app, unzip it, put its marginote.db in the data folder in place of the
current one (delete marginote.db-wal and marginote.db-shm if they are there), start the app.
"""

import logging
import re
import sqlite3
import threading
import time
import uuid
import zipfile
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

log = logging.getLogger("marginote.backup")
DAILY = re.compile(r"^marginote-(\d{4})-(\d{2})-(\d{2})\.(zip|db)$")


def _copy_db(db_path: Path, target: Path) -> None:
    """A consistent copy of the database, even while the app writes to it (SQLite's online backup)."""
    src, dst = sqlite3.connect(db_path), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _zip_db(db_path: Path, target: Path) -> Path:
    tmp_db = target.with_name(f".{uuid.uuid4().hex}.db")
    tmp_zip = target.with_name(f".{uuid.uuid4().hex}.zip")
    try:
        _copy_db(db_path, tmp_db)
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.write(tmp_db, "marginote.db")
        tmp_zip.replace(target)       # appears whole or not at all
    finally:
        tmp_db.unlink(missing_ok=True)
        tmp_zip.unlink(missing_ok=True)
    return target


def snapshot(db_path: Path, backups_dir: Path, keep: int, monthly: int = 6) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = _zip_db(db_path, backups_dir / f"marginote-{datetime.now():%Y-%m-%d}.zip")
    (backups_dir / target.name.replace(".zip", ".db")).unlink(missing_ok=True)
    prune(backups_dir, keep, monthly)
    log.info("Backup written to %s", target.name)
    return target


def before_upgrade(db_path: Path, backups_dir: Path, new_version: str) -> Path:
    """The database as it was before an upgrade, kept until you delete it: to go back to the old version."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"before-{new_version}-{datetime.now():%Y-%m-%d-%H%M}.zip"
    _zip_db(db_path, target)
    log.info("Database copied to backups/%s before upgrading", target.name)
    return target


def prune(backups_dir: Path, keep: int, monthly: int) -> None:
    """Keep the newest `keep` daily copies, and the oldest copy of each of the `monthly` latest months."""
    daily = sorted((p for p in backups_dir.iterdir() if DAILY.match(p.name)), key=lambda p: p.name, reverse=True)
    kept = set(daily[:keep]) if keep > 0 else set()
    first_of_month: dict[str, Path] = {}
    for path in reversed(daily):                              # oldest first
        first_of_month.setdefault(path.name[10:17], path)    # 'YYYY-MM'
    for month in sorted(first_of_month, reverse=True)[:max(0, monthly)]:
        kept.add(first_of_month[month])
    for path in daily:
        if path not in kept:
            path.unlink(missing_ok=True)


def compress_old_copies(backups_dir: Path) -> None:
    """Daily copies left by version 0.4 (plain .db files) become zips: a third of the space."""
    for path in sorted(backups_dir.glob("marginote-*.db")):
        if DAILY.match(path.name):
            target = path.with_suffix(".zip")
            if not target.exists():
                _zip_db(path, target)
            path.unlink(missing_ok=True)


def list_backups(backups_dir: Path) -> list[dict]:
    """Every copy, newest first: file name, size and when it was written (local time)."""
    copies = []
    if not backups_dir.is_dir():
        return copies
    for path in backups_dir.iterdir():
        if path.suffix in (".zip", ".db") and not path.name.startswith("."):
            stat = path.stat()
            copies.append({
                "file": path.name,
                "bytes": stat.st_size,
                "written_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="minutes"),
                "kind": "daily" if DAILY.match(path.name) else "before upgrade" if path.name.startswith("before-") else "other",
            })
    return sorted(copies, key=lambda c: c["written_at"], reverse=True)


class _Pipe:
    """Collects what zipfile writes, so the archive can be sent while it is being made."""

    def __init__(self) -> None:
        self.parts: list[bytes] = []

    def write(self, data) -> int:
        self.parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass

    def take(self) -> bytes:
        out, self.parts = b"".join(self.parts), []
        return out


def archive(db_path: Path, data_dir: Path, folders: tuple[str, ...]) -> Iterator[bytes]:
    """A zip of a fresh, consistent copy of the database plus the given folders, produced piece by piece:
    nothing big is held in memory or written to disk."""
    copy = data_dir / f".download-{uuid.uuid4().hex}.db"
    _copy_db(db_path, copy)
    pipe = _Pipe()
    try:
        with zipfile.ZipFile(pipe, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            z.write(copy, "marginote.db", compress_type=zipfile.ZIP_DEFLATED)
            yield pipe.take()
            for name in folders:
                folder = data_dir / name
                for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
                    if path.is_file():
                        z.write(path, f"{name}/{path.relative_to(folder).as_posix()}")   # images: stored as they are
                        yield pipe.take()
        yield pipe.take()
    finally:
        copy.unlink(missing_ok=True)


def start_maintenance(db_path: Path, backups_dir: Path, hour: int, keep: int, monthly: int,
                      hourly: Callable[[], object] | None = None) -> None:
    """Background loop: a database copy every night at `hour`, and `hourly()` once an hour."""
    def loop() -> None:
        try:
            compress_old_copies(backups_dir)
        except Exception:
            log.exception("Could not compress older backups")
        last_hourly = 0.0
        while True:
            now = datetime.now()
            today = backups_dir / f"marginote-{now:%Y-%m-%d}.zip"
            if now.hour == hour and not today.exists():
                try:
                    snapshot(db_path, backups_dir, keep, monthly)
                except Exception:  # keep the app running whatever happens
                    log.exception("Nightly backup failed")
            if hourly and time.monotonic() - last_hourly >= 3600:
                last_hourly = time.monotonic()
                try:
                    hourly()
                except Exception:
                    log.exception("Hourly maintenance failed")
            time.sleep(300)

    threading.Thread(target=loop, name="maintenance", daemon=True).start()
