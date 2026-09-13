"""
Processing pipeline for the Student Chief of Staff.

This module coordinates:
- AI classification
- output validation
- action planning
- persistence
- processed-state updates

An item is marked as processed only after its analysis has been
successfully validated and saved.
"""

from typing import Any

from src.processing.classifier import (
    classify_email,
    classify_calendar_event,
)
from src.processing.prioritizer import (
    validate_priority,
    prioritize_with_deadline,
    prioritize_calendar_event,
)
from src.processing.planner import (
    plan_email_action,
    plan_calendar_action,
)

from src.storage.database import (
    get_unprocessed_emails,
    save_email_analysis,
    mark_email_processed,
    get_unprocessed_calendar_events,
    save_calendar_analysis,
    mark_calendar_event_processed,
    get_calendar_events,
    get_calendar_analysis,
)

from src.notifications.notifier import notify_from_analysis

from src.processing.opportunity_matcher import (
    evaluate_opportunity,
)


# ============================================================
# VALID CATEGORIES
# ============================================================

VALID_EMAIL_CATEGORIES = {
    "academic",
    "opportunity",
    "administrative",
    "announcement",
    "personal",
    "noise",
}


VALID_CALENDAR_CATEGORIES = {
    "assignment",
    "exam",
    "class",
    "meeting",
    "work",
    "personal",
    "event",
    "other",
}


# ============================================================
# SHARED VALIDATION
# ============================================================

def validate_action_required(
    action_required: Any,
) -> bool:
    if not isinstance(action_required, bool):
        raise ValueError(
            "Invalid action_required value returned by classifier: "
            f"{action_required!r}"
        )

    return action_required


def validate_summary(
    summary: Any,
) -> str:
    if not isinstance(summary, str):
        raise ValueError(
            f"Invalid summary returned by classifier: {summary!r}"
        )

    summary = summary.strip()

    if not summary:
        raise ValueError(
            "Classifier returned an empty summary."
        )

    return summary


def validate_reason(
    reason: Any,
) -> str:
    if not isinstance(reason, str):
        raise ValueError(
            f"Invalid reason returned by classifier: {reason!r}"
        )

    reason = reason.strip()

    if not reason:
        raise ValueError(
            "Classifier returned an empty reason."
        )

    return reason


# ============================================================
# EMAIL VALIDATION
# ============================================================

def validate_email_category(
    category: str | None,
) -> str:
    if category not in VALID_EMAIL_CATEGORIES:
        raise ValueError(
            f"Invalid email category returned by classifier: {category!r}"
        )

    return category


def validate_deadline(
    deadline: Any,
) -> str | None:
    if deadline is None:
        return None

    if not isinstance(deadline, str):
        raise ValueError(
            f"Invalid deadline returned by classifier: {deadline!r}"
        )

    deadline = deadline.strip()

    if not deadline:
        return None

    return deadline


def validate_email_analysis(
    analysis: Any,
) -> dict[str, Any]:
    if not isinstance(analysis, dict):
        raise ValueError(
            "Classifier must return a dictionary."
        )

    category = validate_email_category(
        analysis.get("category")
    )

    priority = validate_priority(
        analysis.get("priority")
    )

    action_required = validate_action_required(
        analysis.get("action_required")
    )

    summary = validate_summary(
        analysis.get("summary")
    )

    reason = validate_reason(
        analysis.get("reason")
    )

    deadline = validate_deadline(
        analysis.get("deadline")
    )

    return {
        "category": category,
        "priority": priority,
        "action_required": action_required,
        "summary": summary,
        "reason": reason,
        "deadline": deadline,
    }


# ============================================================
# CALENDAR VALIDATION
# ============================================================

def validate_calendar_category(
    category: str | None,
) -> str:
    if category not in VALID_CALENDAR_CATEGORIES:
        raise ValueError(
            f"Invalid calendar category returned by classifier: {category!r}"
        )

    return category


def validate_calendar_analysis(
    analysis: Any,
) -> dict[str, Any]:
    if not isinstance(analysis, dict):
        raise ValueError(
            "Classifier must return a dictionary."
        )

    category = validate_calendar_category(
        analysis.get("category")
    )

    priority = validate_priority(
        analysis.get("priority")
    )

    action_required = validate_action_required(
        analysis.get("action_required")
    )

    summary = validate_summary(
        analysis.get("summary")
    )

    reason = validate_reason(
        analysis.get("reason")
    )

    return {
        "category": category,
        "priority": priority,
        "action_required": action_required,
        "summary": summary,
        "reason": reason,
    }


# ============================================================
# EMAIL PROCESSING
# ============================================================

def process_email(
    email: dict[str, Any],
) -> dict[str, Any]:
    email_id = email.get("id")

    if not email_id:
        raise ValueError(
            "Cannot process an email without an id."
        )

    analysis = validate_email_analysis(
        classify_email(email)
    )

    analysis["priority"] = prioritize_with_deadline(
        base_priority=analysis["priority"],
        deadline=analysis["deadline"],
    )

    opportunity_match = None

    if analysis["category"] == "opportunity":
        opportunity_match = evaluate_opportunity(email)

    planned_action = plan_email_action(
        email=email,
        analysis=analysis,
        opportunity_match=opportunity_match,
    )

    save_email_analysis(
        email_id=email_id,
        category=analysis["category"],
        priority=analysis["priority"],
        action_required=analysis["action_required"],
        action_type=planned_action.action_type,
        summary=analysis["summary"],
        reason=analysis["reason"],
        deadline=analysis["deadline"],
    )

    notification_analysis = {
        **analysis,
        "action_type": planned_action.action_type,
    }

    if opportunity_match is not None:
        notification_analysis["summary"] = (
            f"{analysis['summary']} Match score: "
            f"{opportunity_match['score']}/100. "
            f"{opportunity_match['reason']}"
        )

    notified = notify_from_analysis(
        item=email,
        analysis=notification_analysis,
    )

    mark_email_processed(email_id)

    return {
        "email_id": email_id,
        "category": analysis["category"],
        "priority": analysis["priority"],
        "action_required": analysis["action_required"],
        "action_type": planned_action.action_type,
        "summary": analysis["summary"],
        "reason": analysis["reason"],
        "deadline": analysis["deadline"],
        "opportunity_match": opportunity_match,
        "notified": notified,
    }


def process_new_emails() -> dict[str, Any]:
    emails = get_unprocessed_emails()

    result = {
        "found": len(emails),
        "processed": 0,
        "failed": 0,
        "results": [],
        "errors": [],
    }

    for email in emails:
        try:
            completed_analysis = process_email(
                email
            )

            result["results"].append(
                completed_analysis
            )

            result["processed"] += 1

        except Exception as error:
            result["failed"] += 1

            result["errors"].append(
                {
                    "email_id": email.get("id"),
                    "error": str(error),
                }
            )

    return result


# ============================================================
# CALENDAR PROCESSING
# ============================================================

def process_calendar_event(
    event: dict[str, Any],
) -> dict[str, Any]:
    event_id = event.get("id")

    if not event_id:
        raise ValueError(
            "Cannot process a calendar event without an id."
        )

    raw_analysis = classify_calendar_event(
        event
    )

    analysis = validate_calendar_analysis(
        raw_analysis
    )

    analysis["priority"] = prioritize_calendar_event(
        base_priority=analysis["priority"],
        event=event,
        category=analysis["category"],
        action_required=analysis["action_required"],
    )

    planned_action = plan_calendar_action(
        event=event,
        analysis=analysis,
    )

    save_calendar_analysis(
        event_id=event_id,
        category=analysis["category"],
        priority=analysis["priority"],
        action_required=analysis["action_required"],
        action_type=planned_action.action_type,
        summary=analysis["summary"],
        reason=analysis["reason"],
    )

    notify_from_analysis(
    item=event,
    analysis={
        **analysis,
        "action_type": planned_action.action_type,
    },
    )

    mark_calendar_event_processed(
        event_id
    )

    return {
        "event_id": event_id,
        "category": analysis["category"],
        "priority": analysis["priority"],
        "action_required": analysis["action_required"],
        "action_type": planned_action.action_type,
        "summary": analysis["summary"],
        "reason": analysis["reason"],
    }

def process_new_calendar_events() -> dict[str, Any]:
    events = get_unprocessed_calendar_events()

    result = {
        "found": len(events),
        "processed": 0,
        "failed": 0,
        "results": [],
        "errors": [],
    }

    for event in events:
        try:
            completed_analysis = (
                process_calendar_event(
                    event
                )
            )

            result["results"].append(
                completed_analysis
            )

            result["processed"] += 1

        except Exception as error:
            result["failed"] += 1

            result["errors"].append(
                {
                    "event_id": event.get("id"),
                    "error": str(error),
                }
            )

    return result


# ============================================================
# COMBINED PROCESSING
# ============================================================

def process_new_data() -> dict[str, Any]:
    """
    Process all new emails and calendar events.

    Returns:
        Combined processing results.
    """

    return {
        "emails": process_new_emails(),
        "calendar": process_new_calendar_events(),
    }

def refresh_calendar_priorities() -> dict[str, Any]:
    """
    Recalculate priorities for already-processed calendar deadlines.

    This does not call the AI classifier again. It only reevaluates
    deadline-based urgency using existing calendar analysis.
    """

    events = get_calendar_events()

    result = {
        "checked": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": [],
    }

    for event in events:
        event_id = event.get("id")

        if not event_id:
            continue

        analysis = get_calendar_analysis(
            event_id
        )

        if analysis is None:
            continue

        category = analysis.get("category")
        action_required = bool(
            analysis.get("action_required")
        )

        # Only deadline-oriented academic items need
        # continuously changing urgency.
        if (
            category not in {"assignment", "exam"}
            or not action_required
        ):
            continue

        result["checked"] += 1

        try:
            old_priority = analysis["priority"]

            new_priority = prioritize_calendar_event(
                base_priority=old_priority,
                event=event,
                category=category,
                action_required=action_required,
            )

            refreshed_analysis = {
                "category": category,
                "priority": new_priority,
                "action_required": action_required,
            }

            planned_action = plan_calendar_action(
                event=event,
                analysis=refreshed_analysis,
            )

            if new_priority == old_priority:
                result["unchanged"] += 1
                continue

            priority_reason = (
                f"Current priority is {new_priority} "
                "based on deadline proximity."
            )

            save_calendar_analysis(
                event_id=event_id,
                category=category,
                priority=new_priority,
                action_required=action_required,
                action_type=planned_action.action_type,
                summary=analysis["summary"],
                reason=priority_reason,
            )

            notify_from_analysis(
            item=event,
            analysis={
                **analysis,
                "priority": new_priority,
                "action_type": planned_action.action_type,
            },
            )

            result["updated"] += 1

        except Exception as error:
            result["errors"].append(
                {
                    "event_id": event_id,
                    "error": str(error),
                }
            )

    return result