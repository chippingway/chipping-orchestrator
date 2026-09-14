# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read the replay identity an interrupted auto-rebase attempt recorded.

The shape reader distinguishes an absent record, an in-flight attempt, and
damaged evidence. The attempts owner uses this same field group when clearing
a completed or abandoned attempt, while every wire key stays in state.
"""
from __future__ import annotations

from orchestrator.git.base_sync.models import (
    _PendingRewrite,
)
from orchestrator.git.base_sync.state import (
    _PENDING_REWRITE_PR,
    _PENDING_REWRITE_SHA,
    _PENDING_REWRITE_STAGE,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import (
    WorkflowLabel,
    publishes_onto_a_pull_request,
)

# Every key one attempt's record of its own replay goes down as, so a reader
# can tell a comment carrying none of them from one a hand edit or a
# half-finished write took a member out of. The announcement mark is not one
# of them: it is a checkpoint about a finish rather than a term of the
# attempt, and it has its own reader for that reason.
_PENDING_REWRITE_KEYS = (
    _PENDING_REWRITE_SHA, _PENDING_REWRITE_PR, _PENDING_REWRITE_STAGE,
)


def _pending_rewrite(state: PinnedState) -> _PendingRewrite:
    """The record one interrupted attempt left of the replay it made.

    Read whole or not at all, like every other record this domain acts on: a
    pull request that is not an identity, a stage no publication is entered
    from, and a head that is not a whole git object id each answer as a record
    nobody may act on, which every caller reads as "cannot say" rather than as
    a fact about the world. The head is held to the same shape every other
    recorded commit here is, and for the same reason -- it is compared against
    one this tick read off a checkout, and a value that cannot be a commit
    would either never match or match something nothing ever wrote.

    Whole means something different for the TERMS and for the head, because
    they are written a `git rebase` apart. The terms go down with the anchor
    before the branch can move, so a comment carrying them and no head is not
    a group short of a member: it is an attempt this reader can date to the
    window between git returning and the write that records what it produced.
    A comment carrying a head with the terms missing is the other way round --
    nothing writes that order -- so it is damage.

    Which of the three absences a caller has is what travels back on the
    answer: one nobody ever wrote, one still in flight, or one something took
    apart.
    """
    # Lazy for the reason every upward reach in this package is: the shape a
    # recorded commit is held to is the late domain's own, and spelling it
    # twice is how a comment comes to accept what every other reader refuses.
    from orchestrator.workflow.late_split import formats as _formats
    recorded = state.get(_PENDING_REWRITE_SHA)
    number = state.get(_PENDING_REWRITE_PR)
    stage = _recorded_stage(state.get(_PENDING_REWRITE_STAGE))
    if not _formats.whole_number(number) or number <= 0 or stage is None:
        return _PendingRewrite(damaged=_claims_a_record(state))
    if recorded is None:
        return _PendingRewrite(pr_number=number, stage=stage)
    if not _formats.is_hex_of(recorded, _formats.COMMIT_LENGTHS):
        return _PendingRewrite(damaged=True)
    return _PendingRewrite(sha=recorded, pr_number=number, stage=stage)


def _claims_a_record(state: PinnedState) -> bool:
    """Whether a comment with unreadable terms claims an attempt anyway.

    Read by VALUE rather than by the key being there, because the write that
    ends an attempt blanks these fields rather than removing them: a group of
    nulls is the record nobody wrote, and a member carrying something beside
    one that does not is the record something took apart.
    """
    return any(
        state.get(key) is not None for key in _PENDING_REWRITE_KEYS
    )


def _recorded_stage(recorded: object) -> WorkflowLabel | None:
    """The stage a record names, or None where it names no publication.

    Held to the same predicate a permit holds its own evidence to -- the
    states that push onto a pull request the remote already carries -- so a
    record naming any other describes an attempt this workflow never made.
    """
    try:
        stage = WorkflowLabel(recorded)
    except ValueError:
        return None
    return stage if publishes_onto_a_pull_request(stage) else None
