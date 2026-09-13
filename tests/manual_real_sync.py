from src.integrations.emails import sync_gmail_emails
from src.integrations.google_calendar import sync_calendar_events

from src.storage.database import (
    get_recent_emails,
    get_calendar_events,
)


print("\n=== SYNCING GMAIL ===")

gmail_emails = sync_gmail_emails(limit=10)

print(f"Retrieved {len(gmail_emails)} emails from Gmail.")


print("\n=== READING EMAILS FROM SQLITE ===")

stored_emails = get_recent_emails(limit=10)

print(f"SQLite contains {len(stored_emails)} recent emails.")

for email in stored_emails:
    print()
    print("ID:", email["id"])
    print("From:", email["sender"])
    print("Subject:", email["subject"])
    print("Timestamp:", email["timestamp"])


print("\n=== SYNCING GOOGLE CALENDAR ===")

google_events = sync_calendar_events()

print(
    f"Retrieved {len(google_events)} events "
    "from Google Calendar."
)


print("\n=== READING CALENDAR EVENTS FROM SQLITE ===")

stored_events = get_calendar_events()

print(
    f"SQLite contains {len(stored_events)} "
    "calendar events."
)

for event in stored_events[:10]:
    print()
    print("ID:", event["id"])
    print("Title:", event["title"])
    print("Date:", event["date"])
    print("Time:", event["time"])
    print("End:", event.get("end_time"))
    print("Source:", event.get("source"))
    print("Calendar ID:", event.get("calendar_id"))