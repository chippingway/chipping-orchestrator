# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finish of a landed rewrite announced on the attempt, as the dormant settled-evidence policy reads it.

A finish's announcement puts the record of its `base_rebased` event and the
mark on the attempt, and -- under the dormant policy -- its relabel follows
behind a record of its own; another finish of the landing may put them down
meanwhile, or a write of this finish's own may land them with its answer lost
-- the attempt advanced, not replaced. Only a finish held to the dormant
policy reads it: `advanced_by_the_announcement` tells it from another attempt,
and `takes_in_the_announcement` lays it over the tick's state, so movement
read under settled evidence is retired over the attempt as it stands rather
than refused as another road's. The coordinator (`rewrite_finish.finalizes`)
asks `marked` and `relabelled`, so a finish under that policy neither
announces a head another finish marked meanwhile nor relabels -- and files
the stage-entry event of -- an issue another finish already relabelled for
that head, which the relabel's own record on the attempt, landed ahead of
every relabel such a finish makes (`relabels_once`), says beside the label;
every other finish answers both off the mark and the label the tick read, and
relabels with no record.
"""
from __future__ import annotations

import json
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
    `finish`'s landed head: that is this very attempt advanced by a finish of
    its landing. None where any other member moved, or one names another head
    or holds anything but a head -- an object or a list among them: another
    attempt, or another road's.
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
    """Whether this head's relabel to `workflow:validating` is already made, so the route relabels nothing.

    `announced` and the tick's label answer for every finish but one held to
    the settled-evidence policy. Such a finish reads the mark as the attempt
    now carries it (`marked`), the record of the relabel beside it, and the
    label off the issue fetched afresh. The record lands ahead of every
    relabel it makes (`relabels_once`), so with none naming the head no
    finish of the landing relabelled for it, and the route relabels -- an
    issue that wore `workflow:validating` before the rebase among them, as an
    uninterrupted route would; beside a label other than `workflow:validating`
    it is a relabel that never landed, and the route relabels too. Made where
    the record names the head and the issue wears `workflow:validating`: a
    relabel another finish of the landing made meanwhile, or one a finish
    lost before the retirement made, so neither it nor its stage-entry event
    is made twice, with no event log needed. On an issue that already wore
    that label the label says nothing of whether the relabel behind the
    record was made, so where the audit log is configured the relabel's
    stage-entry event naming the head is asked for (`github/events.filed`),
    and the route relabels where the stream does not carry it; with no log
    nothing durable can say, and the relabel is taken as made -- once at most:
    a finish lost between the record and the relabel files no stage-entry
    event for the head, on an issue already wearing the label the route puts
    it on. None where the label or that stream could not be read: nobody can
    say whether the relabel is made, so the route holds rather than risk it.
    """
    if not finish.proves_settled:
        return announced and finish.label == WorkflowLabel.VALIDATING
    wears = marked(finish, already=False) and _wears_validating(finish)
    if not wears:
        return wears
    if finish.state.get(_RELABELLED) != finish.head:
        return False
    if not _github_events.durable():
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


def relabels_once(
    finish: LandedFinish, observed, proves: Callable[[LandedFinish], object],
) -> FinishOutcome | None:
    """Relabel `finish`'s issue to `workflow:validating`, its record landed ahead of it; None where both landed.

    Any other finish relabels with no record and nothing read, as it always
    has. For a finish held to the dormant settled-evidence policy, the record
    (`_records_the_relabel`) lands first whatever label the issue wears, so no
    relabel is made that nothing durable records: read back beside the label
    (`relabelled`), it keeps every later finish from relabelling -- and filing
    the stage-entry event -- a second time, with or without an event log, the
    relabel naming the head on that event for a log to answer. HELD where the
    label would not read; a record that did not land is where the route
    stops, nothing relabelled, its refusal collected on `observed`. A relabel
    that raised has `proves`, the caller's proof of the evidence, asked before
    the error goes on. On an issue that wears another label the label read
    back says whether a relabel whose answer was lost landed, so the record
    stays; on one already on `workflow:validating` it says nothing, so the
    event stream is asked for the stage-entry event the relabel names the head
    on -- this process's own tail first, where a relabel that landed and then
    raised filed it (`github/events.filed`) -- and only where the stream reads
    and carries none, a relabel that raised before it filed anything, is the
    record taken back off for the next finish to relabel. One the stream
    carries, or that could not be read, or a record that could not be taken
    back, leaves the relabel read as made: once at most, never twice.
    """
    if not finish.proves_settled:
        finish.gh.set_workflow_label(finish.issue, WorkflowLabel.VALIDATING)
        return None
    wears = _wears_validating(finish)
    if wears is None:
        return FinishOutcome.HELD
    stopped = _records_the_relabel(finish, observed)
    if stopped is not None:
        return stopped
    try:
        finish.gh.set_workflow_label(finish.issue, WorkflowLabel.VALIDATING, sha=finish.head)
    except Exception:
        proves(finish)
        entered = wears and _github_events.filed(
            finish.gh, _STAGE_ENTER, issue_number=finish.issue.number, stage=_VALIDATING, sha=finish.head,
        )
        if entered is False and wears:
            _records_the_relabel(finish, observed, made=False)
        raise
    return None


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


def _records_the_relabel(finish: LandedFinish, observed, *, made: bool = True) -> FinishOutcome | None:
    """Record on the attempt that `finish`'s relabel is made for its head, in a write of its own; None where it landed.

    Landed as `rewrite_finish_writes.RELABEL` over a copy of the comment as
    the tick last read it, the record alone staged on it -- nothing else the
    tick staged since, a usage total among it, which the retirement behind it
    lands once -- so the tick takes in the record alone and the retirement is
    still decided on every other record as the tick read it; a binding record
    moved refuses it, the movement collected on `observed`. `made` False
    takes the record back off, for a relabel that raised.
    """
    named = finish.head if made else None
    synced = finish.state.synced or json.dumps(finish.state.data)
    held = replace(finish, state=PinnedState(
        comment_id=finish.state.comment_id, state_data=json.loads(synced), parsed=finish.state.parsed,
    ))
    held.state.synced = finish.state.synced
    recorded = _writes.staging(held)
    recorded.set(_RELABELLED, named)
    stopped = _writes.lands(held, recorded, _writes.RELABEL, observed)
    finish.state.withheld = finish.state.withheld or held.state.withheld
    if stopped is None:
        finish.state.set(_RELABELLED, named)
        _commit.takes_in(finish.state, {_RELABELLED: named}, (_RELABELLED,))
    return stopped
