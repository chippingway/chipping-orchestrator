# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which lines of a Codex native session log one invocation wrote, whether the log is the session's own at all, and
the turn each of them settles usage in.

A fresh `codex exec` opens its session log with a `session_meta` line naming the thread it started (`id`), and every
`exec resume` of the session appends to that same file -- under the date the session began, whatever date it is
resumed on -- writing no new `session_meta`, only a `task_started` for the turn it runs. Nothing in the log says
where one process's lines end and the next one's begin, so the log is held to two proofs before anything in it is
attributed to an invocation.

Its identity: the first line has to be a `session_meta` naming the session the run returned as its own thread. A log
found under another name, or one whose first line was unreadable, is never adopted, and nor is any where the run
returned an empty id, which names no session.

Its boundary: nothing in the log says where one process's lines end, so the caller hands over what the log held when
the process was launched (`Invocation`). A fresh run's log did not exist yet, so every line of it is the run's own. A
resumed run's held some number of whole lines, counted at the launch, and the log only ever grows by appending, so the
invocation's lines are exactly the ones past that count -- however its lines are stamped, a line stamped in the
launch's own millisecond, or one with no stamp at all, included. A resumed run with no such count, or one below a
single line -- a log that held none, which no resume continues, or a count no log holds -- is placed by nothing, and
so is one whose log, read whole, holds fewer lines than the count: the log the count was taken of is not the one
read.

The CLI also stamps every line with the time it wrote it, to the millisecond, off the host clock the launch moment is
read from, and every stamp is held against that placement: a line of the invocation's stamped more than a millisecond
before the launch, or an earlier line stamped more than a millisecond after it, means the clock moved under the log --
an earlier invocation's line, say, stamped later than a launch the clock stepped back to -- so nothing in the log is
attributed; so does a stamp earlier than the one before it, anywhere in the log. Where stdout was read whole, the log
may open no more root turns from the boundary on than stdout counts `turn.started` lines -- none, where stdout printed
none -- so a turn some other process appended meanwhile is never taken for one of this run's, whatever the log's read
left out, since a line left unread hides a turn rather than adds one; and where the log was read whole too, no fewer, a
turn whose parentage is unproven counted either way. A stdout with a line the scan could not read could have printed one
more, so it is held to nothing. Stdout is read for its `turn.started` lines alone: the running sum its `turn.completed`
prints is no evidence of any request. Usage the invocation's lines settle in no turn they opened, where the turns open
are known, was written by another process past the count (`request_codex_turns`), and nothing is attributed either.

`NativeScope` reads the log a line at a time as its reader hands it over, never holding more than one: it decodes each
line strictly into the scan it shares with that reader, places it, and follows the turns it opens or closes and the
turn each usage line settles in, so which lines are the invocation's and which turns they settle in are known without
reading the usage they report. Its `refusal` is the admission: why nothing in the log can be attributed to the
invocation, or None where both proofs hold. Where either fails, nothing is attributed; no suffix of the log is ever
guessed. Only the process that created the log wrote its `session_meta`, so only a fresh run is the one whose CLI
version it names. The scope is dormant: nothing in the runtime looks a log up or reads one, and only the dormant
collector in `request_codex` calls it.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from orchestrator.observability.usage import request_coverage as coverage, request_scan
from orchestrator.observability.usage.request_codex_turns import TURN_ID, Turn, Turns

SESSION_META = "session_meta"
PAYLOAD = "payload"
TYPE = "type"
EVENT_MSG = "event_msg"
TURN_CONTEXT = "turn_context"
USAGE_RECORD = "token_usage_record"
TASK_STARTED = "task_started"
TOKEN_COUNT = "token_count"
_TIMESTAMP = "timestamp"
_TURN_STARTED = "turn.started"
_CLOSES = frozenset(("task_complete", "turn_aborted"))
# Where a usage record names the turn it settles in.
_RECORD_TURN = ((TURN_ID,),)
# The kinds of line whose payload a reading of the log takes; every other kind is read for its kind alone.
_READ = frozenset((SESSION_META, TURN_CONTEXT, EVENT_MSG))
# How far either side of the launch moment a stamp contradicts nothing: the CLI stamps its lines to the millisecond, so
# a line stamped that close to the launch could have been written just before it or just after.
_LAUNCH_WINDOW = timedelta(milliseconds=1)
# The gaps that leave a read short of the whole log, so the turns it found are not all the invocation opened, and the
# lines it reached are not all the log holds -- a reader passing an overlong line over hands it to no one, so a last one
# goes uncounted.
_CUT = frozenset((coverage.SCAN_LIMIT, coverage.NATIVE_READ_INTERRUPTED, coverage.OVERSIZE_LINES))


@dataclass(frozen=True)
class Invocation:
    """What the exit knows of the process whose lines are scoped.

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
        """The line the invocation's own begin at: the first, for a fresh run's log, else the first past the count.

        A resumed run's count has to be of one line or more: none taken, or one below that, places no line.
        """
        if not self.invocation.resumed:
            return 0
        counted = self.invocation.prior_lines
        return counted if counted is not None and counted > 0 else None

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
        return bool(session_id) and payload.get("id") == session_id

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


class Envelope(NamedTuple):
    """What one line is read as: its kind, the name of the event it carries where it is one, and its payload."""

    kind: str
    name: str | None
    payload: dict[str, Any]

    @classmethod
    def of(cls, event: dict[str, Any]) -> Envelope | None:
        """A line's envelope, or None where nothing of it can be read: no kind, no payload object, or no event name.

        A line of a kind whose payload is not read -- a `compacted` line, a `response_item`, a usage record -- is its
        kind alone.
        """
        kind = event.get(TYPE)
        payload = event.get(PAYLOAD)
        if not isinstance(kind, str):
            return None
        if kind not in _READ:
            return cls(kind, None, {})
        if not isinstance(payload, dict):
            return None
        name = payload.get(TYPE) if kind == EVENT_MSG else kind
        return cls(kind, name, payload) if isinstance(name, str) else None


class Line(NamedTuple):
    """One line read in: where it sits in the log, whether the invocation wrote it, and the stamp it was written at.

    `event` is what it decoded to and `envelope` what that is read as -- None where nothing of it can be read -- and
    `lost` whether turn knowledge was lost at it: its envelope unreadable, or a line before it the scan left unread.
    `settled` is the turn a usage line settles in -- `UNPLACED` where it settles in none: nothing tells overlapping
    turns apart, its record names a turn by an id this reading refused, or which turns are open is lost -- and None for
    one settling in the thread with no turn open, as for any line settling no usage.
    """

    position: int
    own: bool
    stamp: str | None
    event: dict[str, Any]
    envelope: Envelope | None
    lost: bool = False
    settled: Turn | None = None


@dataclass
class NativeScope:
    """One invocation's scope over its native session log, read a line at a time.

    `scan` is shared with the reader handing the lines over, which records in it any bound that stopped its read, so
    the lines are decoded and counted where the reader's own gaps are; `unread` is how many lines the scan had left
    unread when the last line was read.
    """

    timeline: Timeline
    turns: Turns
    scan: request_scan.EventScan
    metadata: request_scan.Metadata
    unread: int = 0

    @classmethod
    def of(cls, invocation: Invocation, scan: request_scan.EventScan | None = None) -> NativeScope:
        """A scope over `invocation`'s log, decoding into the `scan` its reader shares, held to the bounds that scan was
        opened with, or, where the reader shares none, into one of its own held to the bounds in force.
        """
        decoded = scan or request_scan.EventScan(request_scan.current_limits())
        metadata = request_scan.Metadata(decoded.limits.metadata_chars)
        return cls(Timeline(invocation), Turns(decoded.limits, metadata), decoded, metadata)

    def read(self, position: int, raw_line: str) -> Line | None:
        """Read in one line the reader hands over, numbered by its place in the log; None where it holds no event.

        Every line handed over extends how far the log reached, decoded or not. A line no reading could place -- one
        the scan left unread, or whose envelope nothing can be read off -- could have opened or closed any turn, so
        turn knowledge is lost at it; a line the scan left unread is noticed once the line after it is placed, before
        that one is read as anything.
        """
        self.timeline.extent = max(self.timeline.extent, position + 1)
        event = self.scan.counted(raw_line)
        if event is None:
            return None
        line = self._placed(position, event)
        if line.lost:
            self.unread = self.scan.unread_lines
            self.turns.lost = True
        if line.envelope is None:
            return line
        return line._replace(settled=self._settled(line, line.envelope))

    def refusal(self, stdout: str) -> str | None:
        """Why nothing in the log can be attributed to the invocation, or None where both proofs hold, the root turns
        the log opened held to the ones the invocation's own `stdout` says it started.

        Where stdout was read whole, the log opening more root turns past the boundary than stdout started -- none
        included -- means another process's turn is among them, whatever the log's read left out, since a line left
        unread hides a turn rather than adds one. Fewer, counting a turn whose parentage is unknown as a root, mean one
        is missing only where the log was read whole too: a read cut short, or a line the scan could not read, could
        have held it.
        """
        partial = bool(_CUT.intersection(self.scan.gaps))
        counted = stdout_turns(stdout, self.scan.limits)
        miscounted = False
        if counted is not None:
            whole = not (partial or self.scan.unread_lines)
            ceiling = self.turns.root_turns + self.turns.uncertain if whole else counted
            miscounted = not self.turns.root_turns <= counted <= ceiling
        return self.timeline.refusal(self.turns, miscounted=miscounted, partial=partial)

    def _placed(self, position: int, event: dict[str, Any]) -> Line:
        """The line `event` was read off: its stamp held against where it is placed, and its envelope read."""
        stamp, moment = stamped(event, self.metadata)
        own = self.timeline.place(position, event, moment)
        envelope = Envelope.of(event)
        lost = envelope is None or self.scan.unread_lines != self.unread
        return Line(position, own, stamp, event, envelope, lost)

    def _settled(self, line: Line, envelope: Envelope) -> Turn | None:
        """Open or close the turn a line names, and the turn a usage line settles in.

        A usage record is still a request settled where its payload is no object, so it settles in the innermost open
        turn, as one naming no turn does, while one naming a turn by an id this reading refused names one nothing can
        tell. A `token_count` whose `info` is null is a notification carrying no usage, such as a rate-limit update,
        and settles nothing.
        """
        if envelope.kind == USAGE_RECORD:
            named = self.metadata.first_text(line.event.get(PAYLOAD), _RECORD_TURN)
            return self.turns.current(line.own, named)
        if envelope.name == TASK_STARTED:
            self.turns.start(envelope.payload, line.own)
        elif envelope.name in _CLOSES:
            self.turns.close(envelope.payload)
        elif envelope.name == TOKEN_COUNT and envelope.payload.get("info") is not None:
            return self.turns.current(line.own, report=True)
        return None
