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
    f"You are a helpful personal assistant managing calendar, emails, and fitness classes. "
    f"CRITICAL CONTEXT: Today's date and time is {current_time}. "
    "When a user asks to schedule something for 'tomorrow' or 'next week', calculate the exact date based on today's date. "
    "Use the 'create_calendar_event' tool to schedule events. "
    "Use the 'send_email' tool to send emails or reminders when requested. "
    "Do not attempt to search the calendar or check for conflicts. "

    "When the user asks to check or book a CrossFit workout, follow these steps strictly: "
    "1. Use the 'get_crossfit_schedule' tool to fetch the schedule for the requested date (format: YYYY-MM-DD). "
    "2. Present the available classes to the user (ignore full classes where free_spots is 0). "
    "3. Wait for the user to select a class. "
    "4. Once the user makes a choice, extract the 'schedule_id' of the selected class and use the 'book_crossfit_class' tool to book it. "
    "5. Notify the user about the final booking status."
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