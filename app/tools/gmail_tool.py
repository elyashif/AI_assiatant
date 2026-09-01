import os
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def send_email(to_email: str, subject: str, body: str) -> dict:
    token_path = 'token.json'
    if not os.path.exists(token_path):
        return {"status": "error", "message": "token.json not found."}

    try:
        creds = Credentials.from_authorized_user_file(token_path)
        service = build('gmail', 'v1', credentials=creds)

        message = MIMEText(body)
        message['To'] = to_email
        message['Subject'] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        result = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()

        return {
            "status": "success",
            "message": f"Email sent successfully to {to_email}!",
            "message_id": result.get('id')
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}