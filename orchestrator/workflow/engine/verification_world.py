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
that this host has. Then both commits the binding names are read here and
their FULL trees compared: the commit the commands ran on and the head the
evidence is written for, which is also the head its review subject has to name
(`verification_subject`). Both have to be commits this repository can read --
each id a commit in its own right, never a tag peeling to one -- and both have
to be the one tree the run recorded. That comparison is the whole of what
licenses evidence about one commit to stand for another; a matching patch, an
unchanged topic diff, or a rewrite that calls itself a rebase says nothing
about the tree the base contributes.

A checkout that is not on this host defers, like a report's, and so does an
id git says names no object here, or names one that is not a commit: both are
structural, and the routes behind the reconciliation are what bring a checkout
back or supersede the evidence. A fetch or a comparison that did not happen
holds, since nobody could say which of those it even was. So does a commit
whose presence probe answered no without git saying why -- that probe answers
no on any failure, so what the id names is asked again
(`git/verification/objects.py`), and a lookup that answers neither a type nor
an absence is a read that failed -- and a tree read that answers nothing for a
commit this repository does hold, since every commit has a tree, and an empty
answer is that read failing rather than a tree that differs.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import objects as _verification_objects, probes as _verification_probes
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_remote_evidence as _remote,
    verification_records as _records,
)

# What git names an object that is a commit in its own right.
_COMMIT_TYPE = "commit"


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

    The id itself has to be a commit, asked without peeling: a tree id handed
    where a commit belongs would resolve to itself, and an annotated tag would
    peel to the commit it points at -- either would stand in for a commit
    nobody recorded. Then its tree. The caller has proved `worktree` exists.
    """
    if not commit or not _verification_probes._commit_present(worktree, commit, peeled=False):
        return ""
    return _verification_probes._tree_sha(worktree, commit)


def _trees_verdict(
    worktree: Path, binding: _records.EvidenceBinding,
) -> _evidence_models.ReportEvidence | None:
    """Refuse any named commit that is not here as a commit, or not the tested tree; hold an unread tree; or None.

    A commit this repository holds always has a tree, so a tree read that
    comes back empty for one is a reading that did not happen, not an answer:
    it holds rather than refusing what nobody compared.
    """
    named = (
        ("tested commit", binding.tested_sha),
        ("target head", binding.target.target_head),
    )
    for role, commit in named:
        refused = _tree_refusal(worktree, role, commit, binding.tested_tree)
        if refused is not None:
            return refused
    return None


def _tree_refusal(
    worktree: Path, role: str, commit: str, tested_tree: str,
) -> _evidence_models.ReportEvidence | None:
    """Why the commit in `role` does not vouch for `tested_tree` -- not here, an unread tree, another tree -- or None.

    Read as `tree_of` reads it, each request once: a commit, asked without
    peeling, and then its tree.
    """
    if not commit:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER, f"the evidence's {role} cannot be read",
        )
    if not _verification_probes._commit_present(worktree, commit, peeled=False):
        return _absent_refusal(worktree, role, commit)
    tree = _verification_probes._tree_sha(worktree, commit)
    if not tree:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD, f"the tree of the evidence's {role} could not be read",
        )
    if tree != tested_tree:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER, f"the evidence's {role} does not carry the tested tree",
        )
    return None


def _absent_refusal(worktree: Path, role: str, commit: str) -> _evidence_models.ReportEvidence:
    """Why the id in `role` is not a commit here: proved absent or another kind of object, or a read that failed.

    The presence probe answers no on any failure, so it is asked again what
    the id is (`objects._object_kind`): only git saying that no such object is
    here, or naming another type, refuses; a type nobody could read -- or a
    commit after all, which is the first read failing -- holds.
    """
    kind = _verification_objects._object_kind(worktree, commit)
    if kind is None or kind == _COMMIT_TYPE:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD, f"the evidence's {role} could not be looked up",
        )
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER, f"the evidence's {role} cannot be read",
    )
