# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity failure evidence: terminal diagnostics and the account-quota verdict.

A failed AGY run leaves `last_message` empty, and the reason it stopped
arrives on two failure channels: the `error` an unsuccessful terminal result
carried, and the diagnostic lines the CLI prints to stderr -- a plain
`error: ...` line, and on some failures an `AGY_ERROR: {...}` line with the
provider's structured status. Only those channels are evidence. The terminal
response is assistant text even beside an error status, and a stale or
contradicting response step is never trusted to repair the terminal, so an
answer that merely discusses a quota stays an answer and an error stays an
error.
"""
from __future__ import annotations

import itertools
import json
import re
from typing import Any

from orchestrator.agents import models as _agent_models
from orchestrator.config import credentials as _credentials
from orchestrator.observability.usage import agy_events

_AGY_ERROR_PREFIX = "AGY_ERROR:"
_CLI_ERROR_PREFIX = "error:"

# The structured diagnostic of an exhausted account quota. Every field has to
# match, compared in its JSON spelling so `1` is not `true` and `429.0` is not
# `429`, and an unrelated 429 or a quota error AGY says is not retryable keeps
# its own classification.
_QUOTA_SIGNATURE = (
    ("status", "RESOURCE_EXHAUSTED"),
    ("error_code", 429),
    ("code_kind", "http"),
    ("retryable", True),
)

# How AGY words the same stop where it prints no structure.
_PLAIN_QUOTA_MARKER = "individual quota reached"

# The reset AGY names as a duration, such as `Resets in 2h42m39s.`, which a
# wrapped message can split across lines.
_QUOTA_RESET = re.compile(r"\bresets\s+in\s+(?P<reset>(?:\d+(?:\.\d+)?[hms])+)\b", re.IGNORECASE)

_DIAGNOSTIC_BUDGET = 1024

# A diagnostic as the text that decides it and the complete message it opens.
_Diagnostic = tuple[str, str]


def _redacted_bounded(text: str) -> str:
    """`text` redacted, then cut to its first `_DIAGNOSTIC_BUDGET` characters, the cut marked."""
    redacted = _credentials.redact_secrets(text).strip()
    if len(redacted) <= _DIAGNOSTIC_BUDGET:
        return redacted
    kept = redacted[:_DIAGNOSTIC_BUDGET]
    return f"{kept}…"


def _structured_quota_message(payload_text: str) -> str | None:
    """The decoded text of a quota `AGY_ERROR:` payload, or None when it carries no quota signature.

    The reset is read from the decoded strings rather than the serialized
    line, where a newline inside `short_error` is an escape that hides it.
    """
    try:
        payload = json.loads(payload_text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    expected = dict(_QUOTA_SIGNATURE)
    found = {key: payload.get(key) for key in expected}
    if json.dumps(found) != json.dumps(expected):
        return None
    return "\n".join(field for field in payload.values() if isinstance(field, str))


def _quota_message(evidence: str, message: str) -> str | None:
    """The message a diagnostic names the quota in, or None when it names none.

    `evidence` is the part that decides: a structured payload by its
    signature alone, plain text by AGY's wording. `message` is the complete
    diagnostic, which the reset is read from.
    """
    if evidence.startswith(_AGY_ERROR_PREFIX):
        return _structured_quota_message(evidence.removeprefix(_AGY_ERROR_PREFIX))
    return message if _PLAIN_QUOTA_MARKER in evidence.lower() else None


def _stderr_diagnostics(stderr: str) -> list[_Diagnostic]:
    """The CLI's own diagnostics on stderr, each as its deciding line and its complete message.

    An `AGY_ERROR:` line stands alone. An `error:` line opens a message that
    a wrapped error continues on the lines below it, up to a blank line or
    the next diagnostic; only the opening line decides, so text the CLI
    printed after its diagnostic can lend it a reset but never a verdict.
    Lines outside any diagnostic are no evidence.
    """
    blocks: list[list[str]] = []
    continuing = False
    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        if line.startswith(_AGY_ERROR_PREFIX) or line.lower().startswith(_CLI_ERROR_PREFIX):
            blocks.append([line])
            continuing = not line.startswith(_AGY_ERROR_PREFIX)
        elif continuing and line:
            blocks[-1].append(line)
        else:
            continuing = False
    return [(block[0], "\n".join(block)) for block in blocks]


def _failure_diagnostics(terminal: dict[str, Any], stderr: str) -> list[_Diagnostic]:
    """The unsuccessful terminal's error, which decides and carries its reset whole, then stderr's diagnostics.

    A successful terminal's `error`, if any, is no failure evidence; the
    stderr diagnostics still are, since the run failed anyway. Each text is
    redacted whole before it is split, so a multi-line secret is masked
    before any part of it is classified or has a reset read off it.
    """
    terminal_error = ""
    if terminal.get("status") != agy_events.SUCCESS:
        terminal_error = str(terminal.get("error") or "")
    redacted_error = _credentials.redact_secrets(terminal_error).strip()
    return [(redacted_error, redacted_error), *_stderr_diagnostics(_credentials.redact_secrets(stderr))]


def terminal_failure(
    terminal: dict[str, Any],
    process_result: _agent_models.SubprocessResult,
) -> _agent_models.TerminalFailure:
    """Read the failure record of a run `agy_result` normalized to a failure.

    `terminal` is the last terminal result payload, empty when the stream
    carried none.
    """
    status = terminal.get("status")
    diagnostics = _failure_diagnostics(terminal, process_result.stderr)
    quota_messages = [
        message for message in itertools.starmap(_quota_message, diagnostics) if message is not None
    ]
    resets = (_QUOTA_RESET.search(message) for message in quota_messages)
    return _agent_models.TerminalFailure(
        process_exit_code=process_result.exit_code,
        status=None if status is None else _redacted_bounded(str(status)),
        error=_redacted_bounded(str(terminal.get("error") or "")),
        quota_exhausted=bool(quota_messages),
        quota_reset=next((reset.group("reset") for reset in resets if reset), None),
    )
