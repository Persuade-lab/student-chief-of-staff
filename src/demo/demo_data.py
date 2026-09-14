"""Sanitized fictional data used by the public hosted demo."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from src.storage.database import get_connection
from src.storage.memory import save_profile


LOCAL_TIMEZONE = ZoneInfo("America/New_York")
BRIEF_START_HOUR = 6


def _current_brief_start(now: datetime) -> datetime:
    """Return the most recent 6:00 AM local Inbox Brief boundary."""

    today_at_six = datetime.combine(
        now.date(),
        time(hour=BRIEF_START_HOUR),
        tzinfo=LOCAL_TIMEZONE,
    )

    if now >= today_at_six:
        return today_at_six

    return today_at_six - timedelta(days=1)


def _demo_email_times(now: datetime, count: int) -> list[str]:
    """Create timestamps safely inside the current 6 AM -> now brief window."""

    start = _current_brief_start(now)
    window_seconds = max(
        60,
        int((now - start).total_seconds()),
    )

    timestamps: list[str] = []

    for index in range(count):
        fraction = (index + 1) / (count + 1)
        local_time = start + timedelta(
            seconds=window_seconds * fraction
        )
        timestamps.append(
            local_time.astimezone(timezone.utc).isoformat()
        )

    return timestamps


def seed_demo_data() -> None:
    """
    Seed completely fictional demo data for the hosted Streamlit app.

    Nothing in this file is taken from a real inbox, calendar, school,
    professor, employer, or opportunity. Stable demo IDs are upserted so
    Streamlit reruns do not create duplicates.
    """

    now = datetime.now(LOCAL_TIMEZONE)
    today = now.date()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    save_profile(
        {
            "interests": [
                "artificial intelligence",
                "robotics",
                "software systems",
            ],
            "target_roles": [
                "software engineering intern",
                "undergraduate research assistant",
            ],
            "skills": [
                "Python",
                "Java",
                "C",
            ],
            "locations": [
                "Boston",
                "Remote",
            ],
            "minimum_match_score": 60,
        }
    )

    email_specs = [
        {
            "id": "demo-email-professor",
            "sender": "Professor Elena Park <elena.park@northbridge.example.edu>",
            "subject": "Can you confirm tomorrow's project check-in?",
            "body": (
                "Hi Alex, could you confirm whether 2:30 PM tomorrow still "
                "works for our project check-in?"
            ),
            "category": "personal",
            "priority": "high",
            "action_required": True,
            "response_required": True,
            "action_type": "review_reply",
            "summary": (
                "Professor Park is asking you to confirm tomorrow's "
                "2:30 PM project meeting."
            ),
            "reason": "A direct scheduling question expects a personal reply.",
            "deadline": tomorrow.isoformat(),
        },
        {
            "id": "demo-email-assignment",
            "sender": "Northbridge Learning Portal <notifications@northbridge.example.edu>",
            "subject": "CS 231 Project checkpoint due tomorrow",
            "body": (
                "Reminder: the CS 231 project checkpoint is due tomorrow "
                "at 11:59 PM."
            ),
            "category": "academic",
            "priority": "urgent",
            "action_required": True,
            "response_required": False,
            "action_type": "notify",
            "summary": (
                "CS 231 project checkpoint is due tomorrow at 11:59 PM."
            ),
            "reason": "The academic deadline is less than one day away.",
            "deadline": tomorrow.isoformat(),
        },
        {
            "id": "demo-email-opportunity",
            "sender": "Innovation Lab <opportunities@northbridge.example.edu>",
            "subject": "AI Systems Research Assistant opening",
            "body": (
                "The Human-Centered Computing Lab is seeking a student with "
                "Python and systems experience for a part-time AI research role."
            ),
            "category": "opportunity",
            "priority": "high",
            "action_required": True,
            "response_required": False,
            "action_type": "notify",
            "summary": (
                "Research assistant opening focused on AI systems, Python, "
                "and software infrastructure."
            ),
            "reason": (
                "The opportunity strongly matches the demo student's "
                "saved interests and skills."
            ),
            "deadline": day_after.isoformat(),
        },
        {
            "id": "demo-email-career",
            "sender": "Career Center <careercenter@northbridge.example.edu>",
            "subject": "Spring technology internship fair registration is open",
            "body": (
                "Registration is now open for next week's technology internship fair."
            ),
            "category": "announcement",
            "priority": "high",
            "action_required": False,
            "response_required": False,
            "action_type": "notify",
            "summary": (
                "Registration opened for the spring technology internship fair."
            ),
            "reason": (
                "Useful professional update, but no immediate response is required."
            ),
            "deadline": None,
        },
        {
            "id": "demo-email-club",
            "sender": "Robotics Society <robotics@northbridge.example.edu>",
            "subject": "Open build night this Thursday",
            "body": (
                "The Robotics Society is hosting an open build night this "
                "Thursday from 7:00 PM to 9:00 PM."
            ),
            "category": "announcement",
            "priority": "medium",
            "action_required": False,
            "response_required": False,
            "action_type": "none",
            "summary": (
                "The Robotics Society is hosting an open build night Thursday."
            ),
            "reason": "Relevant interest, but not time-sensitive.",
            "deadline": None,
        },
        {
            "id": "demo-email-newsletter",
            "sender": "Campus Weekly <digest@northbridge.example.edu>",
            "subject": "This week at Northbridge",
            "body": (
                "A weekly digest of campus events, club updates, and announcements."
            ),
            "category": "noise",
            "priority": "low",
            "action_required": False,
            "response_required": False,
            "action_type": "none",
            "summary": "General weekly campus newsletter.",
            "reason": "Informational digest with no required action.",
            "deadline": None,
        },
    ]

    timestamps = _demo_email_times(
        now,
        len(email_specs),
    )

    connection = get_connection()

    # Demo mode must never display records left over from a real local run.
    # Clear user-facing data before inserting the fictional Northbridge data.
    connection.execute("DELETE FROM opportunity_matches")
    connection.execute("DELETE FROM email_analysis")
    connection.execute("DELETE FROM emails")
    connection.execute("DELETE FROM calendar_analysis")
    connection.execute("DELETE FROM calendar_events")
    connection.execute("DELETE FROM notification_log")
    connection.execute("DELETE FROM runtime_state")
    connection.commit()

    for spec, timestamp in zip(email_specs, timestamps):
        connection.execute(
            """
            INSERT INTO emails (
                id,
                sender,
                recipient,
                subject,
                body,
                timestamp,
                read,
                processed,
                processed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(id) DO UPDATE SET
                sender = excluded.sender,
                recipient = excluded.recipient,
                subject = excluded.subject,
                body = excluded.body,
                timestamp = excluded.timestamp,
                read = excluded.read,
                processed = 1,
                processed_at = excluded.processed_at
            """,
            (
                spec["id"],
                spec["sender"],
                "alex.morgan@northbridge.example.edu",
                spec["subject"],
                spec["body"],
                timestamp,
                0,
                now.astimezone(timezone.utc).isoformat(),
            ),
        )

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
                spec["id"],
                spec["category"],
                spec["priority"],
                int(spec["action_required"]),
                int(spec["response_required"]),
                spec["action_type"],
                spec["summary"],
                spec["reason"],
                spec["deadline"],
                now.astimezone(timezone.utc).isoformat(),
            ),
        )

    calendar_specs = [
        {
            "id": "demo-calendar-cs231",
            "title": "CS 231: Systems Programming",
            "date": today.isoformat(),
            "time": "9:30 AM",
            "end_time": "10:45 AM",
            "duration_minutes": 75,
            "all_day": False,
            "calendar_id": "demo-primary",
            "source": "google_calendar",
        },
        {
            "id": "demo-calendar-econ",
            "title": "ECON 110: Principles of Economics",
            "date": today.isoformat(),
            "time": "1:00 PM",
            "end_time": "2:15 PM",
            "duration_minutes": 75,
            "all_day": False,
            "calendar_id": "demo-primary",
            "source": "google_calendar",
        },
        {
            "id": "demo-calendar-assignment",
            "title": "CS 231 Project Checkpoint [Learning Portal]",
            "date": tomorrow.isoformat(),
            "time": "11:59 PM",
            "end_time": None,
            "duration_minutes": None,
            "all_day": False,
            "calendar_id": "demo-learning-portal",
            "source": "canvas",
        },
        {
            "id": "demo-calendar-meeting",
            "title": "Research Project Check-in",
            "date": tomorrow.isoformat(),
            "time": "2:30 PM",
            "end_time": "3:00 PM",
            "duration_minutes": 30,
            "all_day": False,
            "calendar_id": "demo-primary",
            "source": "google_calendar",
        },
        {
            "id": "demo-calendar-career-fair",
            "title": "Technology Internship Fair",
            "date": day_after.isoformat(),
            "time": "12:00 PM",
            "end_time": "2:00 PM",
            "duration_minutes": 120,
            "all_day": False,
            "calendar_id": "demo-primary",
            "source": "google_calendar",
        },
    ]

    for event in calendar_specs:
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
                source,
                processed,
                processed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                date = excluded.date,
                time = excluded.time,
                end_time = excluded.end_time,
                duration_minutes = excluded.duration_minutes,
                all_day = excluded.all_day,
                calendar_id = excluded.calendar_id,
                source = excluded.source,
                processed = 1,
                processed_at = excluded.processed_at
            """,
            (
                event["id"],
                event["title"],
                event["date"],
                event["time"],
                event["end_time"],
                event["duration_minutes"],
                int(event["all_day"]),
                event["calendar_id"],
                event["source"],
                now.astimezone(timezone.utc).isoformat(),
            ),
        )

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
        VALUES (?, ?, ?, 1, ?, ?, ?, ?)
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
            "demo-calendar-assignment",
            "assignment",
            "urgent",
            "notify",
            "CS 231 project checkpoint is due tomorrow at 11:59 PM.",
            "The deadline is tomorrow, so it needs immediate planning.",
            now.astimezone(timezone.utc).isoformat(),
        ),
    )

    connection.commit()
    connection.close()
