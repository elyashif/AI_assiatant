"""
הסוכן: מקבל הודעה, מתייעץ עם Gemini, מפעיל כלים לפי הצורך ומחזיר תשובה.

לולאת הכלים כתובה כאן במפורש (במקום ההפעלה האוטומטית של הספרייה הישנה),
כך שאנחנו שולטים בכל קריאה לכלי: מתקנים פרמטרים, תופסים שגיאות ורושמים ללוג.
"""
import inspect
import json
import typing
from datetime import datetime
from typing import Callable, Dict, List, Optional

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL, TIMEZONE
from app.memory import load_history, save_history

# 1. הכלים של הבוט
from app.tools.calendar_tool import create_calendar_event
from app.tools.gmail_tool import send_email
from app.tools.arbox_tools import get_crossfit_schedule, book_crossfit_class
from app.tools.shopping_tool import add_to_shopping_list, get_pending_shopping_items
from app.tools.web_tool import search_web, read_url

TOOL_FUNCTIONS: List[Callable] = [
    create_calendar_event,
    send_email,
    get_crossfit_schedule,
    book_crossfit_class,
    add_to_shopping_list,
    get_pending_shopping_items,
    search_web,
    read_url,
]
TOOLS: Dict[str, Callable] = {f.__name__: f for f in TOOL_FUNCTIONS}

# כמה סבבים של קריאות לכלים מותר בהודעה אחת (הגנה מלולאה אינסופית)
MAX_TOOL_ROUNDS = 8

# 2. הפרומפט
SYSTEM_PROMPT = (
    "You are a helpful personal assistant managing calendar, emails, fitness classes and a shopping list. "
    "Reply in the user's language (usually Hebrew), briefly and clearly. "
    "CRITICAL CONTEXT: Every user message starts with a line in square brackets that gives the current "
    "date and time in Israel. Always use the most recent one; never assume a date from earlier messages. "
    "All times are in the Asia/Jerusalem timezone. "
    "When a user asks to schedule something for 'tomorrow' or 'next week', calculate the exact date based on today's date. "
    "Use the 'create_calendar_event' tool to schedule events. "
    "Use the 'send_email' tool to send emails or reminders when requested. "
    "Do not attempt to search the calendar or check for conflicts. "

    "The user may send images (for example an invitation, a flyer, a screenshot or a receipt). "
    "Read them carefully, including Hebrew text. If the user asks to add what is in the image to the calendar, "
    "extract the title, date, time and location and use 'create_calendar_event'. "
    "If the image has event details but no instructions, summarize them and offer to add them to the calendar. "

    "When the user mentions groceries or household items that ran out or are needed "
    "(for example 'נגמר החלב', 'צריך לקנות ביצים ולחם'), use 'add_to_shopping_list' with the items "
    "separated by commas, each as a short item name in the user's language. Confirm briefly. "
    "Use 'get_pending_shopping_items' only to show items that were not yet moved to the iPhone. "

    "Use 'search_web' for questions that need current or local information (opening hours, weather, news, "
    "prices, addresses, facts you are not sure about). Use 'read_url' when the user sends a link, "
    "for example a recipe (then offer to add the ingredients to the shopping list) or an article to summarize. "
    "When you use sources, mention them briefly. "

    "The user may send voice messages. Treat what is said in the recording as the user's request and act on it "
    "exactly like a typed message. Start your reply with '🎤 ' and a very short summary of what you understood. "

    "When the user asks to check or book a CrossFit workout, follow these steps strictly: "
    "1. Use the 'get_crossfit_schedule' tool to fetch the schedule for the requested date (format: YYYY-MM-DD). "
    "2. Present the available classes to the user (ignore full classes where free_spots is 0). "
    "3. Wait for the user to select a class. "
    "4. Once the user makes a choice, extract the 'schedule_id' of the selected class and use the 'book_crossfit_class' tool to book it. "
    "5. The tool returns a message with a link. Send it to the user exactly as returned, keeping the full URL unchanged. "
    "The user taps it to complete the booking on their iPhone, and a separate confirmation message "
    "will arrive automatically. Do not claim the booking is already confirmed."
)

# 3. החיבור ל-Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration.from_callable_with_api_option(callable=f, api_option="GEMINI_API")
    for f in TOOL_FUNCTIONS
]

GENERATION_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[types.Tool(function_declarations=FUNCTION_DECLARATIONS)],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)

ERROR_MESSAGE = "מצטער, הייתה שגיאה בעיבוד הבקשה: {}"


def current_time_line() -> str:
    """שורה עם התאריך והשעה העדכניים בישראל, שמצורפת לכל הודעה שנשלחת למודל."""
    now = datetime.now(TIMEZONE)
    return f"[Current date and time in Israel: {now.strftime('%A, %Y-%m-%d %H:%M')}]"


def process_message(user_text: str, session_id: str = "default", media_data: bytes = None,
                    media_mime_type: str = "image/jpeg") -> str:
    """הפונקציה המרכזית: מקבלת הודעה ומחזירה את התשובה של הבוט."""
    history = load_history(session_id)

    parts = [types.Part(text=current_time_line())]
    if user_text:
        parts.append(types.Part(text=user_text))
    elif media_mime_type.startswith("audio/"):
        parts.append(types.Part(text="(voice message)"))
    else:
        parts.append(types.Part(text="תאר לי מה אתה רואה בתמונה הזו ואיך אפשר לעזור לגביה."))
    if media_data:
        parts.append(types.Part.from_bytes(data=media_data, mime_type=media_mime_type))

    conversation = history + [types.Content(role="user", parts=parts)]

    try:
        reply = _run_tool_loop(conversation)
    except Exception as e:
        print(f"[agent] error: {e!r}")
        # לא שומרים היסטוריה חלקית, כדי שהשיחה הבאה לא תתחיל במצב שבור
        return ERROR_MESSAGE.format(e)

    save_history(session_id, conversation)
    return reply


def _run_tool_loop(conversation: List[types.Content]) -> str:
    """שולח ל-Gemini, מריץ את הכלים שביקש, ומחזיר את התשובה הסופית. מעדכן את conversation."""
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=conversation, config=GENERATION_CONFIG
        )

        candidate = response.candidates[0] if response.candidates else None
        if not candidate or not candidate.content or not candidate.content.parts:
            return "לא הצלחתי לנסח תשובה, נסה לנסח את הבקשה אחרת."

        conversation.append(candidate.content)
        calls = [part.function_call for part in candidate.content.parts if part.function_call]

        if not calls:
            text = "".join(
                part.text for part in candidate.content.parts if part.text and not part.thought
            ).strip()
            return text or "✅"

        response_parts = [
            types.Part.from_function_response(
                name=call.name, response={"result": run_tool(call.name, call.args or {})}
            )
            for call in calls
        ]
        conversation.append(types.Content(role="user", parts=response_parts))

    return "הבקשה דרשה יותר מדי פעולות. נסה לפרק אותה לבקשות קטנות יותר."


def run_tool(name: str, args: dict):
    """מריץ כלי לפי שם. מחזיר את התוצאה, או הודעת שגיאה שהמודל יכול להבין."""
    function = TOOLS.get(name)
    if function is None:
        return f"Error: unknown tool '{name}'"

    try:
        clean_args = _coerce_args(function, dict(args))
        print(f"[tool] {name}({json.dumps(clean_args, ensure_ascii=False, default=str)[:300]})")
        result = function(**clean_args)
    except Exception as e:
        print(f"[tool] {name} failed: {e!r}")
        return f"Error while running {name}: {e}"

    # התוצאה חייבת להיות ניתנת להמרה ל-JSON
    try:
        json.dumps(result)
        return result
    except (TypeError, ValueError):
        return str(result)


def _coerce_args(function: Callable, args: dict) -> dict:
    """
    מתקן ערכים שהמודל שולח בפורמט לא מדויק.
    למשל: 58058683.0 בפרמטר מסוג int הופך ל-58058683.
    """
    hints = typing.get_type_hints(function)
    signature = inspect.signature(function)
    clean = {}
    for key, value in args.items():
        if key not in signature.parameters:
            continue  # מתעלמים מפרמטרים שהמודל המציא
        expected = hints.get(key)
        if _accepts_int(expected) and isinstance(value, float) and value.is_integer():
            value = int(value)
        clean[key] = value
    return clean


def _accepts_int(hint) -> bool:
    if hint is int:
        return True
    return typing.get_origin(hint) is typing.Union and int in typing.get_args(hint)
