"""
Student Chief of Staff coordinator agent.

The coordinator keeps one Agent instance alive for the lifetime of the process
so short follow-up messages retain conversational context.
"""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from zoneinfo import ZoneInfo

from strands import Agent
from strands.models import BedrockModel

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import get_tools


MODEL_ID = "us.anthropic.claude-sonnet-4-6"
LOCAL_TIMEZONE = "America/New_York"

_AGENT: Agent | None = None
_AGENT_DATE: str | None = None
_AGENT_LOCK = Lock()


def _runtime_prompt(now: datetime) -> str:
    return f"""
{SYSTEM_PROMPT}

Current date and time:
- Date: {now.strftime("%Y-%m-%d")}
- Day: {now.strftime("%A")}
- Time: {now.strftime("%H:%M")}
- Timezone: {LOCAL_TIMEZONE}

Date interpretation rules:
- Resolve "today", "tomorrow", "yesterday", "this Friday", "next Monday",
  "next week", and similar relative dates from the current date above.
- Before calling a calendar tool, convert a relative date to an explicit
  YYYY-MM-DD date.
- Never guess the current date.
"""


def create_agent(now: datetime | None = None) -> Agent:
    """Create and configure the Student Chief of Staff agent."""

    current = now or datetime.now(ZoneInfo(LOCAL_TIMEZONE))

    model = BedrockModel(
        model_id=MODEL_ID,
        region_name="us-east-1",
    )

    return Agent(
        model=model,
        system_prompt=_runtime_prompt(current),
        tools=get_tools(),
        callback_handler=None,
    )

def get_agent() -> Agent:
    """
    Return the process-wide coordinator agent.

    Recreate it only when the local calendar date changes so the injected
    current-date context stays correct without losing conversation history
    during a normal session.
    """

    global _AGENT, _AGENT_DATE

    today = datetime.now(ZoneInfo(LOCAL_TIMEZONE)).date().isoformat()

    with _AGENT_LOCK:
        if _AGENT is None or _AGENT_DATE != today:
            _AGENT = create_agent()
            _AGENT_DATE = today

        return _AGENT


def reset_agent() -> None:
    """Forget the in-process conversation and create a fresh agent next time."""

    global _AGENT, _AGENT_DATE

    with _AGENT_LOCK:
        _AGENT = None
        _AGENT_DATE = None


def run_agent(message: str):
    """Send a message to the persistent Student Chief of Staff agent."""

    return get_agent()(message)
