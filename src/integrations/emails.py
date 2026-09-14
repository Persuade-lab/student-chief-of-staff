"""
Email integration for the Student Chief of Staff.

This module is responsible for retrieving emails from Gmail and
creating Gmail drafts.

Email data is synchronized from Gmail into the application's
SQLite database.

This module does NOT classify, prioritize, or determine whether an email
is an opportunity, assignment, announcement, action item, or news.
That responsibility belongs to the processing layer.
"""

from typing import Any
import base64
from email.message import EmailMessage
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from strands import tool

from src.integrations.google_auth import get_gmail_service

from src.storage.database import (
    save_emails,
    get_email as get_stored_email,
    get_recent_emails as get_stored_recent_emails,
    get_unread_emails as get_stored_unread_emails,
    get_email_brief_records,
)

LOCAL_TIMEZONE = ZoneInfo("America/New_York")
BRIEF_START_HOUR = 6


# ============================================================
# GMAIL HELPERS
# ============================================================

def _decode_gmail_body(payload: dict[str, Any]) -> str:
    """
    Extract and decode the plain-text body from a Gmail message.

    Args:
        payload: Gmail message payload.

    Returns:
        The decoded plain-text email body.
    """

    if "body" in payload:
        data = payload["body"].get("data")

        if data:
            return base64.urlsafe_b64decode(data).decode(
                "utf-8",
                errors="replace",
            )

    for part in payload.get("parts", []):

        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")

            if data:
                return base64.urlsafe_b64decode(data).decode(
                    "utf-8",
                    errors="replace",
                )

        if part.get("parts"):
            body = _decode_gmail_body(part)

            if body:
                return body

    return ""


def _normalize_gmail_message(
    message: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert a Gmail API message into the application's email format.

    Args:
        message: Raw Gmail API message.

    Returns:
        Email record matching the application's data format.
    """

    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    header_map = {
        header["name"].lower(): header["value"]
        for header in headers
    }

    timestamp = message.get("internalDate")

    if timestamp:
        timestamp = datetime.fromtimestamp(
            int(timestamp) / 1000,
            tz=timezone.utc,
        ).isoformat()

    return {
        "id": message.get("id"),
        "sender": header_map.get("from", ""),
        "recipient": header_map.get("to", ""),
        "subject": header_map.get("subject", ""),
        "body": _decode_gmail_body(payload),
        "timestamp": timestamp or "",
        "read": "UNREAD" not in message.get("labelIds", []),
    }


def _get_gmail_emails(
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Retrieve recent emails from Gmail and store them in the database.

    Args:
        limit: Maximum number of emails to retrieve.

    Returns:
        A list of normalized email records.
    """

    service = get_gmail_service()

    response = (
        service.users()
        .messages()
        .list(
            userId="me",
            maxResults=limit,
        )
        .execute()
    )

    messages = response.get("messages", [])

    emails = []

    for message in messages:

        full_message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message["id"],
                format="full",
            )
            .execute()
        )

        emails.append(
            _normalize_gmail_message(full_message)
        )

    emails.sort(
    key=lambda email: email.get("timestamp", ""),
    reverse=True,
)

    return emails


# ============================================================
# EMAIL STORAGE / SYNCHRONIZATION
# ============================================================

def sync_gmail_emails(
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Synchronize recent Gmail messages with the local database.

    This function retrieves emails from Gmail and then stores
    those emails in SQLite.

    Args:
        limit: Maximum number of emails to synchronize.

    Returns:
        The emails retrieved from Gmail.
    """

    emails = _get_gmail_emails(limit)

    save_emails(emails)

    return emails


# ============================================================
# EMAIL DRAFTS
# ============================================================

def _create_email_draft(
    recipient: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """
    Create a real Gmail draft.

    This creates the draft in Gmail but does not send it.

    Args:
        recipient: Email address of the recipient.
        subject: Subject line of the email.
        body: Body of the email.

    Returns:
        Information about the created Gmail draft.
    """

    service = get_gmail_service()

    message = EmailMessage()

    message["To"] = recipient
    message["Subject"] = subject

    message.set_content(body)

    encoded_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    draft = {
        "message": {
            "raw": encoded_message
        }
    }

    created_draft = (
        service.users()
        .drafts()
        .create(
            userId="me",
            body=draft,
        )
        .execute()
    )

    return {
        "draft_id": created_draft["id"],
        "message_id": created_draft["message"]["id"],
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "status": "draft",
    }

# ============================================================
# EMAIL BRIEFS
# ============================================================

def _current_inbox_brief_window(
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """
    Return the current rolling Inbox Brief window.

    A new window starts every day at 6:00 AM local time.
    The current window ends at the current time.
    """

    current = now or datetime.now(LOCAL_TIMEZONE)

    today_at_six = datetime.combine(
        current.date(),
        time(hour=BRIEF_START_HOUR),
        tzinfo=LOCAL_TIMEZONE,
    )

    if current >= today_at_six:
        start = today_at_six
    else:
        previous_day = current.date().fromordinal(
            current.date().toordinal() - 1
        )

        start = datetime.combine(
            previous_day,
            time(hour=BRIEF_START_HOUR),
            tzinfo=LOCAL_TIMEZONE,
        )

    return start, current

def build_email_brief(
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Build the current rolling Inbox Brief from stored email analysis.
    """

    start, end = _current_inbox_brief_window(now)

    records = get_email_brief_records(
        start.astimezone(timezone.utc).isoformat(),
        end.astimezone(timezone.utc).isoformat(),
    )

    needs_attention = []
    needs_response = []
    opportunities = []
    important_updates = []
    everything_else = []

    for email in records:
        priority = email.get("priority")
        category = email.get("category")

        action_required = bool(
            email.get("action_required")
        )

        response_required = bool(
            email.get("response_required")
        )

        if response_required:
            needs_response.append(email)

        if (
            action_required
            or priority in {"high", "urgent"}
        ):
            needs_attention.append(email)

        if category == "opportunity":
            opportunities.append(email)

        if (
            priority in {"high", "urgent"}
            and not action_required
            and not response_required
        ):
            important_updates.append(email)

        if (
            not action_required
            and not response_required
            and category != "opportunity"
            and priority not in {"high", "urgent"}
        ):
            everything_else.append(email)

    return {
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timezone": "America/New_York",
            "status": "in_progress",
        },
        "total_received": len(records),
        "needs_attention": needs_attention,
        "needs_response": needs_response,
        "opportunities": opportunities,
        "important_updates": important_updates,
        "everything_else": everything_else,
    }


# ============================================================
# AGENT TOOLS
# ============================================================

@tool
def get_recent_emails(
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Retrieve recent emails from local storage.

    Gmail synchronization is handled by the background runtime.

    Use this when the agent needs to inspect recent emails.

    Args:
        limit: Maximum number of recent emails to retrieve.

    Returns:
        A list of recent email records sorted from newest to oldest.
    """

    return get_stored_recent_emails(limit)


@tool
def get_unread_emails() -> list[dict[str, Any]]:
    """
    Retrieve unread emails from local storage.

    Gmail synchronization is handled by the background runtime.

    Use this when the agent needs to inspect messages that
    have not been read.

    Returns:
        A list of unread email records.
    """

    return get_stored_unread_emails()


@tool
def get_email(
    email_id: str,
) -> dict[str, Any] | None:
    """
    Retrieve a specific email from local storage.

    Args:
        email_id: Unique identifier for the email.

    Returns:
        The email record if it exists, otherwise None.
    """

    return get_stored_email(email_id)


@tool
def draft_email(
    recipient: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """
    Create a Gmail draft without sending it.

    Use this when the user asks the agent to draft an email.

    The draft is created in Gmail but is not automatically sent.

    Args:
        recipient: Email address of the recipient.
        subject: Subject line of the email.
        body: Body of the email.

    Returns:
        A dictionary containing information about the created draft.
    """

    return _create_email_draft(
        recipient=recipient,
        subject=subject,
        body=body,
    )

@tool
def get_email_brief() -> dict[str, Any]:
    """
    Return the student's current rolling Inbox Brief.

    The brief covers emails received since the most recent
    6:00 AM America/New_York boundary.

    Use this when the student asks:
    - what important emails they received
    - which emails need attention
    - which emails likely need a reply
    - for an inbox summary or email brief
    """

    return build_email_brief()