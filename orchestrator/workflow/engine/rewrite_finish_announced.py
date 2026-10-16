# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finish of a landed rewrite announced on the attempt, as the dormant settled-evidence policy reads it.

A finish's announcement puts the record of its `base_rebased` event and the
mark on the attempt, and its relabel follows; another finish of the landing
may put them down meanwhile, or a write of this finish's own may land them
with its answer lost -- the attempt advanced, not replaced. Only a finish
held to the dormant policy reads it: `advanced_by_the_announcement` tells it
from another attempt, and `takes_in_the_announcement` lays it over the tick's
state, so movement read under settled evidence is retired over the attempt
as it stands rather than refused as another road's. The coordinator
(`rewrite_finish.finalizes`) asks `marked` and `relabelled`, so a finish under
that policy neither announces a head another finish marked meanwhile nor
relabels -- and files the stage-entry event of -- an issue another finish
already relabelled under that mark; every other finish answers both off the
mark and the label the tick read.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit as _commit, pinned_commit_models as _commit_models
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The attempt's members the announcement writes: the record of its event, and the mark.
_ANNOUNCING = frozenset((_base_sync_state._PENDING_ANNOUNCED_EVENT, _base_sync_state._PENDING_ANNOUNCED_SHA))


def advanced_by_the_announcement(
    finish: LandedFinish, read: _commit_models.PinnedCommit, carried: Mapping[str, Any],
) -> tuple[str, ...] | None:
    """The attempt members `carried` spells otherwise than `read` captured, where its own announcement alone moved them.

    Every one has to be a member the announcement writes -- the mark, or the
    record of its event -- naming `finish`'s landed head: that is this very
    attempt advanced by a finish of its landing. None where any other member
    moved, or one names another head or holds anything but a head -- an
    object or a list among them: another attempt, or another road's.
    """
    moved = read.moved(carried)
    if not _ANNOUNCING.issuperset(moved):
        return None
    if any(carried.get(member) != finish.head for member in moved):
        return None
    return moved


def takes_in_the_announcement(finish: LandedFinish, durable: PinnedState) -> None:
    """Lay the announcement's bookkeeping `durable`, read afresh, carries for `finish`'s attempt over the tick's state.

    Only for a finish held to the settled-evidence policy, and only where that
    bookkeeping alone moved the attempt (`advanced_by_the_announcement`):
    taken in as read, so a write decided on the attempt counts none of it as
    the tick's own move.
    """
    if not finish.proves_settled:
        return
    read = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    moved = advanced_by_the_announcement(finish, read, durable.data)
    if not moved:
        return
    for member in moved:
        finish.state.set(member, durable.get(member))
    _commit.takes_in(finish.state, durable.data, moved)


def marked(finish: LandedFinish, *, already: bool) -> bool:
    """Whether the mark is down for `finish`'s landed head: `already`, as the tick read it, or put down since.

    Only a finish held to the settled-evidence policy reads it again, off the
    tick's state as its evidence phase left it -- which takes in an
    announcement another finish of the landing made meanwhile -- so that
    announcement is not made twice.
    """
    return already or (finish.proves_settled and _attempts._already_announced(finish.state, finish.head))


def relabelled(finish: LandedFinish, *, announced: bool) -> bool | None:
    """Whether the issue is already on `workflow:validating` under the mark, so the route relabels nothing.

    `announced` and the tick's label answer for every finish but one held to
    the settled-evidence policy, which reads the mark as the attempt now
    carries it (`marked`) and, where it is down, the label off the issue
    fetched afresh, so a relabel another finish made meanwhile -- and its
    stage-entry event -- is not made twice. None where that label could not
    be read: nobody can say whether the relabel is made, so the route holds
    rather than risk it.
    """
    if not finish.proves_settled:
        return announced and finish.label == WorkflowLabel.VALIDATING
    if not marked(finish, already=False):
        return False
    try:
        label = finish.gh.workflow_label(finish.gh.get_issue(finish.issue.number))
    except Exception:
        log.exception(
            "issue=#%d could not read its label again before relabelling %.8s; holding the route",
            finish.issue.number, finish.head,
        )
        return None
    return label == WorkflowLabel.VALIDATING
