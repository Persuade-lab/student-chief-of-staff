from src.notifications import notifier
from src.storage.state import (
    get_runtime_status,
    record_monitor_cycle,
)


def test_monitor_state_records_success_and_error():
    record_monitor_cycle(
        {
            "sync": {
                "gmail": {
                    "success": True,
                    "count": 3,
                    "error": None,
                },
                "calendar": {
                    "success": False,
                    "count": 0,
                    "error": "Calendar is unavailable",
                },
            },
            "processing": {
                "emails": {
                    "success": True,
                    "result": {"processed": 1},
                    "error": None,
                },
                "calendar": {
                    "success": False,
                    "result": None,
                    "error": "Calendar process failed",
                },
            },
            "priority_refresh": {
                "success": True,
                "updated": 0,
            },
        }
    )

    status = get_runtime_status()

    assert status["last_gmail_sync"]["count"] == 3
    assert status["last_calendar_sync"] is None
    assert status["last_error"]["source"] == "calendar_processing"


def test_identical_urgent_notification_is_only_delivered_once(
    monkeypatch,
):
    delivered = []

    monkeypatch.setattr(
        notifier,
        "notify",
        lambda **kwargs: delivered.append(kwargs) or True,
    )

    item = {
        "id": "email-1",
        "subject": "Assignment due tomorrow",
    }

    analysis = {
        "action_type": "notify",
        "priority": "urgent",
        "summary": "Submit the assignment tomorrow.",
    }

    assert notifier.notify_from_analysis(item, analysis) is True
    assert notifier.notify_from_analysis(item, analysis) is False
    assert len(delivered) == 1


def test_high_priority_does_not_interrupt_user(
    monkeypatch,
):
    delivered = []

    monkeypatch.setattr(
        notifier,
        "notify",
        lambda **kwargs: delivered.append(kwargs) or True,
    )

    item = {
        "id": "email-2",
        "subject": "Important opportunity",
    }

    analysis = {
        "action_type": "notify",
        "priority": "high",
        "summary": "Review this opportunity soon.",
    }

    assert notifier.notify_from_analysis(item, analysis) is False
    assert delivered == []


def test_non_notify_action_does_not_interrupt_user(
    monkeypatch,
):
    delivered = []

    monkeypatch.setattr(
        notifier,
        "notify",
        lambda **kwargs: delivered.append(kwargs) or True,
    )

    item = {
        "id": "email-3",
        "subject": "Routine message",
    }

    analysis = {
        "action_type": "none",
        "priority": "urgent",
        "summary": "Routine information.",
    }

    assert notifier.notify_from_analysis(item, analysis) is False
    assert delivered == []