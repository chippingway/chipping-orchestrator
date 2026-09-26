# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether current evidence may be carried to another head, decided on two proofs alone.

A rewrite -- a squash, a one-commit subject rewrite, a documentation pass that
changed nothing -- leaves a new head behind evidence recorded for the old one.
That evidence may answer for the new head only when two things are PROVED:
the new head's full tree is the very tree the commands ran on, read from this
repository, and the verification context configured now is the one they ran
under. Nothing else is consulted and nothing else can substitute for either. A
matching patch id, an unchanged contribution fingerprint or topic diff, or a
rewrite that calls itself a rebase says nothing about what the base
contributes, and a rebase onto another base changes the tree whatever its
patches say.

The decision licenses exactly one thing: recording a new transaction whose
binding is the current one with only the target head moved
(`CarryForward.binding`). The tested commit and tree stay the ones that were
actually tested, so the artifact that transaction publishes names the earlier
commit as the one that ran and the new head as the equivalent-tree target.
Everything else -- the pull request standing on that head, the requirements,
the report and review subject -- is proved by the reconciliation before that
transaction is published or becomes current, exactly as for fresh evidence.

Anything short of both proofs is no decision, and says why in the log: no
current evidence, a context that moved, a head that is not a whole commit id,
a checkout not on this host, or a tree that would not read or differs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_world as _world,
)
from orchestrator.workflow.late_split import formats as _formats

log = logging.getLogger("orchestrator.workflow")


@dataclass(frozen=True)
class CarryForward:
    """Current evidence proved to answer for `target_head` as well.

    `target_tree` is the tree read for that head, equal to the tested tree.
    """

    source: _records.CurrentEvidence
    target_head: str
    target_tree: str

    @property
    def binding(self) -> _records.EvidenceBinding:
        """The current binding answering for the new head, its tested run unchanged."""
        return self.source.binding.retargeted(self.target_head)


def carry_forward_decision(
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    target_head: str,
) -> CarryForward | None:
    """The carry-forward the current evidence earns onto `target_head`, or None.

    The source's own tree is read again too, so a record whose tested commit
    no longer reads as the tree it claims carries nothing anywhere.
    """
    current = _settlement.read_current_evidence(state)
    refusal = _refusal(current, target_head) or _tree_refusal(
        spec, issue, current, target_head,
    )
    if refusal:
        log.info(
            "issue=#%d carries no verification evidence to %s: %s",
            issue.number, target_head, refusal,
        )
        return None
    return CarryForward(
        source=current,
        target_head=target_head,
        target_tree=current.binding.tested_tree,
    )


def _refusal(current: _records.CurrentEvidence | None, target_head: str) -> str:
    """What stops a decision before any object is read, or "" for nothing."""
    if current is None:
        return "there is no current evidence to carry"
    if not _formats.is_hex_of(target_head, _formats.COMMIT_LENGTHS):
        return "the target head is not a whole commit id"
    if current.binding.context_revision != _proof.configured_context_revision():
        return "the verification context moved since the evidence was recorded"
    return ""


def _tree_refusal(
    spec: _config_models.RepoSpec,
    issue: Issue,
    current: _records.CurrentEvidence,
    target_head: str,
) -> str:
    """What the checkout says against carrying `current` onto `target_head`, or ""."""
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if not worktree.exists():
        return "the checkout is not on this host"
    tested = current.binding.tested_tree
    trees = (
        _world.tree_of(worktree, current.binding.tested_sha),
        _world.tree_of(worktree, target_head),
    )
    if trees != (tested, tested):
        return "the target head's tree is not proved to be the tested tree"
    return ""
