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

Its boundary: nothing in the log says where one process's lines end, so the caller hands over what the log held when
the process was launched (`Invocation`). A fresh run's log did not exist yet, so every line of it is the run's own. A
resumed run's held some number of whole lines, counted at the launch, and the log only ever grows by appending, so the
invocation's lines are exactly the ones past that count -- however its lines are stamped, a line stamped in the
launch's own millisecond, or one with no stamp at all, included. A resumed run with no such count, or whose log held
no line at all, is placed by nothing, and so is one whose log, read whole, holds fewer lines than the count: the log
the count was taken of is not the one read.

The CLI also stamps every line with the time it wrote it, to the millisecond, off the host clock the launch moment is
read from, and every stamp is held against that placement: a line of the invocation's stamped more than a millisecond
before the launch, or an earlier line stamped more than a millisecond after it, means the clock moved under the log --
an earlier invocation's line, say, stamped later than a launch the clock stepped back to -- so nothing in the log is
attributed; so does a stamp earlier than the one before it, anywhere in the log. Where stdout was read whole, the log
may open no more root turns from the boundary on than stdout counts `turn.started` lines -- none, where stdout printed
none -- so a turn some other process appended meanwhile is never taken for one of this run's, whatever the log's read
left out, since a line left unread hides a turn rather than adds one; and where the log was read whole too, no fewer, a
turn whose parentage is unproven counted either way. A stdout with a line the scan could not read could have printed one
more, so it is held to nothing.

The invocation opens its own turns before it settles any usage in them, so usage its lines settle in no turn they opened
-- none open at all, the innermost open one being an earlier process's, a turn left unfinished, say, that a resume
printing no turn never replaced, a usage record naming a turn the invocation never opened, or a child turn started from
one -- was written by another process past the count, and nothing is attributed either.

Where either proof fails, the collection names why and attributes nothing; it never guesses a suffix of the log.

Turns. A `task_started` opens a turn. One whose `turn_attribution` names a `parent_turn_id` is a child turn run inside
this log, its requests a branch of their own; one naming none is a root turn of the session's own thread, and opening it
abandons every turn still open, since the thread has moved on -- a turn an earlier process left unfinished is never
taken for this one's. A `task_complete` or `turn_aborted` closes the turn it names, and a turn the invocation opened
that none closed -- a child turn its parent finished without included -- never finished. A `turn_attribution` that is no
object, or names a parent this collection could not read, is malformed metadata and leaves the turn's parentage
unproven: it abandons no open turn, and no request settles in it. A request belongs to the turn the usage record written
just before its report names, where that turn is still open, or else to the one open turn; where several are open -- a
parent and its child included -- and no record names one, nothing tells which the report is, and it is placed in none.
A line this collection could not read could have opened or closed any turn, so past it which turns are open is unknown,
and no report is placed in any until a root turn opens, leaving itself alone open.
"""

from __future__ import annotations

from contextlib import suppress
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
# How far either side of the launch moment a stamp contradicts nothing: the CLI stamps its lines to the millisecond, so
# a line stamped that close to the launch could have been written just before it or just after.
_LAUNCH_WINDOW = timedelta(milliseconds=1)


@dataclass(frozen=True)
class Invocation:
    """What the exit knows of the process whose requests are collected.

    `session_id` is the thread the run returned, `resumed` whether it resumed one rather than starting it,
    `launched_at` a moment just before the process was launched, in UTC, off the clock the CLI stamps its lines by --
    None where none was read -- and `prior_lines` the whole lines a resumed run's log held at that moment -- None where
    nothing counted them.
    """

    session_id: str | None
    resumed: bool
    launched_at: datetime | None
    prior_lines: int | None = None


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
    """The stamp a line was written at, as written and as a UTC moment.

    A stamp no UTC moment reads as -- no ISO moment, one naming no offset, or one whose offset moves it past the range a
    moment holds -- is malformed: it is kept as written, and places nothing.
    """
    written = metadata.text(event.get(_TIMESTAMP))
    if written is None:
        return None, None
    try:
        moment = datetime.fromisoformat(written)
    except ValueError:
        moment = None
    utc = None
    if moment is not None and moment.tzinfo is not None:
        with suppress(OverflowError):
            utc = moment.astimezone(UTC)
    if utc is None:
        metadata.malformed += 1
    return written, utc



@dataclass
class Timeline:
    """Where an invocation's lines begin in its log, read a line at a time, and what would leave that unproven.

    `disagreed` is whether a stamp contradicts where its line is placed, so the clock cannot be trusted with the log,
    and `extent` how many lines the log reached as read, every line handed over counted, decoded or not.
    """

    invocation: Invocation
    identified: bool = False
    read_any: bool = False
    extent: int = 0
    boundary: int | None = None
    latest: datetime | None = None
    regressed: bool = False
    disagreed: bool = False

    @property
    def start(self) -> int | None:
        """The line the invocation's own begin at: the first, for a fresh run's log, else the first past the count."""
        return self.invocation.prior_lines if self.invocation.resumed else 0

    def place(self, position: int, event: dict[str, Any], moment: datetime | None) -> bool:
        """Read one line's identity and stamp in; whether it is the invocation's own."""
        if not self.read_any:
            self.read_any = True
            self.identified = position == 0 and self._names_session(event)
        start = self.start
        own = start is not None and position >= start
        if own and self.boundary is None:
            self.boundary = position
        if moment is not None:
            self._stamped(own, moment)
        return own

    def writer_version(self, payload: dict[str, Any], metadata: request_scan.Metadata) -> str | None:
        """The CLI version the log's `session_meta` names, where the invocation is the process that wrote it.

        Only the process that created the log wrote its `session_meta`, so a resumed one's version is not in it.
        """
        version = metadata.text(payload.get("cli_version"))
        return None if self.invocation.resumed else version

    def refusal(self, turns: Turns, miscounted: bool, partial: bool) -> str | None:
        """Why nothing in the log can be attributed to the invocation, or None where both proofs hold.

        `turns` are the ones the log opened, `miscounted` whether their root turns contradict the ones stdout says the
        process started, and `partial` whether the read may have stopped short of the log's end or passed lines over
        unhanded, so its extent proves nothing.
        """
        if not self.identified:
            return coverage.NATIVE_IDENTITY_UNPROVEN
        if not self.start and self.invocation.resumed:
            return coverage.INVOCATION_UNATTRIBUTED
        if self.regressed or self.disagreed or turns.intruded or self._short(partial):
            return coverage.INVOCATION_UNATTRIBUTED
        if miscounted:
            return coverage.INVOCATION_UNATTRIBUTED
        return None

    def _names_session(self, event: dict[str, Any]) -> bool:
        """Whether a line is a `session_meta` naming the session the run returned as its own thread."""
        payload = event.get(PAYLOAD)
        if event.get(TYPE) != SESSION_META or not isinstance(payload, dict):
            return False
        session_id = self.invocation.session_id
        return session_id is not None and payload.get("id") == session_id

    def _short(self, partial: bool) -> bool:
        """Whether a log read whole holds fewer lines than the count its launch took of it."""
        return not partial and self.extent < (self.start or 0)

    def _stamped(self, own: bool, moment: datetime) -> None:
        """Hold one stamp against the stamp before it and against the side of the launch its line is placed on.

        The launch is compared by how far the stamp lies from it, which no moment in range overflows.
        """
        if self.latest is not None and moment < self.latest:
            self.regressed = True
        self.latest = moment
        launched = self.invocation.launched_at
        if launched is None:
            return
        if own and launched - moment > _LAUNCH_WINDOW:
            self.disagreed = True
        if not own and moment - launched > _LAUNCH_WINDOW:
            self.disagreed = True


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

    @property
    def unplaced(self) -> bool:
        """Whether its attribution named a parent this collection could not read: neither root nor child is proven."""
        return self.parent_turn_id == request_scan.REFUSED


# What a `token_count` settles in where nothing tells which of several open turns is its own.
UNPLACED = Turn(None, None, own=False)


@dataclass
class Records:
    """The turn the usage records since the last `token_count` named, which that report's request settled in.

    The CLI writes a request's usage record just before the `token_count` reporting it, so the turn a record names is
    the one its report belongs to -- unless records naming two turns came before one report, which leaves it unknown.
    Where no record names one, only a single open turn places a report.
    """

    named: Turn | None = None
    conflicted: bool = False

    def note(self, turn: Turn) -> None:
        """Note a record naming `turn`."""
        changed = self.named is not None and self.named != turn
        self.conflicted = self.conflicted or changed
        self.named = turn

    def take(self, opened: list[Turn], lost: bool) -> Turn | None:
        """The turn a `token_count` settles in, the records noted for it spent: the one they named, or else the one
        open turn -- `UNPLACED` where the records conflict, none names one of several open turns, a parent and its
        child included, since any of them could have made the request, or the turns open are `lost`.

        A record and its report are written while their turn is open, so a record naming a turn closed since is one
        whose report never came, and tells nothing of this one.
        """
        named = self.named if self.named in opened else None
        conflicted = self.conflicted or lost
        self.named = None
        self.conflicted = False
        if conflicted or (named is None and len(opened) > 1):
            return UNPLACED
        innermost = opened[-1] if opened else None
        settled = innermost if named is None else named
        return UNPLACED if settled is not None and settled.unplaced else settled


@dataclass
class Turns:
    """The turns open as the log is read, the child turns it named, and the root turns the invocation opened.

    `children` maps each child turn named to the turn it was started from, `refused` counts the child turns the
    invocation started past the child turn bound, and `records` correlates usage records with the reports after them.
    `lost` is whether a line no reading could place came since the last root turn opened: it could have opened or
    closed any turn, so which turns are open is unknown, and no report is placed in any, until a root turn opens.
    """

    limits: request_scan.CollectionLimits
    metadata: request_scan.Metadata
    open: list[Turn] = field(default_factory=list)
    children: dict[str, str] = field(default_factory=dict)
    own_children: set[str] = field(default_factory=set)
    root_turns: int = 0
    unclosed: int = 0
    unnamed: int = 0
    refused: int = 0
    overflowed: bool = False
    intruded: bool = False
    uncertain: int = 0
    lost: bool = False
    records: Records = field(default_factory=Records)

    def start(self, payload: dict[str, Any], own: bool) -> None:
        """Open the turn a `task_started` names: a root turn abandoning every open one, or a child beside them.

        A child turn already open is opened once, however often its start repeats. Past the child turn bound -- on
        the children named, or on the ones open at once -- no later request can be told apart from its parent's, so
        none is attributed from there on, and the invocation's child turn refused is a gap of its own, whether or not
        a request follows it. The invocation starts a child only from a turn it opened, so its child of any other
        parent -- an earlier process's, or one not open -- is another process's, which `intruded` records. A turn
        whose parentage is unproven abandons nothing and settles no request, and the invocation's is `uncertain`: a
        root turn of its own, or not. A root turn leaves itself alone open, which is known again after a line no reading
        could place.
        """
        turn_id = self.metadata.text(payload.get(_TURN_ID))
        turn = Turn(turn_id, self._parent(payload), own)
        if turn.parent_turn_id is None:
            self.abandon()
            self.root_turns += own
            self.open = [turn]
            self.lost = False
            return
        parent = self.named(turn.parent_turn_id)
        foreign_parent = parent is None or not parent.own
        if own and foreign_parent and not turn.unplaced:
            self.intruded = True
        if turn in self.open:
            return
        self.uncertain += own and turn.unplaced
        if self._registered(turn):
            self.open.append(turn)
        else:
            self.overflowed = True
            self.refused += own

    def close(self, payload: dict[str, Any]) -> None:
        """Close the turn a `task_complete` or `turn_aborted` names."""
        turn_id = self.metadata.text(payload.get(_TURN_ID))
        if turn_id is not None:
            self.open = [turn for turn in self.open if turn.turn_id != turn_id]

    def current(self, own: bool, turn_id: str | None = None, report: bool = False) -> Turn | None:
        """The turn a usage line settles in, or None for the thread with no turn open.

        A usage record settles in the open turn it names, noted for the report after it; a `token_count` (`report`)
        in the turn the records before it named, as `Records` takes it -- `UNPLACED` where nothing tells overlapping
        turns apart -- and any other line in the innermost open turn. The invocation opens its own turns before it
        settles anything in them, so its line settling usage in no turn it opened -- none open at all, an earlier
        process's, or one it names that is not open -- is another process's, appended past the count: `intruded`
        records it, and the line settles in no turn.
        """
        if report:
            settled = self.records.take(self.open, self.lost)
        elif turn_id is None:
            settled = self.open[-1] if self.open else None
        else:
            settled = self.named(turn_id)
        if settled is UNPLACED:
            return settled
        if own and (settled is None or not settled.own):
            self.intruded = True
            return None
        if turn_id is not None and settled is not None:
            self.records.note(settled)
        return settled

    def named(self, turn_id: str | None) -> Turn | None:
        """The open turn naming `turn_id`: the thread's root turn, or a child turn beside it; None where none does."""
        if turn_id is None:
            return None
        opened = [turn for turn in self.open if turn.turn_id == turn_id]
        return opened[0] if opened else None

    def abandon(self) -> None:
        """Count the invocation's turns still open as never closed, and close every open turn.

        A child turn its parent finished without is as unfinished as a root turn no line closed, whatever requests
        it settled before.
        """
        self.unclosed += sum(turn.own for turn in self.open)
        self.open = []

    def _parent(self, payload: dict[str, Any]) -> str | None:
        """The turn a `task_started` names as the one it was started from: None where its attribution names none, and
        `REFUSED` where it is no object or names one no string or too long to keep, a parentage left unproven.
        """
        attribution = payload.get("turn_attribution")
        if attribution is None:
            return None
        if not isinstance(attribution, dict):
            self.metadata.malformed += 1
            return request_scan.REFUSED
        named = attribution.get("parent_turn_id")
        if named is None or named == "":
            return None
        return self.metadata.text(named) or request_scan.REFUSED

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
        self.children[turn.turn_id] = turn.parent_turn_id
        if turn.own and not turn.unplaced:
            self.own_children.add(turn.turn_id)
        return True
