"""
Tests for src/integrations/calendar.py.

The production calendar integration uses SQLite for local storage
and can optionally synchronize with Google Calendar.

These tests:
    - use mock_calendar.json as predictable test data
    - seed a temporary SQLite database for each test
    - never modify the real database
    - never contact Google Calendar

Run with:

    PYTHONPATH=. pytest tests/test_calendar.py -v
"""

import json
from pathlib import Path

import pytest

from src.integrations import calendar
from src.storage import database


REAL_DATA_FILE = (
    Path(__file__).parent.parent
    / "src"
    / "data"
    / "mock_calendar.json"
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def mock_calendar_data():
    """
    Load the mock calendar data into memory.
    """

    return json.loads(
        REAL_DATA_FILE.read_text(encoding="utf-8")
    )


@pytest.fixture
def test_database(
    tmp_path,
    monkeypatch,
):
    """
    Give each test its own temporary SQLite database.

    Also force calendar.py to use the local database backend
    rather than Google Calendar.
    """

    test_db = tmp_path / "test_student_chief_of_staff.db"

    monkeypatch.setattr(
        database,
        "DATABASE_FILE",
        test_db,
    )

    monkeypatch.setenv(
        "CALENDAR_BACKEND",
        "database",
    )

    database.initialize_database()

    return test_db


@pytest.fixture
def seeded_calendar(
    test_database,
    mock_calendar_data,
):
    """
    Seed the temporary database with mock calendar events.
    """

    database.save_calendar_events(
        mock_calendar_data
    )

    return mock_calendar_data


# ============================================================
# INTERNAL HELPERS
# ============================================================

class TestTimeConversion:

    def test_time_to_minutes_am(self):
        assert (
            calendar._time_to_minutes("9:00 AM")
            == 9 * 60
        )

    def test_time_to_minutes_pm(self):
        assert (
            calendar._time_to_minutes("1:00 PM")
            == 13 * 60
        )

    def test_time_to_minutes_noon(self):
        assert (
            calendar._time_to_minutes("12:00 PM")
            == 12 * 60
        )

    def test_time_to_minutes_midnight(self):
        assert (
            calendar._time_to_minutes("12:00 AM")
            == 0
        )

    def test_minutes_to_time_round_trip(self):

        for original in [
            "9:00 AM",
            "1:00 PM",
            "11:45 PM",
            "12:00 PM",
            "12:00 AM",
        ]:
            minutes = calendar._time_to_minutes(
                original
            )

            assert (
                calendar._minutes_to_time(minutes)
                == original
            )


class TestEventInterval:

    def test_uses_end_time_when_present(self):

        event = {
            "time": "10:00 AM",
            "end_time": "11:30 AM",
        }

        assert (
            calendar._event_interval(event)
            == (600, 690)
        )

    def test_uses_duration_when_no_end_time(self):

        event = {
            "time": "9:00 AM",
            "duration_minutes": 90,
        }

        start, end = calendar._event_interval(
            event
        )

        assert end - start == 90

    def test_falls_back_to_default_duration(self):

        event = {
            "time": "9:00 AM",
        }

        start, end = calendar._event_interval(
            event
        )

        assert (
            end - start
            == calendar.DEFAULT_DURATION_MINUTES
        )


class TestIntervalsOverlap:

    def test_no_overlap_back_to_back(self):

        assert (
            calendar._intervals_overlap(
                720,
                735,
                750,
                800,
            )
            is False
        )

    def test_true_overlap(self):

        assert (
            calendar._intervals_overlap(
                600,
                690,
                630,
                700,
            )
            is True
        )

    def test_identical_intervals_overlap(self):

        assert (
            calendar._intervals_overlap(
                600,
                660,
                600,
                660,
            )
            is True
        )

    def test_touching_edges_do_not_overlap(self):

        assert (
            calendar._intervals_overlap(
                600,
                660,
                660,
                720,
            )
            is False
        )


# ============================================================
# check_calendar
# ============================================================

class TestCheckCalendar:

    def test_no_conflicts_in_real_schedule(
        self,
        seeded_calendar,
    ):
        result = calendar.check_calendar()

        assert result == "No calendar conflicts."

    def test_detects_real_conflict(
        self,
        seeded_calendar,
    ):
        database.save_calendar_event(
            {
                "id": "conflict_1",
                "title": "Club Meeting",
                "date": "2026-08-24",
                "time": "10:30 AM",
                "end_time": "11:00 AM",
            }
        )

        result = calendar.check_calendar()

        assert "CIS 2400" in result
        assert "Club Meeting" in result

    def test_close_but_non_overlapping_events_not_flagged(
        self,
        seeded_calendar,
    ):
        database.save_calendar_event(
            {
                "id": "close_1",
                "title": "Quick Errand",
                "date": "2026-08-24",
                "time": "11:30 AM",
                "end_time": "11:45 AM",
            }
        )

        result = calendar.check_calendar()

        assert "Quick Errand" not in result


# ============================================================
# get_schedule
# ============================================================

class TestGetSchedule:

    def test_returns_all_events_without_date(
        self,
        seeded_calendar,
    ):
        result = calendar.get_schedule()

        assert len(result) == len(
            seeded_calendar
        )

    def test_filters_by_date(
        self,
        seeded_calendar,
    ):
        result = calendar.get_schedule(
            date="2026-08-25"
        )

        assert len(result) == 3

        titles = {
            event["title"]
            for event in result
        }

        assert titles == {
            "Benjamin Franklin Seminar",
            "Lunch with Friend",
            "Computer Engineering Lab",
        }

    def test_empty_for_date_with_no_events(
        self,
        seeded_calendar,
    ):
        result = calendar.get_schedule(
            date="2026-09-01"
        )

        assert result == []


# ============================================================
# create_event
# ============================================================

class TestCreateEvent:

    def test_creates_and_persists_event(
        self,
        seeded_calendar,
    ):
        result = calendar.create_event(
            title="Advising Meeting",
            date="2026-08-28",
            time="2:00 PM",
            end_time="2:30 PM",
        )

        assert "Advising Meeting" in result
        assert "id:" in result

        events = calendar.get_schedule(
            date="2026-08-28"
        )

        assert len(events) == 1
        assert (
            events[0]["title"]
            == "Advising Meeting"
        )


# ============================================================
# schedule_event_in_free_time
# ============================================================

class TestScheduleInFreeTime:

    def test_finds_and_books_a_real_gap(
        self,
        seeded_calendar,
    ):
        result = (
            calendar.schedule_event_in_free_time(
                title="Office Hours",
                date="2026-08-24",
                duration_minutes=60,
            )
        )

        assert "Office Hours" in result
        assert "No " not in result

        events = calendar.get_schedule(
            date="2026-08-24"
        )

        titles = [
            event["title"]
            for event in events
        ]

        assert "Office Hours" in titles

    def test_new_event_does_not_conflict_with_existing(
        self,
        seeded_calendar,
    ):
        calendar.schedule_event_in_free_time(
            title="Office Hours",
            date="2026-08-24",
            duration_minutes=60,
        )

        result = calendar.check_calendar()

        assert result == "No calendar conflicts."

    def test_returns_message_when_no_slot_fits(
        self,
        seeded_calendar,
    ):
        result = (
            calendar.schedule_event_in_free_time(
                title="All Day Retreat",
                date="2026-08-24",
                duration_minutes=20 * 60,
            )
        )

        assert (
            "No" in result
            and "free slot" in result
        )


# ============================================================
# update_the_event
# ============================================================

class TestUpdateEvent:

    def test_updates_title(
        self,
        seeded_calendar,
    ):
        result = calendar.update_the_event(
            event_id="event_001",
            title="CIS 2400 - Room Change",
        )

        assert (
            "CIS 2400 - Room Change"
            in result
        )

        updated = calendar.get_schedule(
            date="2026-08-24"
        )

        titles = [
            event["title"]
            for event in updated
        ]

        assert (
            "CIS 2400 - Room Change"
            in titles
        )

    def test_no_changes_given(
        self,
        seeded_calendar,
    ):
        result = calendar.update_the_event(
            event_id="event_001"
        )

        assert result == "No changes given."

    def test_unknown_id_returns_error(
        self,
        seeded_calendar,
    ):
        result = calendar.update_the_event(
            event_id="does-not-exist",
            title="Ghost Event",
        )

        assert "No event found" in result


# ============================================================
# delete_event
# ============================================================

class TestDeleteEvent:

    def test_deletes_existing_event(
        self,
        seeded_calendar,
    ):
        result = calendar.delete_event(
            "event_010"
        )

        assert result == "Event removed."

        assert (
            calendar.get_schedule(
                date="2026-08-27"
            )
            == []
        )

    def test_unknown_id_returns_error(
        self,
        seeded_calendar,
    ):
        result = calendar.delete_event(
            "does-not-exist"
        )

        assert "No event found" in result


# ============================================================
# reschedule_event
# ============================================================

class TestRescheduleEvent:

    def test_moves_event_to_new_time(
        self,
        seeded_calendar,
    ):
        result = calendar.reschedule_event(
            event_id="event_003",
            new_time="6:00 PM",
        )

        assert "6:00 PM" in result

        events = calendar.get_schedule(
            date="2026-08-24"
        )

        study = [
            event
            for event in events
            if event["id"] == "event_003"
        ][0]

        assert study["time"] == "6:00 PM"

    def test_moves_event_to_new_date(
        self,
        seeded_calendar,
    ):
        calendar.reschedule_event(
            event_id="event_003",
            new_date="2026-08-30",
        )

        moved = calendar.get_schedule(
            date="2026-08-30"
        )

        assert len(moved) == 1
        assert moved[0]["id"] == "event_003"

    def test_no_changes_given(
        self,
        seeded_calendar,
    ):
        result = calendar.reschedule_event(
            event_id="event_003"
        )

        assert "No changes given" in result

    def test_unknown_id_returns_error(
        self,
        seeded_calendar,
    ):
        result = calendar.reschedule_event(
            event_id="does-not-exist",
            new_time="9:00 AM",
        )

        assert "No event found" in result