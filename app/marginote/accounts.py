"""Who can log in. Each account has its own library (database, photos, covers, backups), and nothing in the
app reads one library from another.

The owner is the first account: its password is MARGINOTE_PASSWORD from the compose file and its library is
the data folder itself, as before accounts existed. The others are kept in data/accounts.json, their
passwords scrambled with scrypt (never stored as typed); their libraries are in data/users/<id>/.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

OWNER = "owner"
LANGUAGES = ("fr", "en")
MIN_PASSWORD = 8
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def name_key(name: str) -> str:
    """'Élise ' and 'elise' are the same name."""
    folded = unicodedata.normalize("NFKD", name.casefold().strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    try:
        kind, n, r, p, salt, digest = (stored or "").split("$")
        if kind != "scrypt":
            return False
        found = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), dklen=32, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(found.hex(), digest)
    except ValueError:
        return False


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Accounts:
    """The accounts file. Small, read once, written whole (through a temporary file) on every change."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._stamp: float | None = None
        self._list: list[dict] = []
        self._fresh()

    def _fresh(self) -> None:
        """Read the file again when it changed since (another process, or an edit by hand)."""
        stamp = self.path.stat().st_mtime_ns if self.path.exists() else None
        if stamp == self._stamp and self._list:
            return
        data = json.loads(self.path.read_text(encoding="utf-8")) if stamp is not None else {}
        self._list = data.get("accounts", [])
        if not any(a["id"] == OWNER for a in self._list):
            self._list.insert(0, {"id": OWNER, "name": "admin", "language": "fr", "created_at": _now()})
        self._stamp = stamp

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"accounts": self._list}, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.chmod(0o600)
        os.replace(tmp, self.path)
        self._stamp = self.path.stat().st_mtime_ns

    def all(self) -> list[dict]:
        with self._lock:
            self._fresh()
            return [dict(a) for a in self._list]

    def get(self, account_id: str) -> dict | None:
        with self._lock:
            self._fresh()
            found = next((a for a in self._list if a["id"] == account_id), None)
            return dict(found) if found else None

    def by_name(self, name: str) -> dict | None:
        key = name_key(name)
        with self._lock:
            self._fresh()
            found = next((a for a in self._list if name_key(a["name"]) == key), None)
            return dict(found) if found else None

    def _check_name(self, name: str, account_id: str | None = None) -> str:
        name = " ".join(name.split())
        if not name:
            raise ValueError("A name is needed")
        if len(name) > 60:
            raise ValueError("This name is too long")
        same = self.by_name(name)
        if same and same["id"] != account_id:
            raise ValueError("Someone already has this name")
        return name

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"The password needs at least {MIN_PASSWORD} characters")

    def add(self, name: str, password: str, language: str = "fr") -> dict:
        name = self._check_name(name)
        self._check_password(password)
        account = {
            "id": "u" + secrets.token_hex(4),
            "name": name,
            "language": language if language in LANGUAGES else "fr",
            "password": hash_password(password),
            "session": secrets.token_urlsafe(16),   # part of the login cookie: renewed with the password
            "created_at": _now(),
        }
        with self._lock:
            self._fresh()
            self._list.append(account)
            self._save()
        return dict(account)

    def update(self, account_id: str, *, name: str | None = None, language: str | None = None,
               password: str | None = None) -> dict:
        if name is not None:
            name = self._check_name(name, account_id)
        if password is not None:
            if account_id == OWNER:
                raise ValueError("The owner's password is MARGINOTE_PASSWORD, in the compose file")
            self._check_password(password)
        with self._lock:
            self._fresh()
            account = next((a for a in self._list if a["id"] == account_id), None)
            if account is None:
                raise KeyError(account_id)
            if name is not None:
                account["name"] = name
            if language in LANGUAGES:
                account["language"] = language
            if password is not None:
                account["password"] = hash_password(password)
                account["session"] = secrets.token_urlsafe(16)   # logs this person out everywhere else
            self._save()
            return dict(account)

    def remove(self, account_id: str) -> dict:
        if account_id == OWNER:
            raise ValueError("The owner cannot be removed")
        with self._lock:
            self._fresh()
            account = next((a for a in self._list if a["id"] == account_id), None)
            if account is None:
                raise KeyError(account_id)
            self._list.remove(account)
            self._save()
            return dict(account)


def public(account: dict) -> dict:
    """What the app may show about an account: never its password."""
    return {"id": account["id"], "name": account["name"], "language": account.get("language", "fr"),
            "owner": account["id"] == OWNER, "created_at": account.get("created_at")}
