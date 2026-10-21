import os
import requests
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, BackgroundTasks
from dotenv import load_dotenv

# 1. טעינת משתני סביבה - חייב להיות לפני השימוש ב-os.getenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

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

@app.post("/api/chat")
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
async def telegram_webhook(update: dict, background_tasks: BackgroundTasks):
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_text = update["message"]["text"]

        background_tasks.add_task(process_and_reply, chat_id, user_text)

    return {"status": "ok"}

@app.post("/api/chat")
def chat_with_agent(request: ChatRequest):
    answer = process_message(request.prompt)
    return {"response": answer}

@app.post("/api/calendar/create")
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

@app.post("/api/email/send")
def send_agent_email(request: EmailRequest):
    result = send_email(
        to_email=request.to_email,
        subject=request.subject,
        body=request.body
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result