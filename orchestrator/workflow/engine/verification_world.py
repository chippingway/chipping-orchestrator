# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the branch and the objects a piece of evidence names are the ones on this host.

The pull request is proved by the report domain's own reading, since the
evidence target is a report subject: open, in this repository, on the recorded
branch, and STANDING on the head the evidence is written for. What this owner
adds is the half no pull request can answer.

The branch is fetched and held to the same answer a report transaction's is
(`report_remote_evidence`): the remote tip is the target head and the checkout
is standing on it too, so the evidence is about work that is published and
that this host has. Then every commit the binding names is read here and its
FULL tree compared: the commit the commands ran on, the head the evidence is
written for, and the head the review subject names. All three have to be
commits this repository can read, and all three have to be the one tree the
run recorded. That comparison is the whole of what licenses evidence about one
commit to stand for another; a matching patch, an unchanged topic diff, or a
rewrite that calls itself a rebase says nothing about the tree the base
contributes.

A checkout that is not on this host defers, like a report's, and so does a
commit or tree that will not read: both are structural, and the routes behind
the reconciliation are what bring a checkout back or supersede the evidence. A
fetch or a comparison that did not happen holds, since nobody could say which
of those it even was.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_remote_evidence as _remote,
    verification_records as _records,
)


def world_verdict(
    spec: _config_models.RepoSpec,
    issue: Issue,
    binding: _records.EvidenceBinding,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a branch or object that cannot vouch for `binding`, or None."""
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if not worktree.exists():
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the checkout the evidence names is not on this host",
        )
    adrift = _remote.subject_remote_verdict(spec, issue, binding.target.publication)
    if adrift is not None:
        return adrift
    return _trees_verdict(worktree, binding)


def tree_of(worktree: Path, commit: str | None) -> str:
    """The full tree of `commit` as this repository reads it, or "" for none.

    A commit first, since a tree id handed where a commit belongs would
    resolve to itself; then its tree. The caller has proved `worktree` exists.
    """
    if not commit or not _verification_probes._commit_present(worktree, commit):
        return ""
    return _verification_probes._tree_sha(worktree, commit)


def _trees_verdict(
    worktree: Path, binding: _records.EvidenceBinding,
) -> _evidence_models.ReportEvidence | None:
    """Refuse any named commit that is unreadable or not the tested tree, or None."""
    named = (
        ("tested commit", binding.tested_sha),
        ("target head", binding.target.target_head),
        ("review subject's head", binding.target.subject_commit),
    )
    for role, commit in named:
        tree = tree_of(worktree, commit)
        if tree != binding.tested_tree:
            refusal = "does not carry the tested tree" if tree else "cannot be read"
            return _evidence_models.ReportEvidence(
                _evidence_models.ReportEvidenceVerdict.DEFER,
                f"the evidence's {role} {refusal}",
            )
    return None
