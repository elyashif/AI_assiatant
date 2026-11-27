"""
כל ההגדרות של הבוט במקום אחד. הערכים נקראים ממשתני הסביבה (ב-Render או בקובץ .env).
"""
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# חייב לרוץ לפני הקריאה למשתני הסביבה
load_dotenv()

# --- טלגרם ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME")

# --- אבטחה ---
# chat_id שמורשים לדבר עם הבוט, מופרדים בפסיקים
ALLOWED_CHAT_IDS = {
    int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x
}
# הסיסמה שטלגרם שולח בכל קריאה ל-webhook
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
# מפתח לנתיבי /api/* (כותרת X-API-Key)
API_KEY = os.getenv("API_KEY")

# --- מודל ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# --- מסד נתונים ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- כללי ---
TIMEZONE = ZoneInfo("Asia/Jerusalem")
ENVIRONMENT = os.getenv("ENVIRONMENT", "unknown")
# הכתובת הציבורית של השרת (Render מגדיר את RENDER_EXTERNAL_URL אוטומטית)
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
