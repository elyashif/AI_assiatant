import os
import requests
from pydantic import BaseModel
from typing import List, Optional

from dotenv import load_dotenv

# ייבוא הכלים מהקבצים החדשים
from app.tools.calendar_tool import create_calendar_event
from app.tools.gmail_tool import send_email
from app.agent import process_message
from fastapi import FastAPI, HTTPException, BackgroundTasks


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

load_dotenv()
app = FastAPI(title="AI Agent API")

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

@app.get("/")
def read_root():
    env_name = os.getenv("ENVIRONMENT", "unknown")
    return {"message": "AI Agent is running!", "environment": env_name}

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
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    return result

@app.post("/api/email/send")
def send_agent_email(request: EmailRequest):
    result = send_email(
        to_email=request.to_email,
        subject=request.subject,
        body=request.body
    )
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    return result

class ChatRequest(BaseModel):
    prompt: str

@app.post("/api/chat")
def chat_with_agent(request: ChatRequest):
    answer = process_message(request.prompt)
    return {"response": answer}


def process_and_reply(chat_id: int, user_text: str):
    """משימת רקע: חושבת דרך הסוכן ושולחת תשובה לטלגרם"""
    agent_response = process_message(user_text)

    payload = {
        "chat_id": chat_id,
        "text": agent_response
    }
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)


@app.post("/telegram-webhook")
async def telegram_webhook(update: dict, background_tasks: BackgroundTasks):  # <--- כאן כנראה חסר לך ה-background_tasks
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_text = update["message"]["text"]

        # עכשיו FastAPI מכיר את המשתנה ויודע להפעיל אותו
        background_tasks.add_task(process_and_reply, chat_id, user_text)

    return {"status": "ok"}