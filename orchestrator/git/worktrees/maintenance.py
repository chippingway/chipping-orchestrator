# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A bounded maintenance pass over classified artifact candidates.

Claims, eligibility, recent activity, and continuation are checked in order.
Checkout and branch removal owners spend the same proven tips immediately
before each mutation, stopping the candidate at the first refusal. Results
record that ordered outcome without retaining a retry queue between passes."""
from __future__ import annotations

import logging
from collections.abc import Iterable

from orchestrator.git.worktrees import (
    branch_removal as _branch_removal,
    candidates as _candidates,
    checkout_removal as _checkout_removal,
    eligibility,
    maintenance_guards as _maintenance_guards,
    maintenance_results as _maintenance_results,
    models as _models,
)
from orchestrator.github.client import GitHubClient

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so every artifact this pass takes or
# refuses to take reports where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")


def _kept_subject(verdict: _models.ArtifactVerdict) -> str:
    """The artifact the first reason a classification kept this candidate for names."""
    return verdict.retentions[0].subject if verdict.retentions else ""


def _cleared_tips(proven: tuple[_models.ProvenTip, ...]) -> dict[str, str]:
    """The commit each cleared artifact was standing on, by the artifact's name.

    Keyed the way a proof spells its subject -- a branch by name, a checkout by
    path -- so a teardown looking one up names the artifact exactly as the
    classification did rather than deriving a second spelling of it.
    """
    return {tip.subject: tip.sha for tip in proven}


def _reclaimed(
    candidate: _candidates.MaintenanceCandidate, proven: tuple[_models.ProvenTip, ...],
) -> _maintenance_results.MaintenanceResult:
    """Run the whole teardown for one cleared candidate, and say where it got to."""
    cleared = _cleared_tips(proven)
    stopped = (
        _checkout_removal._take_checkouts(candidate, cleared)
        or _branch_removal._take_branches(candidate, cleared)
    )
    return stopped or _maintenance_results._answered(candidate, _maintenance_results.MaintenanceReason.RECLAIMED)


def _maintained_candidate(
    gh: GitHubClient,
    candidate: _candidates.MaintenanceCandidate,
    *,
    claimed: _maintenance_guards.ActivityGuard,
    going: _maintenance_guards.ContinuationGuard,
) -> _maintenance_results.MaintenanceResult | None:
    """Decide about one candidate, and act on it if everything clears it.

    The classification is taken here rather than handed in, because what it
    reads is what the mutations are pinned to: a verdict taken a tick earlier
    would clear commits the artifacts have since left, and the teardown would
    then be spending a proof about branches that no longer exist.

    `None` is the pass being stopped between the readings and the teardown, and
    it is a different answer from every other one here: the others are what
    this candidate IS, and this one is that nothing was decided about it. The
    reading is taken last, immediately before the first mutation, because the
    readings above it are where the seconds go -- an issue, its pull requests,
    what the remote carries -- and a stop that arrived during them may not be
    answered by deleting anyway.

    Once past it the candidate is taken as ONE unit rather than checked again
    between its artifacts. A teardown is a checkout removal and two pinned ref
    deletes, each already leased to a commit and each idempotent; stopping in
    the middle of them would trade a state this vocabulary can report for one
    it cannot, and buy microseconds of earlier exit for it.
    """
    artifacts = candidate.artifacts
    active = _maintenance_guards._claim_reason(artifacts, claimed)
    if active is not None:
        return _maintenance_results._answered(candidate, active, f"#{artifacts.issue_number}")
    verdict = eligibility._classify_artifacts(gh, artifacts)
    if not verdict.eligible:
        return _maintenance_results._answered(
            candidate,
            _maintenance_results.MaintenanceReason.UNPROVEN,
            _kept_subject(verdict),
            verdict.retentions,
        )
    quiet, disturbed = _maintenance_guards._activity_reason(artifacts)
    if quiet is not None:
        return _maintenance_results._answered(candidate, quiet, disturbed)
    if _maintenance_guards._stopped(going):
        return None
    return _reclaimed(candidate, verdict.proven)


def _maintained_candidates(
    gh: GitHubClient,
    candidates: Iterable[_candidates.MaintenanceCandidate],
    *,
    claimed: _maintenance_guards.ActivityGuard,
    going: _maintenance_guards.ContinuationGuard,
) -> tuple[_maintenance_results.MaintenanceResult, ...]:
    """Run the pass over every candidate of ONE repository, in its order.

    One client for the lot, so the caller is what splits a discovery spanning
    several repositories: the client is authenticated against one repository,
    and asking it about another's issue number would answer about whatever
    issue happens to carry that number there -- and then delete branches on the
    strength of it.

    Every candidate this pass DECIDED about gets a result, the untouched ones
    included: a caller holding only what was cleaned cannot tell a candidate
    this pass kept from one it never reached, and the second is what a pass
    that died half way through looks like. The candidates behind a stop are
    the ones it decided nothing about, and they get none -- so the answer is
    the prefix it reached, in the order the discovery named them.

    Whether it may still act is asked before EACH candidate rather than once
    for the repository, because what a caller is being asked is not a property
    of the artifacts: a process that has begun stopping has no standing to
    spend the quiet it was granted a moment ago, and one asked a repository at
    a time would spend the whole of the repository it was already inside. The
    candidate itself asks once more before it acts, and answers `None` when
    that reading is what stopped it -- so a stop arriving DURING the readings
    ends the pass here rather than being noticed one candidate later.

    A candidate the pass stops before has no answer at all, which is exactly
    what an interrupted pass has always looked like from here.
    """
    answers: list[_maintenance_results.MaintenanceResult] = []
    for candidate in candidates:
        answered = None if _maintenance_guards._stopped(going) else _maintained_candidate(
            gh, candidate, claimed=claimed, going=going,
        )
        if answered is None:
            log.info(
                "issue=#%d artifacts left alone: this pass may no longer act",
                candidate.artifacts.issue_number,
            )
            break
        answers.append(answered)
    return tuple(answers)
