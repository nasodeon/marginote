"""What every part of the API shares: the settings, the accounts, each account's library, the login check.

A library is one account's own folder, data/users/<id>/ (the owner's is data/users/owner/): its database,
photos, covers and backups. A request only ever reaches the library of the account logged in: no call takes
a library as a parameter, so no call can name someone else's.
"""

import dataclasses
import hashlib
import hmac
import logging
import queue
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, HTTPException, Request

from . import backup, db
from .accounts import OWNER, Accounts
from .config import Settings
from .files import Files

log = logging.getLogger("marginote")

# what made up the owner's library, at the top of the data folder, before 0.7.1
OWNER_ITEMS = ("marginote.db", "marginote.db-wal", "marginote.db-shm", "photos", "covers", "backups")


def gather_owner_library(data_dir: Path, version: str) -> list[str]:
    """Until 0.7.1 the owner's library was the data folder itself; it now has a folder like everyone's,
    data/users/owner/. Done once, at start, before anything opens the database. Each item is renamed on the
    same disk, so it is instant whatever the number of photos, and a zip of the database is made first.
    Nothing is ever overwritten: if both places hold something, the app stops and says so."""
    target = data_dir / "users" / OWNER
    present = [name for name in OWNER_ITEMS if (data_dir / name).exists()]
    if not present:
        return []

    def empty_dir(path: Path) -> bool:
        return path.is_dir() and not any(path.iterdir())

    for name in present:
        if (target / name).exists() and not empty_dir(target / name) and not empty_dir(data_dir / name):
            raise RuntimeError(f"Both data/{name} and data/users/{OWNER}/{name} hold files: move one of them aside, "
                               "then start the app again")
    if (data_dir / "marginote.db").exists() and not (target / "marginote.db").exists():
        backup.before_upgrade(data_dir / "marginote.db", data_dir / "backups", version)   # moved with the rest
    target.mkdir(parents=True, exist_ok=True)
    moved = []
    for name in OWNER_ITEMS:
        src, dst = data_dir / name, target / name
        if not src.exists():
            continue
        if empty_dir(src) and dst.exists():
            src.rmdir()
            continue
        if empty_dir(dst):
            dst.rmdir()
        src.rename(dst)
        moved.append(name)
    log.info("Your library now has its own folder, data/users/%s/: moved %s", OWNER, ", ".join(moved))
    return moved


@dataclass
class Library:
    account_id: str
    settings: Settings      # the app's settings, with data_dir = this library's folder
    files: Files

    def connect(self) -> sqlite3.Connection:
        return db.connect(self.settings.db_path, self.account_id)


class Context:
    def __init__(self, settings: Settings, shape_changed_in: str = "", folders_changed_in: str = "") -> None:
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        gather_owner_library(settings.data_dir, folders_changed_in)
        self.accounts = Accounts(settings.data_dir / "accounts.json")
        self.shape_changed_in = shape_changed_in
        self.reader_queue: queue.Queue = queue.Queue()   # (library, photo id) of inbox photos waiting to be read
        self._libraries: dict[str, Library] = {}
        self._lock = threading.Lock()
        self._secret = settings.secret_key().encode()

        def require_library(request: Request) -> Library:
            account = self.account_for(request)
            if account is None:
                raise HTTPException(401, "Log in first with POST /api/login")
            return self.library(account["id"])

        def get_db(lib: Library = Depends(require_library)) -> Iterator[sqlite3.Connection]:
            """FastAPI dependency: one connection per request, to the logged-in account's library."""
            conn = lib.connect()
            try:
                yield conn
            finally:
                conn.close()

        self.require_library = require_library
        self.get_db = get_db
        self.auth = [Depends(require_library)]

    # ----- libraries -----

    def folder_of(self, account_id: str) -> Path:
        return self.settings.data_dir / "users" / account_id

    def library(self, account_id: str) -> Library:
        """The account's library, opened (and brought up to date) the first time it is needed."""
        with self._lock:
            lib = self._libraries.get(account_id)
            if lib is None:
                lib_settings = dataclasses.replace(self.settings, data_dir=self.folder_of(account_id))
                lib = Library(account_id, lib_settings, Files(lib_settings))
                lib.files.make_folders()
                # an existing database is copied to backups/ before its shape changes: the way back
                db.migrate(lib_settings.db_path, before_upgrade=lambda old, s=lib_settings: backup.before_upgrade(
                    s.db_path, s.backups_dir, self.shape_changed_in))
                lib.files.refile_photos()
                lib.files.clean_unused_photos()
                self._libraries[account_id] = lib
            return lib

    def libraries(self) -> list[Library]:
        """Every account's library (for the nightly copies and the hourly cleaning)."""
        out = []
        for account in self.accounts.all():
            try:
                out.append(self.library(account["id"]))
            except Exception:
                log.exception("Could not open the library of account %s", account["id"])
        return out

    def forget_library(self, account_id: str) -> None:
        with self._lock:
            self._libraries.pop(account_id, None)

    # ----- login -----

    def session_tag(self, account: dict) -> str:
        """Kept in the login cookie. It changes with the password, which logs that account out everywhere."""
        key = self.settings.password if account["id"] == OWNER else account.get("session", "")
        return hmac.new(self._secret, f"{account['id']}:{key}".encode(), hashlib.sha256).hexdigest()[:32]

    def legacy_tag(self) -> str:
        """The cookie of versions before accounts (the owner's password alone)."""
        return hmac.new(self._secret, self.settings.password.encode(), hashlib.sha256).hexdigest()[:32]

    def account_for(self, request: Request) -> dict | None:
        session = request.session
        if self.settings.password and session.get("ok") and hmac.compare_digest(str(session["ok"]), self.legacy_tag()):
            owner = self.accounts.get(OWNER)        # logged in before accounts existed: still the owner
            session.clear()
            session.update(uid=OWNER, tag=self.session_tag(owner))
            return owner
        account = self.accounts.get(str(session.get("uid", "")))
        if account is None or (account["id"] == OWNER and not self.settings.password):
            return None
        if not hmac.compare_digest(str(session.get("tag", "")), self.session_tag(account)):
            return None
        return account
