import os
from google_auth_oauthlib.flow import InstalledAppFlow

# הגדרנו כאן את שתי ההרשאות: יומן ו-Gmail
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/gmail.send'
]


def main():
    # מחיקת הטוקן הישן אם קיים
    if os.path.exists('token.json'):
        os.remove('token.json')

    if not os.path.exists('credentials.json'):
        print("Error: credentials.json not found in the project root.")
        return

    # הפעלת תהליך האימות בדפדפן
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)

    # שמירת הטוקן החדש
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
    print("Success! New token.json created with Calendar and Gmail scopes.")


if __name__ == '__main__':
    main()