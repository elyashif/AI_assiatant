import os
import json
import secrets
import requests
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from dotenv import load_dotenv

# 1. טעינת משתני סביבה - חייב להיות לפני השימוש ב-os.getenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# --- אבטחה ---
# רשימת ה-chat_id שמורשים לדבר עם הבוט, מופרדים בפסיקים (למשל: "123456789,987654321")
ALLOWED_CHAT_IDS = {
    int(x) for x in os.getenv("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x
}
# סיסמה סודית שטלגרם שולח בכל קריאה ל-webhook (מוגדרת ב-setWebhook עם secret_token)
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
# מפתח לנתיבי /api/* - יש לשלוח אותו בכותרת X-API-Key
API_KEY = os.getenv("API_KEY")


def _matches(given: Optional[str], expected: Optional[str]) -> bool:
    """השוואה בטוחה. אם הסוד לא הוגדר בכלל - חוסמים (ברירת מחדל סגורה)."""
    if not expected or not given:
        return False
    return secrets.compare_digest(given, expected)


def require_api_key(x_api_key: Optional[str] = Header(None)):
    if not _matches(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")

# 2. ייבוא הכלים והסוכן מהפרויקט
from app.tools.calendar_tool import create_calendar_event
from app.tools.gmail_tool import send_email
from app.agent import process_message
from app.tools.arbox_tools import SCHEDULE_CACHE

# 3. אתחול אפליקציית FastAPI
app = FastAPI(title="AI Agent API")

# 4. הגדרת מודלים (Pydantic) ל-API
class EventRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    location: Optional[str] = None
    description: Optional[str] = None
    attendees: Optional[List[str]] = None
    reminder_minutes: Optional[int] = 15

class EmailRequest(BaseModel):
    to_email: str
    subject: str
    body: str

class ChatRequest(BaseModel):
    prompt: str

class BookingResult(BaseModel):
    schedule_id: str
    result: str = ""


def send_telegram_message(chat_id: int, text: str):
    """שולח הודעה לטלגרם. אם ה-Markdown לא תקין (כמו _ או *), שולח שוב כטקסט רגיל."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"  # מפעיל קישורים לחיצים
    }
    response = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload, timeout=30)

    if not response.ok:
        print(f"[telegram] Markdown send failed ({response.status_code}): {response.text}")
        payload.pop("parse_mode")
        response = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload, timeout=30)
        if not response.ok:
            print(f"[telegram] plain send failed ({response.status_code}): {response.text}")


def process_and_reply(chat_id: int, user_text: str):
    """משימת רקע: חושבת דרך הסוכן ושולחת תשובה לטלגרם"""
    # מעבירים את ה-chat_id כדי שהבוט ידע לשלוף את הזיכרון הנכון
    agent_response = process_message(user_text, session_id=str(chat_id))
    send_telegram_message(chat_id, agent_response)


def _booking_error(raw: str) -> Optional[str]:
    """
    בודק אם התשובה של Arbox היא שגיאה. מחזיר הודעת שגיאה, או None אם ההרשמה הצליחה.
    """
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        # תשובה שאינה JSON (למשל דף שגיאה) נחשבת כישלון
        return (raw or "לא התקבלה תשובה מ-Arbox")[:300]

    if isinstance(data, dict):
        status = data.get("statusCode") or data.get("status_code") or data.get("code")
        if isinstance(status, int) and status >= 400:
            return str(data.get("message") or data.get("error") or status)
        if data.get("error") or data.get("errors"):
            return str(data.get("message") or data.get("error") or data.get("errors"))
        if data.get("success") is False or data.get("status") in ("error", "fail", "failed"):
            return str(data.get("message") or "Arbox דחו את ההרשמה")
    return None


def _add_workout_to_calendar(details: dict) -> bool:
    """מוסיף את האימון ליומן. מחזיר True אם הצליח."""
    try:
        start = datetime.strptime(f"{details['date']} {details['time']}", "%Y-%m-%d %H:%M")
    except (KeyError, ValueError):
        return False

    end = start + timedelta(hours=1)
    if details.get("end_time"):
        try:
            end = datetime.strptime(f"{details['date']} {details['end_time']}", "%Y-%m-%d %H:%M")
        except ValueError:
            pass

    result = create_calendar_event(
        title=f"🏋️ {details.get('type', 'אימון קרוספיט')}",
        start_time=start.strftime("%Y-%m-%dT%H:%M:%S"),
        end_time=end.strftime("%Y-%m-%dT%H:%M:%S"),
        description=f"מאמן: {details.get('coach', '')}",
        reminder_minutes=60,
    )
    return result.get("status") == "success"

@app.post("/api/chat", dependencies=[Depends(require_api_key)])
def chat_with_agent(request: ChatRequest):
    # עבור Swagger נשתמש במזהה קבוע בשם "swagger_test"
    answer = process_message(request.prompt, session_id="swagger_test")
    return {"response": answer}

# 6. נתיבי ה-API (Endpoints)
@app.get("/")
def read_root():
    env_name = os.getenv("ENVIRONMENT", "unknown")
    return {"message": "AI Agent is running!", "environment": env_name}

@app.post("/telegram-webhook")
async def telegram_webhook(
    update: dict,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    # 1. מוודאים שהקריאה באמת הגיעה מטלגרם
    if not _matches(x_telegram_bot_api_secret_token, TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_text = update["message"]["text"]

        # 2. עונים רק למשתמשים מורשים. אחרים מתעלמים בשקט
        if chat_id not in ALLOWED_CHAT_IDS:
            print(f"[security] ignored message from unauthorized chat_id={chat_id}")
            return {"status": "ok"}

        background_tasks.add_task(process_and_reply, chat_id, user_text)

    return {"status": "ok"}

@app.post("/api/calendar/create", dependencies=[Depends(require_api_key)])
def create_event(request: EventRequest):
    result = create_calendar_event(
        title=request.title,
        start_time=request.start_time,
        end_time=request.end_time,
        location=request.location,
        description=request.description,
        attendees_emails=request.attendees,
        reminder_minutes=request.reminder_minutes
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result

@app.post("/api/email/send", dependencies=[Depends(require_api_key)])
def send_agent_email(request: EmailRequest):
    result = send_email(
        to_email=request.to_email,
        subject=request.subject,
        body=request.body
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result


@app.post("/api/arbox/booking-result", dependencies=[Depends(require_api_key)])
def arbox_booking_result(request: BookingResult, background_tasks: BackgroundTasks):
    """
    קיצור הדרך BookArbox באייפון קורא לנתיב הזה אחרי ההרשמה, עם התשובה של Arbox.
    השרת שולח אישור בטלגרם ומוסיף את האימון ליומן.
    """
    print(f"[arbox] booking result for {request.schedule_id}: {request.result[:500]}")
    background_tasks.add_task(handle_booking_result, request.schedule_id, request.result)
    return {"status": "ok"}


def handle_booking_result(schedule_id: str, raw_result: str):
    details = SCHEDULE_CACHE.get(str(schedule_id).strip())
    error = _booking_error(raw_result)

    if error:
        text = f"❌ ההרשמה לא הצליחה.\nArbox ענו: {error}"
    elif details:
        added = _add_workout_to_calendar(details)
        text = (
            f"✅ נרשמת ל{details['type']} ב-{details['date']} בשעה {details['time']}"
            f" עם {details['coach']}."
            + ("\n📅 הוספתי ליומן." if added else "\n⚠️ לא הצלחתי להוסיף ליומן.")
        )
    else:
        # השרת הופעל מחדש מאז שמערכת השעות נמשכה, אז אין לנו את פרטי האימון
        text = "✅ ההרשמה נקלטה ב-Arbox. (לא הוספתי ליומן כי לא שמורים אצלי פרטי האימון.)"

    for chat_id in ALLOWED_CHAT_IDS:
        send_telegram_message(chat_id, text)
