from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ייבוא הכלים מתוך התיקייה שסידרנו
from app.tools.calendar_tool import create_calendar_event
from app.tools.gmail_tool import send_email

load_dotenv()
client = genai.Client()

# הגדרת הזמן הנוכחי וההנחיות למודל
current_time = datetime.now().strftime("%A, %B %d, %Y %H:%M:%S")
sys_prompt = (
    f"You are a helpful calendar and email assistant. "
    f"CRITICAL CONTEXT: Today's date and time is {current_time}. "
    "When a user asks to schedule something for 'tomorrow' or 'next week', calculate the exact date based on today's date. "
    "Use the 'create_calendar_event' tool to schedule events. "
    "Use the 'send_email' tool to send emails or reminders when requested. "
    "Do not attempt to search the calendar or check for conflicts."
)

# יצירת סשן הצ'אט שומר-הזיכרון
chat = client.chats.create(
    model="gemini-3.6-flash",
    config=types.GenerateContentConfig(
        tools=[create_calendar_event, send_email],
        temperature=0.2,
        system_instruction=sys_prompt
    )
)

def process_message(user_input: str) -> str:
    """
    Receives a message string, sends it to Gemini, and returns the response.
    """
    try:
        response = chat.send_message(user_input)
        return response.text
    except Exception as e:
        return f"Agent Error: {str(e)}"