from src.integrations.emails import _get_gmail_emails


emails = _get_gmail_emails(limit=5)

print(f"Retrieved {len(emails)} emails")

for email in emails:
    print()
    print("ID:", email["id"])
    print("From:", email["sender"])
    print("Subject:", email["subject"])
    print("Timestamp:", email["timestamp"])
    print("Read:", email["read"])
    print("Body:", email["body"][:100])