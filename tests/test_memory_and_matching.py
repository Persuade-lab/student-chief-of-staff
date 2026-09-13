from src.processing.opportunity_matcher import (
    evaluate_opportunity,
)
from src.storage.memory import (
    get_profile,
    get_opportunity_match,
    update_profile,
)


def test_profile_persists_and_opportunity_matches():
    update_profile(
        interests=["climate tech"],
        target_roles=["software engineering intern"],
        skills=["python"],
        locations=["Philadelphia"],
        minimum_match_score=50,
    )

    assert get_profile()["skills"] == ["python"]

    match = evaluate_opportunity(
        {
            "id": "email-1",
            "subject": "Climate-tech software engineering internship",
            "body": (
                "Use Python with our team in Philadelphia."
            ),
        }
    )

    assert match["score"] >= 50
    assert match["recommended_action"] == "review_now"
    assert get_opportunity_match("email-1")["score"] == (
        match["score"]
    )


def test_unrelated_opportunity_is_not_recommended():
    update_profile(
        interests=["climate tech"],
        target_roles=["software engineering intern"],
        skills=["python"],
        locations=[],
        minimum_match_score=60,
    )

    match = evaluate_opportunity(
        {
            "id": "email-2",
            "subject": "Fashion merchandising opportunity",
            "body": "Retail buying and brand partnerships.",
        }
    )

    assert match["score"] == 0
    assert match["recommended_action"] == "ignore"