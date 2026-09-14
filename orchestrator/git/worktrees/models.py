# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Eligibility evidence and retention reasons for one discovered candidate.

Discovery records live in candidates; maintenance_results describes a pass
that acts on an eligible verdict. The closed reason vocabulary and proven
commit identities here are shared by those two boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.git.worktrees import candidates as _candidates


class ProbeAnswer(StrEnum):
    """What one fail-closed local read established about an artifact.

    Three answers rather than two, because a caller about to reclaim
    something has to spend the third differently. `REFUTED` is the host
    saying no -- the tree carries changes, the checkout is on somebody
    else's branch -- and it is an established fact about the artifact.
    `UNREADABLE` is the host saying nothing at all: git could not be run, the
    repository would not answer, the exit status was one nothing here claims
    to understand. Collapsed into `REFUTED` it would read as an artifact that
    was inspected and found wanting, and collapsed into `CONFIRMED` it would
    reclaim work on the strength of a probe that never ran.
    """

    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class BranchTip:
    """The commit one ref read resolved, or the way it did not resolve.

    `sha` carries a value under `CONFIRMED` and is empty under the other two,
    so a caller that reads it without asking `answer` first measures against
    an empty string rather than against a commit -- which every git probe
    then refuses, since the empty revision names nothing.

    `REFUTED` is the ref not being there, which for a branch this scan
    reported a moment ago means it has since been deleted; `UNREADABLE` is
    the read that could not say either way.
    """

    answer: ProbeAnswer
    sha: str = ""


class RetentionReason(StrEnum):
    """Why one candidate is kept rather than reclaimed.

    Every member names something an operator can go and look at, because a
    retention that repeats every tick is one somebody has to be able to
    settle: which read failed, which artifact carries what, which claim on
    GitHub is still open. A single "not eligible" would say only that the
    orchestrator will not touch it, and never why.

    The three families the classifier fails closed on are all here and stay
    apart. What was ASKED and answered no -- an open pull request, a dirty
    tree, a tree hiding files its own rules cover, commits nothing accounts
    for -- is a fact about the artifact. What could not be asked -- an issue,
    a pinned comment, a pull-request lookup, a git read -- is the absence of
    one. And what was asked and answered
    something nobody here can act on -- an issue in two workflow states at
    once, a pinned comment carrying something that is not a state, a checkout
    on a branch this issue never published -- is neither.

    The third family is kept apart from the second for what an operator does
    with it. A read that failed is transient and clears itself; a pinned
    comment holding a JSON array never clears, and an operator sent to check
    the API for it would find nothing wrong there.
    """

    ISSUE_UNREADABLE = "issue_unreadable"
    STATE_UNREADABLE = "state_unreadable"
    STATE_MALFORMED = "state_malformed"
    ISSUE_OPEN = "issue_open"
    NO_WORKFLOW_LABEL = "no_workflow_label"
    AMBIGUOUS_WORKFLOW_LABEL = "ambiguous_workflow_label"
    NON_TERMINAL_LABEL = "non_terminal_label"
    OPEN_PULL_REQUEST = "open_pull_request"
    PULL_REQUEST_UNREADABLE = "pull_request_unreadable"
    CHECKOUT_UNREADABLE = "checkout_unreadable"
    FOREIGN_CHECKOUT = "foreign_checkout"
    WORKTREE_UNREADABLE = "worktree_unreadable"
    WORKTREE_DIRTY = "worktree_dirty"
    WORKTREE_IGNORED = "worktree_ignored"
    BRANCH_UNREADABLE = "branch_unreadable"
    BASE_UNREADABLE = "base_unreadable"
    REMOTE_UNREADABLE = "remote_unreadable"
    REMOTE_DIVERGENCE = "remote_divergence"
    UNACCOUNTED_COMMITS = "unaccounted_commits"


@dataclass(frozen=True)
class Retention:
    """One reason a candidate is kept, and the thing that reason is about.

    The subject is carried beside the reason because the reason alone is not
    something anybody can act on: an issue can hold two branches and a
    checkout, and "a branch could not be read" sends an operator looking
    through all of them. It is the artifact's own name -- a branch, a
    checkout path, a pull request, a label -- rather than a rendered
    sentence, so a caller is free to report it as it likes.
    """

    reason: RetentionReason
    subject: str


@dataclass(frozen=True)
class ProvenTip:
    """One commit a classification cleared, and the artifact holding it.

    What an eligible verdict hands over to the teardown that spends it. Every
    proof a classification takes is about a COMMIT -- the base already carries
    it, a pull request that has ended published it -- and the artifact it was
    read from is standing on that commit and no other. A teardown holding only
    the artifact's name would delete whatever that name resolves to by the
    time it gets there, which is not necessarily what anybody proved: a branch
    an agent has committed onto since is the same branch by name and a
    different one by every test that cleared it.

    The subject is spelled the way a retention's is -- a branch by name, a
    checkout by path -- so a caller holding either half of the answer names
    the artifact the same way.
    """

    subject: str
    sha: str


@dataclass(frozen=True)
class ArtifactVerdict:
    """What one classification decided about one issue's artifacts.

    Eligibility is the absence of every reason to keep the artifacts, never
    a flag set beside them: a classifier that reached a failure it did not
    recognize adds a retention, and a verdict cannot come back eligible
    while holding one.

    The candidate is carried along so a caller acting on a verdict does not
    have to pair it back up with the scan that produced it -- and so the
    artifacts it acts on are exactly the ones the classification was about,
    rather than a re-derivation of them.
    """

    artifacts: _candidates.IssueArtifacts
    retentions: tuple[Retention, ...] = ()
    proven: tuple[ProvenTip, ...] = ()

    @property
    def eligible(self) -> bool:
        """Whether every artifact reported for this issue may be reclaimed."""
        return not self.retentions
