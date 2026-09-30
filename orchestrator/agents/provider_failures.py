# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one verdict a run's own output gives about the provider behind it.

The `sessions` parsers answer what the CLI said. This owner answers whether it
said anything of its own: an `API Error: 529 Overloaded` is the provider
refusing to serve the turn, so the text reaching the caller is the refusal
rather than the agent's words. Every stage that reads a final message as the
agent's own has to ask that first, which is why the policy sits beside the
parsers rather than inside one stage -- and apart from them, because what the
stream held is a parse and what it means for the run is a judgement.

Two verdicts are taken off the same evidence, because two questions are asked
of it. Whether a retry on a fresh session recovers is the transient one, over
the server-side family alone. Whether the agent got to its prompt at all is
the wider one: a 401 or a 429 is no more the agent's words than a 529 is, and
a caller settling what a run was handed has to know that whatever a retry
could do about it.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from orchestrator.agents import models as _agent_models, sessions as _agent_sessions

# The server-side refusals a retry is the whole recovery for, matched as a
# PREFIX of the normalized final message. Deliberately only the 5xx family and
# the overload the provider names in words: a 4xx is a request this account may
# not make (auth, permission, a payload the model refused) and retrying it
# changes nothing, and a 429 is quota, whose CLI-level phrasings the
# session-limit classifier already routes to "wait for the reset".
_TRANSIENT_PROVIDER_MESSAGE_MARKERS: tuple[str, ...] = (
    "api error: 500",
    "api error: 502",
    "api error: 503",
    "api error: 504",
    "api error: 529",
    "api error: overloaded",
)

# Every refusal the provider answers a turn with, retryable or not: the CLI
# prints each HTTP error it was handed under this one prefix.
_PROVIDER_REFUSAL_MARKER = "api error:"


def _has_transient_provider_marker(message: Any) -> bool:
    """True iff `message` OPENS with a known transient provider refusal."""
    if not isinstance(message, str):
        return False
    return message.strip().lower().startswith(_TRANSIENT_PROVIDER_MESSAGE_MARKERS)


def _has_provider_refusal_marker(message: Any) -> bool:
    """True iff `message` OPENS with any provider refusal at all."""
    if not isinstance(message, str):
        return False
    return message.strip().lower().startswith(_PROVIDER_REFUSAL_MARKER)


def _structured_provider_verdict(
    jsonl_output: str, refused: Callable[[Any], bool],
) -> bool | None:
    """Return the backend's OWN verdict on a run, or None when it gave none.

    Claude's terminal result event carries `is_error`, which is the only
    signal that separates a provider refusal from an agent that merely wrote
    about one: a successful turn quoting `API Error: 529 Overloaded` back at
    the operator is flagged `is_error: false` and must stay a real answer. A
    stream with no result event, or an older CLI whose result event omits the
    flag, said nothing on the question -- None sends the caller to the
    exit-code fallback rather than letting a missing key read as "healthy".
    """
    terminal_event = _agent_sessions.claude_terminal_result_event(jsonl_output)
    if terminal_event is None or "is_error" not in terminal_event:
        return None
    if terminal_event["is_error"] is not True:
        return False
    return refused(_agent_sessions.claude_result_text(terminal_event))


def is_transient_provider_failure(
    agent_result: _agent_models.AgentResult,
) -> bool:
    """True iff this run ended in a known transient provider refusal.

    The CLI hands a `529 Overloaded` back through the same non-empty final
    message a real agent question arrives on, so a stage that reads that field
    as the agent's words would post a server outage as "agent needs your
    input" and then resume the same doomed session on the reply. Callers ask
    this first and route a True through their retryable session-failure park
    instead.

    Structured backend information wins where there is any: the terminal
    result event's `is_error` flag settles whether the text is the run's
    outcome or its subject. Without it -- a backend that emits no such event,
    or output nothing parsed -- the marker is only honored beside a NON-ZERO
    exit, so a clean run is never reclassified on its prose alone.
    """
    structured_verdict = _structured_provider_verdict(
        agent_result.stdout or "", _has_transient_provider_marker,
    )
    if structured_verdict is not None:
        return structured_verdict
    if agent_result.exit_code == 0:
        return False
    return _has_transient_provider_marker(agent_result.last_message)


def is_provider_refusal(agent_result: _agent_models.AgentResult) -> bool:
    """True iff this run ended on any refusal the provider answered it with.

    Wider than `is_transient_provider_failure`: an auth refusal, a rate limit,
    and a request the provider would not take are all turns the agent never
    got to, and a caller settling what a run was handed -- whether the replies
    quoted into its prompt were read -- asks this rather than whether a retry
    would help.

    The structured `is_error` flag still wins where the run gave one, so a
    turn that quoted a refusal back as its subject stays an answer. Without
    one, the prefix alone decides, whatever the exit code: the question's
    costs are lopsided, since a refusal read as an answer drops a human's
    words while an answer read as a refusal hands them over once more, and an
    agent's own final message does not open with its provider's error line.
    """
    structured_verdict = _structured_provider_verdict(
        agent_result.stdout or "", _has_provider_refusal_marker,
    )
    if structured_verdict is not None:
        return structured_verdict
    return _has_provider_refusal_marker(agent_result.last_message)
