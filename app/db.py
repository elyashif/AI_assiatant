"""
חיבור למסד הנתונים (Postgres ב-Neon). הכתובת נלקחת מ-DATABASE_URL.
הטבלאות נוצרות אוטומטית בפעם הראשונה.
"""
from contextlib import contextmanager

from app.config import DATABASE_URL

_initialized = False

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS shopping_items (
        id          SERIAL PRIMARY KEY,
        item        TEXT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        synced_at   TIMESTAMPTZ
    )
    """,
    # היסטוריית השיחה של כל צ'אט, כדי שהבוט לא ישכח כשהשרת עולה מחדש
    """
    CREATE TABLE IF NOT EXISTS chat_history (
        session_id  TEXT PRIMARY KEY,
        contents    JSONB NOT NULL,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # פרטי אימוני Arbox שנמשכו, כדי לדעת מה להכניס ליומן אחרי ההרשמה מהאייפון
    """
    CREATE TABLE IF NOT EXISTS arbox_classes (
        schedule_id TEXT PRIMARY KEY,
        details     JSONB NOT NULL,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]


def is_configured() -> bool:
    return bool(DATABASE_URL)


@contextmanager
def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    import psycopg  # מיובא כאן כדי שהבוט יעלה גם בלי מסד נתונים

    with psycopg.connect(DATABASE_URL, connect_timeout=10) as conn:
        _ensure_tables(conn)
        yield conn


def _ensure_tables(conn):
    global _initialized
    if _initialized:
        return
    for statement in TABLES:
        conn.execute(statement)
    conn.commit()
    _initialized = True
