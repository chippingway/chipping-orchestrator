# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finish of a landed rewrite announced on the attempt, as the dormant settled-evidence policy reads it.

A finish's announcement puts the record of its `base_rebased` event and the
mark on the attempt; another finish of the landing may put them down
meanwhile, or a write of this finish's own may land them with its answer
lost -- the attempt advanced, not replaced. Only a finish held to the dormant
policy reads it: `advanced_by_the_announcement` tells it from another
attempt, and `takes_in_the_announcement` lays it over the tick's state, so
movement read under settled evidence is retired over the attempt as it
stands rather than refused as another road's.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit as _commit, pinned_commit_models as _commit_models
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

# The attempt's members the announcement writes: the record of its event, and the mark.
_ANNOUNCING = frozenset((_base_sync_state._PENDING_ANNOUNCED_EVENT, _base_sync_state._PENDING_ANNOUNCED_SHA))


def advanced_by_the_announcement(
    finish: LandedFinish, read: _commit_models.PinnedCommit, carried: Mapping[str, Any],
) -> tuple[str, ...] | None:
    """The attempt members `carried` spells otherwise than `read` captured, where its own announcement alone moved them.

    Every one has to be a member the announcement writes -- the mark, or the
    record of its event -- naming `finish`'s landed head: that is this very
    attempt advanced by a finish of its landing. None where any other member
    moved, or one names another head: another attempt, or another road's.
    """
    moved = read.moved(carried)
    named = {carried.get(member) for member in moved}
    if not _ANNOUNCING.issuperset(moved) or not named <= {finish.head}:
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
