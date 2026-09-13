from src.integrations.google_auth import get_google_calendar_service


service = get_google_calendar_service()

calendar_list = service.calendarList().list().execute()

for calendar in calendar_list.get("items", []):
    print("ID:", calendar.get("id"))
    print("Name:", calendar.get("summary"))
    print("Primary:", calendar.get("primary", False))
    print("---")