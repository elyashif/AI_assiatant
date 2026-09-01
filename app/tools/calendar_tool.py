import os
from typing import List, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def create_calendar_event(
        title: str,
        start_time: str,
        end_time: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
        attendees_emails: Optional[List[str]] = None,
        reminder_minutes: Optional[int] = None
) -> dict:
    token_path = 'token.json'
    if not os.path.exists(token_path):
        return {"status": "error", "message": "token.json not found."}

    try:
        creds = Credentials.from_authorized_user_file(token_path, ['https://www.googleapis.com/auth/calendar.events'])
        service = build('calendar', 'v3', credentials=creds)

        event_body = {
            'summary': title,
            'start': {'dateTime': start_time, 'timeZone': 'Asia/Jerusalem'},
            'end': {'dateTime': end_time, 'timeZone': 'Asia/Jerusalem'},
        }

        if location:
            event_body['location'] = location
        if description:
            event_body['description'] = description
        if attendees_emails:
            event_body['attendees'] = [{'email': email} for email in attendees_emails]
        if reminder_minutes is not None:
            event_body['reminders'] = {
                'useDefault': False,
                'overrides': [{'method': 'popup', 'minutes': reminder_minutes}]
            }

        event_result = service.events().insert(calendarId='primary', body=event_body).execute()

        return {
            "status": "success",
            "message": f"Event '{title}' created successfully!",
            "link": event_result.get('htmlLink')
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}