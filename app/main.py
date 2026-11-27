import os
import secrets
import requests
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

def process_and_reply(chat_id: int, user_text: str):
    """משימת רקע: חושבת דרך הסוכן ושולחת תשובה לטלגרם"""
    # מעבירים את ה-chat_id כדי שהבוט ידע לשלוף את הזיכרון הנכון
    agent_response = process_message(user_text, session_id=str(chat_id))

    payload = {
        "chat_id": chat_id,
        "text": agent_response,
        "parse_mode": "Markdown"  # <--- השורה החדשה שמפעילה את הקישורים הלחיציo
    }
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)

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