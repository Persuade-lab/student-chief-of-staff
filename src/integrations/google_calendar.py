"""
Google Calendar storage adapter for the Student Chief of Staff.

Its functions mirror the storage functions in ``calendar.py`` so the existing
Strands tools can perform real work on the signed-in user's primary calendar.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.integrations.google_auth import get_google_calendar_service

from src.storage.database import (
    save_calendar_events,
)


PRIMARY_CALENDAR_ID = "primary"

CANVAS_CALENDAR_ID = (
    "dpfcctbrr7eb20opi9e2evsf3o8c799c"
    "@import.calendar.google.com"
)

CALENDAR_IDS = [
    PRIMARY_CALENDAR_ID,
    CANVAS_CALENDAR_ID,
]

DEFAULT_DURATION_MINUTES = 60
_LOCAL_TIMEZONE = datetime.now().astimezone().tzinfo


def _parse_google_datetime(value: str) -> datetime:
    moment = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if moment.tzinfo is None:
        return moment.replace(
            tzinfo=_LOCAL_TIMEZONE
        )

    return moment.astimezone(
        _LOCAL_TIMEZONE
    )


def _event_to_dict(
    event: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert a Google Calendar event to the project's event shape.
    """

    start = event.get("start", {})
    end = event.get("end", {})

    if "date" in start:
        start_day = datetime.strptime(
            start["date"],
            "%Y-%m-%d",
        )

        end_day = datetime.strptime(
            end.get(
                "date",
                start["date"],
            ),
            "%Y-%m-%d",
        )

        return {
            "id": event["id"],
            "title": (
                event.get("summary")
                or "Untitled event"
            ),
            "date": start["date"],
            "time": "12:00 AM",
            "duration_minutes": max(
                1,
                int(
                    (
                        end_day
                        - start_day
                    ).total_seconds()
                    // 60
                ),
            ),
            "all_day": True,
        }

    start_moment = _parse_google_datetime(
        start["dateTime"]
    )

    end_moment = _parse_google_datetime(
        end["dateTime"]
    )

    return {
        "id": event["id"],
        "title": (
            event.get("summary")
            or "Untitled event"
        ),
        "date": start_moment.strftime(
            "%Y-%m-%d"
        ),
        "time": start_moment.strftime(
            "%-I:%M %p"
        ),
        "end_time": end_moment.strftime(
            "%-I:%M %p"
        ),
        "all_day": False,
    }


def _local_datetime(
    date: str,
    time: str,
) -> datetime:
    return datetime.strptime(
        f"{date} {time}",
        "%Y-%m-%d %I:%M %p",
    ).replace(
        tzinfo=_LOCAL_TIMEZONE
    )


def _list_events(
    calendar_id: str,
    time_min: datetime,
    time_max: datetime,
) -> list[dict[str, Any]]:
    service = get_google_calendar_service()

    events: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )

        events.extend(
            response.get(
                "items",
                [],
            )
        )

        page_token = response.get(
            "nextPageToken"
        )

        if not page_token:
            return events


def get_events(
    date: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return events from the primary and Canvas calendars.
    """

    if date:
        start = datetime.strptime(
            date,
            "%Y-%m-%d",
        ).replace(
            tzinfo=_LOCAL_TIMEZONE
        )

        end = start + timedelta(days=1)

    else:
        now = datetime.now(
            _LOCAL_TIMEZONE
        )

        start = now - timedelta(days=365)
        end = now + timedelta(days=365)

    events: list[dict[str, Any]] = []

    for calendar_id in CALENDAR_IDS:
        raw_events = _list_events(
            calendar_id,
            start,
            end,
        )

        for raw_event in raw_events:
            event = _event_to_dict(
                raw_event
            )

            event["calendar_id"] = (
                calendar_id
            )

            if (
                calendar_id
                == PRIMARY_CALENDAR_ID
            ):
                event["source"] = "primary"

            elif (
                calendar_id
                == CANVAS_CALENDAR_ID
            ):
                event["source"] = "canvas"

            events.append(event)

    events.sort(
        key=lambda event: (
            event.get("date", ""),
            event.get("time", ""),
        )
    )

    return events


def sync_calendar_events() -> list[dict[str, Any]]:
    """
    Synchronize Google Calendar events into the local SQLite database.

    Existing events are updated in place so processing state and saved
    analysis are preserved across synchronization runs.

    Returns:
        The events retrieved from Google Calendar.
    """

    events = get_events()

    save_calendar_events(events)

    return events


def add_event(
    title: str,
    date: str,
    time: str,
    end_time: str | None = None,
    duration_minutes: int | None = None,
) -> dict[str, Any]:
    """
    Create an event in the primary Google Calendar.
    """

    start = _local_datetime(
        date,
        time,
    )

    if end_time is not None:
        end = _local_datetime(
            date,
            end_time,
        )

    else:
        duration = (
            duration_minutes
            if duration_minutes is not None
            else DEFAULT_DURATION_MINUTES
        )

        if duration <= 0:
            raise ValueError(
                "duration_minutes must be positive."
            )

        end = start + timedelta(
            minutes=duration
        )

    if end <= start:
        raise ValueError(
            "The event end time must be after its start time."
        )

    created = (
        get_google_calendar_service()
        .events()
        .insert(
            calendarId=PRIMARY_CALENDAR_ID,
            body={
                "summary": title,
                "start": {
                    "dateTime": start.isoformat(),
                },
                "end": {
                    "dateTime": end.isoformat(),
                },
            },
        )
        .execute()
    )

    event = _event_to_dict(
        created
    )

    event["calendar_id"] = (
        PRIMARY_CALENDAR_ID
    )

    event["source"] = "primary"

    return event


def remove_event(
    event_id: str,
) -> bool:
    """
    Delete an event by its Google Calendar event id.
    """

    try:
        (
            get_google_calendar_service()
            .events()
            .delete(
                calendarId=PRIMARY_CALENDAR_ID,
                eventId=event_id,
            )
            .execute()
        )

    except Exception as error:
        if (
            getattr(
                getattr(
                    error,
                    "resp",
                    None,
                ),
                "status",
                None,
            )
            == 404
        ):
            return False

        raise

    return True


def update_event(
    event_id: str,
    **changes: Any,
) -> dict[str, Any] | None:
    """
    Update a live event while preserving its current duration by default.
    """

    service = get_google_calendar_service()

    try:
        event = (
            service.events()
            .get(
                calendarId=PRIMARY_CALENDAR_ID,
                eventId=event_id,
            )
            .execute()
        )

    except Exception as error:
        if (
            getattr(
                getattr(
                    error,
                    "resp",
                    None,
                ),
                "status",
                None,
            )
            == 404
        ):
            return None

        raise

    if "title" in changes:
        event["summary"] = (
            changes["title"]
        )

    if any(
        field in changes
        for field in (
            "date",
            "time",
            "end_time",
            "duration_minutes",
        )
    ):
        if (
            "dateTime"
            not in event.get(
                "start",
                {},
            )
        ):
            raise ValueError(
                "All-day events must be edited in Google Calendar."
            )

        old_start = _parse_google_datetime(
            event["start"]["dateTime"]
        )

        old_end = _parse_google_datetime(
            event["end"]["dateTime"]
        )

        date = changes.get(
            "date",
            old_start.strftime(
                "%Y-%m-%d"
            ),
        )

        time = changes.get(
            "time",
            old_start.strftime(
                "%-I:%M %p"
            ),
        )

        new_start = _local_datetime(
            date,
            time,
        )

        if "end_time" in changes:
            new_end = _local_datetime(
                date,
                changes["end_time"],
            )

        elif "duration_minutes" in changes:
            if (
                changes["duration_minutes"]
                <= 0
            ):
                raise ValueError(
                    "duration_minutes must be positive."
                )

            new_end = (
                new_start
                + timedelta(
                    minutes=changes[
                        "duration_minutes"
                    ]
                )
            )

        else:
            new_end = (
                new_start
                + (old_end - old_start)
            )

        if new_end <= new_start:
            raise ValueError(
                "The event end time must be after its start time."
            )

        event["start"] = {
            "dateTime": new_start.isoformat()
        }

        event["end"] = {
            "dateTime": new_end.isoformat()
        }

    updated = (
        service.events()
        .update(
            calendarId=PRIMARY_CALENDAR_ID,
            eventId=event_id,
            body=event,
        )
        .execute()
    )

    result = _event_to_dict(
        updated
    )

    result["calendar_id"] = (
        PRIMARY_CALENDAR_ID
    )

    result["source"] = "primary"

    return result