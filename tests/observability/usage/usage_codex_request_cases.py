# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A Codex invocation's native session log collected into its serialized request usage, and lines to extend it with.

The collector is dormant -- no trajectory dispatch reaches it yet -- and reads only the lines it is handed, so a test
calls it directly with the captured log as it stood when an invocation exited, or with that log and the lines an
invocation launched after the capture appended, beside the facts the invocation's launch would establish. The appended
lines are spelled the way the CLI writes them: a stamp, a kind, and a payload, one JSON object per line.
"""

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from orchestrator.observability.usage import request_codex
from orchestrator.observability.usage.request_codex_scope import Invocation
from tests.observability.usage import usage_codex_native_capture as capture, usage_request_cases as cases

COUNTERS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
EVENT_MSG = "event_msg"
TOKEN_COUNT = "token_count"
TASK_STARTED = "task_started"
TURN_CONTEXT = "turn_context"
TURN_ID = "turn_id"
# An invocation resuming the captured session after every captured one, and the stamp its lines carry.
APPENDED_AT = datetime.fromisoformat("2026-11-12T14:10:00.000+00:00")
STAMP = "2026-11-12T14:10:01.000Z"
APPENDED_TURN = "01a1d020-0000-7000-8000-000000000001"
CHILD_TURN = "01a1d020-0000-7000-8000-000000000002"
# The running sum the captured log ends on, and one request that advances it.
LAST_RUNNING = (114000, 92100, 14900, 1250, 228, 115250)
NEXT_REQUEST = (1000, 500, 0, 10, 2, 1010)
NEXT_RUNNING = (115000, 92600, 14900, 1260, 230, 116260)
ONE_TURN_STDOUT = '{"type":"turn.started"}'
APPENDED = capture.Invocation(APPENDED_AT, None, True, ONE_TURN_STDOUT, len(capture.log_lines()))


def counters(counts: Iterable[Any]) -> dict[str, Any]:
    """A usage block of the six counters, in the order `COUNTERS` names them."""
    return dict(zip(COUNTERS, counts, strict=True))


def line(kind: str, payload: Any, stamp: str | None = STAMP) -> str:
    """One log line of `kind` carrying `payload`, stamped `stamp` where it is given."""
    stamped = {} if stamp is None else {"timestamp": stamp}
    return json.dumps({**stamped, "type": kind, "payload": payload}, separators=(",", ":"))


def event(name: str, **fields: Any) -> str:
    """One `event_msg` line naming `name`."""
    return line(EVENT_MSG, {"type": name, **fields})


def token_count(running: Iterable[Any], own: Iterable[Any], **reported: Any) -> str:
    """A `token_count` reporting `own` as its request's usage beside the running sum `running`, and `reported`."""
    usage = {"total_token_usage": counters(running), "last_token_usage": counters(own), **reported}
    return event(TOKEN_COUNT, info=usage)


def collected(
    invocation: capture.Invocation = capture.FRESH,
    lines: Iterable[str] | None = None,
    *,
    session_id: str | None = capture.SESSION_ID,
    fallback_model: str | None = None,
    stdout: str | None = None,
) -> cases.Collected:
    """What `invocation` collects from `lines` -- the captured log as it stood when it exited, by default."""
    read = capture.log_lines(invocation.end) if lines is None else tuple(lines)
    prior_lines = invocation.start if invocation.resumed else None
    facts = Invocation(session_id, invocation.resumed, invocation.launched_at, prior_lines)
    session = request_codex.NativeSession(facts, enumerate(read))
    usage = request_codex.collect(invocation.stdout if stdout is None else stdout, session, fallback_model)
    return cases.Collected(usage.to_dict())


def appended(*lines: str, **options: Any) -> cases.Collected:
    """What an invocation launched after the capture collects, the captured log with its `lines` appended."""
    return collected(APPENDED, (*capture.log_lines(), *lines), **options)


def raw_sums(entries: Iterable[Mapping[str, Any]]) -> tuple[int, ...]:
    """Each of the six raw counters added up over `entries` -- one sample's or checkpoint's own, given only it."""
    totals = dict.fromkeys(COUNTERS, 0)
    for entry in entries:
        for counter in COUNTERS:
            totals[counter] += entry[cases.RAW][counter]
    return tuple(totals.values())
