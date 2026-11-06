"""Nightly database snapshots in data/backups/, using SQLite's safe online backup."""

import logging
import sqlite3
import threading
import time
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
