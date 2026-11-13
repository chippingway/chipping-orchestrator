# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The scope one Codex invocation takes over its native session log, read directly a line at a time.

The scope is dormant -- nothing in the runtime reads a native log yet -- and reads only the lines it is handed, so a
test hands it the captured log as it stood when an invocation exited, or that log with the lines an invocation launched
after the capture appended, beside the facts the invocation's launch would establish.
"""

from collections.abc import Iterable
from typing import Any, NamedTuple

from orchestrator.observability.usage import request_scan
from orchestrator.observability.usage.request_codex_scope import Invocation, Line, NativeScope
from tests.observability.usage import usage_codex_native_capture as capture, usage_codex_request_cases as codex


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
        return self.settled(codex.TOKEN_COUNT)

    @property
    def usage_turns(self) -> set[str | None]:
        """The ids of the turns the invocation's usage records and reports settled in."""
        settled = [*self.settled(codex.USAGE_RECORD), *self.reports]
        return {turn.turn_id for turn in settled if turn is not None}

    def settled(self, kind: str) -> list[Any]:
        """The turn each of the invocation's lines of `kind` -- an event name, or a line kind -- settled in."""
        found = []
        for placed in self.lines:
            envelope = placed.envelope
            if placed.own and envelope and kind in envelope[:2]:
                found.append(placed.settled)
        return found


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
    return scoped(codex.APPENDED, (*capture.log_lines(), *lines), **options)
