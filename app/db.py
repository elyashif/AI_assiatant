"""
חיבור למסד הנתונים (Postgres, למשל ב-Neon).
כתובת החיבור נלקחת ממשתנה הסביבה DATABASE_URL.
"""
import os
from contextlib import contextmanager

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")

_initialized = False


@contextmanager
def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    with psycopg.connect(DATABASE_URL, connect_timeout=10) as conn:
        _ensure_tables(conn)
        yield conn


def _ensure_tables(conn):
    """יוצר את הטבלאות בפעם הראשונה (אם עוד לא קיימות)."""
    global _initialized
    if _initialized:
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shopping_items (
            id          SERIAL PRIMARY KEY,
            item        TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            synced_at   TIMESTAMPTZ
        )
        """
    )
    conn.commit()
    _initialized = True
