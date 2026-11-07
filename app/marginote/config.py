"""Settings, read once from environment variables (set in the compose file)."""

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    password: str
    ocr_langs: str
    lookups_enabled: bool
    cookie_secure: bool
    backup_hour: int
    backups_kept: int                  # daily copies
    unused_photo_hours: int = 24
    straighten_pages: bool = True
    backups_monthly: int = 6           # plus the first copy of each of the last 6 months

    @property
    def db_path(self) -> Path:
        return self.data_dir / "marginote.db"

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def covers_dir(self) -> Path:
        return self.data_dir / "covers"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def secret_key(self) -> str:
        """Session-signing key, created once and kept in the data folder."""
        path = self.data_dir / "secret_key"
        if not path.exists():
            path.write_text(secrets.token_urlsafe(48))
            path.chmod(0o600)
        return path.read_text().strip()


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        password=os.environ.get("MARGINOTE_PASSWORD", ""),
        ocr_langs=os.environ.get("OCR_LANGS", "fra+eng"),
        lookups_enabled=_bool(os.environ.get("LOOKUPS_ENABLED"), True),
        cookie_secure=_bool(os.environ.get("COOKIE_SECURE"), True),
        backup_hour=int(os.environ.get("BACKUP_HOUR", "3")),
        backups_kept=int(os.environ.get("BACKUPS_KEPT", "14")),
        unused_photo_hours=int(os.environ.get("UNUSED_PHOTO_HOURS", "24")),
        straighten_pages=_bool(os.environ.get("STRAIGHTEN_PAGES"), True),
        backups_monthly=int(os.environ.get("BACKUPS_MONTHLY", "6")),
    )
