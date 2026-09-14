"""
Database storage for the Student Chief of Staff.

Currently uses SQLite because it is lightweight, local, and requires
no separate database server.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

DATABASE_FILE = (
    BASE_DIR / "student_chief_of_staff_demo.db"
    if DEMO_MODE
    else BASE_DIR / "student_chief_of_staff.db"
)


# ============================================================
# CONNECTION
# ============================================================

def get_connection() -> sqlite3.Connection:
    """
    Create a connection to the SQLite database.

    Returns:
        A SQLite database connection.
    """

    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# INITIALIZATION
# ============================================================

def initialize_database() -> None:
    """
    Create database tables if they do not already exist.

    Also performs small schema migrations needed by older
    versions of the local database.
    """

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # EMAILS
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            recipient TEXT,
            subject TEXT,
            body TEXT,
            timestamp TEXT,
            read INTEGER NOT NULL DEFAULT 0,
            processed INTEGER NOT NULL DEFAULT 0,
            processed_at TEXT
        )
        """
    )

    # --------------------------------------------------------
    # EMAIL ANALYSIS
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS email_analysis (
            email_id TEXT PRIMARY KEY,
            category TEXT,
            priority TEXT,
            action_required INTEGER NOT NULL DEFAULT 0,
            response_required INTEGER NOT NULL DEFAULT 0,
            action_type TEXT,
            summary TEXT,
            reason TEXT,
            deadline TEXT,
            analyzed_at TEXT,
            FOREIGN KEY (email_id) REFERENCES emails(id)
        )
        """
    )

    email_analysis_columns = {
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(email_analysis)"
        ).fetchall()
    }

    if "response_required" not in email_analysis_columns:
        cursor.execute(
            """
            ALTER TABLE email_analysis
            ADD COLUMN response_required INTEGER NOT NULL DEFAULT 0
            """
        )

    # --------------------------------------------------------
    # CALENDAR EVENTS
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            end_time TEXT,
            duration_minutes INTEGER,
            all_day INTEGER NOT NULL DEFAULT 0,
            calendar_id TEXT,
            source TEXT,
            processed INTEGER NOT NULL DEFAULT 0,
            processed_at TEXT
        )
        """
    )

    # --------------------------------------------------------
    # CALENDAR EVENT MIGRATION
    # --------------------------------------------------------
    #
    # CREATE TABLE IF NOT EXISTS does not modify an existing
    # table. Older databases therefore need these columns added
    # explicitly.
    # --------------------------------------------------------

    calendar_columns = {
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(calendar_events)"
        ).fetchall()
    }

    if "processed" not in calendar_columns:
        cursor.execute(
            """
            ALTER TABLE calendar_events
            ADD COLUMN processed INTEGER NOT NULL DEFAULT 0
            """
        )

    if "processed_at" not in calendar_columns:
        cursor.execute(
            """
            ALTER TABLE calendar_events
            ADD COLUMN processed_at TEXT
            """
        )

    # --------------------------------------------------------
    # CALENDAR ANALYSIS
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_analysis (
            event_id TEXT PRIMARY KEY,
            category TEXT,
            priority TEXT,
            action_required INTEGER NOT NULL DEFAULT 0,
            action_type TEXT,
            summary TEXT,
            reason TEXT,
            analyzed_at TEXT,
            FOREIGN KEY (event_id) REFERENCES calendar_events(id)
        )
        """
    )
      # --------------------------------------------------------
    # USER PREFERENCES AND OPPORTUNITY MATCHES
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_memory (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_matches (
            email_id TEXT PRIMARY KEY,
            match_score INTEGER NOT NULL,
            reason TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            matched_terms_json TEXT NOT NULL,
            evaluated_at TEXT NOT NULL,
            FOREIGN KEY (email_id) REFERENCES emails(id)
        )
        """
    )

    # --------------------------------------------------------
    # RUNTIME STATE AND NOTIFICATION DEDUPLICATION
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_state (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_log (
            source_type TEXT NOT NULL,
            item_id TEXT NOT NULL,
            notification_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (
                source_type,
                item_id,
                notification_key
            )
        )
        """
    )

    connection.commit()
    connection.close()


# ============================================================
# EMAIL STORAGE
# ============================================================

def save_email(email: dict[str, Any]) -> None:
    """
    Save an email to the database.

    If the email already exists, update its information instead
    of creating a duplicate.

    Args:
        email: Email record using the application's email format.
    """

    connection = get_connection()

    connection.execute(
        """
        INSERT INTO emails (
            id,
            sender,
            recipient,
            subject,
            body,
            timestamp,
            read
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(id) DO UPDATE SET
            sender = excluded.sender,
            recipient = excluded.recipient,
            subject = excluded.subject,
            body = excluded.body,
            timestamp = excluded.timestamp,
            read = excluded.read
        """,
        (
            email.get("id"),
            email.get("sender", ""),
            email.get("recipient", ""),
            email.get("subject", ""),
            email.get("body", ""),
            email.get("timestamp", ""),
            int(email.get("read", False)),
        ),
    )

    connection.commit()
    connection.close()


def save_emails(
    emails: list[dict[str, Any]],
) -> None:
    """
    Save multiple emails to the database.

    Args:
        emails: List of email records.
    """

    for email in emails:
        save_email(email)


def get_email(
    email_id: str,
) -> dict[str, Any] | None:
    """
    Retrieve an email from the database by ID.

    Args:
        email_id: Unique email ID.

    Returns:
        Email record if found, otherwise None.
    """

    connection = get_connection()

    row = connection.execute(
        """
        SELECT
            id,
            sender,
            recipient,
            subject,
            body,
            timestamp,
            read,
            processed,
            processed_at
        FROM emails
        WHERE id = ?
        """,
        (email_id,),
    ).fetchone()

    connection.close()

    if row is None:
        return None

    return dict(row)


def get_recent_emails(
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Retrieve recent emails from the database.

    Args:
        limit: Maximum number of emails to retrieve.

    Returns:
        Emails sorted from newest to oldest.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            id,
            sender,
            recipient,
            subject,
            body,
            timestamp,
            read,
            processed,
            processed_at
        FROM emails
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]

def get_email_brief_records(
    start_timestamp: str,
    end_timestamp: str,
) -> list[dict[str, Any]]:
    """
    Return analyzed emails received within a time window.

    Results are sorted newest first.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            e.id,
            e.sender,
            e.recipient,
            e.subject,
            e.timestamp,
            e.read,
            a.category,
            a.priority,
            a.action_required,
            a.response_required,
            a.action_type,
            a.summary,
            a.reason,
            a.deadline
        FROM emails AS e
        LEFT JOIN email_analysis AS a
            ON a.email_id = e.id
        WHERE
            e.timestamp >= ?
            AND e.timestamp < ?
        ORDER BY e.timestamp DESC
        """,
        (
            start_timestamp,
            end_timestamp,
        ),
    ).fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


def get_unread_emails() -> list[dict[str, Any]]:
    """
    Retrieve unread emails from the database.

    Returns:
        A list of unread email records.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            id,
            sender,
            recipient,
            subject,
            body,
            timestamp,
            read,
            processed,
            processed_at
        FROM emails
        WHERE read = 0
        ORDER BY timestamp DESC
        """
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


def get_unprocessed_emails() -> list[dict[str, Any]]:
    """
    Retrieve emails that have not yet been processed by the agent.

    Returns:
        Unprocessed emails sorted from oldest to newest.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            id,
            sender,
            recipient,
            subject,
            body,
            timestamp,
            read,
            processed,
            processed_at
        FROM emails
        WHERE processed = 0
        ORDER BY timestamp ASC
        """
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


def email_exists(
    email_id: str,
) -> bool:
    """
    Check whether an email exists in the database.

    Args:
        email_id: Unique email ID.

    Returns:
        True if the email exists, otherwise False.
    """

    connection = get_connection()

    row = connection.execute(
        """
        SELECT 1
        FROM emails
        WHERE id = ?
        """,
        (email_id,),
    ).fetchone()

    connection.close()

    return row is not None


def mark_email_processed(
    email_id: str,
) -> None:
    """
    Mark an email as processed by the Student Chief of Staff.

    Args:
        email_id: Unique email ID.
    """

    processed_at = datetime.now(
        timezone.utc
    ).isoformat()

    connection = get_connection()

    connection.execute(
        """
        UPDATE emails
        SET
            processed = 1,
            processed_at = ?
        WHERE id = ?
        """,
        (
            processed_at,
            email_id,
        ),
    )

    connection.commit()
    connection.close()


def save_email_analysis(
    email_id: str,
    category: str,
    priority: str,
    action_required: bool,
    action_type: str | None,
    summary: str,
    reason: str,
    deadline: str | None,
    response_required: bool = False,
) -> None:
    """
    Save the agent's analysis of an email.

    Args:
        email_id: ID of the analyzed email.
        category: Classification of the email.
        priority: Importance level of the email.
        action_required: Whether the email requires action.
        action_type: Type of action the agent may need to take.
        summary: Short summary of the email.
        reason: Explanation for the assigned priority/action.
        deadline: Relevant deadline, if one exists.
    """

    analyzed_at = datetime.now(
        timezone.utc
    ).isoformat()

    connection = get_connection()

    connection.execute(
        """
        INSERT INTO email_analysis (
            email_id,
            category,
            priority,
            action_required,
            response_required,
            action_type,
            summary,
            reason,
            deadline,
            analyzed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(email_id) DO UPDATE SET
            category = excluded.category,
            priority = excluded.priority,
            action_required = excluded.action_required,
            response_required = excluded.response_required,
            action_type = excluded.action_type,
            summary = excluded.summary,
            reason = excluded.reason,
            deadline = excluded.deadline,
            analyzed_at = excluded.analyzed_at
        """,
        (
            email_id,
            category,
            priority,
            int(action_required),
            int(response_required),
            action_type,
            summary,
            reason,
            deadline,
            analyzed_at,
        ),
    )

    connection.commit()
    connection.close()


# ============================================================
# CALENDAR STORAGE
# ============================================================

def save_calendar_event(
    event: dict[str, Any],
) -> None:
    """
    Save a calendar event to the database.

    If the event already exists, update the existing record.

    Existing processing state is preserved during synchronization.

    Args:
        event: Calendar event using the application's event format.
    """

    connection = get_connection()

    connection.execute(
        """
        INSERT INTO calendar_events (
            id,
            title,
            date,
            time,
            end_time,
            duration_minutes,
            all_day,
            calendar_id,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            date = excluded.date,
            time = excluded.time,
            end_time = excluded.end_time,
            duration_minutes = excluded.duration_minutes,
            all_day = excluded.all_day,
            calendar_id = excluded.calendar_id,
            source = excluded.source
        """,
        (
            event.get("id"),
            event.get("title", ""),
            event.get("date", ""),
            event.get("time", ""),
            event.get("end_time"),
            event.get("duration_minutes"),
            int(
                event.get(
                    "all_day",
                    False,
                )
            ),
            event.get("calendar_id"),
            event.get("source"),
        ),
    )

    connection.commit()
    connection.close()


def save_calendar_events(
    events: list[dict[str, Any]],
) -> None:
    """
    Save multiple calendar events to the database.

    Args:
        events: List of calendar event records.
    """

    for event in events:
        save_calendar_event(event)


def get_calendar_event(
    event_id: str,
) -> dict[str, Any] | None:
    """
    Retrieve a calendar event by ID.

    Args:
        event_id: Unique calendar event ID.

    Returns:
        Calendar event if found, otherwise None.
    """

    connection = get_connection()

    row = connection.execute(
        """
        SELECT
            id,
            title,
            date,
            time,
            end_time,
            duration_minutes,
            all_day,
            calendar_id,
            source,
            processed,
            processed_at
        FROM calendar_events
        WHERE id = ?
        """,
        (event_id,),
    ).fetchone()

    connection.close()

    if row is None:
        return None

    return dict(row)


def get_calendar_events(
    date: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve calendar events from the database.

    Args:
        date: Optional date in YYYY-MM-DD format.

    Returns:
        Calendar events sorted chronologically.
    """

    connection = get_connection()

    if date is not None:
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                date,
                time,
                end_time,
                duration_minutes,
                all_day,
                calendar_id,
                source,
                processed,
                processed_at
            FROM calendar_events
            WHERE date = ?
            ORDER BY time
            """,
            (date,),
        ).fetchall()

    else:
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                date,
                time,
                end_time,
                duration_minutes,
                all_day,
                calendar_id,
                source,
                processed,
                processed_at
            FROM calendar_events
            ORDER BY date, time
            """
        ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


def get_unprocessed_calendar_events() -> list[dict[str, Any]]:
    """
    Retrieve calendar events that have not yet been processed.

    Returns:
        Unprocessed calendar events sorted chronologically.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            id,
            title,
            date,
            time,
            end_time,
            duration_minutes,
            all_day,
            calendar_id,
            source,
            processed,
            processed_at
        FROM calendar_events
        WHERE processed = 0
        ORDER BY date, time
        """
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


def calendar_event_exists(
    event_id: str,
) -> bool:
    """
    Check whether a calendar event exists in the database.

    Args:
        event_id: Unique calendar event ID.

    Returns:
        True if the event exists, otherwise False.
    """

    connection = get_connection()

    row = connection.execute(
        """
        SELECT 1
        FROM calendar_events
        WHERE id = ?
        """,
        (event_id,),
    ).fetchone()

    connection.close()

    return row is not None


def mark_calendar_event_processed(
    event_id: str,
) -> None:
    """
    Mark a calendar event as processed by the Student Chief of Staff.

    Args:
        event_id: Unique calendar event ID.
    """

    processed_at = datetime.now(
        timezone.utc
    ).isoformat()

    connection = get_connection()

    connection.execute(
        """
        UPDATE calendar_events
        SET
            processed = 1,
            processed_at = ?
        WHERE id = ?
        """,
        (
            processed_at,
            event_id,
        ),
    )

    connection.commit()
    connection.close()


def save_calendar_analysis(
    event_id: str,
    category: str,
    priority: str,
    action_required: bool,
    action_type: str | None,
    summary: str,
    reason: str,
) -> None:
    """
    Save the agent's analysis of a calendar event.

    Args:
        event_id: ID of the analyzed calendar event.
        category: Classification of the event.
        priority: Importance level of the event.
        action_required: Whether the event requires action.
        action_type: Planned action associated with the event.
        summary: Short summary of the event.
        reason: Explanation for the classification and priority.
    """

    analyzed_at = datetime.now(
        timezone.utc
    ).isoformat()

    connection = get_connection()

    connection.execute(
        """
        INSERT INTO calendar_analysis (
            event_id,
            category,
            priority,
            action_required,
            action_type,
            summary,
            reason,
            analyzed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(event_id) DO UPDATE SET
            category = excluded.category,
            priority = excluded.priority,
            action_required = excluded.action_required,
            action_type = excluded.action_type,
            summary = excluded.summary,
            reason = excluded.reason,
            analyzed_at = excluded.analyzed_at
        """,
        (
            event_id,
            category,
            priority,
            int(action_required),
            action_type,
            summary,
            reason,
            analyzed_at,
        ),
    )

    connection.commit()
    connection.close()


def get_calendar_analysis(
    event_id: str,
) -> dict[str, Any] | None:
    """
    Retrieve saved analysis for a calendar event.

    Args:
        event_id: Unique calendar event ID.

    Returns:
        Calendar analysis if found, otherwise None.
    """

    connection = get_connection()

    row = connection.execute(
        """
        SELECT
            event_id,
            category,
            priority,
            action_required,
            action_type,
            summary,
            reason,
            analyzed_at
        FROM calendar_analysis
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()

    connection.close()

    if row is None:
        return None

    return dict(row)


def delete_calendar_event(
    event_id: str,
) -> None:
    """
    Delete a calendar event from local storage.

    Its associated analysis is deleted first.

    Args:
        event_id: Unique calendar event ID.
    """

    connection = get_connection()

    connection.execute(
        """
        DELETE FROM calendar_analysis
        WHERE event_id = ?
        """,
        (event_id,),
    )

    connection.execute(
        """
        DELETE FROM calendar_events
        WHERE id = ?
        """,
        (event_id,),
    )

    connection.commit()
    connection.close()


def clear_calendar_events() -> None:
    """
    Remove all locally stored calendar events and their analyses.

    This is useful when performing a full synchronization
    from Google Calendar.
    """

    connection = get_connection()

    connection.execute(
        """
        DELETE FROM calendar_analysis
        """
    )

    connection.execute(
        """
        DELETE FROM calendar_events
        """
    )

    connection.commit()
    connection.close()

def claim_notification(
    source_type: str,
    item_id: str,
    notification_key: str,
) -> bool:
    """
    Atomically reserve one notification delivery.

    A duplicate delivery returns False. A new delivery is recorded before it
    is printed, so repeated monitor cycles cannot spam the same alert.
    """

    created_at = datetime.now(timezone.utc).isoformat()
    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO notification_log (
                source_type,
                item_id,
                notification_key,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                source_type,
                item_id,
                notification_key,
                created_at,
            ),
        )
        connection.commit()
        return cursor.rowcount == 1

    except sqlite3.IntegrityError:
        connection.rollback()
        return False

    finally:
        connection.close()