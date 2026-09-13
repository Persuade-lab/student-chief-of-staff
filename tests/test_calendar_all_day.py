"""Regression tests for all-day calendar items."""

from src.integrations import calendar


def test_all_day_event_does_not_block_free_time(monkeypatch):
    monkeypatch.setattr(
        calendar,
        "_get_events_for_date",
        lambda date: [
            {
                "id": "deadline-1",
                "title": "HW1 due",
                "date": date,
                "time": "12:00 AM",
                "all_day": 1,
            }
        ],
    )

    slots = calendar._get_free_slots(
        date="2026-09-13",
        duration_minutes=120,
        start_time="2:00 PM",
        end_time="6:00 PM",
    )

    assert slots
    assert slots[0]["start_time"] == "2:00 PM"
    assert slots[0]["end_time"] == "6:00 PM"


def test_all_day_event_does_not_count_as_conflict(monkeypatch):
    monkeypatch.setattr(
        calendar,
        "_get_events_for_date",
        lambda date: [
            {
                "id": "deadline-1",
                "title": "Canvas deadline",
                "date": date,
                "time": "12:00 AM",
                "all_day": True,
            }
        ],
    )

    conflicts = calendar._conflicts_for_interval(
        "2026-09-13",
        start=14 * 60,
        end=16 * 60,
    )

    assert conflicts == []
