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
from orchestrator.workflow.engine import pinned_commit as _commit, pinned_commit_models as _commit_models

# The edits that may have carried what they sent onto the comment: landed, or sent with the answer lost.
_MAY_HAVE_LANDED = frozenset((PinnedEdit.EDITED, PinnedEdit.UNCONFIRMED))


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
