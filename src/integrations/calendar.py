"""
Calendar integration for the Student Chief of Staff.

This module provides calendar operations for the background agent.

Agent-facing tools perform high-level calendar actions such as checking
for conflicts, creating events, updating events, deleting events, and
rescheduling events.

Internal functions handle calendar retrieval, time calculations, and
finding available time slots. These internal functions are used by the
agent-facing tools and processing layer and are not exposed directly
to the model.

Google Calendar is the external source of truth when the Google backend
is enabled. SQLite provides persistent local storage for calendar data.
"""

from strands import tool

import os
import threading
import time as clock
import uuid
from datetime import datetime

from src.integrations import google_calendar

from src.storage.database import (
    save_calendar_event,
    get_calendar_event as get_stored_calendar_event,
    get_calendar_events as get_stored_calendar_events,
    delete_calendar_event as delete_stored_calendar_event,
)


# Default duration used when an event does not provide an end time
# or duration.
DEFAULT_DURATION_MINUTES = 60

# Default period in which the background agent is allowed to schedule
# events.
DEFAULT_DAY_START = "8:00 AM"
DEFAULT_DAY_END = "10:00 PM"


# ============================================================
# INTERNAL CALENDAR FUNCTIONS
# ============================================================

# A model can occasionally emit the same write-tool call twice while
# forming one response. Keep a short idempotency window so that cannot
# create two identical real events.
_RECENT_CREATIONS: dict[tuple, tuple[float, dict]] = {}
_CREATION_LOCK = threading.Lock()
_DUPLICATE_WINDOW_SECONDS = 90


def _use_google_calendar() -> bool:
    """
    Return whether the agent should operate on the live Google Calendar.

    When CALENDAR_BACKEND=google, writes are sent to Google Calendar
    and mirrored into SQLite.

    Otherwise, SQLite is used as the local backend.
    """

    return (
        os.environ.get(
            "CALENDAR_BACKEND",
            "database",
        ).lower()
        == "google"
    )


def get_events(
    date: str | None = None,
) -> list[dict]:
    """
    Retrieve calendar events from local storage.

    Google Calendar synchronization is handled by the
    background runtime.

    Args:
        date: Optional date in YYYY-MM-DD format.

    Returns:
        A list of calendar events.
    """

    return get_stored_calendar_events(date)


def add_event(
    title: str,
    date: str,
    time: str,
    end_time: str | None = None,
    duration_minutes: int | None = None,
) -> dict:
    """
    Add a new calendar event.

    With the Google backend enabled, the event is created in Google
    Calendar first and then stored in SQLite.

    Otherwise, the event is created directly in SQLite.

    Args:
        title: Event title.
        date: Event date in YYYY-MM-DD format.
        time: Event start time.
        end_time: Optional event end time.
        duration_minutes: Optional event duration.

    Returns:
        The created event.
    """

    if _use_google_calendar():

        event = google_calendar.add_event(
            title=title,
            date=date,
            time=time,
            end_time=end_time,
            duration_minutes=duration_minutes,
        )

        save_calendar_event(event)

        return event

    event = {
        "id": str(uuid.uuid4()),
        "title": title,
        "date": date,
        "time": time,
    }

    if end_time is not None:
        event["end_time"] = end_time

    elif duration_minutes is not None:
        event["duration_minutes"] = duration_minutes

    save_calendar_event(event)

    return event


def remove_event(
    event_id: str,
) -> bool:
    """
    Remove a calendar event.

    With the Google backend enabled, remove the event from Google
    Calendar first. If successful, also remove the local SQLite copy.

    Otherwise, remove the event only from SQLite.

    Args:
        event_id: Unique event ID.

    Returns:
        True if an event was removed, otherwise False.
    """

    if _use_google_calendar():

        removed = google_calendar.remove_event(
            event_id
        )

        if removed:
            delete_stored_calendar_event(
                event_id
            )

        return removed

    existing = get_stored_calendar_event(
        event_id
    )

    if existing is None:
        return False

    delete_stored_calendar_event(
        event_id
    )

    return True


def update_event(
    event_id: str,
    **changes,
) -> dict | None:
    """
    Update an existing calendar event.

    With the Google backend enabled, update Google Calendar first
    and then update the local SQLite copy.

    Otherwise, update the event directly in SQLite.

    Args:
        event_id: Unique event ID.
        **changes: Fields to update.

    Returns:
        The updated event, or None if the event does not exist.
    """

    if _use_google_calendar():

        updated = google_calendar.update_event(
            event_id,
            **changes,
        )

        if updated is not None:
            save_calendar_event(updated)

        return updated

    event = get_stored_calendar_event(
        event_id
    )

    if event is None:
        return None

    event.update(changes)

    save_calendar_event(event)

    return event

def _time_to_minutes(time_str: str) -> int:
    """
    Convert a 12-hour time string into minutes after midnight.

    Args:
        time_str: Time in the format "3:00 PM".

    Returns:
        The number of minutes after midnight.
    """
    t, period = time_str.strip().upper().split(" ")
    hour, minute = map(int, t.split(":"))

    if period == "PM" and hour != 12:
        hour += 12

    if period == "AM" and hour == 12:
        hour = 0

    return hour * 60 + minute


def _validate_date_and_time(date: str, time: str) -> None:
    """Reject malformed tool input before a calendar write occurs."""
    try:
        datetime.strptime(date, "%Y-%m-%d")
        minutes = _time_to_minutes(time)
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError("Use date YYYY-MM-DD and time like '3:00 PM'.") from error
    if not 0 <= minutes < 24 * 60:
        raise ValueError("Time must fall within a single day.")


def _conflicts_for_interval(
    date: str, start: int, end: int, exclude_event_id: str | None = None,
) -> list[dict]:
    return [
        event for event in _get_events_for_date(date)
        if event.get("id") != exclude_event_id
        # An all-day item is typically a deadline/reminder, not an occupied
        # timed interval. It must not block creating a timed event.
        and not bool(event.get("all_day"))
        and _intervals_overlap(start, end, *_event_interval(event))
    ]


def _assert_no_conflict(
    date: str, time: str, end_time: str | None, duration_minutes: int | None,
    exclude_event_id: str | None = None,
) -> None:
    _validate_date_and_time(date, time)
    if end_time is not None:
        _validate_date_and_time(date, end_time)
        end = _time_to_minutes(end_time)
    else:
        duration = duration_minutes if duration_minutes is not None else DEFAULT_DURATION_MINUTES
        if duration <= 0:
            raise ValueError("duration_minutes must be positive.")
        end = _time_to_minutes(time) + duration
    start = _time_to_minutes(time)
    if end <= start or end > 24 * 60:
        raise ValueError("The event must end after it starts on the same day.")
    conflicts = _conflicts_for_interval(date, start, end, exclude_event_id)
    if conflicts:
        names = ", ".join(f'"{event["title"]}"' for event in conflicts)
        raise ValueError(f"That time overlaps {names}.")


def _minutes_to_time(minutes: int) -> str:
    """
    Convert minutes after midnight into a 12-hour time string.

    Args:
        minutes: Number of minutes after midnight.

    Returns:
        Time formatted as "3:00 PM".
    """
    minutes = minutes % (24 * 60)

    hour = minutes // 60
    minute = minutes % 60

    period = "AM"

    if hour >= 12:
        period = "PM"

    display_hour = hour % 12

    if display_hour == 0:
        display_hour = 12

    return f"{display_hour}:{minute:02d} {period}"


def _event_interval(event: dict) -> tuple[int, int]:
    """
    Determine the start and end time of a calendar event.

    Args:
        event: Calendar event dictionary.

    Returns:
        A tuple containing the start and end time in minutes
        after midnight.
    """
    start = _time_to_minutes(event["time"])

    if event.get("end_time"):
        end = _time_to_minutes(event["end_time"])
    elif event.get("duration_minutes"):
        end = start + event["duration_minutes"]
    else:
        end = start + DEFAULT_DURATION_MINUTES

    return start, end


def _intervals_overlap(
    a_start: int,
    a_end: int,
    b_start: int,
    b_end: int,
) -> bool:
    """
    Determine whether two time intervals overlap.

    Args:
        a_start: Start time of the first interval.
        a_end: End time of the first interval.
        b_start: Start time of the second interval.
        b_end: End time of the second interval.

    Returns:
        True if the intervals overlap, otherwise False.
    """
    return a_start < b_end and b_start < a_end


def _get_events_for_date(date: str) -> list[dict]:
    """
    Retrieve all calendar events for a specific date.

    This is an internal function used by scheduling operations.

    Args:
        date: Date in YYYY-MM-DD format.

    Returns:
        A list of events occurring on the specified date.
    """
    events = get_events()

    return [
        event
        for event in events
        if event.get("date") == date
    ]


def _get_free_slots(
    date: str,
    duration_minutes: int,
    start_time: str = DEFAULT_DAY_START,
    end_time: str = DEFAULT_DAY_END,
) -> list[dict]:
    """
    Find available time slots large enough for a requested event.

    This function is used internally when the background agent needs
    to schedule something without creating a calendar conflict.

    Args:
        date: Date in YYYY-MM-DD format.
        duration_minutes: Minimum required length of the free slot.
        start_time: Earliest time at which an event may be scheduled.
        end_time: Latest time at which an event may end.

    Returns:
        A list of available time slots.
    """
    day_start = _time_to_minutes(start_time)
    day_end = _time_to_minutes(end_time)

    events = _get_events_for_date(date)

    intervals = []

    for event in events:
        # All-day items (for example Canvas assignment deadlines) belong on
        # the schedule but do not consume every minute of the day.
        if bool(event.get("all_day")):
            continue

        start, end = _event_interval(event)

        # Ignore events completely outside the scheduling window.
        if end <= day_start or start >= day_end:
            continue

        intervals.append(
            (
                max(start, day_start),
                min(end, day_end),
            )
        )

    intervals.sort(key=lambda interval: interval[0])

    free_slots = []
    current_time = day_start

    for start, end in intervals:

        if current_time < start:
            available_duration = start - current_time

            if available_duration >= duration_minutes:
                free_slots.append(
                    {
                        "date": date,
                        "start_minutes": current_time,
                        "end_minutes": start,
                        "duration_minutes": available_duration,
                        "start_time": _minutes_to_time(current_time),
                        "end_time": _minutes_to_time(start),
                    }
                )

        current_time = max(current_time, end)

    # Check the time after the final calendar event.
    if current_time < day_end:
        available_duration = day_end - current_time

        if available_duration >= duration_minutes:
            free_slots.append(
                {
                    "date": date,
                    "start_minutes": current_time,
                    "end_minutes": day_end,
                    "duration_minutes": available_duration,
                    "start_time": _minutes_to_time(current_time),
                    "end_time": _minutes_to_time(day_end),
                }
            )

    return free_slots


def _find_best_free_slot(
    date: str,
    duration_minutes: int,
    preferred_start_time: str | None = None,
    preferred_end_time: str | None = None,
) -> dict | None:
    """
    Find the most appropriate available slot for a new event.

    This function is used internally by scheduling operations.

    Args:
        date: Date in YYYY-MM-DD format.
        duration_minutes: Required event duration.
        preferred_start_time: Optional earliest preferred start time.
        preferred_end_time: Optional latest preferred end time.

    Returns:
        The best available time slot, or None if no suitable slot exists.
    """
    start_time = preferred_start_time or DEFAULT_DAY_START
    end_time = preferred_end_time or DEFAULT_DAY_END

    slots = _get_free_slots(
        date=date,
        duration_minutes=duration_minutes,
        start_time=start_time,
        end_time=end_time,
    )

    if not slots:
        return None

    # For now, choose the earliest suitable slot.
    # Later the planner can rank slots based on the student's
    # preferences, workload, course schedule, etc.
    return slots[0]

def suggest_free_slot(
    date: str,
    duration_minutes: int = 90,
    preferred_start_time: str | None = None,
    preferred_end_time: str | None = None,
) -> dict | None:
    """
    Suggest a conflict-free calendar slot without creating an event.
    """

    _validate_date_and_time(
        date,
        preferred_start_time or DEFAULT_DAY_START,
    )
    _validate_date_and_time(
        date,
        preferred_end_time or DEFAULT_DAY_END,
    )

    if duration_minutes <= 0:
        raise ValueError(
            "duration_minutes must be positive."
        )

    slot = _find_best_free_slot(
        date=date,
        duration_minutes=duration_minutes,
        preferred_start_time=preferred_start_time,
        preferred_end_time=preferred_end_time,
    )

    if slot is None:
        return None

    start_minutes = slot["start_minutes"]

    return {
        "date": date,
        "start_time": slot["start_time"],
        "end_time": _minutes_to_time(
            start_minutes + duration_minutes
        ),
        "duration_minutes": duration_minutes,
    }

def suggest_free_slots(
    date: str,
    duration_minutes: int = 90,
    preferred_start_time: str | None = None,
    preferred_end_time: str | None = None,
    step_minutes: int = 60,
) -> list[dict]:
    """
    Return multiple conflict-free scheduling options without
    creating any calendar events.
    """

    start_time = (
        preferred_start_time
        or DEFAULT_DAY_START
    )

    end_time = (
        preferred_end_time
        or DEFAULT_DAY_END
    )

    _validate_date_and_time(
        date,
        start_time,
    )

    _validate_date_and_time(
        date,
        end_time,
    )

    if duration_minutes <= 0:
        raise ValueError(
            "duration_minutes must be positive."
        )

    if step_minutes <= 0:
        raise ValueError(
            "step_minutes must be positive."
        )

    free_windows = _get_free_slots(
        date=date,
        duration_minutes=duration_minutes,
        start_time=start_time,
        end_time=end_time,
    )

    suggestions = []

    for window in free_windows:
        candidate_start = window["start_minutes"]
        latest_start = (
            window["end_minutes"]
            - duration_minutes
        )

        while candidate_start <= latest_start:
            candidate_end = (
                candidate_start
                + duration_minutes
            )

            suggestions.append(
                {
                    "date": date,
                    "start_time": _minutes_to_time(
                        candidate_start
                    ),
                    "end_time": _minutes_to_time(
                        candidate_end
                    ),
                    "duration_minutes": duration_minutes,
                    "start_minutes": candidate_start,
                    "end_minutes": candidate_end,
                }
            )

            candidate_start += step_minutes

    return suggestions


# ============================================================
# AGENT-FACING TOOLS
# ============================================================

@tool
def check_calendar() -> str:
    """
    Check the calendar for actual scheduling conflicts.

    Use this when the agent needs to determine whether existing
    calendar commitments overlap.

    Returns:
        A human-readable description of calendar conflicts.
    """
    events = get_events()

    by_day = {}

    for event in events:
        by_day.setdefault(event["date"], []).append(event)

    conflicts = []

    for day, day_events in sorted(by_day.items()):

        if len(day_events) < 2:
            continue

        # All-day deadline/reminder items do not represent timed occupancy,
        # so they cannot conflict with normal timed events.
        timed_events = [
            event for event in day_events
            if not bool(event.get("all_day"))
        ]

        if len(timed_events) < 2:
            continue

        intervals = [
            (_event_interval(event), event)
            for event in timed_events
        ]

        intervals.sort(key=lambda pair: pair[0][0])

        for i in range(len(intervals)):
            (a_start, a_end), event_a = intervals[i]

            for j in range(i + 1, len(intervals)):
                (b_start, b_end), event_b = intervals[j]

                if _intervals_overlap(
                    a_start,
                    a_end,
                    b_start,
                    b_end,
                ):
                    conflicts.append(
                        f'- {day}: "{event_a["title"]}" '
                        f'({event_a["time"]}) overlaps '
                        f'"{event_b["title"]}" '
                        f'({event_b["time"]})'
                    )

    if not conflicts:
        return "No calendar conflicts."

    return "Calendar conflicts:\n" + "\n".join(conflicts)


@tool
def get_schedule(date: str | None = None) -> list[dict]:
    """
    Retrieve the student's calendar schedule.

    Use this when the agent needs to inspect the student's existing
    calendar commitments.

    Args:
        date: Optional date in YYYY-MM-DD format. If provided, only
            events on that date are returned.

    Returns:
        A list of calendar events.
    """
    if date:
        return _get_events_for_date(date)

    return get_events()


@tool
def create_event(
    title: str,
    date: str,
    time: str,
    end_time: str | None = None,
    duration_minutes: int | None = None,
) -> str:
    """
    Create a calendar event at a specified time.

    Use this when the desired date and time are already known.

    Args:
        title: Name of the event.
        date: Event date in YYYY-MM-DD format.
        time: Event start time.
        end_time: Optional event end time.
        duration_minutes: Optional event duration.

    Returns:
        A confirmation message containing the created event ID.
    """
    key = (title.strip().casefold(), date, time, end_time, duration_minutes)
    now = clock.monotonic()
    with _CREATION_LOCK:
        stale_keys = [
            cached_key
            for cached_key, (created_at, _) in _RECENT_CREATIONS.items()
            if now - created_at >= _DUPLICATE_WINDOW_SECONDS
        ]
        for stale_key in stale_keys:
            _RECENT_CREATIONS.pop(stale_key, None)
        existing = _RECENT_CREATIONS.get(key)
        if existing and now - existing[0] < _DUPLICATE_WINDOW_SECONDS:
            event = existing[1]
            return (
                f'Event already exists for this request: "{event["title"]}" '
                f'on {event["date"]} at {event["time"]} (id: {event["id"]}).'
            )
    _assert_no_conflict(date, time, end_time, duration_minutes)
    with _CREATION_LOCK:
        event = add_event(
            title=title,
            date=date,
            time=time,
            end_time=end_time,
            duration_minutes=duration_minutes,
        )
        _RECENT_CREATIONS[key] = (now, event)

    return (
        f'Added "{title}" on {date} at {time} '
        f'(id: {event["id"]}).'
    )


@tool
def schedule_event_in_free_time(
    title: str,
    date: str,
    duration_minutes: int,
    preferred_start_time: str | None = None,
    preferred_end_time: str | None = None,
) -> str:
    """
    Schedule an event in an available calendar slot.

    Use this when the agent needs to schedule something but does not
    have an exact time. The function searches the calendar for a
    suitable free period and creates the event there.

    Args:
        title: Name of the event.
        date: Date in YYYY-MM-DD format.
        duration_minutes: Required event duration.
        preferred_start_time: Optional earliest preferred start time.
        preferred_end_time: Optional latest preferred end time.

    Returns:
        A confirmation message containing the scheduled time, or a
        message indicating that no suitable slot was found.
    """
    _validate_date_and_time(date, preferred_start_time or DEFAULT_DAY_START)
    _validate_date_and_time(date, preferred_end_time or DEFAULT_DAY_END)
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive.")
    slot = _find_best_free_slot(
        date=date,
        duration_minutes=duration_minutes,
        preferred_start_time=preferred_start_time,
        preferred_end_time=preferred_end_time,
    )

    if slot is None:
        return (
            f'No {duration_minutes}-minute free slot was found '
            f'on {date}.'
        )

    event = add_event(
        title=title,
        date=date,
        time=slot["start_time"],
        # A slot describes the maximum available window. Reserve only the
        # requested duration, not the whole window.
        end_time=_minutes_to_time(slot["start_minutes"] + duration_minutes),
        duration_minutes=duration_minutes,
    )

    return (
        f'Scheduled "{title}" on {date} from '
        f'{slot["start_time"]} to {_minutes_to_time(slot["start_minutes"] + duration_minutes)} '
        f'(id: {event["id"]}).'
    )


@tool
def update_the_event(
    event_id: str,
    title: str | None = None,
    date: str | None = None,
    time: str | None = None,
    end_time: str | None = None,
    duration_minutes: int | None = None,
) -> str:
    """
    Update an existing calendar event.

    Args:
        event_id: Unique ID of the event.
        title: Optional new title.
        date: Optional new date.
        time: Optional new start time.
        end_time: Optional new end time.
        duration_minutes: Optional new duration.

    Returns:
        A confirmation message or an error message.
    """
    changes = {}

    if title is not None:
        changes["title"] = title

    if date is not None:
        changes["date"] = date

    if time is not None:
        changes["time"] = time

    if end_time is not None:
        changes["end_time"] = end_time

    if duration_minutes is not None:
        changes["duration_minutes"] = duration_minutes

    if not changes:
        return "No changes given."

    current = next((event for event in get_events() if event.get("id") == event_id), None)
    if current is None:
        return "No event found with that id."
    changing_time = "time" in changes
    if "end_time" in changes or "duration_minutes" in changes:
        end_time = changes.get("end_time", current.get("end_time"))
        duration = changes.get("duration_minutes", current.get("duration_minutes"))
    elif changing_time:
        start, end = _event_interval(current)
        end_time, duration = None, end - start
    else:
        end_time, duration = current.get("end_time"), current.get("duration_minutes")
    _assert_no_conflict(changes.get("date", current["date"]), changes.get("time", current["time"]), end_time, duration, event_id)
    updated = update_event(
        event_id,
        **changes,
    )

    if updated is None:
        return "No event found with that id."

    return (
        f'Updated "{updated["title"]}" to '
        f'{updated["date"]} at {updated["time"]}.'
    )


@tool
def delete_event(event_id: str) -> str:
    """
    Delete a calendar event.

    Use this when the user or background agent has determined that
    an existing event should be removed.

    Args:
        event_id: Unique ID of the event to delete.

    Returns:
        A confirmation message indicating whether the event was deleted.
    """
    removed = remove_event(event_id)

    if removed:
        return "Event removed."

    return "No event found with that id."


@tool
def reschedule_event(
    event_id: str,
    new_date: str | None = None,
    new_time: str | None = None,
) -> str:
    """
    Reschedule an existing calendar event.

    Args:
        event_id: Unique ID of the event.
        new_date: Optional new date in YYYY-MM-DD format.
        new_time: Optional new start time.

    Returns:
        A confirmation message or an error message.
    """
    changes = {}

    if new_date is not None:
        changes["date"] = new_date

    if new_time is not None:
        changes["time"] = new_time

    if not changes:
        return (
            "No changes given -- provide a new date and/or time."
        )

    current = next((event for event in get_events() if event.get("id") == event_id), None)
    if current is None:
        return "No event found with that id."
    if new_time:
        start, end = _event_interval(current)
        end_time, duration = None, end - start
    else:
        end_time, duration = current.get("end_time"), current.get("duration_minutes")
    _assert_no_conflict(new_date or current["date"], new_time or current["time"], end_time, duration, event_id)
    updated = update_event(
        event_id,
        **changes,
    )

    if updated is None:
        return "No event found with that id."

    return (
        f'Updated "{updated["title"]}" to '
        f'{updated["date"]} at {updated["time"]}.'
    )
