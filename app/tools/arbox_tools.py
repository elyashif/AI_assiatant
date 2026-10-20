import os
import requests


def get_crossfit_schedule(date_str: str) -> str:
    """
    מושך את מערכת השעות של האימונים מתאריך מסוים במועדון ומסנן את המידע הרלוונטי לסוכן.
    """
    # החלף בכתובת ה-URL המלאה שמצאת בפרוקסימן עבור between-dates
    url = "https://apiappv2.arboxapp.com/api/v2/schedule/betweenDates"

    headers = {
        "Content-Type": "application/json",
        "accesstoken": os.getenv("ARBOX_TOKEN")
    }

    payload = {
        "from": date_str,
        "to": date_str,
        "locations_box_id": 479,
        "boxes_id": 396
    }

    try:
        response = requests.post(url, headers=headers, json=payload)

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
    """
    רושם את המשתמש לאימון ספציפי לפי מזהה האימון (schedule_id).
    """
    # החלף בכתובת ה-URL המלאה שמצאת בפרוקסימן עבור בקשת ההרשמה (book)
    url = "https://apiappv2.arboxapp.com/api/v2/scheduleUser/insert"

    headers = {
        "Content-Type": "application/json",
        "accesstoken": os.getenv("ARBOX_TOKEN"),
        "User-Agent": "Arbox/7200007 CFNetwork/3896.100.1.2.1 Darwin/27.0.0"
    }

    # הנתונים הקבועים שלך להרשמה
    payload = {
        "schedule_id": schedule_id,
        "membership_user_id": 14859324,
        "extras": {
            "spot": None,
            "invited_by": None
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)

        # קודי 200 או 201 מסמנים הצלחה בעולם ה-APIs
        if response.status_code in [200, 201]:
            return f"הרשמה לאימון (מזהה {schedule_id}) בוצעה בהצלחה!"
        else:
            return f"שגיאה בהרשמה: {response.status_code} - {response.text}"

    except Exception as e:
        return f"שגיאת מערכת בעת ניסיון ההרשמה: {str(e)}"


# --- אזור בדיקות מקומיות ---
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    print("בודק את הכלים מול שרתי Arbox...\n")

    # טסט 1: משיכת מערכת השעות
    # אתה יכול לשנות את התאריך למחר כדי לוודא שזה מושך נתונים עדכניים
    test_date = "2026-10-29"
    print(f"1. מושך אימונים לתאריך: {test_date}...")
    schedule_result = get_crossfit_schedule(test_date)
    print(schedule_result)
    print("\n" + "-" * 40 + "\n")

    # טסט 2: הרשמה לאימון
    # השארתי את זה בהערה כדי שלא תירשם בטעות. כדי לבדוק, הסר את הסולמיות (#)
    # והזן schedule_id אמיתי שקיבלת מהבדיקה הקודמת.

    print("2. מנסה להירשם לאימון...")
    booking_result = book_crossfit_class(55192414)
    print(booking_result)