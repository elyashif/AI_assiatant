import os
import re
from urllib.parse import quote
from curl_cffi import requests

from app import db
from app.config import PUBLIC_BASE_URL, TELEGRAM_BOT_USERNAME

# פרטי האימונים שנמשכו, לפי schedule_id. נשמרים גם במסד הנתונים,
# כדי לדעת מה להכניס ליומן אחרי שההרשמה מאושרת מהאייפון, גם אם השרת עלה מחדש בינתיים.
_class_cache = {}


def save_class_details(classes: dict):
    """שומר פרטי אימונים: {schedule_id: {date, time, end_time, type, coach}}."""
    _class_cache.update(classes)
    if not db.is_configured() or not classes:
        return
    from psycopg.types.json import Jsonb
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO arbox_classes (schedule_id, details, updated_at) VALUES (%s, %s, now())
                    ON CONFLICT (schedule_id) DO UPDATE SET details = EXCLUDED.details, updated_at = now()
                    """,
                    [(sid, Jsonb(details)) for sid, details in classes.items()],
                )
            conn.commit()
    except Exception as e:
        print(f"[arbox] could not save class details: {e}")


def get_class_details(schedule_id: str):
    """מחזיר את פרטי האימון, או None אם לא ידועים."""
    if schedule_id in _class_cache:
        return _class_cache[schedule_id]
    if not db.is_configured():
        return None
    try:
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT details FROM arbox_classes WHERE schedule_id = %s", (schedule_id,)
            ).fetchone()
    except Exception as e:
        print(f"[arbox] could not read class details: {e}")
        return None
    return row[0] if row else None


def _hhmm(value) -> str:
    """ממיר שעה כמו '18:00:00' ל-'18:00'."""
    return str(value)[:5] if value else ""

def get_crossfit_schedule(date_str: str) -> str:
    """
    מושך את מערכת השעות של האימונים מתאריך מסוים במועדון ומסנן את המידע הרלוונטי לסוכן.
    """
    # החלף בכתובת ה-URL המלאה שמצאת בפרוקסימן עבור between-dates
    url = "https://apiappv2.arboxapp.com/api/v2/schedule/betweenDates"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "accesstoken": os.getenv("ARBOX_TOKEN"),  # שים לב: שינינו את שם המפתח!
        "version": "15",
        "referername": "app",
        "whitelabel": "Arbox",
        "User-Agent": "Arbox/7200007 CFNetwork/3896.100.1.2.1 Darwin/27.0.0",
        "Content-Type": "application/json"
    }

    payload = {
        "from": date_str,
        "to": date_str,
        "locations_box_id": 479,
        "boxes_id": 396
    }

    try:
        response = requests.post(url, headers=headers, json=payload, impersonate="safari_ios")

        if response.status_code == 200:
            raw_data = response.json()

            # התיקון: שולפים את הרשימה מתוך המפתח "data"
            workouts_list = raw_data.get("data", [])

            filtered_schedule = []
            class_details = {}
            for workout in workouts_list:
                if "id" in workout:
                    # שולפים את המילונים, ואם השרת החזיר null (None), הופכים אותם למילון ריק
                    coach_data = workout.get("coach") or {}
                    category_data = workout.get("box_categories") or {}

                    class_info = {
                        "schedule_id": workout["id"],
                        "time": workout.get("time", "לא ידוע"),
                        "type": category_data.get("name", "אימון קרוספיט"),
                        "coach": coach_data.get("first_name", "צוות קונופיט"),
                        "free_spots": workout.get("free", 0)
                    }
                    filtered_schedule.append(class_info)
                    class_details[str(workout["id"])] = {
                        "date": date_str,
                        "time": _hhmm(workout.get("time")),
                        "end_time": _hhmm(workout.get("end_time")),
                        "type": class_info["type"],
                        "coach": class_info["coach"],
                    }
            save_class_details(class_details)
            if not filtered_schedule:
                return f"לא נמצאו אימונים לתאריך {date_str}."

            return str(filtered_schedule)
        else:
            return f"שגיאה במשיכת הלוז: {response.status_code} - {response.text}"

    except Exception as e:
        return f"שגיאת מערכת בעת משיכת הלוז: {str(e)}"


def normalize_schedule_id(value) -> str:
    """
    Gemini לפעמים מעביר מספרים כ-float (למשל 58058683.0).
    מחזיר את המספר כמחרוזת נקייה ('58058683'), או מחרוזת ריקה אם הערך לא תקין.
    """
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)(?:\.0+)?", text)
    return match.group(1) if match else ""


def build_shortcut_url(schedule_id: str) -> str:
    """הקישור שמפעיל באייפון את קיצור הדרך BookArbox וחוזר לטלגרם בסיום."""
    back_to_telegram = (
        f"tg://resolve?domain={TELEGRAM_BOT_USERNAME}" if TELEGRAM_BOT_USERNAME else "tg://"
    )
    return (
        "shortcuts://x-callback-url/run-shortcut"
        f"?name=BookArbox&input=text&text={schedule_id}"
        f"&x-success={quote(back_to_telegram, safe='')}"
    )


def book_crossfit_class(schedule_id: int) -> str:
    """
    מחזיר קישור הרשמה. טלגרם לא תמיד מציג קישורי shortcuts:// כלחיצים,
    לכן הקישור הוא https לשרת שלנו (/arbox/book/<id>), שמעביר מיד לקיצור הדרך באייפון.
    ההרשמה עצמה נשלחת מהאייפון, וקיצור הדרך מדווח את התוצאה לשרת (/api/arbox/booking-result).
    """
    schedule_id = normalize_schedule_id(schedule_id)
    if not schedule_id:
        return "לא הצלחתי לזהות את מספר האימון. נסה לבחור שוב."

    base_url = PUBLIC_BASE_URL
    if not base_url:
        return f"לחץ להרשמה 👇\n[הירשם ✅]({build_shortcut_url(schedule_id)})"

    return f"לחץ להרשמה, ואני אעדכן אותך כשזה נקלט 👇\n{base_url}/arbox/book/{schedule_id}"
