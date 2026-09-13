from src.integrations.google_auth import get_gmail_service


service = get_gmail_service()

profile = service.users().getProfile(userId="me").execute()

print("Gmail authentication successful!")
print(f"Connected account: {profile['emailAddress']}")