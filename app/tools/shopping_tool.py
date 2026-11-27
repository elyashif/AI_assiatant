"""
רשימת קניות: הבוט שומר פריטים במסד הנתונים, וקיצור דרך באייפון
מושך אותם לרשימה "רשימת קניות" ב-Reminders כשפותחים את האפליקציה.
"""
from app.db import get_connection


def add_to_shopping_list(items: str) -> str:
    """
    מוסיף פריטים לרשימת הקניות.
    items: הפריטים מופרדים בפסיקים, למשל "חלב, ביצים, לחם".
    """
    names = [part.strip() for part in items.replace("\n", ",").split(",") if part.strip()]
    if not names:
        return "לא זיהיתי פריטים להוספה."

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO shopping_items (item) VALUES (%s)", [(n,) for n in names])
            conn.commit()
    except Exception as e:
        return f"שגיאה בשמירת הפריטים: {e}"

    return f"נשמרו {len(names)} פריטים: {', '.join(names)}. הם ייכנסו לרשימת הקניות באייפון בפעם הבאה שתפתח את Reminders."


def get_pending_shopping_items() -> str:
    """מחזיר את הפריטים שנשמרו ועוד לא הועברו לאייפון."""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT item FROM shopping_items WHERE synced_at IS NULL ORDER BY id"
            ).fetchall()
    except Exception as e:
        return f"שגיאה בקריאת הרשימה: {e}"

    if not rows:
        return "אין פריטים שמחכים להעברה לאייפון."
    return "פריטים שמחכים להעברה לאייפון: " + ", ".join(r[0] for r in rows)


def claim_pending_items() -> list:
    """
    מחזיר את הפריטים הממתינים ומסמן אותם כמועברים, בפעולה אחת.
    נקרא על ידי קיצור הדרך באייפון.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            UPDATE shopping_items SET synced_at = now()
            WHERE synced_at IS NULL
            RETURNING id, item
            """
        ).fetchall()
        conn.commit()
    return [item for _, item in sorted(rows)]
