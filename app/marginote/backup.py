"""Nightly database snapshots in data/backups/, using SQLite's safe online backup."""

import logging
import sqlite3
import threading
import time
import uuid
import zipfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

log = logging.getLogger("marginote.backup")


def snapshot(db_path: Path, backups_dir: Path, keep: int) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"marginote-{datetime.now():%Y-%m-%d}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    old = sorted(backups_dir.glob("marginote-*.db"))[:-keep] if keep > 0 else []
    for path in old:
        path.unlink(missing_ok=True)
    log.info("Backup written to %s", target)
    return target


def list_backups(backups_dir: Path) -> list[dict]:
    """The database copies, newest first: file name, size and when it was written (local time)."""
    copies = []
    for path in sorted(backups_dir.glob("marginote-*.db"), reverse=True):
        stat = path.stat()
        copies.append({
            "file": path.name,
            "bytes": stat.st_size,
            "written_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="minutes"),
        })
    return copies


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
    src, dst = sqlite3.connect(db_path), sqlite3.connect(copy)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
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


def start_maintenance(db_path: Path, backups_dir: Path, hour: int, keep: int, hourly=None) -> None:
    """Background loop: a database snapshot every night at `hour`, and `hourly()` once an hour."""
    def loop() -> None:
        last_hourly = 0.0
        while True:
            now = datetime.now()
            today = backups_dir / f"marginote-{now:%Y-%m-%d}.db"
            if now.hour == hour and not today.exists():
                try:
                    snapshot(db_path, backups_dir, keep)
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
