"""Streamlit interface for the Student Chief of Staff."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


# Make `src` imports work when launched with:
#   streamlit run streamlit_app.py
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.chief_of_staff import reset_agent, run_agent
from src.integrations.calendar import add_event, suggest_free_slots
from src.runtime.orchestrator import RuntimeOrchestrator
from src.storage.database import (
    get_calendar_analysis,
    get_calendar_event,
    get_calendar_events,
    initialize_database,
)
from src.storage.memory import get_profile
from src.storage.state import get_runtime_status


LOCAL_TIMEZONE = "America/New_York"


st.set_page_config(
    page_title="Student Chief of Staff",
    page_icon="🎓",
    layout="wide",
)


st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.7rem;
        padding-bottom: 2rem;
    }

    .status-card {
        border: 1px solid rgba(128,128,128,.22);
        border-radius: 14px;
        padding: 14px 16px;
        min-height: 92px;
    }

    .event-card {
        border-left: 4px solid #7c3aed;
        background: rgba(124,58,237,.06);
        border-radius: 8px;
        padding: 10px 12px;
        margin-bottom: 8px;
    }

    .muted {
        opacity: .72;
        font-size: .92rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def start_runtime() -> RuntimeOrchestrator:
    """Start the monitor only once for the life of the Streamlit server."""

    initialize_database()

    runtime = RuntimeOrchestrator()
    runtime.start()

    return runtime


def _now() -> datetime:
    return datetime.now(ZoneInfo(LOCAL_TIMEZONE))


def _event_time(event: dict) -> str:
    if bool(event.get("all_day")):
        return "All day"

    start = event.get("time") or ""
    end = event.get("end_time")

    if end:
        return f"{start} – {end}"

    duration = event.get("duration_minutes")

    if duration:
        return f"{start} · {duration} min"

    return start or "Time not set"


def _upcoming_events(days: int = 7) -> list[dict]:
    today = _now().date()
    last = today + timedelta(days=days)

    events = get_calendar_events()

    result = []

    for event in events:
        try:
            event_date = datetime.strptime(
                event["date"],
                "%Y-%m-%d",
            ).date()

        except (KeyError, TypeError, ValueError):
            continue

        if today <= event_date <= last:
            result.append(event)

    return result

def _clean_assignment_title(title: str) -> str:
    """
    Normalize a Canvas-style assignment title.

    Example:
    "Canvas HW1 [BAN_ECON-0100-001 202630]"
    -> "Canvas HW1"
    """
    return title.split(" [", 1)[0].strip()


def _find_existing_work_session(
    assignment_title: str,
    date: str,
) -> dict | None:
    """
    Find an existing timed work session for this assignment.
    """

    clean_title = _clean_assignment_title(
        assignment_title
    ).lower()

    expected_prefixes = (
        "work session:",
        "study:",
        "review:",
        "prep:",
    )

    for calendar_event in get_calendar_events(date):
        if calendar_event.get("all_day"):
            continue

        event_title = (
            calendar_event.get("title") or ""
        ).strip()

        lowered = event_title.lower()

        matching_prefix = next(
            (
                prefix
                for prefix in expected_prefixes
                if lowered.startswith(prefix)
            ),
            None,
        )

        if matching_prefix is None:
            continue

        session_subject = lowered[
            len(matching_prefix):
        ].strip()

        if session_subject == clean_title:
            return calendar_event

    return None


def _render_attention_view(
    attention_type: str,
    attention_id: str,
) -> bool:
    if attention_type != "calendar_event":
        return False

    event = get_calendar_event(attention_id)

    if event is None:
        st.error("I couldn't find this calendar event.")
        return True

    analysis = get_calendar_analysis(attention_id)

    event_title = event.get(
        "title",
        "Calendar event",
    )

    event_date = datetime.strptime(
        event["date"],
        "%Y-%m-%d",
    ).date()

    today = _now().date()

    st.title("⚠️ Needs your attention")

    st.subheader(event_title)

    if event_date == today:
        st.write("**Due today**")

    elif event_date == today + timedelta(days=1):
        st.write("**Due tomorrow**")

    elif event_date < today:
        st.write("**Deadline has passed**")

    else:
        st.write(
            "**Due "
            + event_date.strftime(
                "%A, %B %-d"
            )
            + "**"
        )

    if event.get("all_day"):
        st.caption("All-day deadline")

    else:
        event_time = event.get("time")

        if event_time:
            st.caption(
                f"Deadline time: {event_time}"
            )

    if analysis:
        summary = analysis.get("summary")

        if summary:
            st.info(summary)

        reason = analysis.get("reason")

        if reason:
            st.caption(
                f"Why I'm alerting you: {reason}"
            )

    # Only recommend work time for deadlines
    # that have not already passed.
    if event_date >= today:
        existing_session = (
            _find_existing_work_session(
                assignment_title=event_title,
                date=event["date"],
            )
        )

        st.divider()
        st.subheader("Suggested plan")

        # -------------------------------------------------
        # A matching study/work session already exists.
        # -------------------------------------------------
        if existing_session:
            st.success(
                "✓ You already have time scheduled "
                "for this assignment."
            )

            st.write(
                f"**{existing_session['title']}**"
            )

            existing_start = (
                existing_session.get("time")
            )

            existing_end = (
                existing_session.get("end_time")
            )

            if existing_start and existing_end:
                st.write(
                    f"{existing_start} – "
                    f"{existing_end}"
                )

            elif existing_start:
                st.write(existing_start)

            st.caption(
                "✓ This time is already on your calendar."
            )

        # -------------------------------------------------
        # No matching work session exists yet.
        # Generate conflict-free recommendations.
        # -------------------------------------------------
        else:
            suggestions = suggest_free_slots(
                date=event["date"],
                duration_minutes=90,
            )

            if not suggestions:
                st.warning(
                    "I couldn't find a 90-minute free "
                    "block on your calendar."
                )

            else:
                slot_key = (
                    f"attention_slot_{attention_id}"
                )

                scheduled_key = (
                    f"scheduled_attention_{attention_id}"
                )

                if slot_key not in st.session_state:
                    st.session_state[slot_key] = 0

                slot_index = min(
                    st.session_state[slot_key],
                    len(suggestions) - 1,
                )

                st.session_state[
                    slot_key
                ] = slot_index

                suggestion = suggestions[
                    slot_index
                ]

                st.success(
                    f"{suggestion['start_time']} – "
                    f"{suggestion['end_time']}"
                )

                st.caption(
                    "✓ No calendar conflicts\n\n"
                    "✓ 90-minute work session"
                )

                scheduled_event_id = (
                    st.session_state.get(
                        scheduled_key
                    )
                )

                if scheduled_event_id:
                    st.success(
                        "This work session has "
                        "been scheduled."
                    )

                else:
                    left, right = st.columns(2)

                    with left:
                        if st.button(
                            "Schedule this",
                            type="primary",
                            use_container_width=True,
                        ):
                            clean_title = (
                                _clean_assignment_title(
                                    event_title
                                )
                            )

                            work_title = (
                                "Work Session: "
                                f"{clean_title}"
                            )

                            try:
                                created = add_event(
                                    title=work_title,
                                    date=suggestion[
                                        "date"
                                    ],
                                    time=suggestion[
                                        "start_time"
                                    ],
                                    end_time=suggestion[
                                        "end_time"
                                    ],
                                    duration_minutes=(
                                        suggestion[
                                            "duration_minutes"
                                        ]
                                    ),
                                )

                            except Exception as error:
                                st.error(
                                    "I couldn't schedule "
                                    "this work session: "
                                    f"{error}"
                                )

                            else:
                                st.session_state[
                                    scheduled_key
                                ] = created["id"]

                                st.rerun()

                    with right:
                        if st.button(
                            "Find another time",
                            use_container_width=True,
                        ):
                            next_index = (
                                slot_index + 1
                            ) % len(suggestions)

                            st.session_state[
                                slot_key
                            ] = next_index

                            st.rerun()

    st.divider()

    if st.button(
        "Back to dashboard",
        use_container_width=True,
    ):
        st.query_params.clear()
        st.rerun()

    return True

runtime = start_runtime()


if "messages" not in st.session_state:
    st.session_state.messages = []


attention_type = st.query_params.get(
    "attention_type"
)

attention_id = st.query_params.get(
    "attention_id"
)


if attention_type and attention_id:
    if _render_attention_view(
        attention_type=attention_type,
        attention_id=attention_id,
    ):
        st.stop()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.title("🎓 Chief of Staff")
    st.caption("Your student operations dashboard")

    page = st.radio(
        "Navigate",
        [
            "Chat",
            "Dashboard",
            "Calendar",
            "Preferences",
            "System",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    status = get_runtime_status()
    last_error = status.get("last_error")

    if last_error:
        st.error("Monitor needs attention")
    else:
        st.success("Monitor healthy")

    if st.button(
        "New conversation",
        use_container_width=True,
    ):
        reset_agent()
        st.session_state.messages = []
        st.rerun()


# ============================================================
# CHAT
# ============================================================

if page == "Chat":
    st.title("Ask your Chief of Staff")

    st.caption(
        "Ask about your schedule, create study blocks, "
        "check monitoring status, or manage opportunity "
        "preferences."
    )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input(
        "e.g. What do I have tomorrow, and where can I "
        "fit 2 hours of CIS 1210?"
    )

    if prompt:
        st.session_state.messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Working on it..."):
                try:
                    response = str(
                        run_agent(prompt)
                    )

                except Exception as error:
                    response = (
                        "I hit an error while handling "
                        f"that request: `{error}`"
                    )

                st.markdown(response)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response,
            }
        )


# ============================================================
# DASHBOARD
# ============================================================

elif page == "Dashboard":
    now = _now()

    st.title("Dashboard")

    st.caption(
        now.strftime(
            "%A, %B %d, %Y · %I:%M %p"
        )
    )

    monitor = get_runtime_status()
    upcoming = _upcoming_events(7)

    today_events = [
        event
        for event in upcoming
        if event.get("date")
        == now.date().isoformat()
    ]

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Today",
            len(today_events),
            "calendar items",
        )

    with c2:
        st.metric(
            "Next 7 days",
            len(upcoming),
            "calendar items",
        )

    with c3:
        scheduler = (
            monitor.get("scheduler_status")
            or {}
        )

        st.metric(
            "Background monitor",
            (
                "Running"
                if scheduler.get("running")
                else "Idle"
            ),
        )

    with c4:
        st.metric(
            "Last error",
            (
                "None"
                if not monitor.get("last_error")
                else "Needs attention"
            ),
        )

    st.subheader("Today")

    if not today_events:
        st.info(
            "Nothing is currently scheduled "
            "for today."
        )

    else:
        for event in today_events:
            st.markdown(
                f"""
                <div class="event-card">
                    <strong>
                        {event.get("title", "Untitled event")}
                    </strong><br/>
                    <span class="muted">
                        {_event_time(event)}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.subheader("Coming up")

    if not upcoming:
        st.info(
            "No calendar items in the next 7 days."
        )

    else:
        for event in upcoming[:12]:
            st.write(
                f"**{event.get('date', '')}** · "
                f"{_event_time(event)} · "
                f"{event.get('title', 'Untitled event')}"
            )


# ============================================================
# CALENDAR
# ============================================================

elif page == "Calendar":
    st.title("Calendar")

    selected = st.date_input(
        "Choose a date",
        value=_now().date(),
    )

    events = get_calendar_events(
        selected.isoformat()
    )

    if not events:
        st.info("No events on this date.")

    else:
        all_day = [
            event
            for event in events
            if bool(event.get("all_day"))
        ]

        timed = [
            event
            for event in events
            if not bool(event.get("all_day"))
        ]

        if all_day:
            st.subheader("All-day items")

            for event in all_day:
                st.markdown(
                    f"- **{event.get('title', 'Untitled event')}**"
                )

        if timed:
            st.subheader("Timed events")

            for event in timed:
                st.markdown(
                    f"""
                    <div class="event-card">
                        <strong>
                            {_event_time(event)}
                        </strong><br/>
                        {event.get("title", "Untitled event")}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ============================================================
# PREFERENCES
# ============================================================

elif page == "Preferences":
    st.title("Opportunity preferences")

    profile = get_profile()

    st.metric(
        "Minimum match score",
        f"{profile.get('minimum_match_score', 60)}/100",
    )

    left, right = st.columns(2)

    with left:
        st.subheader("Target roles")

        roles = profile.get(
            "target_roles"
        ) or []

        st.write(
            "\n".join(
                f"- {item}"
                for item in roles
            )
            or "None saved"
        )

        st.subheader("Skills")

        skills = profile.get(
            "skills"
        ) or []

        st.write(
            "\n".join(
                f"- {item}"
                for item in skills
            )
            or "None saved"
        )

    with right:
        st.subheader("Interests")

        interests = profile.get(
            "interests"
        ) or []

        st.write(
            "\n".join(
                f"- {item}"
                for item in interests
            )
            or "None saved"
        )

        st.subheader("Locations")

        locations = profile.get(
            "locations"
        ) or []

        st.write(
            "\n".join(
                f"- {item}"
                for item in locations
            )
            or "None saved"
        )

    st.caption(
        "To change these, use Chat. "
        "The agent will update the same "
        "persistent profile used by the "
        "opportunity matcher."
    )


# ============================================================
# SYSTEM
# ============================================================

elif page == "System":
    st.title("System status")

    status = get_runtime_status()

    scheduler = (
        status.get("scheduler_status")
        or {}
    )

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Background monitor")

        st.json(
            {
                "running": scheduler.get(
                    "running"
                ),
                "interval_seconds": scheduler.get(
                    "interval_seconds"
                ),
                "last_cycle_started_at": scheduler.get(
                    "last_cycle_started_at"
                ),
                "last_cycle_finished_at": scheduler.get(
                    "last_cycle_finished_at"
                ),
            }
        )

    with c2:
        st.subheader("Latest activity")

        st.json(
            {
                "last_gmail_sync": status.get(
                    "last_gmail_sync"
                ),
                "last_calendar_sync": status.get(
                    "last_calendar_sync"
                ),
                "last_processing_run": status.get(
                    "last_processing_run"
                ),
                "last_priority_refresh": status.get(
                    "last_priority_refresh"
                ),
                "last_error": status.get(
                    "last_error"
                ),
            }
        )

    st.caption(
        "The Streamlit server starts the same "
        "RuntimeOrchestrator used by the terminal app. "
        "Do not run the terminal UI and Streamlit UI "
        "at the same time."
    )