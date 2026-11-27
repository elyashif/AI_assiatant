"""
זיכרון השיחות של הבוט.
ההיסטוריה נשמרת במסד הנתונים, כך שהבוט לא שוכח כש-Render מעדכן את השרת או מרדים אותו.
אם אין מסד נתונים, ההיסטוריה נשמרת בזיכרון השרת (כמו פעם).
"""
from typing import List

from google.genai import types

from app import db

# כמה הודעות (כולל קריאות לכלים) לשמור לכל שיחה
MAX_CONTENTS = 40
# תמונות נשמרות רק בהודעות האחרונות, כדי לא לנפח את המסד
KEEP_IMAGES_IN_LAST = 6

_local_history = {}


def load_history(session_id: str) -> List[types.Content]:
    if not db.is_configured():
        return list(_local_history.get(session_id, []))
    try:
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT contents FROM chat_history WHERE session_id = %s", (session_id,)
            ).fetchone()
    except Exception as e:
        print(f"[memory] load failed: {e}")
        return list(_local_history.get(session_id, []))

    if not row:
        return []
    try:
        return [types.Content.model_validate(item) for item in row[0]]
    except Exception as e:
        print(f"[memory] could not parse history, starting fresh: {e}")
        return []


def save_history(session_id: str, contents: List[types.Content]):
    contents = trim_history(contents)
    _local_history[session_id] = contents
    if not db.is_configured():
        return

    from psycopg.types.json import Jsonb

    data = [c.model_dump(mode="json", exclude_none=True) for c in contents]
    try:
        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_history (session_id, contents, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (session_id)
                DO UPDATE SET contents = EXCLUDED.contents, updated_at = now()
                """,
                (session_id, Jsonb(data)),
            )
            conn.commit()
    except Exception as e:
        print(f"[memory] save failed: {e}")


def clear_history(session_id: str):
    _local_history.pop(session_id, None)
    if not db.is_configured():
        return
    try:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM chat_history WHERE session_id = %s", (session_id,))
            conn.commit()
    except Exception as e:
        print(f"[memory] clear failed: {e}")


def _is_user_turn_start(content: types.Content) -> bool:
    """הודעה רגילה של המשתמש (ולא תשובה של כלי)."""
    if content.role != "user" or not content.parts:
        return False
    return not any(part.function_response for part in content.parts)


def trim_history(contents: List[types.Content]) -> List[types.Content]:
    """
    שומר רק את ההודעות האחרונות, ומוודא שההיסטוריה מתחילה בהודעה של המשתמש
    (Gemini דורש שקריאה לכלי ותשובת הכלי יופיעו יחד).
    """
    contents = list(contents[-MAX_CONTENTS:])
    while contents and not _is_user_turn_start(contents[0]):
        contents.pop(0)

    # מחליפים תמונות ישנות בטקסט קצר
    cutoff = len(contents) - KEEP_IMAGES_IN_LAST
    for index, content in enumerate(contents[:max(cutoff, 0)]):
        if content.parts and any(part.inline_data for part in content.parts):
            new_parts = [
                types.Part(text="[תמונה שנשלחה קודם בשיחה]") if part.inline_data else part
                for part in content.parts
            ]
            contents[index] = types.Content(role=content.role, parts=new_parts)
    return contents
