"""בדיקות אבטחה משותפות."""
import secrets
from typing import Optional

from fastapi import Header, HTTPException

from app.config import API_KEY, ALLOWED_CHAT_IDS


def matches_secret(given: Optional[str], expected: Optional[str]) -> bool:
    """השוואה בטוחה. אם הסוד לא הוגדר - חוסמים (ברירת מחדל סגורה)."""
    if not expected or not given:
        return False
    return secrets.compare_digest(given, expected)


def require_api_key(x_api_key: Optional[str] = Header(None)):
    if not matches_secret(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")


def is_allowed_chat(chat_id: int) -> bool:
    return chat_id in ALLOWED_CHAT_IDS
