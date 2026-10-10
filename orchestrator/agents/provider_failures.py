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

A third verdict is Codex's alone and is read off a different signal. A Codex
turn the account's usage limit stopped writes no final message at all, so the
refusal is taken from the JSONL stream through the `codex_events` reader, and
it is returned as a diagnostic rather than a flag: a caller parking the run
has to tell the operator when the limit resets, in the provider's words.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from orchestrator.agents import (
    codex_events as _codex_events,
    models as _agent_models,
    sessions as _agent_sessions,
)

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

# The `codex_error_info` variant an exhausted account usage limit is coded as.
_CODEX_USAGE_LIMIT_CODE = "usage_limit_exceeded"

# How the provider opens that refusal, matched as a PREFIX of the message after
# folding the typographic apostrophe the CLI prints. `codex exec --json` keeps
# only the message on a failed turn's error, so for the CLIs that print no code
# these words are the whole signal.
_CODEX_USAGE_LIMIT_MESSAGE_PREFIX = "you've hit your usage limit"

# The reset the provider names, as it renders it: `try again at Sep 26th, 2026
# 12:09 PM.`, closing the message or one of its sentences.
_CODEX_USAGE_LIMIT_RESET = re.compile(
    r"\btry again at (?P<reset>.+?)(?:\.\s|\.?$)", re.IGNORECASE,
)


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


@dataclass(frozen=True)
class CodexUsageLimitFailure:
    """A Codex run the account's usage limit stopped, as the provider said it.

    `message` is the provider's text verbatim: neither redacted nor bounded,
    so a consumer that publishes it applies both first.
    """

    message: str

    @property
    def reset_time(self) -> str | None:
        """The time the provider named for a retry, or None when it named none.

        Kept as phrased, such as `Sep 26th, 2026 12:09 PM`: the CLI renders
        it in the local time of the host it ran on and names no zone, so a
        parsed instant would claim a precision the text does not carry.
        """
        reset_match = _CODEX_USAGE_LIMIT_RESET.search(self.message)
        return reset_match.group("reset") if reset_match else None


def codex_usage_limit_failure(
    agent_result: _agent_models.AgentResult,
) -> CodexUsageLimitFailure | None:
    """Return the usage-limit stop a Codex run ended on, or None.

    Read off stdout whatever `last_message` holds, since the stop leaves that
    field empty, and only off the turn the run ENDED on: an error a later turn
    recovered from is no stop, neither is a completed turn quoting the
    provider's words, and a stop an earlier turn closed on is set aside by a
    later turn the stream never closed.

    A code on that turn's error settles it either way, so an error coded as
    anything else is never reclassified by its prose. Only an error printed
    without a code falls back to the provider's opening words, and only beside
    a non-zero exit, so a clean run is never reclassified on its prose alone.
    """
    turn_failure = _codex_events.codex_turn_failure(agent_result.stdout or "")
    if turn_failure is None:
        return None
    if turn_failure.code is None:
        opening = turn_failure.message.replace("\u2019", "'").strip().lower()
        exhausted = agent_result.exit_code != 0 and opening.startswith(
            _CODEX_USAGE_LIMIT_MESSAGE_PREFIX,
        )
    else:
        exhausted = turn_failure.code == _CODEX_USAGE_LIMIT_CODE
    return CodexUsageLimitFailure(turn_failure.message) if exhausted else None
