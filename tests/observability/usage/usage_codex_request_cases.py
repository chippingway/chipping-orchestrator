# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex native session log lines spelled the way the CLI writes them, and the scope one invocation takes over a log.

The scope is dormant -- nothing in the runtime reads a native log yet -- and reads only the lines it is handed, so a
test hands it the captured log as it stood when an invocation exited, or that log with the lines an invocation launched
after the capture appended, beside the facts the invocation's launch would establish. Appended lines carry a stamp, a
kind, and a payload, one JSON object per line.
"""

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, NamedTuple

from orchestrator.observability.usage import request_scan
from orchestrator.observability.usage.request_codex_scope import Invocation, Line, NativeScope
from tests.observability.usage import usage_codex_native_capture as capture

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
TASK_COMPLETE = "task_complete"
TURN_CONTEXT = "turn_context"
USAGE_RECORD = "token_usage_record"
TURN_ID = "turn_id"
# An invocation resuming the captured session after every captured one, and the stamp its lines carry.
APPENDED_AT = datetime.fromisoformat("2026-11-12T14:10:00.000+00:00")
STAMP = "2026-11-12T14:10:01.000Z"
APPENDED_TURN = "01a1d020-0000-7000-8000-000000000001"
CHILD_TURN = "01a1d020-0000-7000-8000-000000000002"
# One request advancing the running sum the captured log ends on.
NEXT_REQUEST = (1000, 500, 0, 10, 2, 1010)
NEXT_RUNNING = (115000, 92600, 14900, 1260, 230, 116260)
ONE_TURN_STDOUT = '{"type":"turn.started"}'
# Launched once the captured log was whole, which is what it reads where no lines are handed over.
APPENDED = capture.Invocation(APPENDED_AT, capture.LAST.end, True, ONE_TURN_STDOUT, capture.LAST.end)


class Scoped(NamedTuple):
    """The scope an invocation took over a log, every line it read an event off, and the stdout it printed."""

    scope: NativeScope
    lines: tuple[Line, ...]
    stdout: str

    @property
    def refusal(self) -> str | None:
        """Why the scope attributes nothing of the log to the invocation; None where it attributes its own lines."""
        return self.scope.refusal(self.stdout)

    @property
    def own(self) -> list[int]:
        """The positions of the lines placed as the invocation's own."""
        return [line.position for line in self.lines if line.own]

    @property
    def reports(self) -> list[Any]:
        """The turn each of the invocation's `token_count` lines settled in."""
        return self.settled(TOKEN_COUNT)

    @property
    def usage_turns(self) -> set[str | None]:
        """The ids of the turns the invocation's usage records and reports settled in."""
        settled = [*self.settled(USAGE_RECORD), *self.reports]
        return {turn.turn_id for turn in settled if turn is not None}

    def settled(self, kind: str) -> list[Any]:
        """The turn each of the invocation's lines of `kind` -- an event name, or a line kind -- settled in."""
        found = []
        for placed in self.lines:
            envelope = placed.envelope
            if placed.own and envelope and kind in envelope[:2]:
                found.append(placed.settled)
        return found


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


def scoped(
    invocation: capture.Invocation = capture.FRESH,
    lines: Iterable[str] | None = None,
    *,
    session_id: str | None = capture.SESSION_ID,
    scan: request_scan.EventScan | None = None,
) -> Scoped:
    """The scope `invocation` takes over `lines` -- the captured log as it stood when it exited, by default -- read
    into `scan`, or into a scan of its own, and held to the turns its stdout started.
    """
    read = capture.log_lines(invocation.end) if lines is None else tuple(lines)
    # A fresh run's log held no line at its launch, which is the count a fresh invocation starts at.
    facts = Invocation(session_id, invocation.resumed, invocation.launched_at, invocation.start)
    scope = NativeScope.of(facts, scan)
    placed = [scope.read(*numbered) for numbered in enumerate(read)]
    return Scoped(scope, tuple(filter(None, placed)), invocation.stdout)


def appended(*lines: str, **options: Any) -> Scoped:
    """The scope an invocation launched after the capture takes, the captured log with its `lines` appended."""
    return scoped(APPENDED, (*capture.log_lines(), *lines), **options)
