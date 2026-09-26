# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the remote branch still stands where the report says it does.

The checkout beside this proves what is on THIS host, and that is half a
publication. A local head equal to the recorded commit says nothing about the
ref the pull request is built from: the branch can be ahead of it -- work an
earlier run committed and never pushed -- behind it, where somebody else has
landed since, or standing on some third commit entirely. A report settled over
any of those describes a state the remote does not have.

So the ref is fetched and the counts are taken against the tip that fetch
resolved, exactly as the stranded-fix probe takes them, and all three questions
are asked of one reading: ahead is unpublished work, behind is a remote that
moved, and a tip that is not the recorded commit is a head that moved off it.
The branch asked about is the one the record FROZE rather than one resolved
again here, because the whole point of freezing it was that a later tick's
answer can differ.

Ahead and behind are structural and stand down: the publication gate pushes an
unpublished commit, and the base-sync and conflict routes answer a remote that
has moved. A fetch or a comparison that did not happen holds instead, since
nobody could say which of those it even was.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_records as _records,
)


def remote_verdict(
    spec: _config_models.RepoSpec,
    issue: Issue,
    pending: _records.PendingReport,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a remote that is not standing on the recorded commit, or None.

    The fetch is what makes the reading about NOW rather than about whatever
    this checkout last heard: the counts below are taken against the tip it
    resolves, so a ref nobody could refresh is a reading that did not happen.
    """
    return subject_remote_verdict(spec, issue, pending.subject)


def subject_remote_verdict(
    spec: _config_models.RepoSpec,
    issue: Issue,
    subject: _records.ReportSubject,
) -> _evidence_models.ReportEvidence | None:
    """The reading above, for any record bound to a report subject.

    Public for the verification-evidence transaction, whose target is a report
    subject about the head the evidence is written for, so both records hold
    the branch and the checkout to the same answer.
    """
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    branch = subject.branch
    fetched = _branch_transport._authed_fetch(
        spec,
        f"+refs/heads/{branch}:refs/remotes/{spec.remote_name}/{branch}",
        cwd=worktree,
    )
    if fetched.returncode != 0:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the recorded branch could not be fetched",
        )
    return _divergence_verdict(
        _publication_probes._branch_divergence(spec, worktree, branch),
        subject.source_sha,
    )


def _divergence_verdict(
    divergence: _publication_probes._BranchDivergence, source_sha: str,
) -> _evidence_models.ReportEvidence | None:
    """Read one divergence against the commit the report is about.

    `readable` is asked first and is not the same question as zero-and-zero: a
    ref nothing could resolve and a comparison git refused both count as
    nothing, and read as "in sync" they would settle a report over a reading
    nobody took.
    """
    if not divergence.readable:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the branch would not say how it stands against the remote",
        )
    if divergence.ahead:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the branch carries commits the remote has not received",
        )
    if divergence.behind:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the remote branch has moved on since the record was written",
        )
    if divergence.tip != source_sha:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the remote branch is not standing on the recorded commit",
        )
    return None
