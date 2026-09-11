# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What every finished late run leaves behind, and the write that keeps it.

The bookkeeping half of the late mode, split from the coordinator that
produces a run and from `late_verdict`, which reads one and decides what it
MEANS. What is here is what any completion owes before the tick does anything
that might not come back: the records each ending hands its caller, the three
emissions that report what those endings left, and the one write every one of
them closes on.

That write is what a completed adjudication is worth. The agent has already
been paid for by the time a run finishes, so a crash between finishing and
recording costs a second run of an agent that already answered -- which is why
the durable write goes out before any external effect, the ordering rule
`late_park_state` owns beside it. A timeout, a contaminated worktree, an unusable
reply, and a verdict are all the same kind of thing here: a run somebody paid
for, whose ending has to survive the tick that saw it.

The three emissions sit here rather than beside the sinks they reach. A
verdict, a typed failure, and the cancellation an owner read earns are each
written straight after the state they describe, and keeping them beside those
writes is what stops one of them reporting a step whose durable half never
landed.

What this owner deliberately does NOT do is decide or publish. Reading a reply
and recording the verdict it carries is `late_verdict`; announcing a question,
restoring or superseding the held PR, creating children, and pushing an
accepted candidate all belong to the steps that act on the verdict.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.agents import AgentResult
from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.late_split import (
    events as _events,
    formats as _formats,
    telemetry as _telemetry,
)
from orchestrator.workflow.late_split.models import (
    IN_FLIGHT_PHASES,
    LateFailure,
    LatePhase,
)
from orchestrator.workflow.stages.decomposition import (
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudication,
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
    _LateRun,
)

log = logging.getLogger("orchestrator.workflow")

_DECOMPOSING_STAGE = "decomposing"

# The boundaries an owner-check claim can be standing at. `owner_check` is
# where a completion ordinarily leaves the record; a transaction re-entered
# after a crash keeps the boundary it interrupted instead -- the record's own
# rule refuses that rewind -- and its claim is as standing as any other.
_CLAIM_PHASES = frozenset((LatePhase.OWNER_CHECK, *IN_FLIGHT_PHASES))


def _reused(
    context: _LateContext, run: _LateRun, *, retired: bool,
) -> _LateAdjudicationRun:
    """Report an answer this tick did not have to earn.

    The announcement a recorded question still owes the issue is not made
    here: it is made past the owner guard, from the question the record kept,
    which is what lets an outcome recorded and never said be said by a later
    tick rather than by another agent run.

    What IS owed here is the write. This is the one branch that returns
    without doing anything else, so a park retired into memory and not
    persisted is a park still standing on the issue -- durably claiming a
    human is owed something, on an issue whose answer is already recorded.
    """
    if retired:
        _late_park_state._persist(context)
    return _finished(
        context,
        _LateDisposition.DECIDED,
        _late_session._recovered_adjudication(run),
    )


def _parked_run(
    context: _LateContext,
    agent_result: AgentResult,
    message: str,
    *,
    reason: str,
) -> _LateAdjudicationRun:
    """Pin the session this run opened, then hand the issue back.

    Both parks that follow a finished run come through here, so the session a
    later resume has to land on is recorded at every exit that writes and at
    no exit that does not -- what the returned record claims is what the
    pinned comment holds.

    Staged rather than said, because the run this parks has already been paid
    for: the session and the park are made durable by the write below, and the
    notice waits for a read that proves the issue is still there.

    That write is this owner's own and not the guard's, which is the whole
    difference between a completion nobody has to pay for twice and one that
    can be lost. A timeout and a contaminated worktree are as finished as a
    verdict is -- the agent ran, the issue paid for it, and what it left is
    exactly as unrepeatable -- so what they decided goes down here, before
    anything that could fail to come back.
    """
    _late_session._record_late_session(context.state, agent_result)
    _late_parks._stage_park(context, message, reason=reason)
    _completed(context)
    return _finished(context, _LateDisposition.PARKED)


def _emit_verdict(
    context: _LateContext, adjudication: _LateAdjudication,
) -> None:
    """Report one adjudication on both sinks, or lose the record instead.

    The event contract is checked where the event is built, which is here
    rather than inside the emission, so the refusal it raises is caught here
    too: a record nobody should have written and a tick broken by the attempt
    to write it are both failures, and only the first one is recoverable.
    """
    try:
        decided = _events.LateEvent(
            family=_events.LateEventFamily.VERDICT,
            verdict=adjudication.verdict,
            category=adjudication.category,
            child_count=adjudication.child_count,
        )
    except _formats.InvalidLateValue as refused:
        log.error(
            "issue=#%d late verdict refused as an event (%s); nothing "
            "emitted", context.issue.number, refused,
        )
        return
    _telemetry.emit_late_event(
        context.gh, decided, context.generation, stage=_DECOMPOSING_STAGE,
    )


def _emit_failure(
    context: _LateContext,
    failure: LateFailure,
    step: MeasurementFailure | None = None,
    detail: str = "",
) -> None:
    """Report one typed late failure on both sinks.

    A refused size reading carries two companions the rest do not -- the step
    the git layer stopped at and the line behind it -- and they ride this
    emitter rather than one of their own because a reading that did not happen
    has to read alike wherever it was taken: the same family and the same
    typed failure the size gate writes, since the question an operator asks of
    one of these is the question they ask of all of them. A refusal that took
    no reading names no step and carries neither. A re-measurement is taken in
    a checkout an agent has been running in, so the step it stops at is the
    one thing telling a base a fetch cannot bring from a diff something in
    that tree made unreadable.
    """
    reported = (
        _events.LateEvent(
            family=_events.LateEventFamily.FAILURE, failure=failure,
        )
        if step is None
        else _events.measurement_failure_event(step, detail)
    )
    _telemetry.emit_late_event(
        context.gh, reported, context.generation, stage=_DECOMPOSING_STAGE,
    )


def _emit_cancellation(context: _LateContext) -> None:
    """Report that this generation's owner was observed gone.

    Emitted after the cancellation is durable, like every other record here,
    so what a sink carries is a mark the cleanup can already read rather than
    a claim about a write that may not have landed. The family says everything
    on its own -- who was cancelled is the generation's own correlation -- so
    it carries no detail of its own.
    """
    _telemetry.emit_late_event(
        context.gh,
        _events.LateEvent(family=_events.LateEventFamily.CANCELLATION),
        context.generation,
        stage=_DECOMPOSING_STAGE,
    )


def _completed(context: _LateContext) -> None:
    """Write what a finished run left, and the read it now owes, as one thing.

    The last step of every completion and the first one that could survive it.
    A run that finished is not free to repeat -- the agent has been paid for,
    and a second one is free to decide differently -- so what it decided is
    durable before the tick does anything that might not come back. That is
    as true of a timeout, an unusable reply, an outcome too large to record,
    a contaminated worktree, and a reconciliation nobody could make as it is
    of a verdict: each is a completed run, and each leaves a park a later tick
    would otherwise neither find nor be able to rebuild.

    The owner read the completion now owes rides the very same write, and that
    is not a convenience. Deriving the obligation from the guard a step later
    means a tick that dies in between leaves a generation still reading as
    `adjudicating` -- no park, no claim, and a next tick that pays for another
    agent against a candidate this one already answered.

    Which is why this is the LAST step of a completion and never a step in the
    middle of one. Everything the completion staged -- the session, the park,
    the notice it owes, the recorded outcome -- is already in memory when this
    runs, so the one write carries all of it. A caller that staged something
    afterwards would be staging it into a write that has already happened.
    """
    context.generation = replace(
        context.generation.at_phase(LatePhase.OWNER_CHECK),
        owner_check_pending=True,
    )
    _late_park_state._persist(context)


def _finished(
    context: _LateContext,
    disposition: _LateDisposition,
    adjudication: _LateAdjudication | None = None,
) -> _LateAdjudicationRun:
    """Report what this call did, with the run pinned state now records.

    The one shape every ending hands its caller, an answer included: what a
    decided run travels on is the adjudication itself rather than a re-read of
    the comment it was just written to, so the step that acts on a verdict
    acts on exactly what was recorded.
    """
    return _LateAdjudicationRun(
        disposition=disposition,
        generation=context.generation,
        run=_late_session._read_late_run(context.state),
        adjudication=adjudication,
    )
