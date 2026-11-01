# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late developer revision's reconciliation writes, and what becomes of the report its run captured.

The run a human's guidance buys is captured as it returns on a READY or
VERIFIED report (`late_revision_road`), so by the time its reconciliation
(`late_revision_reconciliation`) answers it, the capture holds the one copy
of that report. Every write the reconciliation makes decides what becomes of
it, and this owner makes those writes.

What the reconciliation writes once it re-measures the candidate -- the
advanced generation, the guidance consumed on every baseline, the owed replies
repaid, the park answered, the operator's authorization withdrawn, and the
owner read it now owes -- lands in the very commit that hands the captured
report to the delivery (`lands_the_revision`), each field the tick dropped
carried as a removal, so a write GitHub never confirmed leaves all of it or
none: the guidance is never consumed beside a report nothing owns, nor a
report recorded beside a generation that never advanced. That commit is
decided on every record the handoff was frozen over -- the split's children
and ledgers among them -- so an obligation recorded since the launch, while the
candidate was measured included, refuses it rather than being left against a
generation it no longer names. A transfer refused for
the report itself -- a verification this orchestrator cannot hold against its
own repository, or a record the report records' reader refuses, neither of
which any later attempt changes -- withdraws the capture. Any other refusal
keeps the capture pending and writes nothing of the reconciliation: a comment
with no room for the transfer, which a human freeing room answers, as much as
one that moved or a write never confirmed. The dispatcher's recovery then
hands the capture on again on every later reading, so the report is never
discarded while the guidance it answers is consumed.

A run that finished on a report no capture holds -- one whose capture the
comment had no room for as it returned, or one withdrawn above -- has that
report recorded by the delivery's own recording, the reconciliation riding
the same commit (`report_delivery.recording_stops_the_tick`): recorded where
the comment takes it, and otherwise parked for a human with the refusal named
and the report owed, so a successful report is never silently dropped either.

A reconciliation that parks over a clean commit it only could not measure
keeps that report: the commit it is about is the one a bare `/orchestrator
continue` measures again as it stands, with no developer run and so no report
of its own, so the park lands in the very commit that hands the report to the
delivery, as a re-measured candidate's does (`lands_the_park`). Every other
park hands the report to nobody, so the capture is withdrawn -- behind the
park's own write, which records the consumption and the owed read with the
capture still pending, so a write lost between the two leaves that capture for
the recovery to finish again rather than unread guidance beside a retired one
(`withdraws`). That write is a guarded commit while the capture is pending,
decided on every record the capture's handoff was frozen over as its transfer
is, and landed by the strict edit, which asks a recovery's question behind its
own walk to the comment: a hold, a close, an edit, or a move landing while the
recovery read, or while that walk did, keeps it from going out at all, and a
generation another road or a human advanced meanwhile never has the guidance
it is owed consumed under the old one.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.agents.models import AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_commits as _commits,
    completion_handoff as _handoff,
    completion_records as _completion_records,
    completion_state as _completion_state,
    report_commits as _report_commits,
    report_delivery as _report_delivery,
    report_outcomes as _report_outcomes,
    report_records as _report_records,
)
from orchestrator.workflow.engine.pinned_commit_models import ABSENT, CommitStatus, loaded, spelled
from orchestrator.workflow.engine.report_record_values import RecordRefusal
from orchestrator.workflow.late_split import phases as _late_phases, state as _late_state
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import captured_report as _captured_report
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# A park's write while the run's capture is pending: owning only what the tick
# moved, and decided on that capture still reading as the tick read it -- and,
# behind it, on every record the capture's handoff was frozen over
# (`lands_the_park`), as its transfer is.
_PARK = _report_commits.ReportWrite(
    frozenset(), decided_on=frozenset((_completion_records.DEVELOPER_COMPLETION,)),
)


def lands_the_revision(context: _LateContext, agent_result: AgentResult | None) -> bool:
    """Write the re-measured generation, handing the run's report to the delivery in that very commit; whether it did.

    A captured report is transferred, the reconciliation riding it
    (`_handed_on`); one the capture still has to hold answers False, the
    state withheld with nothing more written. A run that finished on a
    report no capture holds has it recorded by the delivery's own recording,
    a park for a report that recording refuses answering False. Every other
    run is written whole, as every revision was before any road captured.
    """
    state = context.state
    _late_state.write_late_generation(state, context.generation)
    if _pending(state, agent_result):
        handed = _handed_on(context, agent_result)
        if handed is not None:
            return handed
    if agent_result is not None and _report_outcomes._finished_on_a_report(agent_result):
        return not _report_delivery.recording_stops_the_tick(
            context.gh, context.issue, state, agent_result, WorkflowLabel.DECOMPOSING,
        )
    context.gh.write_pinned_state(context.issue, state)
    return True


def withdraws(context: _LateContext, agent_result: AgentResult | None) -> bool:
    """Retire the run's own pending capture behind a park handing its report to nobody; whether it settled."""
    if agent_result is None:
        return True
    return _captured_report.withdraws_the_capture(context.gh, context.issue, context.state, agent_result)


def lands_the_park(context: _LateContext, agent_result: AgentResult | None, *, keeps_the_report: bool) -> bool:
    """Write the staged park with the owner read it now owes, as one thing; whether it landed.

    The read is claimed as `late_outcome._completed` claims it. A park that
    `keeps_the_report` lands as a re-measured candidate does
    (`lands_the_revision`), the report handed to the delivery in that commit.
    Any other lands through a guarded commit where the run's capture is still
    pending, decided on that capture and every record its handoff was frozen
    over reading as the tick read them -- a generation, a pair, a phase, or a
    watermark another road or a human moved since refuses it, so guidance a
    later candidate is owed is never consumed under the old one -- and a
    recovery's question is asked by the strict edit behind its own walk to the
    comment. A write refused or held, or one that never landed, leaves the
    state withheld with nothing written. With no capture pending it is the
    whole-state write every park was.
    """
    context.generation = replace(
        context.generation.at_phase(_late_phases.LatePhase.OWNER_CHECK),
        owner_check_pending=True,
    )
    if keeps_the_report:
        return lands_the_revision(context, agent_result)
    state = context.state
    _late_state.write_late_generation(state, context.generation)
    if not _pending(state, agent_result):
        context.gh.write_pinned_state(context.issue, state)
        return True
    frozen = dict(_completion_state.read(state).handoff.frozen)
    commit = _report_commits.ReportCommit(context.gh, context.issue, state)
    landed = commit.lands(commit.staging(), _PARK.deciding_on(*frozen))
    return landed.status is CommitStatus.COMMITTED


def reports_on(context: _LateContext, agent_result: AgentResult | None, revised: str) -> bool:
    """Whether `revised` is the commit the run's pending capture reports on, where it left one; True where none.

    The capture froze the head the run left as it returned, and the report it
    holds is about that commit alone. A checkout that moved before the
    reconciliation read it again is one the report does not describe, so
    nothing of the reconciliation is written -- the state withheld, the
    guidance unread, the generation where it stood -- and the capture is left
    pending for the dispatcher's recovery, whose admission reads the checkout
    against it and retires it.
    """
    source = "" if agent_result is None else _captured_report.pending_source(context.state, agent_result)
    if not source or source == revised:
        return True
    context.state.withheld = True
    log.warning(
        "issue=#%d its checkout moved to %s after its late revision's report was captured over %s; reconciling "
        "nothing, for the recovery to decide on the capture",
        context.issue.number, revised, source,
    )
    return False


def _pending(state: PinnedState, agent_result: AgentResult | None) -> bool:
    """Whether `state` carries a pending capture of the very process `agent_result` came from."""
    return agent_result is not None and bool(_captured_report.pending_source(state, agent_result))


def _handed_on(context: _LateContext, agent_result: AgentResult) -> bool | None:
    """Transfer the run's pending capture with the reconciliation riding it; whether the revision landed.

    Decided, as every transfer is, on each record the capture's handoff was
    frozen over -- the split's children and ledgers among them -- so one
    recorded since refuses it with nothing written. True where it settled;
    False, the state withheld, wherever the capture still holds the report;
    None where a refusal for the report itself withdrew the capture, leaving
    that report to the delivery's own recording.
    """
    state = context.state
    handed = _handoff.transfer(
        context.gh, context.issue, state, agent_result.invocation,
        _report_records.HandedRun(WorkflowLabel.DECOMPOSING, retires=_staged_moves(state)),
    )
    if handed.settled:
        return True
    itself = handed.refusal is _commits.CheckpointRefusal.UNRECORDABLE or isinstance(handed.refusal, RecordRefusal)
    if not state.withheld and itself and withdraws(context, agent_result):
        return None
    state.withheld = True
    log.warning(
        "issue=#%d could not hand the captured report of its late revision to the delivery (%s); keeping the "
        "capture and writing nothing more, for the recovery to decide on it on a later reading",
        context.issue.number, handed.refusal or handed.status,
    )
    return False


def _staged_moves(state: PinnedState) -> tuple:
    """Every field the tick moved since its comment last read, as `(field, value)`: ABSENT for one it dropped.

    The late record is rewritten whole (`late_split.state.write_late_generation`),
    so a member a re-measurement clears -- the replies it repaid among them --
    is dropped rather than spelled, and the transfer's commit carries that
    drop like any other move.
    """
    synced = {} if state.synced is None else loaded(state.synced)
    staged = state.state_data
    return tuple(
        (field, staged.get(field, ABSENT))
        for field in sorted(synced.keys() | staged.keys())
        if spelled(staged, field) != spelled(synced, field)
    )
