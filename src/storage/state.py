"""Persistent runtime metadata for the background monitor."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.storage.database import (
    get_connection,
    initialize_database,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_state(key: str, value: Any) -> None:
    """Store a JSON-serializable runtime value."""

    initialize_database()
    connection = get_connection()

    connection.execute(
        """
        INSERT INTO runtime_state (
            key,
            value_json,
            updated_at
        )
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at
        """,
        (
            key,
            json.dumps(value, default=str),
            _now(),
        ),
    )

    connection.commit()
    connection.close()


def get_state(key: str, default: Any = None) -> Any:
    """Read one runtime value, returning default if it was never recorded."""

    initialize_database()
    connection = get_connection()

    row = connection.execute(
        """
        SELECT value_json
        FROM runtime_state
        WHERE key = ?
        """,
        (key,),
    ).fetchone()

    connection.close()

    if row is None:
        return default

    try:
        return json.loads(row["value_json"])
    except (TypeError, json.JSONDecodeError):
        return default


def get_runtime_status() -> dict[str, Any]:
    """Return the values useful for a CLI/UI status screen."""

    return {
        "last_gmail_sync": get_state("last_gmail_sync"),
        "last_calendar_sync": get_state("last_calendar_sync"),
        "last_processing_run": get_state(
            "last_processing_run"
        ),
        "last_priority_refresh": get_state(
            "last_priority_refresh"
        ),
        "last_error": get_state("last_error"),
        "scheduler_status": get_state(
            "scheduler_status",
            {"running": False},
        ),
    }


def record_monitor_cycle(cycle: dict[str, Any]) -> None:
    """
    Persist one monitor cycle's outcomes without letting state persistence
    affect the useful work of the cycle.
    """

    timestamp = _now()
    sync = cycle.get("sync", {})
    gmail = sync.get("gmail", {})
    calendar = sync.get("calendar", {})
    processing = cycle.get("processing", {})
    priority = cycle.get("priority_refresh", {})

    if gmail.get("success"):
        set_state(
            "last_gmail_sync",
            {
                "at": timestamp,
                "count": gmail.get("count", 0),
            },
        )

    if calendar.get("success"):
        set_state(
            "last_calendar_sync",
            {
                "at": timestamp,
                "count": calendar.get("count", 0),
            },
        )

    set_state(
        "last_processing_run",
        {
            "at": timestamp,
            "emails": processing.get("emails"),
            "calendar": processing.get("calendar"),
        },
    )

    set_state(
        "last_priority_refresh",
        {
            "at": timestamp,
            "result": priority,
        },
    )

    errors: list[dict[str, Any]] = []

    for source, result in (
        ("gmail", gmail),
        ("calendar", calendar),
        ("email_processing", processing.get("emails", {})),
        (
            "calendar_processing",
            processing.get("calendar", {}),
        ),
        ("priority_refresh", priority),
    ):
        error = result.get("error")

        if error:
            errors.append(
                {
                    "source": source,
                    "error": str(error),
                    "at": timestamp,
                }
            )

    set_state("last_error", errors[-1] if errors else None)