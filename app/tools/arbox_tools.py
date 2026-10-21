import os
import requests
from curl_cffi import requests

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
            if not filtered_schedule:
                return f"לא נמצאו אימונים לתאריך {date_str}."

            return str(filtered_schedule)
        else:
            return f"שגיאה במשיכת הלוז: {response.status_code} - {response.text}"

    except Exception as e:
        return f"שגיאת מערכת בעת משיכת הלוז: {str(e)}"


def book_crossfit_class(schedule_id: int) -> str:
    shortcut_url = f"shortcuts://run-shortcut?name=BookArbox&input={schedule_id}"

    # עכשיו אנחנו שולחים את זה בפורמט של קישור לחיץ
    return f"הכנתי את ההרשמה לאימון! 👇\n[לחץ כאן לאישור והרשמה באייפון]({shortcut_url})"