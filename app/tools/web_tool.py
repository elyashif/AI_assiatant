"""
חיפוש באינטרנט וקריאת קישורים, בעזרת הכלים המובנים של Gemini
(Google Search ו-URL context).

כל כלי כאן שולח בקשה נפרדת ל-Gemini עם הכלי המובנה בלבד, ומחזיר לסוכן תשובה מוכנה.
ככה לא צריך לשלב כלים מובנים עם הכלים שלנו באותה בקשה.
"""
from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL

_client = genai.Client(api_key=GEMINI_API_KEY)

_SEARCH_CONFIG = types.GenerateContentConfig(
    tools=[types.Tool(google_search=types.GoogleSearch())],
    system_instruction=(
        "Answer using up-to-date information from Google Search. Be concise and factual. "
        "Answer in the language of the question. Mention when information may be outdated."
    ),
)

_URL_CONFIG = types.GenerateContentConfig(
    tools=[types.Tool(url_context=types.UrlContext())],
    system_instruction=(
        "Read the given web page and answer the request based on its content. "
        "Be concise. Answer in the language of the request."
    ),
)


def _sources(response) -> str:
    """מחזיר רשימת מקורות קצרה מתוך נתוני ה-grounding, אם יש."""
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
    except (AttributeError, IndexError, TypeError):
        return ""
    lines = []
    for chunk in chunks[:3]:
        web = getattr(chunk, "web", None)
        if web and web.uri:
            lines.append(f"- {web.title or web.uri}: {web.uri}")
    return "\nSources:\n" + "\n".join(lines) if lines else ""


def search_web(query: str) -> str:
    """
    מחפש באינטרנט מידע עדכני: שעות פתיחה, מזג אוויר, חדשות, מחירים, פרטי עסקים ועוד.
    query: מה לחפש, כשאלה מלאה (למשל "מתי נסגר הסופר רמי לוי בגבעת שמואל ביום שישי").
    """
    try:
        response = _client.models.generate_content(model=GEMINI_MODEL, contents=query, config=_SEARCH_CONFIG)
        return (response.text or "לא נמצאה תשובה.") + _sources(response)
    except Exception as e:
        return f"שגיאה בחיפוש: {e}"


def read_url(url: str, request: str) -> str:
    """
    קורא דף אינטרנט ועונה עליו: סיכום כתבה, מצרכים ממתכון, פרטי אירוע מדף הזמנה וכו'.
    url: הכתובת המלאה של הדף.
    request: מה להוציא מהדף (למשל "רשימת המצרכים", "סיכום בשלוש נקודות").
    """
    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL, contents=f"{request}\n\nURL: {url}", config=_URL_CONFIG
        )
        return response.text or "לא הצלחתי לקרוא את הדף."
    except Exception as e:
        return f"שגיאה בקריאת הדף: {e}"
