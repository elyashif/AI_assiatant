"""
הרשמה לאימוני Arbox דרך האייפון:
1. הבוט שולח קישור לדף ההעברה (booking_redirect_page), שפותח את קיצור הדרך BookArbox.
2. קיצור הדרך נרשם ב-Arbox מהאייפון, ומדווח את התשובה לשרת.
3. handle_booking_result שולח אישור בטלגרם ומוסיף את האימון ליומן.
"""
import json
from datetime import datetime, timedelta
from html import escape
from typing import Optional

from app.telegram_client import send_to_owner
from app.tools.arbox_tools import get_class_details, build_shortcut_url, normalize_schedule_id
from app.tools.calendar_tool import create_calendar_event


def handle_booking_result(schedule_id: str, raw_result: str):
    details = get_class_details(normalize_schedule_id(schedule_id))
    error = _booking_error(raw_result)
    already_registered_here = _is_already_registered_for(details, raw_result)

    if already_registered_here:
        send_to_owner("✅ אתה כבר רשום לאימון הזה.")
        return

    if error:
        text = f"❌ ההרשמה לא הצליחה:\n{error}"
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

    send_to_owner(text)


def _is_already_registered_for(details: Optional[dict], raw: str) -> bool:
    """האם Arbox ענו שכבר רשומים בדיוק לאימון הזה (למשל אם קיצור הדרך רץ פעמיים)."""
    if not details:
        return False
    try:
        items = json.loads(raw).get("messageToUser")
    except (ValueError, TypeError, AttributeError):
        return False
    if isinstance(items, dict):
        items = [items]
    for item in items or []:
        if isinstance(item, dict) and item.get("name") == "alreadyRegistered":
            value = item.get("value") or {}
            # Arbox מחזירים תאריך בפורמט 29/11/26, ואצלנו הוא 2026-11-29
            try:
                y, m, d = details["date"].split("-")
                same_date = value.get("date") == f"{d}/{m}/{y[2:]}"
            except (KeyError, ValueError):
                same_date = False
            if same_date and value.get("time") == details.get("time"):
                return True
    return False


def _describe_arbox_problems(data: dict) -> Optional[str]:
    """הופך את רשימת הבעיות של Arbox (messageToUser) להודעה ברורה בעברית."""
    items = data.get("messageToUser")
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return None

    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value") if isinstance(item.get("value"), dict) else {}
        if name == "alreadyRegistered":
            lines.append(
                f"כבר רשום ל-{value.get('name', 'אימון')} ב-{value.get('date', '')} בשעה {value.get('time', '')}."
            )
        elif name == "categoryFrequencyRestricts":
            lines.append(
                f"הגעת למכסה של המנוי: {value.get('frequency', '')} אימונים "
                f"ל{'יום' if value.get('unit') == 'DAY' else 'תקופה'} ({value.get('groupName', '')})."
            )
        else:
            lines.append(str(item.get("message") or name or item))
    return "\n".join(f"• {line}" for line in lines) if lines else None


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
        failed = (
            (isinstance(status, int) and status >= 400)
            or bool(data.get("error") or data.get("errors"))
            or data.get("success") is False
            or data.get("status") in ("error", "fail", "failed")
        )
        if failed:
            return (
                _describe_arbox_problems(data)
                or str(data.get("message") or data.get("error") or data.get("errors") or status)
            )
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


def booking_redirect_page(schedule_id: str) -> Optional[str]:
    """
    דף קצר שטלגרם פותח בלחיצה, ומעביר מיד לקיצור הדרך BookArbox באייפון.
    לא מבצע הרשמה בעצמו, רק מעביר לאייפון. מחזיר None אם המספר לא תקין.
    """
    schedule_id = normalize_schedule_id(schedule_id)
    if not schedule_id:
        return None

    shortcut_url = build_shortcut_url(schedule_id)
    target = escape(shortcut_url, quote=True)  # לשימוש בתוך HTML
    target_js = json.dumps(shortcut_url)       # לשימוש בתוך JavaScript
    details = get_class_details(schedule_id) or {}
    label = escape(f"{details.get('type', 'אימון')} {details.get('date', '')} {details.get('time', '')}".strip())

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>הרשמה לאימון</title>
<style>body{{font-family:-apple-system,sans-serif;text-align:center;padding:48px 20px}}
a{{display:inline-block;margin-top:24px;padding:16px 28px;background:#2f6fed;color:#fff;
border-radius:14px;text-decoration:none;font-size:20px}}</style></head>
<body><p>פותח את קיצור הדרך להרשמה…</p><p>{label}</p>
<a href="{target}">הירשם ✅</a>
<script>
// פותחים את קיצור הדרך פעם אחת בלבד, גם אם הדף נטען מחדש
if (!sessionStorage.getItem("opened-{schedule_id}")) {{
  try {{ sessionStorage.setItem("opened-{schedule_id}", "1"); }} catch (e) {{}}
  location.href = {target_js};
}}
</script></body></html>"""
