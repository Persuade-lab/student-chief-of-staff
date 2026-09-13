from src.integrations.google_auth import get_google_calendar_service


service = get_google_calendar_service()

events_result = (
    service.events()
    .list(
        calendarId="primary",
        maxResults=10,
        singleEvents=True,
        orderBy="startTime",
    )
    .execute()
)

events = events_result.get("items", [])

print("Google Calendar authentication successful!")
print(f"Found {len(events)} events")

for event in events:
    print(event.get("summary", "Untitled event"))