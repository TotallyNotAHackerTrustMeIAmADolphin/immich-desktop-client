import sqlite3
from collections import namedtuple
from contextlib import closing, contextmanager
from pathlib import Path

Entry = namedtuple("Entry", "path asset_id checksum own_upload")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    path TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    checksum TEXT,
    own_upload INTEGER NOT NULL DEFAULT 0
)
"""


class UploadRecord:
    """The local upload record: what this client has uploaded, and whether it can vouch for it."""

    def __init__(self, db_path):
        self.__db_path = str(db_path)
        Path(self.__db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.__transaction() as db:
            db.execute(_SCHEMA)

    def get(self, path):
        with closing(self.__connect()) as db:
            row = db.execute("SELECT path, asset_id, checksum, own_upload FROM uploads WHERE path = ?",
                             (str(path),)).fetchone()
        return self.__entry(row) if row else None

    def entries(self):
        with closing(self.__connect()) as db:
            rows = db.execute("SELECT path, asset_id, checksum, own_upload FROM uploads").fetchall()
        return [self.__entry(row) for row in rows]

    def upsert(self, path, asset_id, checksum, own_upload):
        with self.__transaction() as db:
            db.execute("INSERT OR REPLACE INTO uploads (path, asset_id, checksum, own_upload) VALUES (?, ?, ?, ?)",
                       (str(path), asset_id, checksum, 1 if own_upload else 0))

    def remove(self, path):
        with self.__transaction() as db:
            db.execute("DELETE FROM uploads WHERE path = ?", (str(path),))

    def __connect(self):
        return sqlite3.connect(self.__db_path)

    @contextmanager
    def __transaction(self):
        with closing(self.__connect()) as db:
            with db:  # commits on success, rolls back on error
                yield db

    @staticmethod
    def __entry(row):
        return Entry(row[0], row[1], row[2], bool(row[3]))
