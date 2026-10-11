# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The git world one piece of verification evidence is proved against.

The fetch result and the divergence say what the ref the pull request is built
from looks like -- the checkout on the branch's head, or a commit past it where
it is ahead -- `remote_answers` whether the remote answers a read of the branch
at all, and `base` where a landed rewrite's head stands against the base it was
counted against; `trees` says which commits this repository reads and the full
tree each carries, so a commit missing from it is one git could not read; and
`tags` says which ids are annotated tags and the commit each points at. The
tags are answered as git answers them: `^{tree}` peels one to its commit's
tree, and only the unpeeled type says it is a tag. They travel on one record,
owned apart from the case that uses them, so a case that moves one of them is
writing a world rather than a race.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding, _CheckoutReading
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.ref_transport import _RefRead
from orchestrator.git.verification.status import _WorktreeStatus
from tests.workflow.engine import verification_record_test_support as _record_support
from tests.workflow.engine.report_checkout_fixture import Fetched

BRANCH = _record_support.BRANCH

TESTED_SHA = _record_support.TESTED_SHA

TESTED_TREE = _record_support.TESTED_TREE

# A rewrite of the tested commit onto the same tree: a squash, or a docs pass
# that changed nothing.
SQUASHED_SHA = "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"

# A rewrite that replays the same patches over a base that moved: the patches
# match, the tree does not.
REBASED_SHA = _record_support.REBASED_SHA

REBASED_TREE = "d670460b4b4aece5915caf5c68d12f560a9fe3e4"

# An annotated tag object pointing at the squash: peeled, it reads as the
# tested tree, and it is not a commit.
TAG_SHA = "c3499c2729730a7f807efb8676a92dcb6f8a3f8f"

# A commit the checkout made past the head its remote branch stands on.
STRAY_SHA = "5742a7c0" * 5


def standing_on(head: str) -> _BranchDivergence:
    """A remote branch, and a checkout in sync with it, standing on `head`."""
    return _BranchDivergence(tip=head, readable=True)


def unreadable_divergence() -> _BranchDivergence:
    """A comparison git refused, which says nothing about where anything stands."""
    return _BranchDivergence()


@dataclass
class EvidenceWorld:
    """Every git reading the evidence proof takes, answered from one record."""

    path: Path
    fetched: int = 0
    remote: _BranchDivergence = field(default_factory=lambda: standing_on(TESTED_SHA))
    trees: dict[str, str] = field(default_factory=lambda: {
        TESTED_SHA: TESTED_TREE, SQUASHED_SHA: TESTED_TREE, REBASED_SHA: REBASED_TREE,
    })
    tags: dict[str, str] = field(default_factory=lambda: {TAG_SHA: SQUASHED_SHA})
    base: _BaseStanding = _BaseStanding.STANDING
    remote_answers: bool = True
    checkout_head: str = ""

    def fetch(self, *_args, **_kw) -> Fetched:
        """What `_authed_fetch` hands back in this world."""
        return Fetched(self.fetched)

    def divergence(self, *_args, **_kw) -> _BranchDivergence:
        """What `_branch_divergence` reads in this world."""
        return self.remote

    def standing(self, *_args) -> _BaseStanding:
        """Where a landed head stands against its base in this world (`_standing_on_the_remote_base`)."""
        return self.base

    def commit_present(self, _worktree, revision: str, *_rest, peeled: bool = True) -> bool:
        """Whether `revision` reads as a commit here -- peeled through a tag, unless not."""
        return revision in self.trees or (peeled and revision in self.tags)

    def tree_sha(self, _worktree, revision: str) -> str:
        """The tree `revision` peels to in this world, or "" for none."""
        return self.trees.get(self.tags.get(revision, revision), "")

    def retags(self, commit: str) -> None:
        """Make `commit` an annotated tag of the squash rather than a commit."""
        self.trees.pop(commit)
        self.tags[commit] = SQUASHED_SHA


def remote_read(world: EvidenceWorld, *_args) -> _RefRead:
    """What `_remote_branch_read` answers for the pull request's branch in `world`: its head, or nothing it read."""
    return _RefRead(sha=world.remote.tip if world.remote_answers else None)


def checkout_of(world: EvidenceWorld, *_args) -> _CheckoutReading:
    """What `_reads_the_checkout` reads in `world`: the remote branch's head, or a commit past it the checkout made.

    `checkout_head` stands the checkout somewhere of its own instead, with the
    divergence every other reading takes left as it is.
    """
    head = world.checkout_head
    if not head:
        head = STRAY_SHA if world.remote.ahead else world.remote.tip
    return _CheckoutReading(
        head=head,
        tree=world.trees.get(head, ""),
        status=_WorktreeStatus(readable=True),
        base=world.remote,
    )
