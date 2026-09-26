# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the review records, the settled report, and the issue say about the subject evidence answers for.

Evidence is written for a review subject in `review_subjects`' own shape, and
it is current only while that subject is still the authoritative one, which is
asked three ways.

The pull request comes first: the evidence has to name the one this issue
records as its own (`pr_number`), since evidence about any other thread is
evidence about somewhere else, however open and well-proved that thread is.

The RECORDED subject next. Which record is applicable follows the witness: a
reviewer's own account answers for the subject the reviewer that RETURNED was
handed (`review_returned_subject`), and a run this orchestrator executed
answers for the subject the latest reviewer was handed (`review_subject`),
which is the one an approval is later recorded over. The bound subject has to
equal that record whole -- pull request, head, requirements, report revision
and digest -- so evidence bound to a subject no reviewer was handed, or handed
since, is not current. An issue that records no such subject, or one nobody
can read, has no subject any evidence answers for. A developer report still
owed is a subject about to move, so it defers first.

The SETTLED REPORT second, read exactly as a reviewer is handed it
(`stages/validating/review_report.py`, resolved when called): the current
report and the handoff that settled it held to each other, and the report
re-read at its recorded location, published or verified, under an author this
deployment trusts, and still hashing to its digest. The bound subject has to
name that report's revision and digest, and the report may not be stale against
it by that reader's own rule: about the subject's very head, and written
against the requirements baseline the issue is held to. A report gone, edited, or out of step
with its handoff is a subject nobody can hand a reviewer, and one nobody could
re-read holds.

The REQUIREMENTS last: the issue still has to carry the revision the evidence
was bound to, read by the fingerprint the drift owner and every report
transaction read.

Every refusal but an unreadable reading DEFERS: what clears it is a route
behind the reconciliation -- the report transaction settling, a fresh reviewer
round, a drift resume, or fresher evidence superseding this.
"""
from __future__ import annotations

import importlib
import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    report_evidence_models as _evidence_models,
    report_record_state as _report_record_state,
    review_subjects as _review_subjects,
    stage_targets as _stage_targets,
    verification_records as _records,
)
from orchestrator.workflow.late_split import payloads as _payloads

log = logging.getLogger("orchestrator.workflow")

# The pull request this issue records as its own, the canonical identity every
# piece of evidence has to name.
_PR_NUMBER = "pr_number"

# The recorded review subject each witness's evidence answers for.
_APPLICABLE_SUBJECT = MappingProxyType({
    EvidenceSource.ORCHESTRATOR_EXECUTED: _review_subjects.REVIEW_SUBJECT,
    EvidenceSource.REVIEWER_REPORTED: _review_subjects.RETURNED_SUBJECT,
})


def subject_verdict(
    state: PinnedState, binding: _records.EvidenceBinding,
) -> _evidence_models.ReportEvidence | None:
    """Refuse evidence whose subject is not the applicable recorded one, or None."""
    applicable = _APPLICABLE_SUBJECT[binding.source]
    recorded = state.get(applicable)
    refusal = ""
    if _payloads.as_identity(state.get(_PR_NUMBER)) != binding.target.publication.pr_number:
        refusal = "the evidence names another pull request than the one this issue records"
    elif _report_record_state.carries_pending_report(state):
        refusal = "a developer report the review subject would describe is still owed"
    elif _review_subjects.ReviewSubject.identity_recorded_in(recorded) is None:
        refusal = f"no readable {applicable} is recorded for the evidence to answer for"
    elif recorded != binding.target.subject:
        refusal = f"the evidence answers for another subject than the recorded {applicable}"
    if not refusal:
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER, refusal,
    )


def report_verdict(
    gh: GitHubClient, state: PinnedState, target: _records.EvidenceTarget,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a subject that is not about the settled report as re-read now, or None.

    The report has to be the revision and words the subject names, and not
    stale against that subject by the validating reader's own rule
    (`review_report._stale_refusal`): about the very commit the subject's head
    is, and written against the requirements baseline the drift check holds
    the issue to. A report about another commit on the same tree is one no
    reviewer would be handed with this subject.
    """
    review_report = importlib.import_module(_stage_targets._VALIDATING_REVIEW_REPORT_OWNER)
    report, refusal = review_report._settled_report(gh, state, target.publication.pr_number)
    if report is None and not refusal:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the settled developer report could not be re-read",
        )
    if report is not None and target.subject_identity != (
        target.publication.pr_number, report.report_revision, report.content_revision,
    ):
        refusal = "the review subject is not about the report the pull request carries"
    elif report is not None:
        refusal = review_report._stale_refusal(state, _review_subjects.ReviewSubject(
            pr_number=target.publication.pr_number,
            commit=target.subject_commit,
            requirements_revision=target.subject_requirements,
            report=report,
        ))
    if not refusal:
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER, refusal,
    )


def requirements_verdict(
    issue: Issue, state: PinnedState, revision: str,
) -> _evidence_models.ReportEvidence | None:
    """Refuse evidence bound to requirements the issue has moved past, or None.

    Deferred rather than held, because the route that answers an edit is the
    drift resume behind the reconciliation. The READING holds where it fails:
    an edit nobody could look for is not an issue whose requirements are
    unchanged.
    """
    try:
        current = _content_hash._compute_user_content_hash(
            issue, _comments._orchestrator_ids(state),
        )
    except Exception:
        log.exception(
            "issue=#%d could not be read to say whether its requirements "
            "moved under its verification evidence", issue.number,
        )
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the issue's own requirements could not be read",
        )
    if current == revision:
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        "the issue requirements moved since the evidence was bound",
    )
