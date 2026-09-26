# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The git world one piece of verification evidence is proved against.

The fetch result and the divergence say what the ref the pull request is built
from looks like; `trees` says which commits this repository reads and the full
tree each carries, so a commit missing from it is one git could not read. They
travel on one record, owned apart from the case that uses them, so a case that
moves one of them is writing a world rather than a race.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.git.publication.probes import _BranchDivergence
from tests.workflow.engine.report_checkout_fixture import Fetched

TESTED_SHA = "3f786850e387550fdab836ed7e6dc881de23001b"

TESTED_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# A rewrite of the tested commit onto the same tree: a squash, or a docs pass
# that changed nothing.
SQUASHED_SHA = "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"

# A rewrite that replays the same patches over a base that moved: the patches
# match, the tree does not.
REBASED_SHA = "1f40fc92da241694750979ee6cf582f2d5d7d28e"

REBASED_TREE = "d670460b4b4aece5915caf5c68d12f560a9fe3e4"


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

    def fetch(self, *_args, **_kw) -> Fetched:
        """What `_authed_fetch` hands back in this world."""
        return Fetched(self.fetched)

    def divergence(self, *_args, **_kw) -> _BranchDivergence:
        """What `_branch_divergence` reads in this world."""
        return self.remote

    def commit_present(self, _worktree, commit: str, *_rest) -> bool:
        """Whether this repository reads `commit` as a commit."""
        return commit in self.trees

    def tree_sha(self, _worktree, commit: str) -> str:
        """The tree this repository reads for `commit`, or "" for none."""
        return self.trees.get(commit, "")
