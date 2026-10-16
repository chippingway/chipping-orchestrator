# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finish of a landed rewrite announced on the attempt, read again wherever the tick's reading may be stale.

A finish's announcement puts the record of its `base_rebased` event and the
mark on the attempt, and its relabel follows with a record of its own;
another finish of the landing
may put them down meanwhile, or a write of this finish's own may land them
with its answer lost -- the attempt advanced, not replaced.
`advanced_by_the_announcement` tells that from another attempt, and
`takes_in_the_announcement` lays it over the tick's state, so movement read
under settled evidence is retired over the attempt as it stands rather than
refused as another road's. The coordinator (`rewrite_finish.finalizes`) asks
`marked` and `relabelled`, so a finish neither announces a head another
finish marked meanwhile nor relabels -- and files the stage-entry event of --
an issue another finish already relabelled for that head, which the relabel's
own record on the attempt says beside the label (`relabels_once`).
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github import events as _github_events
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    pinned_commit_models as _commit_models,
    rewrite_finish_writes as _writes,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

# The record of the relabel a finish made for the landed head.
_RELABELLED = _base_sync_state._PENDING_RELABELLED

# The event a relabel files, and the stage the route's relabel enters.
_STAGE_ENTER = "stage_enter"
_VALIDATING = stage_name(WorkflowLabel.VALIDATING)

# The attempt's members a finish of the landing writes naming its head: the
# record of its event, the mark, and the record of its relabel.
_ANNOUNCING = frozenset((
    _base_sync_state._PENDING_ANNOUNCED_EVENT,
    _base_sync_state._PENDING_ANNOUNCED_SHA,
    _RELABELLED,
))


def advanced_by_the_announcement(
    finish: LandedFinish, read: _commit_models.PinnedCommit, carried: Mapping[str, Any],
) -> tuple[str, ...] | None:
    """The attempt members `carried` spells otherwise than `read` captured, where its own announcement alone moved them.

    Every one has to be a member a finish of the landing writes -- the mark,
    the record of its event, or the record of its relabel -- naming
    `finish`'s landed head: that is this very
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

    Read off the mark as the attempt now carries it (`marked`), the record of
    the relabel beside it (`relabels_once`), and the label off the issue
    fetched afresh: made where the record names the head and the issue wears
    `workflow:validating`, so a relabel another finish of the landing made
    meanwhile, or one a finish lost before the retirement made -- and its
    stage-entry event -- is not made twice, with no event log needed. One
    recorded ahead of a relabel that never landed leaves another label, and
    the route relabels. An issue on `workflow:validating` with no record
    beside it either wore that label before the rebase -- whose relabel lands
    its record right behind it -- or was lost between that relabel and its
    record, which only the relabel's own stage-entry event, naming the head,
    can say: the event stream is asked for it (`github/events.filed`), and the
    route relabels only where it does not carry it, as an uninterrupted route
    would. None where the label or that stream could not be read: nobody can
    say whether the relabel is made, so the route holds rather than risk it.
    """
    if not marked(finish, already=False):
        return False
    wears = _wears_validating(finish)
    if not wears:
        return wears
    if finish.state.get(_RELABELLED) == finish.head:
        return True
    made = _github_events.filed(
        finish.gh, _STAGE_ENTER, issue_number=finish.issue.number, stage=_VALIDATING, sha=finish.head,
    )
    if made is None:
        log.warning(
            "issue=#%d could not read the event stream for the relabel of %.8s; holding the route",
            finish.issue.number, finish.head,
        )
    return made


def _wears_validating(finish: LandedFinish) -> bool | None:
    """Whether the issue, fetched afresh, wears `workflow:validating`; None, logged, where its label would not read."""
    try:
        label = finish.gh.workflow_label(finish.gh.get_issue(finish.issue.number))
    except Exception:
        log.exception(
            "issue=#%d could not read its label again before relabelling %.8s; holding the route",
            finish.issue.number, finish.head,
        )
        return None
    return label == WorkflowLabel.VALIDATING


def _records_the_relabel(finish: LandedFinish, observed) -> FinishOutcome | None:
    """Record on the attempt that `finish`'s relabel is made for its head, in a write of its own; None where it landed.

    Landed as `rewrite_finish_writes.RELABEL` over a copy of the tick's
    state, so the tick takes in the record alone and the retirement behind it
    is still decided on every other record as the tick read it; a binding
    record moved refuses it, the movement collected on `observed`.
    """
    held = copy.deepcopy(finish.state)
    recorded = _writes.staging(finish)
    recorded.set(_RELABELLED, finish.head)
    stopped = _writes.lands(replace(finish, state=held), recorded, _writes.RELABEL, observed)
    finish.state.withheld = finish.state.withheld or held.withheld
    if stopped is None:
        finish.state.set(_RELABELLED, finish.head)
        _commit.takes_in(finish.state, {_RELABELLED: finish.head}, (_RELABELLED,))
    return stopped


def relabels_once(
    finish: LandedFinish, observed, proves: Callable[[LandedFinish], object],
) -> FinishOutcome | None:
    """Relabel `finish`'s issue to `workflow:validating` with its record around it; None where both landed.

    The record (`_records_the_relabel`) lands ahead of the relabel where the
    issue wears another label -- the label read back then says whether the
    relabel landed -- and right behind it where the issue already wears
    `workflow:validating`, which a relabel onto it leaves as it was -- a
    relabel naming the head on its stage-entry event, which `relabelled`
    asks the event stream for where a finish was lost between the two. HELD
    where the label would not read. A relabel that raised has `proves`,
    the caller's proof of the evidence, asked before the error goes on; a
    record that did not land is where the route stops.
    """
    wears = _wears_validating(finish)
    if wears is None:
        return FinishOutcome.HELD
    stopped = None if wears else _records_the_relabel(finish, observed)
    if stopped is None:
        try:
            finish.gh.set_workflow_label(finish.issue, WorkflowLabel.VALIDATING, sha=finish.head)
        except Exception:
            proves(finish)
            raise
        stopped = _records_the_relabel(finish, observed) if wears else None
    return stopped
