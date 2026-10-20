# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick staged ahead of a base rewrite's dormant recovery proof, kept across the writes that proof lands.

The proof a recovery hold or park asks first
(`rewrite_recovery_parks.proves_before_a_park`) may run over a state the tick
already staged on -- a gate's record of the hold, or the tip the git owner
stages back behind a reset git refused -- and each write it lands lays what
landed over that state whole (`report_commits.ReportCommit.lands`).
`keeps_the_staging` stages again behind the proof each such field no strict
edit of the proof's landed, over the comment as the tick read it before --
an equal total another road wrote proves nothing: the record behind lands it
as the tick's own move, refuses it as a conflict where the comment moved it,
and never adds a carried counter twice. A field the proof itself left staged
keeps the proof's staging. Within the proof, each field of the tick's staging
an edit landed is taken in as it spelled it. A write whose answer was lost
lays nothing over the state, and what survives on the comment cannot say
whether it landed, so nothing is read into it: what the tick staged rides the
next write again, which the guarded commit takes over a comment already
carrying it as over one that never did -- every field of it, save a total
that adds up. Sent again over itself, such a total -- usage -- would count
twice, so the proof's writes send none: they are taken off the state for the
proof and land first, ahead of every other write the proof or the reset's
record makes (`adds_the_totals`), in a guarded write of their own, decided
on nothing and added to the total the comment carries then. That write is
read through the client that asks every reading, so what it reads moving is
proved and an attempt any of its readings carries in place of the one
recovered holds the caller, however soon it is put back and however little
evidence is left to prove; a lost answer there takes them as sent, so they
are never sent twice -- save where the comment read afresh carries any of
them short of what that write sent: a total only grows, so that comment
carries none of what the write added, landed or not, however another road
added to it -- and a refusal, or such a lost answer, stages them again behind
the block, for the record behind it.

A checkout gone from disk, or read gone, leaves the proof nothing to read the
landing over, so what the tick holds for it is retired as over a reset
(`rewrite_landing_retirement.retires_over_the_reset`) in a guarded write of
its own (`lands_the_retirement`), asked again over the comment read afresh --
read first where the tick holds nothing, so evidence put back since its
reading is retired too, not left current behind an empty answer.

Both are dormant, as that proof is: no recovery context the workflow builds
reaches them.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

from github.Issue import Issue

from orchestrator.git.base_sync import models as _base_sync_models, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedEdit, PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    rewrite_finish_writes as _writes,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_readings as _readings,
    verification_durable as _durable,
    verification_record_state as _record_state,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence

# The edits that may have carried what they sent onto the comment: landed, or sent with the answer lost; and the
# commits that did.
_MAY_HAVE_LANDED = frozenset((PinnedEdit.EDITED, PinnedEdit.UNCONFIRMED))
_SENT = frozenset((_commit_models.CommitStatus.COMMITTED, _commit_models.CommitStatus.UNCONFIRMED))

# The write a retirement over a checkout gone from disk rides, logged, and the last one asked over a fresh reading.
_GONE = "in a write of its own, the checkout it was captured on gone"

_LAST = f"{_GONE}, asked once more over the comment read afresh, holding"

# The write the totals the tick staged land in ahead of the proof: decided on nothing, since a total another road
# moved meanwhile is added to rather than refused, and owning nothing besides them.
_TOTALS = _commits.ReportWrite(owned=frozenset(), decided_on=frozenset())


class _KeepsWhatItCarried:
    """`gh` for one proof, every call passed through, and what the tick staged before it, kept across its edits.

    That staging is what `context.state` moved off the comment as the tick read it. Ahead of a record it stays on the
    state for the proof, save the totals among it that add up again sent over themselves (`_TOTALS`), which are taken
    off; each field of it an edit of the issue's comment landed is taken in on the state as the edit spelled it, so
    no later write of the proof sends it again, and one whose answer was lost takes in nothing, for the next write to
    send it again. Behind a record all of it is taken off, and `carried` names every field an edit landed or may have.
    """

    def __init__(self, context: _base_sync_models._AutoRebaseRecoveryContext, *, ahead: bool) -> None:
        self._gh = context.gh
        self._issue = context.issue
        self._tick = context.state
        self._ahead = ahead
        self._staged = copy.deepcopy(context.state.data)
        self._read = json.loads(context.state.synced)
        staging = _moved(self._staged, self._read)
        self._moves = frozenset(staging)
        self._staging = frozenset(staging if ahead else ())
        self._totals = frozenset(field for field in self._staging if self._adds_again(field))
        self._lost: Mapping[str, Any] = {}
        self.carried: set[str] = set()
        _lays(self._tick, self._read, self._totals if ahead else staging)

    def __getattr__(self, name: str):
        return getattr(self._gh, name)

    def edit_pinned_state(self, issue: Issue, state: PinnedState, **options) -> PinnedEdit:
        """The strict edit, sent through; what it moved over its comment kept where it landed, or may have.

        What an edit whose answer was lost sent is kept too, for the totals' own write to read the comment afresh
        against (`_never_landed`).
        """
        edit = self._gh.edit_pinned_state(issue, state, **options)
        if issue.number != self._issue.number or edit not in _MAY_HAVE_LANDED:
            return edit
        moved = _moved(state.data, options.get("over") or {})
        if edit is PinnedEdit.UNCONFIRMED:
            self._lost = dict(state.data)
            self.carried.update(moved - self._staging)
            return edit
        self.carried.update(moved)
        _lays(self._tick, state.data, moved & self._staging)
        _commit.takes_in(self._tick, state.data, moved & self._staging)
        return edit

    def restages(self) -> None:
        """Stage again on the state, over the tick's reading, each field it staged that nothing carried or stages now.

        Ahead of a record always; behind one only where no edit of the proof's landed or may have.
        """
        if self.carried and not self._ahead:
            return
        tick = self._tick
        stages_now = _moved(tick.data, json.loads(tick.synced))
        left = sorted(self._moves - self.carried - stages_now)
        _lays(tick, self._staged, left)
        _commit.takes_in(tick, self._read, left)

    def adds_the_totals(self, gh) -> None:
        """Land the totals the tick staged, taken off its state for the block, in a guarded write of their own, once.

        Through `gh`, the block's caller's client that asks every reading, ahead of every other write of the block, so
        what that write reads moving is proved and an attempt put in place meanwhile holds whatever the block answers.
        Over the tick's reading, so the total another road reached meanwhile is added to rather than written over.
        Landed, they are taken in as the comment then carries them; refused, they are staged again behind the block,
        for the record behind it, and so are those sent with the answer lost where the comment read afresh carries any
        of them short of what was sent (`_never_landed`); any other sent with the answer lost is taken as sent, the
        tick's state withheld, so nothing sends them twice.
        """
        tick = self._tick
        moving = sorted(self._totals - self.carried)
        if not moving:
            return
        reading = _readings.RecordsALostCheckout.as_read(tick)
        _lays(reading, self._staged, moving)
        commit = _commits.ReportCommit(gh, self._issue, reading)
        landed = commit.lands(reading, _TOTALS).status
        if landed not in _SENT:
            return
        if landed is _commit_models.CommitStatus.UNCONFIRMED:
            if self._never_landed(gh, moving):
                return
            _lays(tick, self._staged, moving)
            tick.withheld = True
        else:
            _lays(tick, reading.data, moving)
        _commit.takes_in(tick, tick.data, moving)
        self.carried.update(moving)

    def _never_landed(self, gh, totals: list[str]) -> bool:
        """Whether the comment read afresh through `gh` carries any of `totals` short of what the edit whose answer was
        lost sent.

        A total only grows, so a comment that took that edit carries at least as much of each as it sent, whatever
        another road added since; one carrying less of any carries none of what that edit added -- it never landed, or
        another road wrote an older total back over it -- however another road added to it meanwhile, so the totals
        are sent again by a write behind. A comment carrying at least as much of each cannot say whether another road
        added that much meanwhile, and nor can one that would not read: the totals are taken as sent there, so they are
        never added twice.
        """
        fresh = _durable.durable_comment(gh, self._issue, self._tick)[0]
        if fresh is None:
            return False
        carried = [fresh.data.get(total) or 0 for total in totals]
        sent = [self._lost.get(total) or 0 for total in totals]
        return any(
            isinstance(now, int | float) and now < was
            for now, was in zip(carried, sent, strict=True)
        )

    def _adds_again(self, field: str) -> bool:
        """Whether `field` as the tick staged it, sent again over a comment already carrying it, moves on: a total."""
        staged = _commit_models.loaded(_commit_models.spelled(self._staged, field))
        read = _commit_models.loaded(_commit_models.spelled(self._read, field))
        return _commits._both_moves(field, staged, read, staged) != staged


@contextmanager
def keeps_the_staging(
    context: _base_sync_models._AutoRebaseRecoveryContext, *, ahead: bool = True,
) -> Iterator[_base_sync_models._AutoRebaseRecoveryContext]:
    """The context to prove over, what the tick staged kept for a record `ahead` of it, and out of it behind one.

    Ahead of a record, the totals among that staging are taken off the state for the block, so no write of the
    proof's sends them: the block's caller lands them first, in a write of their own (`adds_the_totals`), and
    those that did not land are staged again behind the block.
    Behind a record that did not land, all of it is taken off the state for the block, so no write of the proof's
    carries it, and put back only where no edit of the proof's landed or may have. A context whose client already
    keeps the tick's staging -- a block asked inside another -- is handed back as it is.
    """
    if context.state.synced is None or isinstance(context.gh, _KeepsWhatItCarried):
        yield context
        return
    keeper = _KeepsWhatItCarried(context, ahead=ahead)
    try:
        yield replace(context, gh=keeper)
    finally:
        keeper.restages()


def adds_the_totals(kept: _base_sync_models._AutoRebaseRecoveryContext, into: dict[str, ReportEvidence]) -> bool:
    """Land the totals `kept`'s block took off the tick's state, as the block's first write; whether its attempt stands.

    For the caller of a block ahead of a record (`keeps_the_staging`), before any other request it makes, through a
    client that asks every reading (`rewrite_recovery_readings.AsksEveryReading`), so each comment that write reads
    is read for movement under the evidence the tick holds (`rewrite_landing_retirement.moved_under`), kept in
    `into` for the caller's proof. False where any comment it read carries another attempt in place of the one `kept`
    recovers -- however soon it is put back -- the tick's state withheld, for the caller to hold whatever evidence it
    holds. A context nothing keeps took no totals off, and lands none.
    """
    keeper = kept.gh
    if not isinstance(keeper, _KeepsWhatItCarried):
        return True
    seen: list[PinnedState] = []
    keeper.adds_the_totals(_readings.asks_every_reading(kept, seen.append).gh)
    for reading in seen:
        _retirement.moved_under(reading, tick=kept.state, into=into)
    if all(_readings.stands_as_recovered(kept, read) for read in seen):
        return True
    kept.state.withheld = True
    return False


def lands_the_retirement(
    context: _base_sync_models._AutoRebaseRecoveryContext, write: _commits.ReportWrite,
    held: frozenset[str] | None = None, *, behind: bool = False,
) -> bool:
    """Retire what `context.state` holds for the landed head, its checkout read gone, as `write`; whether it did.

    Retired as over a reset, then asked again over the comment read afresh (`_lands`) -- its decided-on fields and
    every evidence record, a successor's floor and handoff among them, laid behind a write, the whole reading behind
    a refusal for room or a second -- evidence put back retired again, and False.
    A successor or another attempt is left alone, False -- a transaction recorded pending under a receipt the attempt
    does not name among them, its floor kept; True where nothing held stands. Where the tick holds nothing
    at the first asking, the comment is read afresh and laid over its state first, so evidence another road put back
    since the tick's reading is retired rather than left current behind an answer of True; a comment that would not
    read is False. A state nothing was read into is staged only. `held` is the receipts first asked over; `behind`
    marks the last asking.
    """
    asked = _retirement.receipts(context.state) if held is None else held
    if context.state.synced is None:
        return _retirement.retires_over_the_reset(context, _GONE)
    if held is None and not asked:
        durable = _durable.durable_comment(context.gh, context.issue, context.state)[0]
        if durable is not None:
            _lays(context.state, durable.data, write.decided_on | _durable._EVIDENCE_RECORDS)
            _commit.takes_in(context.state, durable.data, write.decided_on | _durable._EVIDENCE_RECORDS)
        fresh = _retirement.receipts(context.state)
        return durable is not None and lands_the_retirement(context, write, fresh)
    standing = set(_retirement.receipts(context.state))
    pending = _record_state.read_pending_evidence(context.state)
    if pending is not None:
        standing.add(pending.receipt)
    if standing - asked or not _readings.stands_as_recovered(context):
        return False
    if not standing & asked:
        return True
    return _lands(context, write, asked, again=held is None, behind=behind)


def _lands(
    context: _base_sync_models._AutoRebaseRecoveryContext, write: _commits.ReportWrite, asked: frozenset[str], *,
    again: bool, behind: bool,
) -> bool:
    """Retire what `context.state` holds as over a reset, land it as `write`, and read the comment afresh behind it.

    With no room for history, or a last asking refused, the evidence stays pending or current, its base tip -- where it
    records one -- blanked in a shrinking write a replacement or successor refuses. False on the last asking, or where
    the comment would not read afresh.
    """
    _retirement.retires_over_the_reset(context, _LAST if behind else _GONE)
    commit = _commits.ReportCommit(context.gh, context.issue, context.state)
    outcome = commit.lands(context.state, write)
    landed = outcome.status is _commit_models.CommitStatus.COMMITTED
    if behind and not landed:
        staged = PinnedState(
            comment_id=context.state.comment_id, state_data=json.loads(context.state.synced),
        )
        if staged.get(_base_sync_state._PENDING_REWRITE_BASE) is not None:
            staged.set(_base_sync_state._PENDING_REWRITE_BASE, None)
            commit.lands(staged, _writes.INVALIDATION)
    if behind:
        return False
    durable = _durable.durable_comment(context.gh, context.issue, context.state)[0]
    if durable is None:
        return False
    if not (landed or again) or outcome.refusal in _commits._ROOM:
        return lands_the_retirement(replace(context, state=durable), write, asked, behind=True)
    _lays(context.state, durable.data, write.decided_on | _durable._EVIDENCE_RECORDS)
    _commit.takes_in(context.state, durable.data, write.decided_on | _durable._EVIDENCE_RECORDS)
    return lands_the_retirement(context, write, asked, behind=landed)


def _lays(state: PinnedState, spelled: Mapping[str, Any], fields: Iterable[str]) -> None:
    """Lay each of `fields` on `state` as `spelled` spells it, dropping one it lacks; nothing is taken in as read."""
    for field in fields:
        state.data.pop(field, None)
        held = _commit_models.loaded(_commit_models.spelled(spelled, field))
        if held is not _commit_models.ABSENT:
            state.set(field, held)


def _moved(
    after: Mapping[str, Any], before: Mapping[str, Any],
) -> set[str]:
    """Every field `after` spells otherwise than `before`, one that either lacks included."""
    spelled = _commit_models.spelled
    return {
        field for field in after.keys() | before.keys()
        if spelled(after, field) != spelled(before, field)
    }
