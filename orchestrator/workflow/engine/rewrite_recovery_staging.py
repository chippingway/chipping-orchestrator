# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick staged ahead of a base rewrite's dormant recovery proof, kept across the writes that proof lands.

The proof a recovery hold or park asks first
(`rewrite_recovery_parks.proves_before_a_park`) may run over a state the tick
already staged on -- a gate's record of the hold, or the tip the git owner
stages back behind a reset git refused -- and each write it lands lays what
landed over that state whole (`report_commits.ReportCommit.lands`).
`keeps_the_staging` stages again behind the proof each such field no strict
edit of the proof's carried, landed or unconfirmed, over the comment as the
tick read it before -- an equal total another road wrote proves nothing: the
record behind lands it as the tick's own move, refuses it as a conflict where
the comment moved it, and never adds a carried counter twice. A field the
proof itself left staged keeps the proof's staging. Within the proof, a
write whose answer was lost lays nothing over the state, so each field of
the tick's staging such an edit carried is taken in as it spelled it, and no
later write of the proof sends it -- usage among it -- a second time.

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
)

# The edits that may have carried what they sent onto the comment: landed, or sent with the answer lost.
_MAY_HAVE_LANDED = frozenset((PinnedEdit.EDITED, PinnedEdit.UNCONFIRMED))

# The write a retirement over a checkout gone from disk rides, logged, and the last one asked over a fresh reading.
_GONE = "in a write of its own, the checkout it was captured on gone"

_LAST = f"{_GONE}, asked once more over the comment read afresh, holding"


class _KeepsWhatItCarried:
    """`gh` for one proof: every call passed through, the fields each edit of the issue's comment moved kept.

    `staging` is what the tick staged on `context.state` before the proof: each of those an edit may have landed --
    one whose answer was lost included -- is taken in on that state as the edit spelled it, so no later write of the
    proof sends it again, a counter added twice among it.
    """

    def __init__(
        self, context: _base_sync_models._AutoRebaseRecoveryContext, carried: set[str], staging: frozenset[str],
    ) -> None:
        self._gh = context.gh
        self._issue_number = context.issue.number
        self._tick = context.state
        self._carried = carried
        self._staging = staging

    def __getattr__(self, name: str):
        return getattr(self._gh, name)

    def edit_pinned_state(self, issue: Issue, state: PinnedState, **options) -> PinnedEdit:
        """The strict edit, sent through; what it moved over its comment kept where it may have landed."""
        edit = self._gh.edit_pinned_state(issue, state, **options)
        if issue.number == self._issue_number and edit in _MAY_HAVE_LANDED:
            over = options.get("over") or {}
            moved = _moved(state.data, over)
            self._carried.update(moved)
            _lays(self._tick, state.data, moved & self._staging)
            _commit.takes_in(self._tick, state.data, moved & self._staging)
        return edit


@contextmanager
def keeps_the_staging(
    context: _base_sync_models._AutoRebaseRecoveryContext, *, ahead: bool = True,
) -> Iterator[_base_sync_models._AutoRebaseRecoveryContext]:
    """The context to prove over, what the tick staged kept for a record `ahead` of it, and out of it behind one.

    Behind a record that did not land, that staging is taken off the state for
    the block, so no write of the proof's carries it, and put back only where
    no edit of the proof's landed or may have.
    """
    state = context.state
    if state.synced is None:
        yield context
        return
    staged = copy.deepcopy(state.data)
    read = json.loads(state.synced)
    carried: set[str] = set()
    staging = frozenset(_moved(staged, read) if ahead else ())
    if not ahead:
        _lays(state, read, _moved(staged, read))
    try:
        yield replace(context, gh=_KeepsWhatItCarried(context, carried, staging))
    finally:
        if ahead or not carried:
            _restages(state, staged, read, carried)


def lands_the_retirement(
    context: _base_sync_models._AutoRebaseRecoveryContext, write: _commits.ReportWrite,
    held: frozenset[str] | None = None, *, behind: bool = False,
) -> bool:
    """Retire what `context.state` holds for the landed head, its checkout read gone, as `write`; whether it did.

    Retired as over a reset, then asked again over the comment read afresh (`_lands`) -- its decided-on fields and
    every evidence record, a successor's floor and handoff among them, laid behind a write, the whole reading behind
    a refusal for room or a second -- evidence put back retired again, and False.
    A successor or another attempt is left alone, False; True where nothing held stands. Where the tick holds nothing
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
    standing = _retirement.receipts(context.state)
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

    With no room for history, or a last asking refused, the evidence stays current, its base tip blanked in a shrinking
    write a replacement or successor refuses. False on the last asking, or where the comment would not read afresh.
    """
    _retirement.retires_over_the_reset(context, _LAST if behind else _GONE)
    commit = _commits.ReportCommit(context.gh, context.issue, context.state)
    outcome = commit.lands(context.state, write)
    landed = outcome.status is _commit_models.CommitStatus.COMMITTED
    if behind and not landed:
        staged = PinnedState(
            comment_id=context.state.comment_id, state_data=json.loads(context.state.synced),
        )
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


def _restages(
    state: PinnedState,
    staged: Mapping[str, Any],
    read: Mapping[str, Any],
    carried: set[str],
) -> None:
    """Stage again on `state`, over `read`, each field `staged` moved that nothing carried or stages now."""
    if state.synced is None:
        return
    synced = json.loads(state.synced)
    left = _moved(staged, read) - carried - _moved(state.data, synced)
    fields = sorted(left)
    _lays(state, staged, fields)
    _commit.takes_in(state, read, fields)


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
