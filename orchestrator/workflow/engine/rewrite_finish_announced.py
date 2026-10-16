# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finish of a landed rewrite announced on the attempt, read again wherever the tick's reading may be stale.

A finish's announcement puts the record of its `base_rebased` event and the
mark on the attempt, and its relabel follows; another finish of the landing
may put them down meanwhile, or a write of this finish's own may land them
with its answer lost -- the attempt advanced, not replaced.
`advanced_by_the_announcement` tells that from another attempt, and
`takes_in_the_announcement` lays it over the tick's state, so movement read
under settled evidence is retired over the attempt as it stands rather than
refused as another road's. The coordinator (`rewrite_finish.finalizes`) asks
`marked` and `relabelled`, so a finish neither announces a head another
finish marked meanwhile nor relabels -- and files the stage-entry event of --
an issue another finish already relabelled for that head, which the
stage-entry event naming the head says.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github import events as _github_events
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit as _commit, pinned_commit_models as _commit_models
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

# The attempt's members the announcement writes: the record of its event, and the mark.
_ANNOUNCING = frozenset((_base_sync_state._PENDING_ANNOUNCED_EVENT, _base_sync_state._PENDING_ANNOUNCED_SHA))

# The event a relabel files, and the stage the route's relabel enters.
_STAGE_ENTER = "stage_enter"
_VALIDATING = stage_name(WorkflowLabel.VALIDATING)


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

    Only where that bookkeeping alone moved the attempt
    (`advanced_by_the_announcement`): taken in as read, so a write decided on
    the attempt counts none of it as the tick's own move.
    """
    read = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    moved = advanced_by_the_announcement(finish, read, durable.data)
    if not moved:
        return
    for member in moved:
        finish.state.set(member, durable.get(member))
    _commit.takes_in(finish.state, durable.data, moved)


def marked(finish: LandedFinish, *, already: bool) -> bool:
    """Whether the mark is down for `finish`'s landed head: `already`, as the tick read it, or put down since.

    Read again off the tick's state as the evidence phase left it -- which
    takes in an announcement another finish of the landing made meanwhile --
    so that announcement is not made twice.
    """
    return already or _attempts._already_announced(finish.state, finish.head)


def relabelled(finish: LandedFinish) -> bool | None:
    """Whether this head's relabel to `workflow:validating` is already made, so the route relabels nothing.

    Read off the mark as the attempt now carries it (`marked`), the label off
    the issue fetched afresh, and -- where that label reads
    `workflow:validating` -- the event stream: a relabel the route made names
    the head on its `stage_enter` event (`rewrite_finish_stops.relabels`), so
    one another finish of the landing made, or a finish lost behind its
    relabel, is found there and not made twice, nor its stage-entry event. A
    label the issue already wore before the rebase, which a relabel onto it
    leaves as it was, is no relabel of this head's: with no such event filed,
    the route relabels it as an uninterrupted journey's does. None where the
    label or the event stream could not be read: nobody can say whether the
    relabel is made, so the route holds rather than risk it.
    """
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
    if label != WorkflowLabel.VALIDATING:
        return False
    made = _github_events.filed(
        finish.gh, _STAGE_ENTER, issue_number=finish.issue.number, stage=_VALIDATING, sha=finish.head,
    )
    if made is None:
        log.warning(
            "issue=#%d could not read the event stream for the relabel of %.8s; holding the route",
            finish.issue.number, finish.head,
        )
    return made
