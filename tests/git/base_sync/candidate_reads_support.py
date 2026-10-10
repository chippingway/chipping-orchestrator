# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a rewrite candidate is read on, for a base refresh with no checkout or remote behind it.

A clean rebase is published as the candidate the git owner reads off the
checkout and the remote: the trees of the head it replaced and of the head it
produced, the base the replay sits over, and where the remote has the branch.
A hermetic case has neither a checkout to read nor a token to reach a remote
with, so these answer the ordinary readings -- trees that read, a head level
with its base, and a remote branch on the head its pull request stands on in
the case's in-memory client, which a push a case lands, or one somebody else
makes, moves. A case about one of them seeds the one reading it is about.
"""
from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import MagicMock

from orchestrator.git import branch_transport
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.ref_transport import _RefRead
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from tests.git.base_sync.refresh_test_support import (
    CONFLICT_PR_HEAD_SHA,
    GATE_BASE_SHA,
    _patched,
)

# The tree every commit a candidate names reads as. Nothing past the reading
# compares two of them, so one id stands for all.
_TREE_SHA = "7ee5" * 10


class _LevelWithTheBase:
    """The divergence probe, answering the base branch as level with whatever is counted against it.

    Every other branch is read as the probe beneath reads it, so a case about
    a pull request branch keeps exactly what it seeds there.
    """

    def __init__(self, probe) -> None:
        self._probe = probe

    def __call__(self, spec, worktree, branch, *revision):
        if branch == spec.base_branch:
            return _publication_probes._BranchDivergence(tip=GATE_BASE_SHA, readable=True)
        return self._probe(spec, worktree, branch, *revision)


class _BehindTheBase:
    """The divergence probe, answering each head counted against the base branch as far behind as `behind` names it.

    A head it does not name is level with the base. Every other branch -- the
    pull request's -- reads as `branch`, the comparison a crash recovery
    classifies its checkout on. A recovered head a further base advance left
    behind, and the head the rebase behind its finish replays it into, are two
    readings of one probe, which is why the count is the head's own.
    """

    def __init__(self, branch: _publication_probes._BranchDivergence, behind: Mapping[str, int]) -> None:
        self._branch = branch
        self._behind = behind

    def __call__(self, spec, _worktree, branch, *revision):
        if branch != spec.base_branch:
            return self._branch
        counted = self._behind.get(revision[0] if revision else "", 0)
        return _publication_probes._BranchDivergence(tip=GATE_BASE_SHA, behind=counted, readable=True)


class _PullRequestBranches:
    """The remote as the authenticated branch read answers it: each branch on the head its pull request stands on.

    Read off the case's in-memory client at the moment of the read, so the
    client a case swaps in and the pushes it lands are what the next reading
    finds. A case with no client, or no pull request on the branch, finds the
    branch on the head every pull request here stands on before its rebase.
    The base branch is on the tip every divergence double here counts a head
    against, where the rebase left it.
    """

    def __init__(self, test_case) -> None:
        self._case = test_case

    def __call__(self, spec, _worktree, branch) -> _RefRead:
        if branch == spec.base_branch:
            return _RefRead(sha=GATE_BASE_SHA)
        pulls = getattr(getattr(self._case, "gh", None), "pulls", {})
        heads = [pull.head.sha for pull in pulls.values() if pull.head_branch == branch]
        return _RefRead(sha=heads[0] if heads else CONFLICT_PR_HEAD_SHA)


def _candidate_reads(test_case) -> None:
    """Answer the readings a rewrite candidate is prepared and published on, for the rest of the test."""
    _patched(test_case, _verification_probes, "_tree_sha", MagicMock(return_value=_TREE_SHA))
    _patched(
        test_case, _publication_probes, "_branch_divergence",
        _LevelWithTheBase(_publication_probes._branch_divergence),
    )
    _patched(test_case, branch_transport, "_remote_branch_read", _PullRequestBranches(test_case))


def _checkout_carries(test_case, *paths: str) -> None:
    """Have the checkout's status name `paths` as uncommitted, a reading that happened."""
    _patched(test_case, _worktree_status, "_worktree_status", MagicMock(
        return_value=_worktree_status._WorktreeStatus(readable=True, paths=paths),
    ))
