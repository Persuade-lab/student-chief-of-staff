"""
AI-powered classification for the Student Chief of Staff.

This module classifies incoming emails and calendar events into
useful categories.
"""

import json
from typing import Any

from strands import Agent
import os
from strands.models import BedrockModel


# ============================================================
# EMAIL CLASSIFICATION
# ============================================================

EMAIL_CLASSIFICATION_PROMPT = """
You are the email classification system for a Student Chief of Staff.

Analyze the email and return ONLY valid JSON.

Valid categories:
- academic
- opportunity
- administrative
- announcement
- personal
- noise

Valid priorities:
- low
- medium
- high
- urgent

Return exactly:

{
  "category": "...",
  "priority": "...",
  "action_required": true,
  "response_required": false,
  "summary": "...",
  "reason": "...",
  "deadline": null
}

Rules:
- Use the email's meaning, not simple keyword matching.
- Marketing emails, newsletters, social notifications, and promotional content
  should usually be low priority unless genuinely important.
- Academic means coursework, instructors, assignments, grades, exams,
  course administration, or Canvas-related academic content.
- Opportunity means internships, jobs, research, fellowships, hackathons,
  scholarships, clubs, or relevant professional opportunities.
- Administrative means university or institutional actions such as enrollment,
  housing, immigration, billing, registration, or financial aid.
- Personal means direct interpersonal communication.
- Noise means content with little useful value to the student.
- Set action_required=true only when the student plausibly needs to do something.
- Extract a deadline only if one is clearly stated or strongly inferable.
- If there is no deadline, use null.
- Extract a deadline only if one is clearly stated or strongly inferable.
- Resolve relative dates such as "today", "tomorrow", "this Friday",
  and "next week" relative to the email's received timestamp.
- Do NOT interpret relative dates relative to the current time when the
  classifier is running.
- Return deadlines in ISO format whenever possible:
  YYYY-MM-DD
  or
  YYYY-MM-DDTHH:MM:SS
- If there is no deadline, use null.
- Set response_required=true only when the student plausibly needs to personally
  reply to the sender.
- A task can require action without requiring a response.
- Assignment reminders, Canvas notifications, grades, newsletters, job alerts,
  automated notifications, and promotional emails should usually have
  response_required=false.
- Direct questions, requests for confirmation, meeting coordination, or personal
  messages that reasonably expect a reply should usually have
  response_required=true.
"""

MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-6",
)
BEDROCK_REGION = os.environ.get(
    "AWS_REGION",
    "us-east-1",
)


def _classification_model() -> BedrockModel:
    return BedrockModel(
        model_id=MODEL_ID,
        region_name=BEDROCK_REGION,
    )

email_agent = Agent(
    model=_classification_model(),
    system_prompt=EMAIL_CLASSIFICATION_PROMPT,
    callback_handler=None,
)


# ============================================================
# CALENDAR CLASSIFICATION
# ============================================================

CALENDAR_CLASSIFICATION_PROMPT = """
You are the calendar classification system for a Student Chief of Staff.

Analyze the calendar event and return ONLY valid JSON.

Valid categories:
- assignment
- exam
- class
- meeting
- work
- personal
- event
- other

Valid priorities:
- low
- medium
- high
- urgent

Return exactly:

{
  "category": "...",
  "priority": "...",
  "action_required": true,
  "summary": "...",
  "reason": "..."
}

Rules:
- Use the meaning of the event, not simple keyword matching.
- assignment means the calendar event itself is a homework, project, quiz, lab,
  paper, submission, or other coursework deadline/deliverable.
- exam means the calendar event itself is a midterm, final, test, assessment,
  or major graded examination.
- class means lectures, recitations, labs, office hours, or normal course meetings.
- meeting means appointments, advising meetings, research meetings, interviews,
  group meetings, or scheduled conversations.
- work means employment shifts or job-related commitments.
- personal means personal appointments or private commitments.
- event means clubs, talks, workshops, social events, hackathons, fairs,
  conferences, or other organized activities.
- A scheduled study session, review session, work block, preparation block, or
  "final review" for an assignment is NOT the assignment deadline merely because
  its title contains a course name or the word "assignment".
- Classify an individual study/review/work block as other unless it is clearly a
  class, group meeting, or another more specific category.
- Never infer that a study block's start time or end time is the assignment's
  due time.
- Only classify something as assignment or exam when the event itself represents
  the graded deliverable, due date, submission deadline, quiz, test, or exam.
- other is only for events that do not reasonably fit another category.

Priority guidance:
- urgent should be rare and reserved for events requiring immediate attention.
- high is appropriate for major deadlines, exams, interviews, or important meetings.
- medium is appropriate for normal commitments that matter but are not critical.
- low is appropriate for routine or informational events.
- Use the event's explicit date/time fields as schedule facts. Do not invent
  a separate coursework deadline from a study session's time.

Action guidance:
- Set action_required=true only when the student needs to do something beyond
  simply attending or having the event already placed on the calendar.
- Normal classes should usually have action_required=false.
- Routine meetings and work shifts should usually have action_required=false.
- Assignment deadlines should usually have action_required=true.
- Exams should usually have action_required=true because preparation is required.
- An event may still be high priority even when action_required=false.

The summary should be short and useful to the student.
The reason should briefly explain the classification and priority.
"""


calendar_agent = Agent(
    model=_classification_model(),
    system_prompt=CALENDAR_CLASSIFICATION_PROMPT,
    callback_handler=None,
)


# ============================================================
# RESPONSE PARSING
# ============================================================

def _parse_json_response(
    response: Any,
) -> dict[str, Any]:
    """
    Convert a Strands model response into a Python dictionary.

    Handles responses wrapped in Markdown code fences.
    """

    text = str(response).strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"Classifier returned invalid JSON: {text}"
        ) from error

    if not isinstance(result, dict):
        raise ValueError(
            "Classifier response must be a JSON object."
        )

    return result


# ============================================================
# EMAIL
# ============================================================

def classify_email(
    email: dict[str, Any],
) -> dict[str, Any]:
    """
    Analyze an email using Strands/Bedrock.

    Returns:
        Structured email analysis.
    """

    message = f"""
Email received:
{email.get("timestamp", "")}

Sender:
{email.get("sender", "")}

Subject:
{email.get("subject", "")}

Body:
{email.get("body", "")}
"""

    response = email_agent(message)

    return _parse_json_response(response)

# ============================================================
# CALENDAR
# ============================================================

def classify_calendar_event(
    event: dict[str, Any],
) -> dict[str, Any]:
    """
    Analyze a calendar event using Strands/Bedrock.

    Returns:
        Structured calendar-event analysis.
    """

    message = f"""
Title:
{event.get("title", "")}

Date:
{event.get("date", "")}

Start time:
{event.get("time", "")}

End time:
{event.get("end_time", "")}

Duration minutes:
{event.get("duration_minutes", "")}

All day:
{event.get("all_day", False)}

Source:
{event.get("source", "")}
"""

    response = calendar_agent(message)

    return _parse_json_response(response)