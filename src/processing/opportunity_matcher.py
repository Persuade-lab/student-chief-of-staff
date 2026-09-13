"""
Deterministic, explainable matching for opportunity emails.

This deliberately does not make another model call. It makes matching easy to
test and gives users a concrete reason for every recommendation.
"""

from __future__ import annotations

from typing import Any

from src.storage.memory import (
    get_profile,
    save_opportunity_match,
)


FIELD_WEIGHTS = {
    "target_roles": 4,
    "skills": 3,
    "interests": 3,
    "locations": 1,
}


def _email_text(email: dict[str, Any]) -> str:
    return " ".join(
        str(email.get(field, ""))
        for field in ("subject", "body", "sender")
    ).casefold()


def _clean_term(term: Any) -> str:
    return term.strip().casefold() if isinstance(term, str) else ""


def match_opportunity(
    email: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Score an opportunity using visible profile terms.

    The score is the percentage of weighted profile terms found in the email.
    Explicit positive/negative term feedback can nudge a matching term by up
    to three points; it cannot turn an unrelated email into a high match.
    """

    profile = profile or get_profile()
    text = _email_text(email)
    signals = profile.get("term_signals", {})

    total_weight = 0
    matched_weight = 0
    matched_terms: list[dict[str, Any]] = []

    for field, base_weight in FIELD_WEIGHTS.items():
        for raw_term in profile.get(field, []):
            term = _clean_term(raw_term)

            if not term:
                continue

            total_weight += base_weight

            if term not in text:
                continue

            signal = int(signals.get(term, 0))
            matched_weight += base_weight
            matched_terms.append(
                {
                    "term": raw_term,
                    "field": field,
                    "signal": signal,
                }
            )

    if total_weight == 0:
        return {
            "score": 0,
            "reason": (
                "No preferences are configured yet. Add interests, "
                "roles, skills, or locations before matching."
            ),
            "recommended_action": "update_profile",
            "matched_terms": [],
        }

    signal_bonus = sum(
        int(term["signal"])
        for term in matched_terms
    )

    score = round(100 * matched_weight / total_weight)
    score = max(0, min(100, score + signal_bonus))
    minimum_score = int(
        profile.get("minimum_match_score", 60)
    )

    if score >= minimum_score:
        action = "review_now"
    elif score >= max(40, minimum_score - 20):
        action = "save_for_later"
    else:
        action = "ignore"

    if matched_terms:
        explanation = ", ".join(
            f"{term['field'].replace('_', ' ')}: "
            f"{term['term']}"
            for term in matched_terms
        )
        reason = (
            f"Matched {len(matched_terms)} saved preference(s): "
            f"{explanation}."
        )
    else:
        reason = (
            "The opportunity did not contain any saved preference terms."
        )

    return {
        "score": score,
        "reason": reason,
        "recommended_action": action,
        "matched_terms": matched_terms,
    }


def evaluate_opportunity(
    email: dict[str, Any],
) -> dict[str, Any]:
    """Match and persist an opportunity email."""

    email_id = email.get("id")

    if not email_id:
        raise ValueError("Cannot match an opportunity without an email id.")

    match = match_opportunity(email)
    save_opportunity_match(email_id, match)

    return match