# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Describe failed measurement steps and emit their attributed park events and notices.

Failure descriptions keep the exact operational guidance. A park emits
the generation's failure before recording its wait, and publication-side
events retain the stage the gate call was entered from.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.engine import (
    guards as _guards,
)
from orchestrator.workflow.late_split import (
    events as _events,
    models as _late_models,
    telemetry as _telemetry,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_measurement_state as _late_measurement_state,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


# What each step means to the operator who has to clear it, one line apiece.
# The member is what code branches on and what the record and the streams
# carry, and on a thread it says nothing: `candidate_absent` names a host to
# bring a commit to and `diff_unpinnable` names a checkout to clean, and the
# difference between them is the whole of somebody's next move. The lines are
# here rather than beside the vocabulary because they are addressed to the
# human on this issue -- what was refused, and what would change it -- rather
# than to the step that stopped.
_FAILURE_LINES = MappingProxyType({
    MeasurementFailure.BASE_UNREADABLE: (
        "The `git ls-remote` this reading takes against the base branch never "
        "came back with a commit, so there was no base to diff against: a "
        "remote that could not be reached or was throttling the request, or a "
        "token that has expired or cannot see this repository. Three retries "
        "have already been taken quietly, one per tick, and the same pair "
        "goes on being re-read on every tick after this notice -- so a "
        "transport that comes back settles this with no reply at all. The "
        "invocation that failed is logged under `orchestrator.git_plumbing`."
    ),
    MeasurementFailure.BASE_ABSENT: (
        "The remote named the base commit and a fetch did not bring that "
        "object to this host, so there was nothing here to take the diff "
        "against: a base branch rewritten under this clone, an object a prune "
        "took, or a fetch that could not finish. It is retried on the same "
        "quiet bound as `base_unreadable` and re-read on every tick after "
        "this notice, and the fetch is logged under "
        "`orchestrator.git_plumbing`."
    ),
    MeasurementFailure.CANDIDATE_UNREADABLE: (
        "The commit this issue is about does not resolve in the worktree on "
        "this host -- a checkout that was rebuilt, reset, or reaped out from "
        "under the record. Restore the checkout that holds it, or commit the "
        "work again; another reading of the same worktree answers the same "
        "way."
    ),
    MeasurementFailure.CANDIDATE_ABSENT: (
        "The revision resolved to an object id this host cannot read as a "
        "commit -- work made on a host this one is not, or an object a prune "
        "took. The commit has to be here before any reading of it can be "
        "taken."
    ),
    MeasurementFailure.DIFF_UNPINNABLE: (
        "The checkout carries configuration that would decide what counts as "
        "text -- a repository diff driver, or a planted `info/attributes` "
        "file -- and no override this reading takes reaches either, so a "
        "count taken under it could be made to read as a small candidate. "
        "Clear it in the worktree before the pair is measured again."
    ),
    MeasurementFailure.DIFF_FAILED: (
        "`git diff` over the two frozen commits exited non-zero, so no count "
        "came back at all. The invocation and what it wrote are logged under "
        "`orchestrator.git_plumbing`."
    ),
    MeasurementFailure.DIFF_UNREADABLE: (
        "`git diff --numstat` answered with a record this build cannot count, "
        "so no number could be taken from it. The invocation is logged under "
        "`orchestrator.git_plumbing`."
    ),
})

# What the step said for itself, where it said anything. Free text a human
# reads rather than anything to branch on, and scrubbed of the credential by
# the transport long before it reaches here.
_REPORTED_DETAIL = "The step reported: {detail}"


def _described(failure, detail: str) -> str:
    """The line an operator acts on, and what the step said for itself.

    The member alone is a contract term: it tells the reading what to do and
    tells the person holding the issue nothing about what to fix. So the
    notice carries the sentence written for them, and the transport's own line
    after it where there is one -- by the time a human reads this the process
    that saw that stderr is minutes and a tick gone, and nothing else kept it.

    Empty for a member no line covers, which is what keeps the notice's own
    sentences the contract: a park says what was refused whether or not this
    table has caught up with the vocabulary.
    """
    described = _FAILURE_LINES.get(failure, "")
    if not detail:
        return described
    reported = _REPORTED_DETAIL.format(detail=detail)
    return f"{described} {reported}" if described else reported


def _parked(
    gate: _late_gate_models._Gate,
    generation: _late_models.LateGeneration,
    failure,
    message: str,
    detail: str = "",
) -> bool:
    """Record the typed failure on both sinks, then hand the issue back.

    Every reading that did not happen is reported, which is why the generation
    reaching here is one a caller has already made reportable: a candidate the
    gate could not even name has no record of its own yet, and the identity
    minted for it is what lets the failure be joined to the cycle a later
    freeze writes under the same number.

    `failure` is whatever the caller stopped at, and the roads in do not agree
    about what that is: the ones a reading refused name a member, while the
    ones a RECORD refused -- a pinned comment too damaged to act on, a debt no
    push can pay -- name the repair in their own words, because the whole
    point of those parks is telling a human which part to fix. The record
    keeps the member where there is one and says nothing where there is not,
    so a step nobody reached is never reported as one that was.
    """
    log.error(
        "issue=#%d committed work could not be measured (%s); parking rather "
        "than publishing an unadjudicated candidate",
        gate.issue.number, failure,
    )
    _emit(gate, generation, _events.measurement_failure_event(failure, detail))
    _guards._park_awaiting_human(
        gate.gh, gate.issue, gate.state, message,
        reason=_late_measurement_state.PARK_MEASUREMENT_FAILED,
    )
    gate.state.set(_state._PARK_REASON, _late_measurement_state.PARK_MEASUREMENT_FAILED)
    return True


def _emit(
    gate: _late_gate_models._Gate,
    generation: _late_models.LateGeneration,
    event: _events.LateEvent,
) -> None:
    """Report one late event from the stage the measurement happened in.

    Which stage that is comes off the entry the call was taken on rather than
    off this package's own name: the same gate runs at the seam that publishes
    a pull request for the first time and at the one that pushes to a pull
    request the remote already carries, and a record filed under
    `implementing` for a reading taken in `fixing` would put a measurement in
    a stage no developer of it ever ran under.
    """
    stage = _state._IMPLEMENTING_STAGE
    if gate.entry is not None:
        stage = gate.entry.stage
    _telemetry.emit_late_event(gate.gh, event, generation, stage=stage)
