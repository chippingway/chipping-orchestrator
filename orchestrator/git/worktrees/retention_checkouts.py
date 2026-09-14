# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Identity, cleanliness, and surviving-commit proofs for one checkout.

The ownership check gates all content reads, so a clean foreign checkout can
never supply evidence for deleting another issue's work."""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple

from orchestrator.git.worktrees import (
    evidence,
    retention_tips as _retention_tips,
    tip_evidence as _tip_evidence,
)
from orchestrator.git.worktrees.candidates import IssueArtifacts
from orchestrator.git.worktrees.models import (
    BranchTip,
    ProbeAnswer,
    Retention,
    RetentionReason,
)
from orchestrator.github.client import GitHubClient

# Nothing is reported from here. Every read this composes is behind a
# boundary in ``claims``, ``commit_claims``, or ``evidence`` that already names
# what it could not take, and a retention is returned rather than logged: what
# an operator is shown about a candidate is the caller's to decide, once,
# rather than this pass's to repeat every tick.

# What each answer about the checkout costs, as the reason it is kept for.
# `CONFIRMED` is absent from both tables on purpose: it is the only answer
# that costs nothing, so a lookup that misses is the checkout passing.
_IDENTITY_REASONS = MappingProxyType({
    ProbeAnswer.UNREADABLE: RetentionReason.CHECKOUT_UNREADABLE,
    ProbeAnswer.REFUTED: RetentionReason.FOREIGN_CHECKOUT,
})

_CLEANLINESS_REASONS = MappingProxyType({
    ProbeAnswer.UNREADABLE: RetentionReason.WORKTREE_UNREADABLE,
    ProbeAnswer.REFUTED: RetentionReason.WORKTREE_DIRTY,
})

# What a tree hiding files under its own ignore rules costs. Apart from the
# table above because what an operator does with it differs: `git status` shows
# them nothing, and what they have to go and look at is what the rules cover.
_HIDDEN_REASONS = MappingProxyType({
    ProbeAnswer.UNREADABLE: RetentionReason.WORKTREE_UNREADABLE,
    ProbeAnswer.REFUTED: RetentionReason.WORKTREE_IGNORED,
})


class _CheckoutReads(NamedTuple):
    """The three readings one checkout's commit proof is measured against.

    Carried together because they are established together and spent together:
    the base once for the whole candidate, the branch tips once for all of its
    checkouts, and the HEAD of the one checkout being judged. Passed as three
    arguments instead, a caller could hand over a head belonging to another
    tree -- which on an issue holding both checkout layouts is a reading that
    clears the wrong directory.
    """

    base: BranchTip
    tips: tuple[BranchTip, ...]
    head: BranchTip


def _checkout_retentions(
    artifacts: IssueArtifacts, worktree: Path,
) -> tuple[Retention, ...]:
    """Why one of this issue's checkouts may not be removed, if it may not.

    Identity first, and the cleanliness read is skipped when it fails.
    Whether a tree is carrying loose files is a question about the tree, and
    a directory that is not this issue's checkout is one whose answer says
    nothing about what removing it would cost -- an empty foreign clone is
    exactly as clean as an empty one of ours, and a probe reporting so would
    be handing over the reason to delete it.

    An issue with no checkout on this host has nothing to keep, which is a
    real answer rather than an unasked question: the scan reports the
    branch-only shape as such, and the reads below would have no path to run
    in.
    """
    kept_for = _checkout_reason(artifacts, worktree)
    if kept_for is None:
        return ()
    return (Retention(kept_for, str(worktree)),)


def _checkout_reason(
    artifacts: IssueArtifacts, worktree: Path,
) -> RetentionReason | None:
    """The first thing about this checkout that keeps it, if anything does.

    Three reads in the order they may be spent, each skipped once one before
    it has refused. Identity gates both of the others for the reason given
    above; the two about what the tree holds are asked in the order git
    itself would meet them, since a tree that is dirty is one `worktree
    remove` refuses without being asked anything further.

    What is hidden is asked at all because git does not ask it. Untracked and
    modified paths are what a removal that does not force refuses over; a path
    the repository's own rules cover is neither, so a tree carrying nothing
    else answers clean and comes down with whatever is under those rules
    inside it.
    """
    identity = evidence._checkout_identity(
        artifacts.spec, artifacts.issue_number, worktree,
    )
    kept_for = _IDENTITY_REASONS.get(identity)
    if kept_for is not None:
        return kept_for
    kept_for = _CLEANLINESS_REASONS.get(evidence._clean_worktree(worktree))
    if kept_for is not None:
        return kept_for
    return _HIDDEN_REASONS.get(evidence._nothing_ignored(worktree))


def _checkout_tip_retentions(
    gh: GitHubClient,
    artifacts: IssueArtifacts,
    worktree: Path,
    reads: _CheckoutReads,
) -> tuple[Retention, ...]:
    """Why the commit one checkout stands on may not be removed with it.

    A checkout is an artifact that HOLDS something rather than a directory
    that merely sits somewhere. A linked worktree keeps a HEAD and a reflog of
    its own, and when no ref points at the commit that HEAD names, those two
    are the only things keeping it reachable -- so removing the checkout is
    what takes the commit, and the proof a branch owes is owed here too.

    A commit one of this issue's reported branches is standing on needs
    nothing further: that branch is proven on its own terms, and whichever way
    its verdict goes the checkout is not the only thing holding the commit.
    Equality is the whole of that test -- a HEAD somewhere further back in a
    branch's history is not something this establishes cheaply, and it fails
    closed.

    A HEAD that names no commit is the shape this exists for, and it is
    reported as a checkout nothing could be established about. `update-ref -d`
    removes a branch a live checkout is on, and afterwards every other reading
    comes back unchanged: the symbolic ref still spells this issue's branch,
    and a tree whose commits went with it still reports clean. That read is
    handed in rather than taken here, because the commit it resolves is also
    what an eligible verdict has to hand over -- one reading, spent twice.

    What is left runs the proof a branch runs, on the branch HEAD is on. The
    commit is a branch tip whichever artifact the report names it through, so
    a rejected issue reported as a checkout alone reaches the same pull
    request -- and the same verdict -- as one reported as a branch. Anything
    narrower would have the three shapes of one issue disagree.
    """
    on_branch, branch = evidence._head_ref(worktree)
    answers = (reads.head.answer, on_branch)
    if any(answer is not ProbeAnswer.CONFIRMED for answer in answers):
        return (Retention(
            RetentionReason.CHECKOUT_UNREADABLE, str(worktree),
        ),)
    if any(tip.sha == reads.head.sha for tip in reads.tips):
        return ()
    return _retention_tips._tip_retentions(
        gh, artifacts, reads.base, branch, reads.head.sha,
    )


def _checkout_head(
    worktree: Path, kept: tuple[Retention, ...],
) -> BranchTip:
    """The commit one checkout stands on, when it is worth resolving.

    Answered as the read that established nothing where it is not taken at
    all: a checkout something about the tree itself already refuses. That is
    the reason the read is skipped rather than merely ignored -- a directory
    that is not this issue's checkout is one whose HEAD says nothing about
    what removing it would cost.
    """
    if kept:
        return BranchTip(answer=ProbeAnswer.UNREADABLE)
    return _tip_evidence._checkout_tip(worktree)


def _checkout_reading(
    gh: GitHubClient,
    artifacts: IssueArtifacts,
    worktree: Path,
    base: BranchTip,
    tips: tuple[BranchTip, ...],
) -> tuple[tuple[Retention, ...], BranchTip]:
    """One checkout's whole answer: why it is kept, and what it is holding.

    Per checkout rather than per issue, because an issue that was in flight
    when slug namespacing landed can be holding two of them -- the flat one it
    started in and the per-repository one the next tick made -- and they are
    two directories with two trees, two HEADs, and two reflogs. A reading that
    covered one of them would clear the issue while the other stayed on disk
    with whatever it holds.

    The tree's own state gates the commit read for the reason it always has: a
    directory that is not this issue's checkout is one whose HEAD says nothing
    about what removing it would cost.
    """
    kept = _checkout_retentions(artifacts, worktree)
    head = _checkout_head(worktree, kept)
    if kept:
        return kept, head
    return _checkout_tip_retentions(
        gh, artifacts, worktree, _CheckoutReads(base, tips, head),
    ), head
