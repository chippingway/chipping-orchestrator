# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a run's capture holds, handed to the delivery or withdrawn, as its disposition decides.

An implementing run that finished on a report is captured as it returns
(`completion_roads`), so by the time its disposition reaches the point where
the report is recorded -- between proving a clean tree and the size gate --
the capture already holds the one copy of it. The developer a reviewer's
change request hands its fix to is captured the same way, on either half of
that round: the run its handoff launches, whose report `validating/fix_reports`
records, and the fixing stage's resume of it on the far side of a park, whose
report `fixing/reporting` records -- each naming its own road, and the direct
run's transfer retiring the change request it answers. Recorded again from
the run, the issue would carry two reports the next tick could publish. So where the
run's own capture stands pending, the recording is the capture's transfer
(`completion_handoff.transfer`): the delivery is minted from the outcome the
capture kept, under the requirements and delivered input its road froze, and
the capture is handed off in the very commit that records it. A run with no
capture of its own -- one the road's contract refused, or whose capture was
refused for its report or for room -- is recorded by the delivery's own
recording, exactly as one was before any road captured.

What the tick settled around the run -- the pinned session, the delivered
input, the park it answered, the waiver of an earlier unfinished run it
retires -- rides the transfer's own commit (`HandedRun.retires`), so it lands
with the handoff or not at all: a process lost before that commit leaves the
capture pending over a record that settled none of it, which the recovery
then settles once from the capture, and never a session charged twice, nor a
report beside a park or a batch that would buy a second run. A
transfer that does not settle for a reason about the comment -- one that
moved, or a write never confirmed -- ends the tick with nothing more
written, the state withheld; the capture still holds the report, and the
dispatcher's recovery decides it on a later reading. One refused for the
report itself -- a verification this orchestrator cannot hold against its
own repository, or a record or room the delivery refuses -- can never be
handed on, so the capture is withdrawn and the delivery's own recording
answers the run as it always has: recorded where the comment takes it, and
parked for a human with the reason where it does not.

Wherever a report a capture handed off is still owed, the size gate is held
to the commit that capture reported on (`captured_source`), beside any
candidate a record names: a checkout that moved off it, or a record naming
another commit, is parked before anything is measured, pushed, or opened, as
the binding would refuse that publication after the fact.

A disposition that parks without handing the report on -- a run that
committed nothing past what it started on, or left a tree no push may
publish -- withdraws the capture first (`withdraws_the_capture`): a guarded
invalidation of it, so a reply that resumes the developer is captured afresh
rather than refused behind it. A retirement that does not settle holds the
park too, so no notice goes out for a park the comment never took. A park
over a reading that merely did not return -- a status, a fetch, a count --
takes neither (`parks_beside_the_capture`): the capture still holds a report
the next tick may prove, so it is kept and the tick held with nothing written.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_commits as _commits,
    completion_handoff as _handoff,
    completion_records as _records,
    completion_state as _completion_state,
    pinned_commit_models as _commit_models,
    report_delivery as _report_delivery,
    report_record_room as _room,
)
from orchestrator.workflow.engine.report_records import HandedRun
from orchestrator.workflow.stages.implementing import state as _state
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def recording_stops_the_tick(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    route: WorkflowLabel | HandedRun = _state._REPORT_ROUTE,
) -> bool:
    """Record what a finished run wrote, or hold the tick over it; True is a tick this ended.

    The run's own pending capture is handed to the delivery, with what the
    tick settled around the run and what its road retires with the report
    (`HandedRun.retires`) riding that very commit, decided on what that road
    decides its recording on (`HandedRun.decided_on`); anything else is recorded
    by the delivery under `route`, which parks the reports it cannot record
    -- a captured report whose transfer is refused for itself included, once
    its capture is withdrawn. `route` is the implementing route unless a
    caller on another road names its own: a reviewer's change request's
    direct run, which answers the request it retires (`validating/fix_reports`),
    and the fixing stage's resume of that round (`fixing/reporting`).
    """
    pending = _pending_of(state, agent_result)
    if pending is None:
        return _report_delivery.recording_stops_the_tick(gh, issue, state, agent_result, route)
    answering = route if isinstance(route, HandedRun) else HandedRun(route)
    behind = replace(answering, retires=_staged_moves(state) + answering.retires)
    handed = _handoff.transfer(gh, issue, state, pending.invocation, behind)
    if handed.settled:
        return False
    refused_for_itself = handed.refusal is _commits.CheckpointRefusal.UNRECORDABLE or isinstance(
        handed.refusal, _room.RecordingRefusal,
    )
    if not state.withheld and refused_for_itself and withdraws_the_capture(gh, issue, state, agent_result):
        return _report_delivery.recording_stops_the_tick(gh, issue, state, agent_result, route)
    state.withheld = True
    log.warning(
        "issue=#%d could not hand the captured report of agent invocation %d/%s to the delivery (%s); "
        "publishing nothing and writing nothing more, for the recovery to decide on a later reading",
        issue.number, pending.invocation.ordinal, pending.invocation.nonce, handed.refusal or handed.status,
    )
    return True


def withdraws_the_capture(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState, agent_result: AgentResult,
) -> bool:
    """Retire the run's own pending capture ahead of a park that hands its report to nobody; whether the park may go on.

    True where the run left no capture pending, and where the retirement
    settled; False -- the state withheld -- where it did not.
    """
    pending = _pending_of(state, agent_result)
    if pending is None:
        return True
    retired = _checkpoint.retire(gh, issue, state, pending.invocation, _records.RetirementReason.INVALIDATED)
    if retired.settled:
        return True
    state.withheld = True
    log.warning(
        "issue=#%d could not retire the captured completion of agent invocation %d/%s ahead of its park (%s); "
        "parking nothing, for the recovery to decide on a later reading",
        issue.number, pending.invocation.ordinal, pending.invocation.nonce, retired.refusal or retired.status,
    )
    return False


def parks_beside_the_capture(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    *,
    unread: bool,
) -> bool:
    """Whether a park that hands the run's report to nobody may go on, the run's own capture settled for it first.

    `unread` is a park over a reading that did not return rather than one
    the branch or the record refused. There the run's own pending capture
    still holds the report the next tick can prove, so it is kept and the
    tick held, its state withheld and nothing written, for the dispatcher's
    recovery to take the reading again with no developer run; False. Every
    other park withdraws the capture first (`withdraws_the_capture`).
    """
    pending = _pending_of(state, agent_result)
    if not unread or pending is None:
        return withdraws_the_capture(gh, issue, state, agent_result)
    state.withheld = True
    log.warning(
        "issue=#%d could not take the reading the captured report of agent invocation %d/%s is published on; "
        "keeping the capture and writing nothing, for the recovery to read it again on a later tick",
        issue.number, pending.invocation.ordinal, pending.invocation.nonce,
    )
    return False


def captured_source(state: _pinned_state.PinnedState) -> str:
    """The commit the report this issue still owes a pull request was captured over; "" where no capture names one.

    The handed-off capture still owed to the delivery or the transaction its
    report became -- or the one a pending or retired capture carries -- is
    the one record of that commit, and the binding holds the report's
    publication to it (`completion_state.binding_hold`). The size gate holds
    the head to that commit beside any candidate its caller names, so a
    checkout something moved off it after the capture -- across its
    transfer, or a restart behind that -- or a recorded candidate naming
    another commit publishes nothing rather than a commit the report is not
    about.
    """
    handoff = getattr(_completion_state.read(state), "standing_handoff", None)
    return handoff.source_sha if _completion_state.source_owed(state, handoff) else ""


def _staged_moves(state: _pinned_state.PinnedState) -> tuple:
    """Every field the tick has staged a value for since its comment last read, as `(field, value)` pairs.

    What a recovery would settle again from the capture, written in the
    transfer's own commit so it lands with the handoff or not at all.
    """
    synced = {} if state.synced is None else json.loads(state.synced)
    return tuple(
        (field, staged) for field, staged in state.state_data.items()
        if _commit_models.spelled(state.state_data, field) != _commit_models.spelled(synced, field)
    )


def _pending_of(state: _pinned_state.PinnedState, agent_result: AgentResult) -> _records.CompletionCapture | None:
    """The pending capture `state` carries of the very process `agent_result` came from, or None."""
    captured = _completion_state.read(state)
    if not isinstance(captured, _records.CompletionCapture) or agent_result.invocation is None:
        return None
    return captured if captured.invocation == agent_result.invocation else None
