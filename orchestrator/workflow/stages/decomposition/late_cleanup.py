# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settle and report late-split cleanup, and guard the umbrella's terminal on its debts.

A pass persists only changed resource states while reporting attempted
failures. The terminal requires all obligations and the superseded publication
to settle; damaged identities with uncorrelated obligations remain held.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    events as _events,
    obligations as _obligations,
    state as _late_state,
    telemetry as _telemetry,
)
from orchestrator.workflow.late_split.models import LateFailure, LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_reading as _late_cleanup_reading,
    late_cleanup_state as _late_cleanup_state,
    late_publication as _late_publication,
    late_reclamation as _late_reclamation,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")

# The typed failure each refused reclamation is reported under. The plan pull
# request is here rather than beside the cancellation that settles it, because
# what reports it is the emission below: a kind this map does not carry is an
# entry no sink could name the failure of.
_FAILURES = MappingProxyType({
    _late_cleanup_state._BRANCH: LateFailure.BRANCH_CLEANUP_FAILED,
    _late_cleanup_reading._SNAPSHOT: LateFailure.SNAPSHOT_DELETE_FAILED,
    _obligations.LateResourceKind.PLAN_PR: LateFailure.PR_RECONCILE_FAILED,
})


def _settle(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _ChildScan,
) -> LateGeneration:
    """Settle what this issue owes right now, and answer the record it leaves.

    The write is behind what MOVED, not behind what was attempted. An entry
    already reconciled is not asked about at all, and one a retry left exactly
    as it found it has nothing to write down -- so a remote that goes on
    refusing one delete costs a request per visit rather than a request and a
    pinned write per visit, for as long as the refusal lasts.

    What is reported is behind the same reading, and the log line beside it is
    not: the sinks carry the transitions, and every visit that ends with
    something still owed says so where an operator reads it.

    The stage both sinks record is read off the issue rather than named by the
    caller, because it is a fact about where the reclamation happened and not
    about which owner drove it: the umbrella's terminal reaches here on
    `umbrella`, and the closed-owner sweep on whichever of the two cleanup
    states its issue was closed on.
    """
    walk = _late_cleanup_state._Pass(
        gh=gh, spec=spec, issue=issue, state=state, scan=scan,
    )
    settled = _late_reclamation._reclaimed(walk, _late_state.read_late_generation(state))
    if settled.moved:
        walk.persist(settled.generation)
    if settled.attempted:
        _report(gh, issue, settled, stage=stage_name(gh.workflow_label(issue)))
    return settled.generation


def _settled_for_terminal(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _ChildScan,
) -> bool:
    """Whether this umbrella may complete, settling what it still owes.

    The caller is the umbrella's all-children-resolved branch, and the answer
    is a decision rather than a report: False keeps the parent open on
    `workflow:umbrella` for the next tick to ask again, which is what makes an
    unreclaimed remote loud instead of silent. An issue with no recorded
    generation owes nothing and answers without a write.

    The ledger is not the whole of what holds it. A split entered past
    publication owes the terminal one question as well as its obligations --
    whether the pull request it closed is still closed -- and that is asked
    HERE rather than left to the ledger, because the two can disagree: a
    reclamation that finished leaves nothing owed, so a human who restores the
    branch and reopens the change afterwards would find every entry settled
    and the terminal free to fire. What that terminal writes is `done` and a
    close, and the write ahead of it drops the publication group -- so nothing
    would ever ask again, and an open change carrying superseded work would be
    left under a parent this workflow had declared finished.

    Asked before anything is SAID, which is why it belongs to this owner and
    not to the completion behind it: the resolution comment is gated on a
    stamp the retirement write puts down, so a refusal taken past that comment
    would repeat it on every tick that holds.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        return _owes_nothing_uncorrelated(issue, generation)
    settled = _settle(gh, spec, issue, state, scan)
    held = _late_cleanup_reading._blocking(settled) + _unsettled_publication(gh, issue, settled)
    if not held:
        return True
    # Said on every tick that holds, because a hold with nothing attempted
    # writes nothing and emits nothing: an umbrella that will not close and
    # never says why is the one shape an operator cannot act on.
    log.info(
        "issue=#%d holds its terminal on: %s", issue.number, ", ".join(held),
    )
    return False


def _unsettled_publication(
    gh: GitHubClient, issue: Issue, generation: LateGeneration,
) -> tuple[str, ...]:
    """What holds a terminal when the change a split closed has come back.

    A reason rather than an obligation, and it is deliberately not written to
    the ledger. Nothing here is owed the remote: the branch really was
    reclaimed and the ref really was let go, and an entry claiming otherwise
    would send a later pass to delete a branch a human put back on purpose.
    What is unfinished is the pull request, and the only thing this workflow
    may do about that is decline to close over it and say so.

    Empty for everything that never had a publication, and no request is spent
    on any of them -- which is every umbrella the initial decomposer made and
    every split entered before the first push.
    """
    undone = _late_publication._publication_undone(gh, issue, generation)
    return (undone,) if undone else ()


def _owes_nothing_uncorrelated(
    issue: Issue, generation: LateGeneration,
) -> bool:
    """Whether an issue with no cycle identity may still close.

    An issue that never entered the late gate carries no ledger either, and
    answers True without a write -- which is every umbrella the initial
    decomposer made.

    A ledger with entries on a record whose identity is damaged is the other
    case, and it may not close. There is nothing to correlate a reclamation
    to, no issue number to prove a branch belongs to this generation, and no
    record either sink would accept -- so the only safe answer is to stay open
    and say so where an operator reads it. The write that damaged the identity
    kept the ledger on purpose; closing over it would finish the job.
    """
    if not generation.obligations.resources and not generation.obligations.is_opaque:
        return True

    log.error(
        "issue=#%d still records external obligations under a damaged late "
        "identity; holding the umbrella open rather than closing over them",
        issue.number,
    )
    return False


def _report(
    gh: GitHubClient,
    issue: Issue,
    settled: _late_cleanup_state._Reclamation,
    *,
    stage: str | None,
) -> None:
    """Say on both sinks what each attempted reclamation changed.

    One `late_cleanup` per obligation whose recorded state MOVED, carrying the
    state the record now gives it. A typed failure rides with the one state
    that names a remote that REFUSED; an obligation still `reclaiming` is work
    in progress, not a failure, and says so by carrying that state rather than
    a second event. A retry that reached the same answer as the visit before
    it reports nothing at all: the record already carries that answer, and a
    stream of identical failures is one fact repeated per cadence rather than
    a second thing having gone wrong.

    The log is the other half and is deliberately not bounded that way. Every
    entry short of `reconciled` is warned about on every visit that attempted
    it, because a visit that keeps happening is happening for one of these,
    and an object nobody can reclaim has to stay visible for as long as it is
    held rather than only on the tick it first refused.
    """
    for moved in settled.moved:
        _emit_cleanup(gh, settled.generation, moved, stage)
    for entry in settled.entries:
        if entry.resource_state != _obligations.LateResourceState.RECONCILED:
            log.warning(
                "issue=#%d still owes the remote %s %r (%s); it is retried "
                "on every visit until it is reclaimed",
                issue.number,
                entry.kind,
                entry.target,
                entry.resource_state,
            )


def _emit_cleanup(
    gh: GitHubClient,
    generation: LateGeneration,
    entry: _obligations.LateResource,
    stage: str | None,
) -> None:
    """Report what happened to one external resource, on both sinks."""
    if entry.resource_state == _obligations.LateResourceState.FAILED:
        _telemetry.emit_late_event(
            gh,
            _events.LateEvent(
                family=_events.LateEventFamily.FAILURE,
                failure=_FAILURES[entry.kind],
            ),
            generation,
            stage=stage,
        )
    _telemetry.emit_late_event(
        gh,
        _events.LateEvent(
            family=_events.LateEventFamily.CLEANUP,
            resource=entry,
        ),
        generation,
        stage=stage,
    )
