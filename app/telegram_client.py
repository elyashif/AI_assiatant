"""שליחת הודעות לטלגרם והורדת קבצים שנשלחו לבוט."""
from typing import Optional

import requests

from app.config import TELEGRAM_API_URL, TELEGRAM_TOKEN, ALLOWED_CHAT_IDS

# טלגרם מגביל הודעה ל-4096 תווים
MAX_MESSAGE_LENGTH = 4000


def send_telegram_message(chat_id: int, text: str):
    """שולח הודעה. אם ה-Markdown לא תקין (כמו _ או *), שולח שוב כטקסט רגיל."""
    text = text or "..."
    for start in range(0, len(text), MAX_MESSAGE_LENGTH):
        _send_chunk(chat_id, text[start:start + MAX_MESSAGE_LENGTH])


def _send_chunk(chat_id: int, text: str):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        response = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload, timeout=30)
        if response.ok:
            return
        print(f"[telegram] Markdown send failed ({response.status_code}): {response.text}")
        payload.pop("parse_mode")
        response = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload, timeout=30)
        if not response.ok:
            print(f"[telegram] plain send failed ({response.status_code}): {response.text}")
    except requests.RequestException as e:
        print(f"[telegram] send error: {e}")


def send_to_owner(text: str):
    """שולח הודעה לכל המשתמשים המורשים."""
    for chat_id in ALLOWED_CHAT_IDS:
        send_telegram_message(chat_id, text)


def send_typing(chat_id: int):
    """מציג "מקליד..." בטלגרם בזמן שהבוט חושב."""
    try:
        requests.post(f"{TELEGRAM_API_URL}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except requests.RequestException:
        pass


def download_telegram_file(file_id: str) -> Optional[bytes]:
    """מוריד קובץ שנשלח לבוט. מחזיר את התוכן, או None אם נכשל."""
    try:
        info = requests.get(f"{TELEGRAM_API_URL}/getFile", params={"file_id": file_id}, timeout=30)
        if not info.ok:
            print(f"[telegram] getFile failed ({info.status_code}): {info.text}")
            return None

        file_path = info.json().get("result", {}).get("file_path")
        if not file_path:
            return None

        file_response = requests.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}", timeout=60
        )
        if not file_response.ok:
            print(f"[telegram] file download failed ({file_response.status_code})")
            return None
        return file_response.content
    except requests.RequestException as e:
        print(f"[telegram] download error: {e}")
        return None
