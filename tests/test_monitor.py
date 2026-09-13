from src.runtime import monitor


def test_monitor_cycle_runs_every_stage(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "sync_gmail_emails",
        lambda limit: [{"id": "email-1"}],
    )
    monkeypatch.setattr(
        monitor,
        "sync_calendar_events",
        lambda: [{"id": "event-1"}],
    )
    monkeypatch.setattr(
        monitor,
        "process_new_emails",
        lambda: {"processed": 1, "failed": 0},
    )
    monkeypatch.setattr(
        monitor,
        "process_new_calendar_events",
        lambda: {"processed": 1, "failed": 0},
    )
    monkeypatch.setattr(
        monitor,
        "refresh_calendar_priorities",
        lambda: {"updated": 1, "errors": []},
    )

    result = monitor.run_monitor_cycle()

    assert result["sync"]["gmail"] == {
        "success": True,
        "count": 1,
        "error": None,
    }
    assert result["processing"]["emails"]["result"][
        "processed"
    ] == 1
    assert result["priority_refresh"]["updated"] == 1


def test_one_broken_integration_does_not_stop_the_cycle(
    monkeypatch,
):
    def broken_gmail(limit):
        raise RuntimeError("Gmail token expired")

    monkeypatch.setattr(
        monitor,
        "sync_gmail_emails",
        broken_gmail,
    )
    monkeypatch.setattr(
        monitor,
        "sync_calendar_events",
        lambda: [{"id": "event-1"}],
    )
    monkeypatch.setattr(
        monitor,
        "process_new_emails",
        lambda: {"processed": 0, "failed": 0},
    )
    monkeypatch.setattr(
        monitor,
        "process_new_calendar_events",
        lambda: {"processed": 1, "failed": 0},
    )
    monkeypatch.setattr(
        monitor,
        "refresh_calendar_priorities",
        lambda: {"updated": 0, "errors": []},
    )

    result = monitor.run_monitor_cycle()

    assert result["sync"]["gmail"]["success"] is False
    assert "token expired" in result["sync"]["gmail"]["error"]
    assert result["sync"]["calendar"]["success"] is True
    assert result["processing"]["calendar"]["success"] is True