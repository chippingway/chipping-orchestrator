# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkpoints one auto-rebase attempt's road makes over the reading its tick last confirmed.

A road reads the attempt and the verification evidence it guards once, under
the issue writer claim its caller took before that reading
(`workflow/engine/base_refresh.py`, and the dispatcher's anchor hold under its
dispatch claim), and every write it lands moves the reading the tick's state
is synced with (`PinnedState.synced`) on to what landed. Its own earlier writes
are so many checkpoints of one sequence, never another writer's moves; an
attempt or evidence record that reads otherwise than the last of them was moved
by no write of this road's, which only an invariant failure explains.

So each step lands as a checkpoint (`_lands_the_checkpoint`) -- every
auto-rebase park, and a recovery's clear, its abandonment of what a finish
captured, and its record of a gate's hold -- through the tick-state guarded
commit (`workflow/engine/report_commits.py`) over that reading, decided on the
attempt and its evidence as it spells them. And a step whose first effect no
guarded write precedes -- the hard reset a park's tail makes, every road the
workflow's recovery takes off a completed comparison (the gate's whole-state
writes, a settled transfer's report, the push), and the end of a terminal
handoff -- first asks whether the comment still spells them so
(`_still_owns_the_attempt`), with nothing written. Either way, a comment that does not answer as the road last
confirmed it is left exactly as it stands, neither put back, adopted, nor
repaired: the road goes no further, logged, and the next tick takes up
whatever the comment then records.
"""
from __future__ import annotations

import json

from github.Issue import Issue

from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.git.base_sync.state import log
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState


def _lands_the_checkpoint(
    gh: GitHubClient, issue: Issue, state: PinnedState, step: str, staged: PinnedState | None = None,
) -> bool:
    """Land one step of the road as a checkpoint over the reading `state` last confirmed; whether it landed.

    `staged` is a copy of `state` the step was staged on, which owns every
    field it spells otherwise than `state` does, or None for `state` itself.
    Whatever the tick staged on `state` since that reading rides the write as
    the tick's own -- a gate's records, the watermark a notice moved, a run's
    usage, each counted once by the rule its domain keeps both moves by --
    and the write is decided on the attempt and its evidence as that reading
    spells them.

    True only where GitHub confirmed the write, or the comment already read as
    it, and `state` then reads as the comment does: the caller may go on.
    Anything else is logged with nothing more written, and `state` is withheld
    from every whole-state write behind it: a refusal wrote nothing, and an
    answer that was lost may or may not have landed, which only the next
    tick's reading can say. That includes a refusal for room over a comment
    still reading as `state` last confirmed it, which the guarded commit alone
    would leave writable (`report_commits.ReportCommit.withholds`): the caller
    goes no further, so nothing behind it in this tick is owed that room, and
    `state` carries the step the comment refused.
    """
    # Lazy import: the guarded commit sits in the workflow layer above this
    # package, and that layer imports this package at module load time.
    from orchestrator.workflow.engine import pinned_commit_models as _commit_models, report_commits as _commits
    stepped = staged or state
    write = _commits.ReportWrite(owned=_stepped_fields(state, stepped), decided_on=_decided_on())
    landed = _commits.ReportCommit(gh, issue, state).lands(stepped, write)
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        return True
    state.withheld = True
    log.warning(
        "issue=#%d auto-rebase road: the write %s came back %s; going no further, with the pinned comment "
        "left as it stands for the next tick to read",
        issue.number, step, (landed.refusal or landed.status).value,
    )
    return False


def _still_owns_the_attempt(gh: GitHubClient, issue: Issue, state: PinnedState, step: str) -> bool:
    """Whether the comment, read afresh, spells the attempt and its evidence as `state` last confirmed; nothing written.

    Asked ahead of a step whose effect no write can take back. False, logged,
    where the comment would not read as the one `state` was read from, or one
    of those records moved by no write of this road's: `state` is withheld
    from every whole-state write, and the caller makes no such effect.
    """
    # Lazy for the reason the commit above is: its owner sits in the workflow layer.
    from orchestrator.workflow.engine import pinned_commit as _commit
    guard = _confirmed(state)
    fresh = _commit.reread(gh, issue, guard)
    if isinstance(fresh, PinnedState):
        moved = ", ".join(guard.moved(fresh.data))
    else:
        moved = fresh.refusal.value
    if not moved:
        return True
    state.withheld = True
    log.warning(
        "issue=#%d auto-rebase road: holding rather than %s, since the pinned comment does not read as this "
        "road last confirmed it (%s); it is left as it stands for the next tick to read",
        issue.number, step, moved,
    )
    return False


def _confirmed(state: PinnedState):
    """The guard over the reading `state` last confirmed, decided on the attempt and its evidence."""
    from orchestrator.workflow.engine import pinned_commit_models as _commit_models
    synced = state.data if state.synced is None else json.loads(state.synced)
    reading = PinnedState(
        comment_id=state.comment_id, state_data=synced, parsed=state.parsed, supported=state.supported,
    )
    return _commit_models.PinnedCommit.capture(reading, prerequisites=_decided_on())


def _decided_on() -> frozenset[str]:
    """The records every checkpoint is decided on: the whole attempt, and the verification evidence it guards."""
    from orchestrator.workflow.engine import verification_records as _evidence
    return frozenset((
        *_attempts._ATTEMPT_KEYS,
        _evidence.PENDING_EVIDENCE,
        _evidence.CURRENT_EVIDENCE,
        _evidence.EVIDENCE_HISTORY,
        _evidence.EVIDENCE_HANDOFF,
        _evidence.REVISION_FLOOR,
    ))


def _stepped_fields(state: PinnedState, stepped: PinnedState) -> frozenset[str]:
    """Every field `stepped` spells otherwise than `state`, one that either lacks included."""
    from orchestrator.workflow.engine import pinned_commit_models as _commit_models
    return frozenset(
        field for field in state.data.keys() | stepped.data.keys()
        if _commit_models.spelled(state.data, field) != _commit_models.spelled(stepped.data, field)
    )
