"""Native notification handling with persistence-backed deduplication."""

from __future__ import annotations

from hashlib import sha256
import platform
import subprocess
from typing import Any

from src.storage.database import claim_notification

import os
import platform
import shutil
import subprocess
from urllib.parse import urlencode


URGENT_PRIORITY = "urgent"

APP_URL = os.environ.get(
    "APP_URL",
    "http://localhost:8501",
).rstrip("/")


def _escape_applescript(value: str) -> str:
    """
    Escape text before inserting it into an AppleScript string.
    """

    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
    )

def _build_attention_url(
    source_type: str,
    item_id: str,
) -> str:
    """Build a deep link to the item's attention view."""

    query = urlencode(
        {
            "attention_type": source_type,
            "attention_id": item_id,
        }
    )

    return f"{APP_URL}/?{query}"


def _send_macos_notification(
    title: str,
    message: str,
) -> bool:
    """
    Deliver a native macOS Notification Center alert.

    Returns True when osascript executes successfully.
    """

    safe_title = _escape_applescript(title)
    safe_message = _escape_applescript(message)

    script = (
        f'display notification "{safe_message}" '
        f'with title "{safe_title}" '
        f'sound name "Glass"'
    )

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
        )

        return result.returncode == 0

    except OSError:
        return False


def _send_clickable_macos_notification(
    title: str,
    message: str,
    open_url: str,
) -> bool:
    """
    Send a clickable macOS notification with terminal-notifier.

    Returns False when terminal-notifier is unavailable or delivery fails,
    allowing the caller to fall back to osascript.
    """

    executable = shutil.which("terminal-notifier")

    if executable is None:
        return False

    try:
        result = subprocess.run(
            [
                executable,
                "-title",
                title,
                "-message",
                message,
                "-sound",
                "Glass",
                "-open",
                open_url,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        return result.returncode == 0

    except OSError:
        return False

def notify(
    title: str,
    message: str,
    priority: str = "medium",
    open_url: str | None = None,
) -> bool:
    """
    Deliver an interruptive notification.

    Only urgent notifications should normally reach this function.
    """

    priority = priority.strip().lower()

    print(
        f"[NOTIFICATION] [{priority.upper()}] "
        f"{title}: {message}"
    )

    if platform.system() == "Darwin":

        notification_title = (
            f"🚨 Student Chief of Staff — {title}"
        )

        if open_url:
            delivered = _send_clickable_macos_notification(
                title=notification_title,
                message=message,
                open_url=open_url,
            )

            if delivered:
                return True

        return _send_macos_notification(
            title=notification_title,
            message=message,
        )

    # Terminal fallback for non-macOS development environments.
    return True


def _notification_identity(
    item: dict[str, Any],
    analysis: dict[str, Any],
) -> tuple[str, str, str]:
    """
    Build the persistent identity used to suppress duplicate alerts.
    """

    source_type = (
        "email"
        if "subject" in item
        else "calendar_event"
    )

    item_id = str(item.get("id") or "")

    if not item_id:
        raise ValueError(
            "Cannot deduplicate a notification without an item id."
        )

    fingerprint_source = "|".join(
        (
            str(analysis.get("priority", "medium")),
            str(analysis.get("summary", "")),
            str(analysis.get("action_type", "")),
        )
    )

    notification_key = sha256(
        fingerprint_source.encode("utf-8")
    ).hexdigest()

    return source_type, item_id, notification_key


def notify_from_analysis(
    item: dict[str, Any],
    analysis: dict[str, Any],
) -> bool:
    """
    Interrupt the student only for an urgent item.

    The item must:
    1. have a planned notify action,
    2. have final priority == urgent,
    3. not already have delivered the same alert.
    """

    if analysis.get("action_type") != "notify":
        return False

    priority = str(
        analysis.get("priority", "medium")
    ).strip().lower()

    # The Chief of Staff monitors everything,
    # but only urgent information interrupts the student.
    if priority != URGENT_PRIORITY:
        return False

    source_type, item_id, notification_key = (
        _notification_identity(
            item,
            analysis,
        )
    )

    if not claim_notification(
        source_type,
        item_id,
        notification_key,
    ):
        return False

    title = (
        item.get("title")
        or item.get("subject")
        or "Urgent item"
    )

    attention_url = _build_attention_url(
        source_type=source_type,
        item_id=item_id,
    )

    return notify(
        title=str(title),
        message=str(
            analysis.get(
                "summary",
                "This item needs your attention.",
            )
        ),
        priority=priority,
        open_url=attention_url,
    )