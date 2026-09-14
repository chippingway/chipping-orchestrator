# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why an artifact branch tip must remain after its issue has ended.

Publication identity, base containment, and ended pull-request accounting
prove where a commit survives; failed reads retain the branch."""
from __future__ import annotations

from itertools import chain

from orchestrator.git.worktrees import commit_claims, tip_evidence as _tip_evidence
from orchestrator.git.worktrees.candidates import IssueArtifacts
from orchestrator.git.worktrees.models import (
    BranchTip,
    ProbeAnswer,
    Retention,
    RetentionReason,
)
from orchestrator.github.client import GitHubClient


def _tip_retentions(
    gh: GitHubClient,
    artifacts: IssueArtifacts,
    base: BranchTip,
    branch: str,
    tip_sha: str,
) -> tuple[Retention, ...]:
    """Why one commit an artifact is holding may not go with it.

    The remote is asked first, and asked whatever the base says, because the
    two answer different questions. The base says whether the commit about to
    be deleted survives the deletion; the remote says whether the branch this
    host holds is still the branch the remote has. A tip the base already
    carries can sit under a remote branch somebody has since pushed past --
    and a reclaim that took the ancestry as the whole answer would report the
    branch as free while work nobody here has seen stands on it.

    An answer that disagrees with the local tip ends it. The two disagreeing
    is divergence nothing here can explain: the branch was force-moved
    locally, or the remote moved on since it was pushed, and either way the
    commits on one side are not the commits on the other.

    A branch the remote does not carry is not divergence and does not end it.
    It is the ordinary shape of a finished issue -- the head branch of a
    merged pull request is deleted there -- so the question passes to the
    base, and from the base to the pull request that carried the commit.
    """
    published = _tip_evidence._published_tip(artifacts.spec, branch)
    if published.answer is ProbeAnswer.UNREADABLE:
        return (Retention(RetentionReason.REMOTE_UNREADABLE, branch),)
    if published.answer is ProbeAnswer.CONFIRMED and published.sha != tip_sha:
        return (Retention(RetentionReason.REMOTE_DIVERGENCE, branch),)
    contained = _tip_evidence._base_contains(artifacts.spec, base, tip_sha)
    if contained is ProbeAnswer.CONFIRMED:
        return ()
    if contained is ProbeAnswer.UNREADABLE:
        return (Retention(RetentionReason.BASE_UNREADABLE, branch),)
    return commit_claims._commit_accounting(gh, branch, tip_sha)


def _branch_retentions(
    gh: GitHubClient,
    artifacts: IssueArtifacts,
    base: BranchTip,
    branch: str,
    tip: BranchTip,
) -> tuple[Retention, ...]:
    """Why one of this issue's branches may not be deleted, if it may not.

    The proof runs on the tip rather than on a count of commits, because the
    tip is the only thing the two ways out are stated in: the base either
    contains that commit or it does not, and a pull request either carries it
    or carries something else. A branch whose tip the base already holds is
    the ordinary merged shape and needs nothing further.

    `base` and `tip` are both established once for the whole candidate and
    handed in: the base because every artifact under this issue is measured
    against the same commit, and the tip because the checkout beside this
    branch has to know what it is standing on to tell whether the branch is
    already holding it.

    A branch that has gone from BOTH hosts since the scan named it is eligible
    rather than a problem. There is nothing left to delete, and the
    alternative -- keeping an issue back over an artifact that no longer
    exists -- is a retention no operator could ever settle. Which hosts still
    have it is `_branch_tip`'s answer, not this one's: what arrives here is
    the commit the branch is standing on wherever it still stands.
    """
    if tip.answer is ProbeAnswer.UNREADABLE:
        return (Retention(RetentionReason.BRANCH_UNREADABLE, branch),)
    if tip.answer is ProbeAnswer.REFUTED:
        return ()
    return _tip_retentions(gh, artifacts, base, branch, tip.sha)


def _branch_tip(artifacts: IssueArtifacts, branch: str) -> BranchTip:
    """The commit one of this issue's branches stands on, wherever it stands.

    The clone's own ref first, because a branch this host holds is the
    artifact a teardown takes and the commit it would take with it. A branch
    the clone no longer has is not the same thing as an artifact that has
    gone: the scan named it moments earlier, something deleted it since, and
    the copy the remote carries is an artifact of this issue exactly as the
    local one was. So the remote is asked, and what it answers is what the
    proof runs on -- which is what lets an eligible verdict hand over a commit
    for that branch at all. Without one, the reclamation of the copy left on
    the remote would be a deletion nobody had proved and nothing had recorded.

    Both readings that failed come back as the tip that could not be read.
    Which side would not answer is not something an operator settles
    differently, and the retention over it names the branch either way.
    """
    tip = _tip_evidence._local_branch_tip(artifacts.spec, branch)
    if tip.answer is not ProbeAnswer.REFUTED:
        return tip
    return _tip_evidence._published_tip(artifacts.spec, branch)


def _branch_reasons(
    gh: GitHubClient,
    artifacts: IssueArtifacts,
    base: BranchTip,
    tips: tuple[BranchTip, ...],
) -> tuple[Retention, ...]:
    """Every reason this issue's branches give, in the order they were named.

    Each branch is put to the proof against the tip already read for it, so
    the reading the proof is about and the reading the caller hands on as what
    it cleared are one and the same.
    """
    return tuple(chain.from_iterable(
        _branch_retentions(gh, artifacts, base, branch, tip)
        for branch, tip in zip(artifacts.branches, tips)
    ))
