# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retire a superseded candidate onto its children and reclaim its recorded branch.

The generation and umbrella label are written together before any child runs.
Activation preserves the shared walk's owner and publication barriers; cleanup
runs afterwards and records failures for the umbrella's terminal to retry.
The transaction calls these effects only after its fresh supersession checks.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split import (
    events as _events,
    telemetry as _telemetry,
)
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
    LatePhase,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.stages.decomposition import (
    activation as _activation,
    late_cleanup as _late_cleanup,
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    parents as _parents,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateContext,
    _LateDisposition,
)
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


_DECOMPOSING_STAGE = "decomposing"


_PR_NUMBER = "pr_number"


def _handed_to_children(
    context: _LateContext, plan: _SplitPlan, branch: str,
) -> _LateDisposition | None:
    """Retire the generation onto `umbrella`, then let the children run.

    One write for the label and the retirement, because the two are the same
    statement: this issue has no candidate of its own any more. The branch it
    still owes the remote is recorded in that write as well, so the obligation
    is durable before the cleanup that reconciles it is attempted -- and the
    activation that follows can therefore never be waiting on it.

    Reports the disposition that ended the cycle, or None where the children
    were started. The retirement write is itself a request, and a close
    landing inside it is the last one this transaction can still catch: past
    the read below, an agent is running on somebody's repository.

    Activation is last and is best-effort: a child this pass could not flip
    reads as deps-satisfied on the umbrella's own next walk, which is the
    retry. It runs through that same walk rather than the initial split's
    one-shot flip, because by the time it runs a child's state is no longer
    this transaction's to assume. The supersession above can park for as long
    as a human takes to settle a pull request, and a child that reached
    `rejected` or `done` in that window would be flipped back to `ready` by a
    write that reads nothing -- the transition guard only warns by default, so
    nothing else would stop it. The walk reads each child fresh and moves only
    the ones still `blocked` with their recorded dependencies satisfied.

    And the publication is asked about again inside that walk rather than
    here, immediately in front of each relabel it makes. Here would be one
    child scan too early: the scan is a request per child, and a walk licensed
    by a reading taken in front of it would release its second child on
    evidence taken before its first. A pull request that came back leaves
    every child exactly where it is -- the umbrella's own walk is the retry,
    and it asks the same question in the same place on its next tick.
    """
    context.generation = _settled_generation(context.generation, branch)
    # The pull request this issue recorded is closed and carries superseded
    # work. Left in place it would point every later reader -- and the merged-PR
    # terminal above all -- at a change the umbrella's children are replacing.
    context.state.set(_PR_NUMBER, None)
    context.gh.set_workflow_label(context.issue, WorkflowLabel.UMBRELLA)
    _late_park_state._persist(context)
    ended = _late_owner._still_activating(context)
    if ended is not None:
        return ended
    return _activated(context, plan)


def _activated(
    context: _LateContext, plan: _SplitPlan,
) -> _LateDisposition | None:
    """Let the children this split may still start, run.

    A read that failed leaves every child where it is. The umbrella's own walk
    takes the same reading on its next tick, so nothing is lost by declining
    to guess -- while flipping a child whose state could not be established is
    the write this exists to avoid.

    The walk asks the latch before every relabel of its own, and what it does
    with a close it finds there is HOLD the children after it -- it does not
    own this issue's record. So the answer is asked for again here, and the
    cycle ends on it: a transaction that reported settled would go on to
    reclaim the superseded branch, which is external work on an issue this
    reading says nobody wants, and would leave no mark saying why.
    """
    scan = _parents._read_child_labels(
        context.gh, context.issue, [number for number, _ in plan.created],
    )
    if scan is None:
        log.warning(
            "issue=#%d could not read its children to activate them; the "
            "umbrella's own walk retries on the next tick",
            context.issue.number,
        )
        return None
    _activation._activate_ready_children(
        context.gh, context.spec, context.issue, context.state, scan,
    )
    return _late_owner._latch_stops(context)


def _reclaimed_branch(context: _LateContext, branch: str) -> None:
    """Take the first swing at the superseded branch, and record the answer.

    After activation on purpose: the branch is tidiness with a deadline rather
    than a precondition, and children held back until a remote delete succeeded
    would be work stalled on housekeeping. What it does gate is the umbrella's
    own terminal completion -- which is why a failure is written down rather
    than logged and forgotten, and why the retry lives on the umbrella
    (`late_cleanup`) rather than here: an issue this transaction has finished
    with is one nothing brings back to this owner.

    The local checkout goes with it -- the reclamation takes every surface the
    branch exists on -- and it is safe here for one reason: the snapshot was
    created and proved before any of this, so the commit the worktree holds is
    no longer the only copy. A worktree left on a superseded branch is not
    merely untidy: the per-tick base refresh treats it as a pre-PR checkout and
    accretes merges onto a branch nobody will publish.
    """
    context.generation = _late_cleanup._reclaim_branch(
        context.gh,
        context.spec,
        context.issue.number,
        context.generation,
        branch,
    )
    deleted = branch not in _late_cleanup._owed_branches(context.generation)
    if not deleted:
        _late_outcome._emit_failure(context, LateFailure.BRANCH_CLEANUP_FAILED)
    _late_park_state._persist(context)
    _emit_cleanup(context, branch, deleted)


def _settled_generation(
    generation: LateGeneration, branch: str,
) -> LateGeneration:
    """What is left of a generation whose candidate became children.

    The measurement is what goes. A parent that has become an umbrella has no
    candidate to measure -- the work is its children's now -- and keeping the
    reading would leave the record answering "oversized", which is the one
    thing that pins `workflow:decomposing` and would put the umbrella label
    back on every tick.

    Everything a later reader still needs stays. The identity is what a
    cleanup record is correlated by, the commits are what the snapshot
    preserves, and both ledgers are what the remote is still owed -- including
    the branch this write is recording as owed for the first time. The ordered
    child register stays with them: it is what says which child owns which
    slice of the manifest, and a transaction re-entered against a retired
    generation has to adopt them rather than open a second set.

    And the publication group stays, which is the one part of this that is
    about a question rather than an obligation. Everything the supersession
    licenses is not finished when this write lands: children are still to be
    released and a branch is still to be deleted, and both run on later ticks
    under `umbrella`, where nothing else on the issue could say which pull
    request this split closed or what head it closed over. Dropping the group
    here would leave those two steps with nothing to re-ask, so a change
    somebody reopened afterwards would have its branch deleted under it and
    its work handed to children anyway. It costs no live adjudication: what
    pins `workflow:decomposing` is the measurement, and that is what goes.
    """
    owed = _late_cleanup._record_branch_obligation(generation, branch)
    return LateGeneration(
        cycle_id=owed.cycle_id,
        generation=owed.generation,
        root_issue=owed.root_issue,
        current_issue=owed.current_issue,
        lineage_depth=owed.lineage_depth,
        scope=owed.scope,
        candidate_sha=owed.candidate_sha,
        base_sha=owed.base_sha,
        phase=LatePhase.CLEANING_UP,
        post_publication=owed.post_publication,
        source_stage=owed.source_stage,
        published_pr_number=owed.published_pr_number,
        published_sha=owed.published_sha,
        resources=owed.resources,
        consumers=owed.consumers,
        split_children=owed.split_children,
        links_announced=owed.links_announced,
    )


def _emit_cleanup(
    context: _LateContext, branch: str, deleted: bool,
) -> None:
    """Report what happened to the superseded branch, on both sinks."""
    _telemetry.emit_late_event(
        context.gh,
        _events.LateEvent(
            family=_events.LateEventFamily.CLEANUP,
            resource=LateResource(
                kind=LateResourceKind.BRANCH,
                target=branch,
                resource_state=(
                    LateResourceState.RECONCILED if deleted
                    else LateResourceState.FAILED
                ),
            ),
        ),
        context.generation,
        stage=_DECOMPOSING_STAGE,
    )
