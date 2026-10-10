# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex terminal-turn parsing, read against `codex exec --json`'s own schema.

A failed Codex turn writes no final message, so the `-o` file the backend
reads `last_message` from stays empty while stdout still carries the JSONL
event stream. Whether the run ended on a failure, and what that failure said,
is therefore asked of stdout, and this owner answers it: the turn the run
ended on and the error it closed with, named field by field as the CLI emits
them. What the error means for the provider behind the run is the
`provider_failures` owner's question, the same split the `sessions` parsers
keep for Claude.
"""
from __future__ import annotations

from typing import Any, NamedTuple

from orchestrator.observability.usage import event_stream

_TYPE_FIELD = "type"
_TURN_STARTED = "turn.started"
_TURN_FAILED = "turn.failed"
_TERMINAL_TURN_EVENTS = ("turn.completed", _TURN_FAILED)
_ERROR_INFO_FIELD = "codex_error_info"


class CodexTurnFailure(NamedTuple):
    """The error a Codex run's last turn failed with, as the CLI printed it.

    `code` is the `codex_error_info` the error carried, or None for a CLI
    that printed the message alone.
    """

    message: str
    code: str | None


def _error_code(error_payload: dict[str, Any]) -> str | None:
    """Return the variant `codex_error_info` names, in either serde shape.

    Codex's error-info enum serializes a variant without fields, such as
    `usage_limit_exceeded`, as a bare string and one with fields, such as
    `http_connection_failed`, as a mapping keyed by the variant's name.
    Either is a code, so a caller's message fallback stays out of it.
    """
    error_info = error_payload.get(_ERROR_INFO_FIELD)
    if isinstance(error_info, str):
        return error_info or None
    if isinstance(error_info, dict) and len(error_info) == 1:
        return next(iter(error_info))
    return None


def codex_turn_failure(jsonl_output: str) -> CodexTurnFailure | None:
    """Return the failure the run's LAST turn ended on, or None.

    Only the `turn.completed` / `turn.failed` event closing the last turn the
    stream started decides. A `turn.started` sets aside whatever an earlier
    turn closed on, so a final turn left unfinished -- no closing event, or a
    closing line that did not decode -- reports none, as does a stream that
    closed no turn at all. The standalone `error` events the CLI streams
    mid-turn never decide, since they include reconnect notices a later
    success recovers from, and a turn that completed is no failure whatever
    its items quoted. A line that is not a JSON object is skipped wherever it
    sits, so noise printed after the closing event leaves that event standing.
    """
    closing_event: dict[str, Any] | None = None
    for event_payload in event_stream.iter_events(jsonl_output):
        event_type = event_payload.get(_TYPE_FIELD)
        if event_type == _TURN_STARTED:
            closing_event = None
        elif event_type in _TERMINAL_TURN_EVENTS:
            closing_event = event_payload
    if closing_event is None or closing_event.get(_TYPE_FIELD) != _TURN_FAILED:
        return None
    error_payload = closing_event.get("error")
    if not isinstance(error_payload, dict):
        return CodexTurnFailure("", None)
    error_message = error_payload.get("message")
    return CodexTurnFailure(
        error_message if isinstance(error_message, str) else "",
        _error_code(error_payload),
    )
