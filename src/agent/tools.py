"""Tools exposed to the Student Chief of Staff agent."""

from __future__ import annotations

from strands import tool

from src.integrations.calendar import (
    check_calendar,
    create_event,
    delete_event,
    get_schedule,
    reschedule_event,
    schedule_event_in_free_time,
    update_the_event,
)
from src.storage.memory import (
    get_opportunity_match,
    get_profile,
    update_profile,
)
from src.storage.state import get_runtime_status

from src.integrations.emails import (
    draft_email,
    get_email,
    get_email_brief,
    get_recent_emails,
    get_unread_emails,
)

def _csv(value: str | None) -> list[str] | None:
    if value is None:
        return None

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


@tool
def get_background_monitor_status() -> dict:
    """
    Return the most recent Gmail sync, Calendar sync, processing result,
    priority refresh, scheduler status, and last recorded error.
    """

    return get_runtime_status()


@tool
def get_student_preferences() -> dict:
    """
    Return the student's saved opportunity-matching preferences.

    Use this before discussing how opportunities are ranked.
    """

    return get_profile()


@tool
def update_student_preferences(
    interests: str | None = None,
    target_roles: str | None = None,
    skills: str | None = None,
    locations: str | None = None,
    minimum_match_score: int | None = None,
) -> dict:
    """
    Update opportunity-matching preferences after an explicit user request.

    The list arguments are comma-separated strings. Never use this tool to
    infer preferences from an email; ask the student first.
    """

    changes = {}

    for field, value in (
        ("interests", interests),
        ("target_roles", target_roles),
        ("skills", skills),
        ("locations", locations),
    ):
        parsed = _csv(value)

        if parsed is not None:
            changes[field] = parsed

    if minimum_match_score is not None:
        changes["minimum_match_score"] = minimum_match_score

    if not changes:
        return get_profile()

    return update_profile(**changes)


@tool
def get_saved_opportunity_match(
    email_id: str,
) -> dict | None:
    """
    Return the saved opportunity-match score, explanation, and recommendation
    for an email ID.
    """

    return get_opportunity_match(email_id)


CALENDAR_TOOLS = [
    check_calendar,
    get_schedule,
    create_event,
    schedule_event_in_free_time,
    update_the_event,
    delete_event,
    reschedule_event,
]

EMAIL_TOOLS = [
    get_email_brief,
    get_recent_emails,
    get_unread_emails,
    get_email,
    draft_email,
]

PROFILE_AND_STATUS_TOOLS = [
    get_background_monitor_status,
    get_student_preferences,
    update_student_preferences,
    get_saved_opportunity_match,
]


def get_tools():
    """Return every tool available to the coordinator agent."""

    return (
        CALENDAR_TOOLS
        + EMAIL_TOOLS
        + PROFILE_AND_STATUS_TOOLS
    )