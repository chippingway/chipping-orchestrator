# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the checkout can vouch for the commit a report is about.

Asked first of the local groups because it costs no request and answers the
commonest refusals: a worktree on another host, a tree somebody left dirty, a
head a later run moved off the commit.

Clean is asked of the READING rather than of the path list, which is the one
place this differs from the probes the fix routes use. A `git status` that failed
names no paths, and so does a tree with nothing in it -- so a caller that
truth-tested the list would read a failed read as a clean tree. Here the
difference decides whether a report is published, so only a reading that
happened AND named nothing is clean, and the failure is its own answer.

The head is compared rather than adopted. A checkout standing anywhere but on
the commit the record names is one whose work is not what the report describes,
and publishing from there would put a report about one commit onto a pull
request carrying another.

DORMANT: `report_evidence.py` composes this reading and its own tests take it
directly, and no dispatcher or stage handler reaches either yet.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_records as _records,
)


def checkout_verdict(
    spec: _config_models.RepoSpec,
    issue: Issue,
    pending: _records.PendingReport,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a checkout that cannot vouch for the commit, or None when it can.

    A worktree that is not here defers rather than holding: the commit is on
    whichever host made it, and the stage behind this evidence has its own
    answer for an issue whose checkout is absent. A tree that would not report
    its state holds, since nobody could say anything about it at all.
    """
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if not worktree.exists():
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the checkout the transaction names is not on this host",
        )
    status = _worktree_status._worktree_status(worktree)
    if not status.readable:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the worktree would not report its state",
        )
    if status.paths:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the worktree is carrying loose work",
        )
    return _head_verdict(worktree, pending)


def _head_verdict(
    worktree: Path, pending: _records.PendingReport,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a head that is not the commit the report is about, or None."""
    head = _verification_probes._head_sha(worktree)
    if not head:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the worktree would not name its head",
        )
    if head != pending.subject.source_sha:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the checkout has moved off the commit the report is about",
        )
    return None
