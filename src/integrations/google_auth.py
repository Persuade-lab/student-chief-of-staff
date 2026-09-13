"""
Google authentication for the Student Chief of Staff.

Handles OAuth authentication with Google and provides authenticated
Gmail and Google Calendar API services.
"""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"


SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]


# ============================================================
# SHARED GOOGLE AUTHENTICATION
# ============================================================

def get_google_credentials() -> Credentials:
    """
    Authenticate the user with Google and return valid credentials.

    On the first run, Google opens a browser window asking the user
    to authorize the requested Gmail and Calendar permissions.

    On later runs, token.json is reused when possible.

    Returns:
        Valid Google OAuth credentials.
    """

    credentials = None

    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES,
        )

    if not credentials or not credentials.valid:

        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):
            credentials.refresh(Request())

        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Could not find {CREDENTIALS_FILE}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES,
            )

            credentials = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    return credentials


# ============================================================
# GMAIL
# ============================================================

def get_gmail_service():
    """
    Return an authenticated Gmail API service.
    """

    credentials = get_google_credentials()

    return build(
        "gmail",
        "v1",
        credentials=credentials,
    )


# ============================================================
# GOOGLE CALENDAR
# ============================================================

def get_google_calendar_service():
    """
    Return an authenticated Google Calendar API service.
    """

    credentials = get_google_credentials()

    return build(
        "calendar",
        "v3",
        credentials=credentials,
    )