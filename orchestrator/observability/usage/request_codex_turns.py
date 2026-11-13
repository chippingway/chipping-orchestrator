# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The turns a Codex native session log opens, which of them an invocation opened, and the turn each usage line settles
in, within the child turn bound.

A `task_started` opens a turn. One whose `turn_attribution` names a `parent_turn_id` is a child turn run inside the log,
its requests a branch of their own; one naming none is a root turn of the session's own thread, and opening it abandons
every turn still open, since the thread has moved on -- a turn an earlier process left unfinished is never taken for
this one's. A `task_complete` or `turn_aborted` closes the turn it names, and a turn the invocation opened that none
closed -- a child turn its parent finished without included -- never finished. A `turn_attribution` that is no object,
or names a parent this reading could not read, is malformed metadata and leaves the turn's parentage unproven: it
abandons no open turn, and no request settles in it.

A usage line settles in a turn. A usage record settles in the open turn it names, else in the innermost open one; a
`token_count` in the turn the usage records written since the last report name, where that turn is still open, or else
in the one open turn: a record whose turn closed since tells nothing of it. Where several are open -- a parent and its
child included -- and no record names one, or records name two still open, nothing tells which turn the report is, and
it is placed in none (`UNPLACED`); so is a record naming a turn whose id this reading refused -- no string, or one too
long to keep -- which is no record naming none, and the report after it. The
invocation opens its own turns before it settles any usage in them, so its usage settled in no turn it opened -- none
open at all, the innermost open one being an earlier process's, a turn left unfinished, say, that a resume printing no
turn never replaced, or a usage record naming a turn the invocation never opened -- and a child turn it starts from a
turn it did not open were written by another process past the count its launch took, which `Turns.intruded` records.

A line no reading could place could have opened or closed any turn, the invocation's own root turn included, so past it
which turns are open is unknown (`Turns.lost`): no usage record or report is placed in any, and neither a usage line nor
a child turn's start proves another process wrote it, until a root turn opens, leaving itself alone open. What is kept
stays bounded: a child turn's start repeated opens it once, and past `MAX_BRANCHES` child turns named, or open at once,
no later child turn is kept, which `Turns.overflowed` records. A turn refused could make any request after it, its
parent's own included, so from there on no usage line is placed in any turn, and no child turn's start -- one of the
refused turn's, say -- is taken for another process's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.usage import request_scan

TURN_ID = "turn_id"


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
        """Whether its attribution named a parent this reading could not read: neither root nor child is proven."""
        return self.parent_turn_id == request_scan.REFUSED


# What a `token_count` settles in where nothing tells which of several open turns is its own.
UNPLACED = Turn(None, None, own=False)


@dataclass
class Records:
    """The turns the usage records since the last `token_count` named, which that report's request settled in.

    The CLI writes a request's usage record just before the `token_count` reporting it, while its turn is open, so the
    turn a record names is the one its report belongs to -- unless records naming two turns still open came before one
    report, which leaves it unknown. A record naming a turn closed since is one whose report never came, and tells
    nothing of a later one, so only the records naming a turn still open are kept: never more than the turns open.
    Where no record names one, only a single open turn places a report.
    """

    named: list[Turn] = field(default_factory=list)
    refused: bool = False

    def note(self, turn: Turn, opened: list[Turn]) -> None:
        """Note a record naming `turn`, among the records before it naming a turn still `opened`."""
        live = [kept for kept in self.named if kept in opened]
        self.named = [*(kept for kept in live if kept != turn), turn]

    def refuse(self) -> None:
        """Note a record naming a turn whose id was refused: nothing tells which turn the report after it settles in."""
        self.refused = True

    def take(self, opened: list[Turn], untracked: bool) -> Turn | None:
        """The turn a `token_count` settles in, the records noted for it spent: the one they named still open, or else
        the one open turn -- `UNPLACED` where they name two still open or one refused, none names one of several open
        turns, a parent and its child included, since any of them could have made the request, or the turns open are
        `untracked`: lost, or past the child turn bound.
        """
        live = [turn for turn in self.named if turn in opened]
        unknown = self.refused or untracked or len(live) > 1
        self.named = []
        self.refused = False
        if unknown or (not live and len(opened) > 1):
            return UNPLACED
        innermost = opened[-1] if opened else None
        settled = live[0] if live else innermost
        return UNPLACED if settled is not None and settled.unplaced else settled


@dataclass
class Turns:
    """The turns open as the log is read, the child turns it named, and the root turns the invocation opened.

    `children` maps each child turn named to the turn it was started from, `own_children` the invocation's own among
    them, `unclosed` counts the invocation's turns abandoned unfinished, `unnamed` its child turns naming no id,
    `refused` its child turns started past the child turn bound, and `uncertain` its turns whose parentage is unproven,
    and `records` correlates usage records with the reports after them. `lost` is whether a line no reading could place
    came since the last root turn opened: it could have opened or closed any turn, so which turns are open is unknown,
    and no usage line is placed in any, nor any line taken for another process's, until a root turn opens; past
    `overflowed`, for the rest of the log.
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
        none is attributed from there on, and the invocation's child turn refused is counted, whether or not a request
        follows it. The invocation starts a child only from a turn it opened, so its child of any other parent -- an
        earlier process's, or one not open -- is another process's, which `intruded` records, unless which turns are
        open is `lost`, since the parent's own start could be the line no reading placed, or `overflowed`, since the
        parent could be a turn the bound refused. A turn whose parentage is
        unproven abandons nothing and settles no request, and the invocation's is `uncertain`: a root turn of its own,
        or not. A root turn leaves itself alone open, which is known again after a line no reading could place.
        """
        turn_id = self.metadata.text(payload.get(TURN_ID))
        turn = Turn(turn_id, self._parent(payload), own)
        if turn.parent_turn_id is None:
            self.abandon()
            self.root_turns += own
            self.open = [turn]
            self.lost = False
            return
        parent = self.named(turn.parent_turn_id)
        foreign_parent = parent is None or not parent.own
        untracked = self.lost or self.overflowed
        if own and foreign_parent and not (turn.unplaced or untracked):
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
        turn_id = self.metadata.text(payload.get(TURN_ID))
        if turn_id is not None:
            self.open = [turn for turn in self.open if turn.turn_id != turn_id]

    def current(self, own: bool, turn_id: str | None = None, report: bool = False) -> Turn | None:
        """The turn a usage line settles in, or None for the thread with no turn open.

        A usage record settles in the open turn it names, noted for the report after it; a `token_count` (`report`)
        in the turn the records before it named, as `Records` takes it -- `UNPLACED` where nothing tells overlapping
        turns apart -- and any other line in the innermost open turn. A record naming a turn whose id was `REFUSED`,
        and the report after it, settle in none, and so does every usage line while which turns are open is `lost`,
        and every one once the child turns `overflowed`.
        The invocation opens its own turns before it settles anything in them, so, where the turns open are known,
        its line settling usage in no turn it opened -- none open at all, an earlier process's, or one it names that is
        not open -- is another process's, appended past the count: `intruded` records it, and the line settles in no
        turn.
        """
        settled = _settling(self, turn_id, report)
        if settled is UNPLACED:
            return settled
        if own and (settled is None or not settled.own):
            self.intruded = True
            return None
        if turn_id is not None and settled is not None:
            self.records.note(settled, self.open)
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


def _settling(turns: Turns, turn_id: str | None, report: bool) -> Turn | None:
    """The turn a usage line names or falls to, before whether the invocation opened it is judged: `UNPLACED` for a
    record naming a turn by a `REFUSED` id, and for any usage line while which turns are open is lost or past the child
    turn bound.
    """
    if turn_id == request_scan.REFUSED:
        turns.records.refuse()
        return UNPLACED
    untracked = turns.lost or turns.overflowed
    if report:
        return turns.records.take(turns.open, untracked)
    if untracked:
        return UNPLACED
    if turn_id is None:
        return turns.open[-1] if turns.open else None
    return turns.named(turn_id)
