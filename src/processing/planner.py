"""
Action planning for the Student Chief of Staff.

Planning decides whether to notify. It does not execute a side effect.
"""

from typing import Any

from src.models.schemas import PlannedAction


def plan_email_action(
    email: dict[str, Any],
    analysis: dict[str, Any],
    opportunity_match: dict[str, Any] | None = None,
) -> PlannedAction:
    """Determine the action for one analyzed email."""

    category = analysis["category"]
    priority = analysis["priority"]
    action_required = analysis["action_required"]

    if category == "opportunity":
        recommendation = (
            opportunity_match or {}
        ).get("recommended_action", "ignore")

        if recommendation == "review_now":
            return PlannedAction(
                action_type="notify",
                description=(
                    "Notify the student about a strong opportunity "
                    "match."
                ),
                requires_confirmation=False,
            )

        if recommendation == "save_for_later":
            return PlannedAction(
                action_type="none",
                description=(
                    "Keep this moderate opportunity match without "
                    "interrupting the student."
                ),
                requires_confirmation=False,
            )

        return PlannedAction(
            action_type="none",
            description=(
                "Ignore this low-match opportunity without notifying "
                "the student."
            ),
            requires_confirmation=False,
        )

    if not action_required:
        if priority in {"high", "urgent"}:
            return PlannedAction(
                action_type="notify",
                description="Notify the user about this important email.",
                requires_confirmation=False,
            )

        return PlannedAction(
            action_type="none",
            description="No action is currently required.",
            requires_confirmation=False,
        )

    if category in {"academic", "administrative"}:
        return PlannedAction(
            action_type="notify",
            description="Notify the user about an actionable email.",
            requires_confirmation=False,
        )

    if category == "personal":
        return PlannedAction(
            action_type="review_reply",
            description="Review whether this email needs a response.",
            requires_confirmation=False,
        )

    return PlannedAction(
        action_type="notify",
        description="Notify the user about this actionable email.",
        requires_confirmation=False,
    )


def plan_calendar_action(
    event: dict[str, Any],
    analysis: dict[str, Any],
) -> PlannedAction:
    """Determine what action should be taken for a calendar event."""

    category = analysis["category"]
    priority = analysis["priority"]
    action_required = analysis["action_required"]

    if category in {"assignment", "exam"}:
        if priority in {"high", "urgent"}:
            return PlannedAction(
                action_type="notify",
                description=(
                    "Notify the user about an approaching academic "
                    "deadline."
                ),
                requires_confirmation=False,
            )

        return PlannedAction(
            action_type="none",
            description="Track this deadline without interrupting.",
            requires_confirmation=False,
        )

    if not action_required:
        if priority in {"high", "urgent"}:
            return PlannedAction(
                action_type="notify",
                description="Notify the user about this important event.",
                requires_confirmation=False,
            )

        return PlannedAction(
            action_type="none",
            description="No additional action is currently required.",
            requires_confirmation=False,
        )

    return PlannedAction(
        action_type="notify",
        description="Notify the user about this actionable event.",
        requires_confirmation=False,
    )