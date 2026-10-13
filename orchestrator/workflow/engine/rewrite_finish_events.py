# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The `base_rebased` event a landed base rewrite's finish files, once per landed head.

The event goes out behind the landing's notice and ahead of the checkpoint
that marks the head announced (`rewrite_finish`), and no write lands in the
same breath as it: the event stream is not the pinned comment. A finish lost
between the two -- or one whose checkpoint was refused or never confirmed
behind the event -- leaves an attempt with no mark, whose event may already be
out, and nothing on the comment can say it is not: a finish from before the
attempt recorded its events (`pending_auto_base_rebase_announced_event`)
filed the event and died behind it with no record at all. So until the mark
is down, every finish asks the event stream itself first
(`github.events.filed`: the client's in-memory tail, then the whole audit log
and every rotated copy of it beside it, however long the retry took and
however often the log was rotated meanwhile), record or no record, and files
the event only where the stream does not carry it. A stream that would not
read is nobody's answer: the finish is held with nothing filed, relabelled, or
retired, for the next tick to ask again -- so an audit log the process cannot
read holds every landed rewrite's route until it reads. Once the mark is down,
no later finish announces the head at all.

The attempt records the event ahead of filing it, in a guarded write of its
own (`rewrite_finish_writes.ANNOUNCED_EVENT`), decided on the attempt: the
event goes out only behind a write proving the attempt still stands as the
finish read it, and the record tells whoever reads the comment that the event
may be out. It lands over a copy of the tick's state, and the tick takes in
that one field and nothing else the write read, so the checkpoint behind it
is still decided on every other record as the tick read it. It is decided on
the records settled evidence's binding rests on as well
(`rewrite_finish_writes.BINDING_RECORDS`), so a report or review record
another road moved while the notice was posted refuses it rather than riding
into that copy unread: the refusal is movement read under that evidence,
which the finish invalidates before it stops
(`rewrite_finish_readiness.invalidates_behind`), so putting the record back
before the checkpoint or the next poll revives nothing. A record that did not
land is where the finish stops, with nothing filed. That write is
prepared ahead of the notice too (`prepares_the_record`), beside the
checkpoint's own preparation: it is made over the comment as the tick read
it, its round included, which only the checkpoint resets, so a comment with
room for the checkpoint can still have none for the record, and nothing is
posted or filed for an announcement whose first write could not land.

The event reports the round the reviewer is asked to spend afresh on the
landed head, which every finish resets, and how the head reached its finish
(`method`) -- the payload every finish has always filed, which live issues and
the audit sink already carry.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import replace

from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.github import events as _github_events
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit as _commit, rewrite_finish_writes as _writes
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")

# The attempt's record of the `base_rebased` event a finish files for its head.
_FILED = _base_sync_state._PENDING_ANNOUNCED_EVENT

_REBASED = "base_rebased"


def method(finish: LandedFinish) -> str:
    """How the landed head reached its finish, as the `base_rebased` event names it."""
    if not finish.pushed:
        return "crash_recovery_relabel_only"
    if finish.road is FinishRoad.PUBLICATION:
        return "auto_clean_rebase"
    return "crash_recovery_pushed"


def files(finish: LandedFinish, staged: PinnedState, observed: list | None = None) -> FinishOutcome | None:
    """File `finish`'s `base_rebased` event once, recorded on the attempt ahead of it; None to go on.

    The event stream is asked first, whatever the attempt records, and
    nothing is filed where it carries the event; HELD where it would not read.
    `staged` is the checkpoint's own state, which carries the record too. The
    outcome of the record's own write where that did not land, the movement
    its refusal read collected on `observed` (`rewrite_finish_writes.lands`).
    """
    issue_number = finish.issue.number
    found = _github_events.filed(finish.gh, _REBASED, issue_number=issue_number, sha=finish.head)
    if found is None:
        log.warning(
            "issue=#%d could not read the event stream back for the base_rebased event of %.8s, which may "
            "already be filed; holding the finish with nothing filed",
            issue_number, finish.head,
        )
        return FinishOutcome.HELD
    if found:
        log.info(
            "issue=#%d finds the base_rebased event of %.8s already on the event stream; not filing it again",
            issue_number, finish.head,
        )
        return None
    if finish.state.get(_FILED) != finish.head:
        stopped = _records(finish, staged, observed)
        if stopped is not None:
            return stopped
    finish.gh.emit_event(
        _REBASED,
        issue_number=issue_number,
        stage=stage_name(finish.label),
        pr_number=finish.pr_number,
        sha=finish.head,
        method=method(finish),
        review_round=0,
        retry_count=finish.state.get("retry_count"),
    )
    return None


def prepares_the_record(finish: LandedFinish, observed: list | None = None) -> FinishOutcome | None:
    """None where the record of `finish`'s event would land now, or the attempt already carries it; REFUSED otherwise.

    Measured over the comment read afresh, as `_records` would write it, the
    movement a refusal read collected on `observed`.
    """
    if finish.state.get(_FILED) == finish.head:
        return None
    return _writes.prepares(finish, _recording(finish), _writes.ANNOUNCED_EVENT, observed)


def _records(finish: LandedFinish, staged: PinnedState, observed: list | None) -> FinishOutcome | None:
    """Record on the attempt that `finish`'s event is being filed, in a write of its own; None where it landed.

    Landed over a copy of the tick's state, so the tick and `staged` take in
    the record alone: every other field the checkpoint is decided on stays as
    the tick read it, and a move another road made before the record still
    refuses the checkpoint behind it. A binding record moved refuses the
    record itself, the movement collected on `observed`.
    """
    held = copy.deepcopy(finish.state)
    recorded = _recording(finish)
    stopped = _writes.lands(replace(finish, state=held), recorded, _writes.ANNOUNCED_EVENT, observed)
    finish.state.withheld = finish.state.withheld or held.withheld
    if stopped is None:
        finish.state.set(_FILED, finish.head)
        _commit.takes_in(finish.state, {_FILED: finish.head}, (_FILED,))
        staged.set(_FILED, finish.head)
    return stopped


def _recording(finish: LandedFinish) -> PinnedState:
    """A copy of the tick's state with the record of `finish`'s event staged on it: all the record's write carries."""
    recorded = _writes.staging(finish)
    recorded.set(_FILED, finish.head)
    return recorded
