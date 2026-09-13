"""One safe monitoring cycle: sync, process, refresh, record status."""

from __future__ import annotations

from src.integrations.emails import sync_gmail_emails
from src.integrations.google_calendar import sync_calendar_events
from src.processing.processor import (
    process_new_emails,
    process_new_calendar_events,
    refresh_calendar_priorities,
)
from src.storage.database import initialize_database
from src.storage.state import record_monitor_cycle


DEFAULT_EMAIL_SYNC_LIMIT = 50


def sync_external_data() -> dict:
    """Synchronize Gmail and Calendar independently."""

    result = {
        "gmail": {
            "success": False,
            "count": 0,
            "error": None,
        },
        "calendar": {
            "success": False,
            "count": 0,
            "error": None,
        },
    }

    try:
        emails = sync_gmail_emails(
            limit=DEFAULT_EMAIL_SYNC_LIMIT
        )
        result["gmail"]["success"] = True
        result["gmail"]["count"] = len(emails)
    except Exception as error:
        result["gmail"]["error"] = str(error)

    try:
        events = sync_calendar_events()
        result["calendar"]["success"] = True
        result["calendar"]["count"] = len(events)
    except Exception as error:
        result["calendar"]["error"] = str(error)

    return result


def process_new_data() -> dict:
    """Process email and calendar records independently."""

    result = {
        "emails": {
            "success": False,
            "result": None,
            "error": None,
        },
        "calendar": {
            "success": False,
            "result": None,
            "error": None,
        },
    }

    try:
        result["emails"]["result"] = process_new_emails()
        result["emails"]["success"] = True
    except Exception as error:
        result["emails"]["error"] = str(error)

    try:
        result["calendar"]["result"] = (
            process_new_calendar_events()
        )
        result["calendar"]["success"] = True
    except Exception as error:
        result["calendar"]["error"] = str(error)

    return result


def run_monitor_cycle() -> dict:
    """
    Run one complete, fault-isolated monitor cycle.

    A failure in Gmail does not prevent Calendar processing, and a failure in
    either processing pipeline does not prevent priority refresh.
    """

    initialize_database()
    cycle = {
        "sync": sync_external_data(),
        "processing": process_new_data(),
    }

    try:
        cycle["priority_refresh"] = {
            "success": True,
            **refresh_calendar_priorities(),
        }
    except Exception as error:
        cycle["priority_refresh"] = {
            "success": False,
            "error": str(error),
        }

    try:
        record_monitor_cycle(cycle)
    except Exception as error:
        # Metadata must never make a successful cycle fail.
        cycle["state_error"] = str(error)

    return cycle