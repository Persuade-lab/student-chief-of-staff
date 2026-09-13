from src.storage.database import (
    initialize_database,
    save_email,
    get_email,
    get_recent_emails,
    get_unread_emails,
    email_exists,
    mark_email_processed,
)


initialize_database()


test_email = {
    "id": "database_test_001",
    "sender": "test@example.com",
    "recipient": "student@example.com",
    "subject": "Database Test",
    "body": "Testing email database storage.",
    "timestamp": "2026-08-23T12:00:00",
    "read": False,
}


save_email(test_email)

print("Email saved.")

print("Exists:", email_exists("database_test_001"))

print("Retrieved:")
print(get_email("database_test_001"))

print("Recent emails:")
print(get_recent_emails())

print("Unread emails:")
print(get_unread_emails())

mark_email_processed("database_test_001")

print("After processing:")
print(get_email("database_test_001"))