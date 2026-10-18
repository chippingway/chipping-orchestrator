# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick staged ahead of a base rewrite's recovery proof, kept across the writes that proof lands.

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
proof itself left staged keeps the proof's staging.

A checkout gone from disk leaves the proof nothing to read the landing over,
so what the tick holds for the landed head is retired as over a reset
(`rewrite_landing_retirement.retires_over_the_reset`) and landed at once in a
guarded write of its own (`lands_the_retirement`), rather than staged for a
write behind that a quiet hold, a park already standing, or another road's
refusal never makes. Nothing behind a quiet hold proves that evidence again,
so the comment is read afresh behind the write that landed, and evidence it
retired found put back there is retired once more, or its movement recorded,
and the tick held.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

from github.Issue import Issue

from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedEdit, PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_readings as _readings,
    verification_durable as _durable,
)

# The edits that may have carried what they sent onto the comment: landed, or sent with the answer lost.
_MAY_HAVE_LANDED = frozenset((PinnedEdit.EDITED, PinnedEdit.UNCONFIRMED))

# The write a retirement over a checkout gone from disk rides, logged -- and
# the last, over the comment read afresh behind one that landed or was refused for room.
_GONE = "in a write of its own, the checkout it was captured on gone"

_LAST = f"{_GONE}, asked once more over the comment read afresh, holding"


class _KeepsWhatItCarried:
    """`gh` for one proof: every call passed through, the fields each edit of the issue's comment moved kept."""

    def __init__(self, gh: GitHubClient, issue_number: int, carried: set[str]) -> None:
        self._gh = gh
        self._issue_number = issue_number
        self._carried = carried

    def __getattr__(self, name: str):
        return getattr(self._gh, name)

    def edit_pinned_state(self, issue: Issue, state: PinnedState, **options) -> PinnedEdit:
        """The strict edit, sent through; what it moved over its comment kept where it may have landed."""
        edit = self._gh.edit_pinned_state(issue, state, **options)
        if issue.number == self._issue_number and edit in _MAY_HAVE_LANDED:
            over = options.get("over") or {}
            self._carried.update(_moved(state.data, over))
        return edit


@contextmanager
def keeps_the_staging(
    context: _AutoRebaseRecoveryContext, *, ahead: bool = True,
) -> Iterator[_AutoRebaseRecoveryContext]:
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
    if not ahead:
        _lays(state, read, _moved(staged, read))
    try:
        yield replace(context, gh=_KeepsWhatItCarried(context.gh, context.issue.number, carried))
    finally:
        if ahead or not carried:
            _restages(state, staged, read, carried)


def lands_the_retirement(
    context: _AutoRebaseRecoveryContext, write: _commits.ReportWrite, held: frozenset[str] | None = None, *,
    behind: bool = False,
) -> bool:
    """Retire what `context.state` holds for the landed head, its checkout gone, landed as `write`; whether it did.

    Retired as over a reset, and landed over the comment the tick read; a
    write refused or never confirmed has the fields `write` is decided on laid
    from the comment read afresh -- a base tip another road put back, or a
    record it moved, kept as that road wrote it -- and is retired and landed
    once more over that. One that landed has them laid from the comment read
    afresh behind it too, since nothing behind a quiet hold proves the
    evidence again: evidence another road put back there is retired once
    more, or its movement recorded, and the answer is False, for the git
    owner to hold the tick. One refused for room is asked once more over that
    comment read whole, so where it has no room the base tip is blanked in a
    shrinking write of its own as the record of the movement, and the tick
    held the same way. Only while the comment carries nothing for the
    head under a receipt the tick did not hold, and the attempt `context`
    recovers: a successor another road settled is left for its own proof, and
    another attempt for its own recovery, both answered False before anything
    is read as retired. True where nothing the tick held stands any more. A
    state nothing was read into is staged only, for the whole-state write
    behind it. `held` is the receipts the first write was asked over, and
    `behind` says the reading follows a write that landed or was refused for
    room, and is the last.
    """
    asked = _retirement.receipts(context.state) if held is None else held
    if context.state.synced is None:
        return _retirement.retires_over_the_reset(context, _GONE)
    standing = _retirement.receipts(context.state)
    if standing - asked or not _readings.stands_as_recovered(context):
        return False
    if not standing & asked:
        return True
    return _lands(context, write, asked, again=held is None, behind=behind)


def _lands(
    context: _AutoRebaseRecoveryContext, write: _commits.ReportWrite, asked: frozenset[str], *, again: bool,
    behind: bool,
) -> bool:
    """Retire what `context.state` holds as over a reset, land it as `write`, and read the comment afresh behind it.

    Read afresh behind a write that landed, one refused and asked `again`,
    or one refused for room, whose last asking runs over that reading whole.
    With no room for its history the evidence stays current, its base tip
    blanked as the record of its movement, so the reading behind blanks a tip
    put back there once more and holds. False `behind` a write that landed or
    was refused for room, or where the comment would not read afresh.
    """
    _retirement.retires_over_the_reset(context, _LAST if behind else _GONE)
    commit = _commits.ReportCommit(context.gh, context.issue, context.state)
    outcome = commit.lands(context.state, write)
    full = outcome.refusal in _commits._ROOM
    landed = outcome.status is _commit_models.CommitStatus.COMMITTED
    if behind or not (landed or again or full):
        return False
    durable = _durable.durable_comment(context.gh, context.issue, context.state)[0]
    if durable is None:
        return False
    if full:
        return lands_the_retirement(replace(context, state=durable), write, asked, behind=True)
    _lays(context.state, durable.data, write.decided_on)
    _commit.takes_in(context.state, durable.data, write.decided_on)
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
