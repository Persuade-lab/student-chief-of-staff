"""
Persistent, user-editable preferences for opportunity matching.

The agent may update this only when the user explicitly asks. The values are
kept in SQLite so they survive restarts and are easy to inspect or change.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.storage.database import (
    get_connection,
    initialize_database,
)


PROFILE_KEY = "student_profile"

DEFAULT_PROFILE = {
    "interests": [],
    "target_roles": [],
    "skills": [],
    "locations": [],
    "minimum_match_score": 60,
    "term_signals": {},
}

LIST_FIELDS = (
    "interests",
    "target_roles",
    "skills",
    "locations",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_terms(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if not isinstance(value, str):
            continue

        cleaned = value.strip()
        key = cleaned.casefold()

        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)

    return result


def _normalise_profile(profile: Any) -> dict[str, Any]:
    result = {
        "interests": [],
        "target_roles": [],
        "skills": [],
        "locations": [],
        "minimum_match_score": 60,
        "term_signals": {},
    }

    if not isinstance(profile, dict):
        return result

    for field in LIST_FIELDS:
        result[field] = _clean_terms(profile.get(field))

    try:
        score = int(profile.get("minimum_match_score", 60))
    except (TypeError, ValueError):
        score = 60

    result["minimum_match_score"] = max(0, min(100, score))

    raw_signals = profile.get("term_signals", {})

    if isinstance(raw_signals, dict):
        for term, value in raw_signals.items():
            if not isinstance(term, str):
                continue

            try:
                weight = int(value)
            except (TypeError, ValueError):
                continue

            cleaned = term.strip().casefold()

            if cleaned:
                result["term_signals"][cleaned] = max(
                    -3,
                    min(3, weight),
                )

    return result


def get_profile() -> dict[str, Any]:
    """Return the current profile, or an empty default profile."""

    initialize_database()
    connection = get_connection()

    row = connection.execute(
        """
        SELECT value_json
        FROM user_memory
        WHERE key = ?
        """,
        (PROFILE_KEY,),
    ).fetchone()

    connection.close()

    if row is None:
        return _normalise_profile(DEFAULT_PROFILE)

    try:
        value = json.loads(row["value_json"])
    except (TypeError, json.JSONDecodeError):
        value = DEFAULT_PROFILE

    return _normalise_profile(value)


def save_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist a complete user profile."""

    clean_profile = _normalise_profile(profile)
    initialize_database()
    connection = get_connection()

    connection.execute(
        """
        INSERT INTO user_memory (
            key,
            value_json,
            updated_at
        )
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at
        """,
        (
            PROFILE_KEY,
            json.dumps(clean_profile, sort_keys=True),
            _now(),
        ),
    )

    connection.commit()
    connection.close()

    return clean_profile


def update_profile(**changes: Any) -> dict[str, Any]:
    """
    Update only supplied profile fields.

    Example:
        update_profile(
            interests=["climate tech", "machine learning"],
            target_roles=["software engineering intern"],
        )
    """

    profile = get_profile()

    for field in LIST_FIELDS:
        if field in changes:
            profile[field] = changes[field]

    if "minimum_match_score" in changes:
        profile["minimum_match_score"] = changes[
            "minimum_match_score"
        ]

    return save_profile(profile)


def record_interest_signal(
    term: str,
    liked: bool,
) -> dict[str, Any]:
    """
    Record explicit user feedback about a term.

    This is intentionally small and transparent: a positive signal slightly
    helps future matching, while a negative signal slightly lowers it.
    """

    cleaned = term.strip().casefold()

    if not cleaned:
        raise ValueError("term must not be empty")

    profile = get_profile()
    signals = profile["term_signals"]
    current = int(signals.get(cleaned, 0))
    signals[cleaned] = max(
        -3,
        min(3, current + (1 if liked else -1)),
    )

    return save_profile(profile)


def save_opportunity_match(
    email_id: str,
    match: dict[str, Any],
) -> None:
    """Persist the latest transparent match result for one email."""

    initialize_database()
    connection = get_connection()

    connection.execute(
        """
        INSERT INTO opportunity_matches (
            email_id,
            match_score,
            reason,
            recommended_action,
            matched_terms_json,
            evaluated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(email_id) DO UPDATE SET
            match_score = excluded.match_score,
            reason = excluded.reason,
            recommended_action = excluded.recommended_action,
            matched_terms_json = excluded.matched_terms_json,
            evaluated_at = excluded.evaluated_at
        """,
        (
            email_id,
            int(match["score"]),
            str(match["reason"]),
            str(match["recommended_action"]),
            json.dumps(match.get("matched_terms", [])),
            _now(),
        ),
    )

    connection.commit()
    connection.close()


def get_opportunity_match(
    email_id: str,
) -> dict[str, Any] | None:
    """Return a stored match result for an email."""

    initialize_database()
    connection = get_connection()

    row = connection.execute(
        """
        SELECT
            email_id,
            match_score,
            reason,
            recommended_action,
            matched_terms_json,
            evaluated_at
        FROM opportunity_matches
        WHERE email_id = ?
        """,
        (email_id,),
    ).fetchone()

    connection.close()

    if row is None:
        return None

    result = dict(row)
    result["score"] = result.pop("match_score")
    result["matched_terms"] = json.loads(
        result.pop("matched_terms_json")
    )

    return result