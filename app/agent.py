import os
import google.generativeai as genai
from datetime import datetime

# 1. ייבוא כל הכלים שלך (יומן, מייל וקרוספיט)
from app.tools.calendar_tool import create_calendar_event
from app.tools.gmail_tool import send_email
from app.tools.arbox_tools import get_crossfit_schedule, book_crossfit_class

# 2. הגדרת חיבור לגוגל
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# 3. חישוב הזמן הנוכחי כדי שהבוט ידע מה זה "מחר"
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 4. הפרומפט המעודכן שכולל את ארבוקס
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

# 5. הגדרת המודל - כאן הוא מוגדר כך שהפונקציה למטה תכיר אותו
model = genai.GenerativeModel(
    model_name="gemini-3.6-flash",  # ודא שזה המודל שמוגדר אצלך (למשל gemini-1.5-pro אם צריך)
    tools=[
        create_calendar_event,
        send_email,
        get_crossfit_schedule,
        book_crossfit_class
    ],
    system_instruction=sys_prompt
)

# מילון גלובלי שישמור את השיחות הפעילות (הזיכרון של הבוט)
active_chats = {}

# 6. הפונקציה המרכזית שמנהלת את התקשורת
def process_message(user_text: str, session_id: str = "default", image_data: bytes = None) -> str:
    # אם זו פעם ראשונה שהמשתמש הזה פונה, ניצור לו שיחה חדשה ונשמור אותה
    if session_id not in active_chats:
        active_chats[session_id] = model.start_chat(enable_automatic_function_calling=True)

    # שולפים את השיחה הקיימת של המשתמש (עם כל ההיסטוריה)
    chat = active_chats[session_id]

    prompt_parts = []

    if user_text:
        prompt_parts.append(user_text)
    else:
        prompt_parts.append("תאר לי מה אתה רואה בתמונה הזו ואיך אפשר לעזור לגביה.")

    if image_data:
        image_part = {
            "mime_type": "image/jpeg",
            "data": image_data
        }
        prompt_parts.append(image_part)

    try:
        response = chat.send_message(prompt_parts)

        try:
            return response.text
        except ValueError:
            safe_text = "".join([part.text for part in response.parts if hasattr(part, 'text')])
            return safe_text

    except Exception as e:
        return f"מצטער, הייתה שגיאה בעיבוד הבקשה: {str(e)}"