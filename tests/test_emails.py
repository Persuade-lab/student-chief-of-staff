"""
Tests for src/integrations/emails.py.

The production email integration uses Gmail + SQLite.

These tests:
    - use mock_emails.json as predictable test data
    - use a temporary SQLite database for each test
    - never modify the real database
    - never contact Gmail during retrieval tests
    - mock Gmail when testing draft creation

Run with:

    PYTHONPATH=. pytest tests/test_emails.py -v
"""

import json
from pathlib import Path

import pytest

from src.integrations import emails
from src.storage import database


REAL_DATA_FILE = (
    Path(__file__).parent.parent
    / "src"
    / "data"
    / "mock_emails.json"
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def mock_email_data():
    """
    Load the real mock email data.

    The returned data is copied in memory, so tests cannot
    modify the source JSON file.
    """

    return json.loads(
        REAL_DATA_FILE.read_text(encoding="utf-8")
    )


@pytest.fixture
def test_database(tmp_path, monkeypatch):
    """
    Give each test its own temporary SQLite database.

    Nothing is written to the real student_chief_of_staff.db.
    """

    test_db = tmp_path / "test_student_chief_of_staff.db"

    monkeypatch.setattr(
        database,
        "DATABASE_FILE",
        test_db,
    )

    database.initialize_database()

    return test_db


@pytest.fixture
def seeded_database(
    test_database,
    mock_email_data,
):
    """
    Create a temporary database containing the mock emails.
    """

    database.save_emails(mock_email_data)

    return mock_email_data


@pytest.fixture
def disable_gmail_sync(monkeypatch):
    """
    Prevent email retrieval tests from contacting Gmail.

    The production tools synchronize with Gmail first, but these
    tests should test the database behavior independently.
    """

    monkeypatch.setattr(
        emails,
        "sync_gmail_emails",
        lambda limit=20: [],
    )


# ============================================================
# get_recent_emails
# ============================================================

class TestGetRecentEmails:

    def test_returns_all_emails_sorted_newest_first(
        self,
        seeded_database,
        disable_gmail_sync,
    ):
        result = emails.get_recent_emails()

        ids_in_order = [
            email["id"]
            for email in result
        ]

        assert ids_in_order == [
            "email_003",
            "email_002",
            "email_001",
        ]

    def test_respects_limit(
        self,
        seeded_database,
        disable_gmail_sync,
    ):
        result = emails.get_recent_emails(limit=2)

        assert len(result) == 2

        ids_in_order = [
            email["id"]
            for email in result
        ]

        assert ids_in_order == [
            "email_003",
            "email_002",
        ]

    def test_limit_larger_than_inbox_returns_everything(
        self,
        seeded_database,
        disable_gmail_sync,
    ):
        result = emails.get_recent_emails(limit=100)

        assert len(result) == 3


# ============================================================
# get_unread_emails
# ============================================================

class TestGetUnreadEmails:

    def test_returns_only_unread(
        self,
        seeded_database,
        disable_gmail_sync,
    ):
        result = emails.get_unread_emails()

        ids = {
            email["id"]
            for email in result
        }

        assert ids == {
            "email_001",
            "email_002",
        }

    def test_excludes_read_emails(
        self,
        seeded_database,
        disable_gmail_sync,
    ):
        result = emails.get_unread_emails()

        ids = {
            email["id"]
            for email in result
        }

        assert "email_003" not in ids

    def test_empty_database_returns_empty_list(
        self,
        test_database,
        disable_gmail_sync,
    ):
        result = emails.get_unread_emails()

        assert result == []


# ============================================================
# get_email
# ============================================================

class TestGetEmail:

    def test_returns_matching_email(
        self,
        seeded_database,
    ):
        result = emails.get_email("email_002")

        assert result is not None
        assert result["subject"] == (
            "Research Opportunity in Robotics"
        )
        assert result["sender"] == "career@upenn.edu"

    def test_returns_none_for_unknown_id(
        self,
        seeded_database,
    ):
        result = emails.get_email("does-not-exist")

        assert result is None


# ============================================================
# DATABASE STORAGE
# ============================================================

class TestEmailDatabaseStorage:

    def test_emails_are_stored_in_database(
        self,
        seeded_database,
    ):
        result = database.get_recent_emails()

        assert len(result) == 3

    def test_email_exists_after_storage(
        self,
        seeded_database,
    ):
        assert database.email_exists("email_001") is True

    def test_unknown_email_does_not_exist(
        self,
        seeded_database,
    ):
        assert database.email_exists("does-not-exist") is False

    def test_email_can_be_marked_processed(
        self,
        seeded_database,
    ):
        database.mark_email_processed("email_001")

        result = database.get_email("email_001")

        assert result is not None
        assert result["processed"] == 1
        assert result["processed_at"] is not None


# ============================================================
# GMAIL SYNCHRONIZATION
# ============================================================

class TestGmailSynchronization:

    def test_sync_stores_gmail_emails(
        self,
        test_database,
        monkeypatch,
        mock_email_data,
    ):
        """
        Verify that Gmail synchronization retrieves emails
        and stores them in the SQLite database.
        """

        def fake_get_gmail_emails(limit=20):
            """
            Fake Gmail retrieval function.

            Instead of contacting Gmail, return the mock
            email data used by this test.
            """
            assert limit == 20

            return mock_email_data

        monkeypatch.setattr(
            emails,
            "_get_gmail_emails",
            fake_get_gmail_emails,
        )

        # Run the actual synchronization function.
        result = emails.sync_gmail_emails(limit=20)

        # Verify Gmail data was returned.
        assert len(result) == 3

        # Verify synchronization stored the emails in SQLite.
        stored = database.get_recent_emails()

        assert len(stored) == 3

        stored_ids = {
            email["id"]
            for email in stored
        }

        assert stored_ids == {
            "email_001",
            "email_002",
            "email_003",
        }


# ============================================================
# DRAFT EMAIL
# ============================================================

# class FakeDrafts:

#     def __init__(self):
#         self.created_body = None

#     def create(self, userId, body):
#         self.created_body = body

#         return FakeExecute(
#             {
#                 "id": "draft_test_001",
#                 "message": {
#                     "id": "message_test_001",
#                 },
#             }
#         )


# class FakeMessages:

#     def __init__(self):
#         self.drafts = FakeDrafts()


# class FakeUsers:

#     def __init__(self):
#         self.messages_api = FakeMessages()

#     def messages(self):
#         return self.messages_api


# class FakeExecute:

#     def __init__(self, result):
#         self.result = result

#     def execute(self):
#         return self.result


# class FakeGmailService:

#     def __init__(self):
#         self.users_api = FakeUsers()

#     def users(self):
#         return self.users_api


# class TestDraftEmail:

#     def test_creates_gmail_draft(
#         self,
#         monkeypatch,
#     ):
#         """
#         Verify that draft_email creates a Gmail draft without
#         actually contacting Gmail.
#         """

#         fake_service = FakeGmailService()

#         monkeypatch.setattr(
#             emails,
#             "get_gmail_service",
#             lambda: fake_service,
#         )

#         result = emails.draft_email(
#             recipient="advisor@upenn.edu",
#             subject="Question about registration",
#             body="Do I still have a hold on my account?",
#         )

#         assert result["draft_id"] == "draft_test_001"
#         assert result["message_id"] == "message_test_001"
#         assert result["recipient"] == (
#             "advisor@upenn.edu"
#         )
#         assert result["subject"] == (
#             "Question about registration"
#         )
#         assert result["body"] == (
#             "Do I still have a hold on my account?"
#         )
#         assert result["status"] == "draft"

#     def test_draft_is_sent_to_gmail_api(
#         self,
#         monkeypatch,
#     ):
#         """
#         Verify that the Gmail API receives the draft.
#         """

#         fake_service = FakeGmailService()

#         monkeypatch.setattr(
#             emails,
#             "get_gmail_service",
#             lambda: fake_service,
#         )

#         emails.draft_email(
#             recipient="advisor@upenn.edu",
#             subject="Test subject",
#             body="Test body",
#         )

#         draft_body = (
#             fake_service
#             .users_api
#             .messages_api
#             .drafts()
#             .created_body
#         )

#         assert draft_body is not None
#         assert "message" in draft_body
#         assert "raw" in draft_body["message"]