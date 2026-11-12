# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which lines of a Codex native session log one invocation wrote, whether the log is the session's own at all, and
the turns those lines open.

A fresh `codex exec` opens its session log with a `session_meta` line naming the thread it started (`id`), and every
`exec resume` of the session appends to that same file -- under the date the session began, whatever date it is
resumed on -- writing no new `session_meta`, only a `task_started` for the turn it runs. Nothing in the log says
where one process's lines end and the next one's begin, so the log is held to two proofs before anything in it is
attributed to an invocation.

Its identity: the first line has to be a `session_meta` naming the session the run returned as its own thread. A log
found under another name, or one whose first line was unreadable, is never adopted.

Its boundary: the tracked spawn observes the moment it launched the process, and the CLI stamps every line with the
time it wrote it, off the same host clock, to the millisecond. A line stamped more than a millisecond after the launch
was written after it, and one stamped more than a millisecond before it was written before it, however the CLI cut its
stamp; one stamped within a millisecond of the launch, on either side, could be either, and places nothing. The
invocation's lines are the ones from the first line stamped past that window onward. The process could write nothing
before it was started, and every earlier invocation of the session had exited before this one was launched, so its
lines are the only ones that can land there -- as long as the stamps never go backward. Every line is held to that: a
stamp earlier than the one before it, anywhere in the log, means the clock or the file cannot place the invocation, and
nothing in the log is attributed to it. A line with no stamp is placed by its order in the file, the order it was
appended in, but only where a stamped line proves which side it is on: one followed by a line stamped before the launch
was an earlier invocation's, and one following the boundary is this one's. A line nothing places -- unstamped between
the last earlier line and the boundary, or after the last earlier line of a log read whole with no boundary at all, or
stamped within the launch's window -- could be this invocation's or an earlier one's, so no line is attributed. A
fresh run's log has to begin inside its own boundary, since this process created it, and a resumed run's has to begin
before it. Where stdout counts the turns this process started, the log has to have opened as many root turns from the
boundary on, so a turn some other process appended meanwhile is never taken for one of this run's; that count is
checked only on a log read whole, since a cut short read proves nothing about the turns past the cut, and only on a
stdout the scan read whole, since one with a line it could not read could have printed one more.

Where either proof fails, the collection names why and attributes nothing; it never guesses a suffix of the log.

Turns. A `task_started` opens a turn. One whose `turn_attribution` names a `parent_turn_id` is a child turn run inside
this log, its requests a branch of their own; one naming none is a root turn of the session's own thread, and opening
it abandons every turn still open, since the thread has moved on -- a turn an earlier process left unfinished is never
taken for this one's. A `task_complete` or `turn_aborted` closes the turn it names. A request belongs to the innermost
turn the invocation opened that is still open when it settles, or to the thread where there is none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from orchestrator.observability.usage import request_coverage as coverage, request_scan

SESSION_META = "session_meta"
PAYLOAD = "payload"
TYPE = "type"
_TIMESTAMP = "timestamp"
_TURN_STARTED = "turn.started"
_TURN_ID = "turn_id"
# How far either side of the launch moment a stamp places nothing: the CLI stamps its lines to the millisecond, so a
# line stamped that close to the launch could have been written just before it or just after.
_LAUNCH_WINDOW = timedelta(milliseconds=1)


@dataclass(frozen=True)
class Invocation:
    """What the exit knows of the process whose requests are collected.

    `session_id` is the thread the run returned, `resumed` whether it resumed one rather than starting it, and
    `launched_at` the moment the tracked spawn observed just before launching it, in UTC.
    """

    session_id: str | None
    resumed: bool
    launched_at: datetime | None


def stdout_turns(stdout: str, limits: request_scan.CollectionLimits) -> int | None:
    """How many turns this process's stdout says it started; None where a line the scan left unread could be one."""
    scan = request_scan.scan_events(stdout, limits)
    if scan.gaps:
        return None
    kinds = [event.get(TYPE) for _, event in scan.events]
    return kinds.count(_TURN_STARTED)


def stamped(
    event: dict[str, Any],
    metadata: request_scan.Metadata,
) -> tuple[str | None, datetime | None]:
    """The stamp a line was written at, as written and as a UTC moment; a stamp no moment reads as is malformed."""
    written = metadata.text(event.get(_TIMESTAMP))
    if written is None:
        return None, None
    try:
        moment = datetime.fromisoformat(written)
    except ValueError:
        moment = None
    if moment is None or moment.tzinfo is None:
        metadata.malformed += 1
        return written, None
    return written, moment.astimezone(UTC)


def names_session(event: dict[str, Any], session_id: str | None) -> bool:
    """Whether a line is a `session_meta` naming `session_id` as its own thread."""
    payload = event.get(PAYLOAD)
    if event.get(TYPE) != SESSION_META or not isinstance(payload, dict):
        return False
    return session_id is not None and payload.get("id") == session_id


@dataclass
class Timeline:
    """Where an invocation's lines begin in its log, read a line at a time, and what would leave that unproven.

    `pending` counts the unstamped lines read since the last line stamped before the launch, while no boundary is
    found, and `unplaced` the lines nothing places on either side of the boundary.
    """

    invocation: Invocation
    identified: bool = False
    read_any: bool = False
    boundary: int | None = None
    latest: datetime | None = None
    regressed: bool = False
    pending: int = 0
    unplaced: int = 0

    def place(self, position: int, event: dict[str, Any], moment: datetime | None) -> bool:
        """Read one line's identity and stamp in; whether it is the invocation's own."""
        if not self.read_any:
            self.read_any = True
            self.identified = position == 0 and names_session(event, self.invocation.session_id)
        if moment is None:
            self.pending += self.boundary is None
        else:
            self._stamped(position, moment)
        return self.boundary is not None

    def writer_version(self, payload: dict[str, Any], metadata: request_scan.Metadata) -> str | None:
        """The CLI version the log's `session_meta` names, where the invocation is the process that wrote it.

        Only the process that created the log wrote its `session_meta`, so a resumed one's version is not in it.
        """
        version = metadata.text(payload.get("cli_version"))
        return None if self.invocation.resumed else version

    def refusal(self, root_turns: int, stdout_turn_count: int | None, whole: bool) -> str | None:
        """Why nothing in the log can be attributed to the invocation, or None where both proofs hold.

        `root_turns` counts the root turns the log opened from the boundary on, `stdout_turn_count` the turns stdout
        says the process started -- None where that is not to be compared -- and `whole` whether the read reached the
        log's end, past which an unstamped line still pending could not have been proven earlier anyway.
        """
        if not self.identified:
            return coverage.NATIVE_IDENTITY_UNPROVEN
        unplaced = self.unplaced + self.pending * whole
        created_here = self.boundary == 0
        if self.regressed or unplaced or created_here == self.invocation.resumed:
            return coverage.INVOCATION_UNATTRIBUTED
        if stdout_turn_count is not None and stdout_turn_count != root_turns:
            return coverage.INVOCATION_UNATTRIBUTED
        return None

    def _stamped(self, position: int, moment: datetime) -> None:
        """Place one stamped line, and with it the unstamped ones read since the last line placed earlier."""
        if self.latest is not None and moment < self.latest:
            self.regressed = True
        self.latest = moment
        launched = self.invocation.launched_at
        if self.boundary is not None or launched is None:
            return
        if moment < launched - _LAUNCH_WINDOW:
            # An earlier invocation's line, so every unstamped line before it was written earlier still.
            self.pending = 0
            return
        unplaced = moment <= launched + _LAUNCH_WINDOW
        if not unplaced:
            self.boundary = position
        self.unplaced += self.pending + unplaced
        self.pending = 0


@dataclass(frozen=True)
class Turn:
    """One open turn: its id, the turn it was started from where it is a child, and whether the invocation opened it."""

    turn_id: str | None
    parent_turn_id: str | None
    own: bool

    @property
    def branch(self) -> str | None:
        """The branch its requests are kept under: its own where it is a child, the thread's otherwise."""
        return None if self.parent_turn_id is None else self.turn_id

    @property
    def unnamed_child(self) -> bool:
        """Whether it is a child turn naming no id, whose requests no branch can be kept under."""
        return self.parent_turn_id is not None and self.turn_id is None


@dataclass
class Turns:
    """The turns open as the log is read, the child turns it named, and the root turns the invocation opened."""

    limits: request_scan.CollectionLimits
    metadata: request_scan.Metadata
    open: list[Turn] = field(default_factory=list)
    children: set[str] = field(default_factory=set)
    own_children: set[str] = field(default_factory=set)
    root_turns: int = 0
    unclosed: int = 0
    unnamed: int = 0
    overflowed: bool = False

    def start(self, payload: dict[str, Any], own: bool) -> None:
        """Open the turn a `task_started` names: a root turn abandoning every open one, or a child beside them.

        A child turn already open is opened once, however often its start repeats. Past the child turn bound -- on
        the children named, or on the ones open at once -- no later request can be told apart from its parent's, so
        none is attributed from there on.
        """
        turn_id = self.metadata.text(payload.get(_TURN_ID))
        turn = Turn(turn_id, self._parent(payload), own)
        if turn.parent_turn_id is None:
            self.abandon()
            self.root_turns += own
            self.open = [turn]
        elif turn in self.open:
            return
        elif self._registered(turn):
            self.open.append(turn)
        else:
            self.overflowed = True

    def close(self, payload: dict[str, Any]) -> None:
        """Close the turn a `task_complete` or `turn_aborted` names."""
        turn_id = self.metadata.text(payload.get(_TURN_ID))
        if turn_id is not None:
            self.open = [turn for turn in self.open if turn.turn_id != turn_id]

    def current(self, own: bool) -> Turn | None:
        """The innermost open turn a line belongs to; for the invocation's own line, only a turn it opened itself."""
        if not self.open or (own and not self.open[-1].own):
            return None
        return self.open[-1]

    def abandon(self) -> None:
        """Count the invocation's root turns still open as never closed, and close every open turn."""
        open_roots = [turn for turn in self.open if turn.parent_turn_id is None]
        self.unclosed += sum(turn.own for turn in open_roots)
        self.open = []

    def _parent(self, payload: dict[str, Any]) -> str | None:
        """The turn a `task_started` names as the one it was started from, where its attribution names one."""
        attribution = payload.get("turn_attribution")
        if not isinstance(attribution, dict):
            return None
        return self.metadata.text(attribution.get("parent_turn_id"))

    def _registered(self, turn: Turn) -> bool:
        """Note a child turn within the child turn bound; False past it.

        One naming no id is open, but no branch can keep its requests, so the invocation's is counted as unnamed.
        """
        if len(self.open) > self.limits.branches:
            return False
        if turn.turn_id is None:
            self.unnamed += turn.own
            return True
        full = len(self.children) >= self.limits.branches
        if full and turn.turn_id not in self.children:
            return False
        self.children.add(turn.turn_id)
        if turn.own:
            self.own_children.add(turn.turn_id)
        return True
