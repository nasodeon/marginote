"""What every part of the API shares: the settings, the files, database connections, the login check."""

import queue
import sqlite3
from collections.abc import Iterator

from . import db
from .config import Settings
from .files import Files


class Context:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.files = Files(settings)
        self.reader_queue: queue.Queue = queue.Queue()   # inbox photos waiting to be read
        self.auth: list = []                              # set by main: the login check

    def connect(self) -> sqlite3.Connection:
        return db.connect(self.settings.db_path)

    def get_db(self) -> Iterator[sqlite3.Connection]:
        """FastAPI dependency: one connection per request."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()
