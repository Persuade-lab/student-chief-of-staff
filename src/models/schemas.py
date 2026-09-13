"""
Shared data models for the Student Chief of Staff.
"""

from dataclasses import dataclass


# ============================================================
# EMAIL
# ============================================================

@dataclass
class EmailAnalysis:
    email_id: str
    category: str
    priority: str
    action_required: bool
    action_type: str | None
    summary: str
    reason: str
    deadline: str | None = None


# ============================================================
# CALENDAR
# ============================================================

@dataclass
class CalendarEvent:
    id: str
    title: str
    date: str
    time: str
    end_time: str | None
    duration_minutes: int | None
    all_day: bool
    calendar_id: str | None
    source: str | None


# ============================================================
# ACTIONS
# ============================================================

@dataclass
class PlannedAction:
    action_type: str
    description: str
    requires_confirmation: bool = True


# ============================================================
# NOTIFICATIONS
# ============================================================

@dataclass
class Notification:
    title: str
    message: str
    priority: str