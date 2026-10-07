# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The typed handoffs an automatic PR base rewrite crosses the git boundary as.

Two records, one per boundary. A `_RewriteCandidate` is what a rebase left
behind -- the head the pull request stood on and the head the replay produced,
the trees they carry, whether the checkout is provably clean, the base the
replay sits over, where the remote says the branch is, and which attempt made
it. A `_LandedRewrite` is what one lease-pinned publication of that candidate
came to, an answer nobody could confirm included.

Data and nothing else. Neither carries a GitHub client, an issue, the pinned
state, or anything to call back into, so whatever decides on a candidate --
the size gate, the transfer permit, the announcement, the route -- reads these
records and owns its own writes. The readings are taken by `rewrite_facts` and
the push is made by `rewrite_transport`, so every reading here is one of
theirs; only the attempt and the branch are handed in, as the attempt pinned
them before git ran.

The ordinary publication of a clean rebase crosses here: the workflow reads
the candidate the rebase left, rules on it with the size gate and the transfer
permit, has exactly that candidate published, and hands the landed record to
its finish (`workflow/engine/rewrite_publication.py`,
`workflow/engine/rewrite_finish.py`). A crash recovery does not yet: it still
recovers through `replay_recovery` and `persistence`, reached from the
workflow's base-rewrite coordinator (`workflow/engine/base_rewrite.py`), and
the observation of a landing an earlier tick left stays dormant until it takes
that road over.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.ref_transport import _RefRead
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.state import WorkflowLabel


class _RewriteRefusal(StrEnum):
    """Why a candidate may not be published, named rather than swallowed.

    Members are `StrEnum` so what a log line or a park reason carries is the
    member itself. Unreadable and moved are kept apart for every fact that
    can be either, because the operator's next step differs: a reading that
    did not happen is a checkout or a transport to look at, while one that
    happened and disagrees is somebody else's write to account for.
    """

    UNREADABLE_HEAD = "unreadable_head"
    UNMOVED = "unmoved"
    UNREADABLE_TREE = "unreadable_tree"
    DIRTY_TREE = "dirty_tree"
    UNREADABLE_BASE = "unreadable_base"
    UNREADABLE_REMOTE = "unreadable_remote"
    PUBLISHED = "published"
    MOVED_REMOTE = "moved_remote"
    MOVED_CHECKOUT = "moved_checkout"
    MOVED_BASE = "moved_base"


class _PushOutcome(StrEnum):
    """What one publication of a candidate came to, as far as anyone can say.

    `REFUSED` sent nothing: a guard stopped it first -- for a remote already
    on the candidate, one the caller may have proved still there with a push
    leased to the candidate itself, which has nothing to send. `ACCEPTED` is git
    answering that the leased update landed. The other two are a push git
    answered with a failure, told apart by reading the remote again:
    `REJECTED` found the branch somewhere other than the candidate, so nothing
    of this push is there, and `UNCERTAIN` found it ON the candidate -- an
    update that landed and whose answer was lost -- or could not read it at
    all. That last pair is one outcome because the response itself is what
    cannot be trusted; `landed` on the record says which of the two it was.

    `OBSERVED` is no push at all: the remote read as it stands, for a rewrite
    an earlier tick may already have published.
    """

    REFUSED = "refused"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"
    OBSERVED = "observed"


@dataclass(frozen=True)
class _RewriteAttempt:
    """Which attempt a rewrite belongs to, in the terms it was started under.

    `anchor` is the head the pull request stood on before git ran: the commit
    the rewrite replaced, and the lease its publication is pinned to. The pull
    request and the stage are the publication the attempt was made for. All
    three are the attempt's own, pinned before the rebase, which is why a
    caller hands them in rather than having them re-read off the issue.
    """

    anchor: str
    pr_number: int
    stage: WorkflowLabel | None


@dataclass(frozen=True)
class _CheckoutReading:
    """One reading of the checkout a rewrite stands in, taken together.

    `head` is the proved commit the checkout is on and `tree` is that commit's
    tree, each "" where it could not be read. `status` is the hardened worktree
    status, unreadable kept apart from empty. `base` is the head counted
    against `<remote>/<base>`, resolved once: its tip is the base the replay
    sits over and its `behind` says whether that base has advanced past it.
    """

    head: str
    tree: str
    status: _WorktreeStatus
    base: _BranchDivergence


@dataclass(frozen=True)
class _RewriteCandidate:
    """What a rebase left behind, as the evidence its publication is decided on.

    `original_tree` is the tree of the head the rewrite replaced; the
    rewritten head and its tree are on `checkout`. `remote` is what the remote
    said the branch was at when the candidate was prepared.
    """

    attempt: _RewriteAttempt
    branch: str
    original_tree: str
    checkout: _CheckoutReading
    remote: _RefRead

    @property
    def original_head(self) -> str:
        """The head the rewrite replaced, which is also the publication's lease."""
        return self.attempt.anchor

    @property
    def rewritten_head(self) -> str:
        """The head the rewrite produced, which is the commit a publication names."""
        return self.checkout.head

    @property
    def refusal(self) -> _RewriteRefusal | None:
        """The first reason this candidate may not be published, or None.

        Asked in the order the auto-rebase publisher asks its own: a head
        nobody can name, then a rebase that moved nothing -- which is no
        failure, only nothing to send -- then a tree that is not provably
        clean, and only then the base and the remote the push would go out
        over. A remote already on the candidate is refused too, since a
        second push of it is exactly what a recovery has to avoid; a remote on
        anything but the anchor is one the lease would reject, so it is
        refused before anything is sent.
        """
        remote = self.remote.sha
        refusals = (
            (not (self.original_head and self.rewritten_head), _RewriteRefusal.UNREADABLE_HEAD),
            (self.rewritten_head == self.original_head, _RewriteRefusal.UNMOVED),
            (not self._trees_read(), _RewriteRefusal.UNREADABLE_TREE),
            (bool(self.checkout.status.paths), _RewriteRefusal.DIRTY_TREE),
            (not self.checkout.base.readable, _RewriteRefusal.UNREADABLE_BASE),
            (remote is None, _RewriteRefusal.UNREADABLE_REMOTE),
            (remote == self.rewritten_head, _RewriteRefusal.PUBLISHED),
            (remote != self.original_head, _RewriteRefusal.MOVED_REMOTE),
        )
        return next((refusal for refused, refusal in refusals if refused), None)

    def _trees_read(self) -> bool:
        """Whether both tree identities and the status reading happened."""
        return bool(
            self.original_tree
            and self.checkout.tree
            and self.checkout.status.readable,
        )


@dataclass(frozen=True)
class _LandedRewrite:
    """What one publication of a candidate came to, beside the candidate itself.

    `remote` is the latest answer about the branch this record holds: what git
    said the leased update left it at, what a reading taken after a push git
    did not confirm found, what an observation found standing, or -- for a
    refusal, which sent nothing -- the reading the refusal was decided on.
    `refusal` names the guard that stopped a `REFUSED` publication.
    """

    candidate: _RewriteCandidate
    outcome: _PushOutcome
    remote: _RefRead
    refusal: _RewriteRefusal | None = None

    @property
    def landed(self) -> bool:
        """Whether the remote was shown standing on the candidate.

        False on an `UNCERTAIN` outcome whose reading failed, and that is not
        a "no": neither the response nor the reading established where the
        branch is, which only the outcome beside this says.
        """
        rewritten = self.candidate.rewritten_head
        return bool(rewritten) and self.remote.sha == rewritten
