"""
Priority logic for the Student Chief of Staff.

The AI classifier estimates semantic importance.

This module adjusts final priority using deadline proximity so
near-term deadlines are prioritized above distant deadlines.
"""

from datetime import datetime
from typing import Any


VALID_PRIORITIES = {
    "low",
    "medium",
    "high",
    "urgent",
}


def validate_priority(
    priority: str | None,
) -> str:
    """
    Validate a priority returned by the AI classifier.
    """

    if priority not in VALID_PRIORITIES:
        raise ValueError(
            f"Invalid priority returned by classifier: {priority!r}"
        )

    return priority


def _parse_deadline(
    deadline: str | None,
) -> datetime | None:
    """
    Parse an ISO-formatted deadline.

    Supported forms:
    - YYYY-MM-DD
    - YYYY-MM-DDTHH:MM:SS
    - ISO timestamps with timezone information
    """

    if not deadline:
        return None

    text = deadline.strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text)

    except ValueError:
        return None

    # A date-only deadline should represent the end of that day,
    # rather than midnight at the beginning of the day.
    if (
        len(text) == 10
        and text[4] == "-"
        and text[7] == "-"
    ):
        parsed = parsed.replace(
            hour=23,
            minute=59,
            second=59,
        )

    return parsed


def priority_from_deadline(
    deadline: str | None,
    now: datetime | None = None,
) -> str | None:
    """
    Determine urgency from deadline proximity.

    Returns None when no usable deadline exists.
    """

    parsed_deadline = _parse_deadline(deadline)

    if parsed_deadline is None:
        return None

    if now is None:
        now = datetime.now().astimezone()

    # If the parsed deadline has no timezone, compare using
    # local wall-clock time.
    if parsed_deadline.tzinfo is None:
        now = now.replace(tzinfo=None)

    days_remaining = (
    parsed_deadline.date() - now.date()
    ).days

    # Do not interrupt the student about historical deadlines.
    if days_remaining < 0:
        return "low"

    if days_remaining <= 1:
        return "urgent"

    if days_remaining <= 3:
        return "high"

    if days_remaining <= 7:
        return "medium"

    return "low"


def prioritize_with_deadline(
    base_priority: str,
    deadline: str | None,
) -> str:
    """
    Produce the final priority for an item.

    If there is a usable deadline, deadline proximity determines
    urgency. Otherwise, the AI classifier's priority is preserved.
    """

    validate_priority(base_priority)

    deadline_priority = priority_from_deadline(
        deadline
    )

    if deadline_priority is None:
        return base_priority

    return deadline_priority


def calendar_deadline(
    event: dict[str, Any],
) -> str | None:
    """
    Build an ISO deadline from a calendar event.

    For timed events, use the event start time.
    For all-day events, treat the deadline as the end of that date.
    """

    date = event.get("date")

    if not date:
        return None

    if event.get("all_day"):
        return date

    time = event.get("time")

    if not time:
        return date

    return f"{date}T{time}"


def prioritize_calendar_event(
    base_priority: str,
    event: dict[str, Any],
    category: str,
    action_required: bool,
) -> str:
    """
    Produce final priority for a calendar event.

    Routine events such as classes should keep their AI priority.
    Deadline-oriented items are adjusted according to how soon
    they occur.
    """

    validate_priority(base_priority)

    if not action_required:
        return base_priority

    if category not in {
        "assignment",
        "exam",
    }:
        return base_priority

    deadline = calendar_deadline(
        event
    )

    return prioritize_with_deadline(
        base_priority=base_priority,
        deadline=deadline,
    )