# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Classify discovered artifacts without changing issues, refs, or checkouts.

Issue state and open pull requests are checked before artifact content. The
checkout and branch retention owners prove what survives removal, and this
classifier returns both the reasons to retain and every exact tip it cleared.
An unreadable claim or proof always retains the candidate."""
from __future__ import annotations

from collections.abc import Iterable
from itertools import chain

from orchestrator.git.worktrees import (
    claims,
    retention_checkouts as _retention_checkouts,
    retention_tips as _retention_tips,
    tip_evidence as _tip_evidence,
)
from orchestrator.git.worktrees.candidates import IssueArtifacts
from orchestrator.git.worktrees.models import (
    ArtifactVerdict,
    BranchTip,
    ProbeAnswer,
    ProvenTip,
    Retention,
    RetentionReason,
)
from orchestrator.github.client import GitHubClient


def _proven_tips(
    artifacts: IssueArtifacts,
    heads: tuple[BranchTip, ...],
    tips: tuple[BranchTip, ...],
) -> tuple[ProvenTip, ...]:
    """Every commit this reading found an artifact of this issue standing on.

    The proof an eligible verdict is spent on, in the artifacts' own order:
    the checkouts first, since that is the order the teardown takes them down
    in, and then one entry per branch the clone still carries.

    An artifact that has gone since the scan named it contributes nothing,
    which is the same answer the classification gives it: there is no commit
    to clear because there is no longer anything holding one. A teardown that
    found the name back in place would then be holding no proof for it, and
    proof is what it deletes on.
    """
    return tuple(
        ProvenTip(str(worktree), head.sha)
        for worktree, head in zip(artifacts.worktrees, heads)
        if head.answer is ProbeAnswer.CONFIRMED
    ) + tuple(
        ProvenTip(branch, tip.sha)
        for branch, tip in zip(artifacts.branches, tips)
        if tip.answer is ProbeAnswer.CONFIRMED
    )


def _artifact_reading(
    gh: GitHubClient, artifacts: IssueArtifacts,
) -> tuple[tuple[Retention, ...], tuple[ProvenTip, ...]]:
    """What the artifacts say: why they are kept, and what they are holding.

    Every side is read even when one of them already refuses, because what an
    operator is being handed is a list of what to go and look at. A dirty
    checkout beside a branch nothing accounts for is two pieces of work in
    two places, and reporting only the first sends them back for the second
    on the tick after they clear it.

    Every side also owes the same proof, which is why a checkout is not done
    once it is clean: a commit is held by whatever points at it, and for a
    checkout whose branch is gone that is the checkout. Its tip is put to the
    proof only when nothing about that tree itself already refuses -- a tree
    that could not be read establishes nothing about what it holds either --
    and the branch tips are resolved first, so a commit one of them is already
    standing on is one the removal cannot strand.

    What the base is on is asked of the remote once and handed to every
    proof, since every artifact under this issue is measured against the same
    commit -- and it is asked only when there is an artifact to measure.

    The tips come back beside the reasons because they are the same readings.
    A caller that took the verdict and then re-read them would be acting on
    commits nobody adjudicated: between the two readings an agent can commit,
    and the branch that comes back is the one the proof is not about.
    """
    if not artifacts.worktrees and not artifacts.branches:
        return (), ()
    base = _tip_evidence._published_tip(
        artifacts.spec, artifacts.spec.base_branch,
    )
    tips = tuple(
        _retention_tips._branch_tip(artifacts, branch) for branch in artifacts.branches
    )
    return _read_artifacts(gh, artifacts, base, tips)


def _read_artifacts(
    gh: GitHubClient,
    artifacts: IssueArtifacts,
    base: BranchTip,
    tips: tuple[BranchTip, ...],
) -> tuple[tuple[Retention, ...], tuple[ProvenTip, ...]]:
    """The reading itself, once the base and the branch tips are established.

    Every checkout is read against the same two, so an issue holding both
    layouts measures them identically -- and the branch reasons are asked
    afterwards rather than first, so the answer reads in the artifacts' own
    order.
    """
    readings = tuple(
        _retention_checkouts._checkout_reading(gh, artifacts, worktree, base, tips)
        for worktree in artifacts.worktrees
    )
    return (
        tuple(chain.from_iterable(kept for kept, _head in readings))
        + _retention_tips._branch_reasons(gh, artifacts, base, tips),
        _proven_tips(artifacts, tuple(head for _kept, head in readings), tips),
    )


def _classify_artifacts(
    gh: GitHubClient, artifacts: IssueArtifacts,
) -> ArtifactVerdict:
    """Whether one discovered candidate's artifacts may be reclaimed.

    The remote gates come first and each one settles the verdict on its own.
    An issue that could not be fetched, one that has not ended, and one whose
    pinned state could not be read are all answers about whether this
    candidate is a candidate at all, and reading the host's artifacts under
    any of them would spend git processes on a question already closed.

    The pinned state is read after the ending is established rather than
    beside the issue, for the same reason: it costs a comment listing on
    every closed issue this host holds artifacts for, and an issue still
    running never needs it.

    The issue number every gate is spelled against is the candidate's own,
    never one read back off the fetched issue: the artifacts are what this
    verdict is about, and the attribute naming them on the issue is one more
    lazy read that can fail.

    Only the verdict that clears the artifacts carries what it cleared. A
    retained one has established that these commits stay, and a proof beside
    that answer would be a permission nothing here gave.
    """
    issue = claims._fetched_issue(gh, artifacts.issue_number)
    if issue is None:
        return ArtifactVerdict(artifacts, (Retention(
            RetentionReason.ISSUE_UNREADABLE, f"#{artifacts.issue_number}",
        ),))
    ended = claims._terminal_retentions(issue, artifacts.issue_number)
    if ended:
        return ArtifactVerdict(artifacts, ended)
    state = claims._read_state(gh, issue, artifacts.issue_number)
    if isinstance(state, Retention):
        return ArtifactVerdict(artifacts, (state,))
    claimed = claims._open_pull_request_retentions(
        gh, artifacts.spec, artifacts.issue_number, artifacts.branches, state,
    )
    if claimed:
        return ArtifactVerdict(artifacts, claimed)
    return _artifact_verdict(gh, artifacts)


def _artifact_verdict(
    gh: GitHubClient, artifacts: IssueArtifacts,
) -> ArtifactVerdict:
    """The verdict the artifacts' own reading comes to, once GitHub is done.

    The two halves of that reading are exclusive by construction: a candidate
    is cleared for exactly the commits it was found holding, and one that is
    kept hands over nothing at all.
    """
    kept, proven = _artifact_reading(gh, artifacts)
    if kept:
        return ArtifactVerdict(artifacts, kept)
    return ArtifactVerdict(artifacts, proven=proven)


def _classified_candidates(
    gh: GitHubClient, candidates: Iterable[IssueArtifacts],
) -> tuple[ArtifactVerdict, ...]:
    """Classify every candidate one repository's scan reported, in its order.

    One client for the lot, so the caller is the one that splits an inventory
    spanning several repositories: the client is authenticated against one
    repository and asking it about another repository's issue number would
    answer about whatever issue happens to carry that number there.

    Every candidate gets a verdict, the retained ones included. A caller
    holding only the eligible ones cannot tell an issue it may not touch from
    one this pass never reached, and the second is what a failure looks like.
    """
    return tuple(
        _classify_artifacts(gh, artifacts) for artifacts in candidates
    )
