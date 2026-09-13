from src.integrations.emails import _create_email_draft


draft = _create_email_draft(
    recipient="perusade.p@usapschool.org",
    subject="Student Chief of Staff Test Draft",
    body="This is a test draft created by the Student Chief of Staff.",
)

print("Draft created successfully!")
print("Draft ID:", draft["draft_id"])
print("Message ID:", draft["message_id"])
print("Recipient:", draft["recipient"])
print("Subject:", draft["subject"])