"""
השרת של הבוט: מקבל הודעות מטלגרם ובקשות מקיצורי הדרך באייפון.
הלוגיקה עצמה נמצאת בקבצים אחרים:
  agent.py           - הסוכן (Gemini + כלים)
  memory.py          - זיכרון השיחות
  telegram_client.py - שליחה וקבלה מטלגרם
  arbox_booking.py   - אישור הרשמה לאימונים
  tools/             - הכלים שהסוכן יכול להפעיל
"""
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import ENVIRONMENT, TELEGRAM_WEBHOOK_SECRET
from app.security import matches_secret, require_api_key, is_allowed_chat
from app.agent import process_message
from app.memory import clear_history
from app.telegram_client import send_telegram_message, send_typing, download_telegram_file
from app.arbox_booking import handle_booking_result, booking_redirect_page
from app.tools.calendar_tool import create_calendar_event
from app.tools.gmail_tool import send_email

app = FastAPI(title="AI Agent API")


# ---------- מודלים ל-API ----------

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


# ---------- טלגרם ----------

RESET_COMMANDS = {"/new", "/reset", "שיחה חדשה"}
# טלגרם מאפשר לבוטים להוריד קבצים עד 20MB
MAX_MEDIA_BYTES = 19 * 1024 * 1024


@app.post("/telegram-webhook")
async def telegram_webhook(
    update: dict,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    # 1. מוודאים שהקריאה באמת הגיעה מטלגרם
    if not matches_secret(x_telegram_bot_api_secret_token, TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")

    message = update.get("message")
    if not message:
        return {"status": "ok"}

    chat_id = message["chat"]["id"]

    # 2. עונים רק למשתמשים מורשים. אחרים מתעלמים בשקט
    if not is_allowed_chat(chat_id):
        print(f"[security] ignored message from unauthorized chat_id={chat_id}")
        return {"status": "ok"}

    if "text" in message:
        text = message["text"].strip()
        if text in RESET_COMMANDS:
            background_tasks.add_task(reset_conversation, chat_id)
        else:
            background_tasks.add_task(reply_to_text, chat_id, text)

    elif "photo" in message:
        # טלגרם שולח כמה גדלים של אותה תמונה. האחרון הוא הגדול ביותר
        file_id = message["photo"][-1]["file_id"]
        background_tasks.add_task(reply_to_media, chat_id, file_id, "image/jpeg", message.get("caption", ""))

    elif "voice" in message or "audio" in message:
        # הודעה קולית (voice) או קובץ שמע (audio)
        media = message.get("voice") or message.get("audio")
        mime_type = media.get("mime_type") or "audio/ogg"
        if media.get("file_size", 0) > MAX_MEDIA_BYTES:
            background_tasks.add_task(send_telegram_message, chat_id, "ההקלטה ארוכה מדי, נסה הקלטה קצרה יותר.")
        else:
            background_tasks.add_task(
                reply_to_media, chat_id, media["file_id"], mime_type, message.get("caption", "")
            )

    elif message.get("document", {}).get("mime_type", "").startswith("image/"):
        # תמונה שנשלחה כקובץ (באיכות מלאה)
        document = message["document"]
        background_tasks.add_task(
            reply_to_media, chat_id, document["file_id"], document["mime_type"], message.get("caption", "")
        )

    else:
        background_tasks.add_task(send_telegram_message, chat_id, "כרגע אני יודע לקרוא טקסט, תמונות והודעות קוליות 🙂")

    return {"status": "ok"}


def reply_to_text(chat_id: int, text: str):
    """משימת רקע: חושבת דרך הסוכן ושולחת תשובה לטלגרם"""
    send_typing(chat_id)
    send_telegram_message(chat_id, process_message(text, session_id=str(chat_id)))


def reply_to_media(chat_id: int, file_id: str, mime_type: str, caption: str):
    """משימת רקע: מורידה תמונה או הקלטה מטלגרם, מעבירה לסוכן ושולחת את התשובה"""
    send_typing(chat_id)
    media_data = download_telegram_file(file_id)
    if media_data is None:
        send_telegram_message(chat_id, "לא הצלחתי להוריד את הקובץ, נסה לשלוח שוב.")
        return
    reply = process_message(caption, session_id=str(chat_id), media_data=media_data, media_mime_type=mime_type)
    send_telegram_message(chat_id, reply)


def reset_conversation(chat_id: int):
    clear_history(str(chat_id))
    send_telegram_message(chat_id, "🧹 התחלנו שיחה חדשה.")


# ---------- כללי ----------

@app.get("/")
def read_root():
    return {"message": "AI Agent is running!", "environment": ENVIRONMENT}


@app.post("/api/chat", dependencies=[Depends(require_api_key)])
def chat_with_agent(request: ChatRequest):
    # עבור Swagger נשתמש במזהה קבוע בשם "swagger_test"
    return {"response": process_message(request.prompt, session_id="swagger_test")}


@app.post("/api/calendar/create", dependencies=[Depends(require_api_key)])
def create_event(request: EventRequest):
    result = create_calendar_event(
        title=request.title,
        start_time=request.start_time,
        end_time=request.end_time,
        location=request.location,
        description=request.description,
        attendees_emails=request.attendees,
        reminder_minutes=request.reminder_minutes,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result


@app.post("/api/email/send", dependencies=[Depends(require_api_key)])
def send_agent_email(request: EmailRequest):
    result = send_email(to_email=request.to_email, subject=request.subject, body=request.body)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result


# ---------- קרוספיט (Arbox) ----------

@app.get("/arbox/book/{schedule_id}", response_class=HTMLResponse)
def arbox_book_redirect(schedule_id: str):
    page = booking_redirect_page(schedule_id)
    if page is None:
        raise HTTPException(status_code=400, detail="Invalid schedule id")
    return page


@app.post("/api/arbox/booking-result", dependencies=[Depends(require_api_key)])
def arbox_booking_result(request: BookingResult, background_tasks: BackgroundTasks):
    """קיצור הדרך BookArbox באייפון מדווח לכאן את התשובה של Arbox."""
    print(f"[arbox] booking result for {request.schedule_id}: {request.result[:500]}")
    background_tasks.add_task(handle_booking_result, request.schedule_id, request.result)
    return {"status": "ok"}


# ---------- רשימת קניות ----------

@app.post("/api/shopping/claim", dependencies=[Depends(require_api_key)])
def shopping_claim():
    """
    קיצור הדרך באייפון קורא לנתיב הזה כשפותחים את Reminders.
    מחזיר את הפריטים הממתינים ומסמן אותם כמועברים.
    """
    from app.tools.shopping_tool import claim_pending_items
    try:
        items = claim_pending_items()
    except Exception as e:
        print(f"[shopping] claim failed: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    print(f"[shopping] sent {len(items)} items to the iPhone")
    return {"items": items, "count": len(items)}
