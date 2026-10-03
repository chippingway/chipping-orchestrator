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
since, is not current. And that subject has to be about the very head the
evidence answers for: a reviewer handed the pull request at that head is what
the validating reader builds a subject from, so evidence carried to a new head
still answering for a review of the old one answers for a subject nobody can
hand a reviewer any more. The one exception is the review an approval was
given over, carried across the rewrite that approval's own handoff publishes
(`verification_carry_forward`): no reviewer is handed that head at all, every
road acting on the approval holds it to the approved subject, and a subject
about the commit that was tested is current there while it is the one the
approval record (`review_approved_subject`) covers -- the world proof holds
the tested commit and the head alike to the tested tree. An issue that
records no such subject, or one nobody
can read, has no subject any evidence answers for. A developer report still
owed -- by the rule the validating hold asks (`report_delivery.owes_a_report`):
a delivery, a transaction, or an undeliverable park -- is a subject about to
move, so it defers first.

The SETTLED REPORT second, read exactly as a reviewer is handed it
(`stages/validating/review_report.py`, resolved when called): the current
report and the handoff that settled it held to each other, and the report
re-read at its recorded location, published or verified, under an author this
deployment trusts, and still hashing to its digest. The bound subject has to
name that report's revision and digest, and pass every rule that reader holds
a subject read whole to before it hands one over: requirements that are the
revision the round was due -- the drift baseline, or the thread through the
reply that bought the round -- and a report not stale against the subject,
about its very head and written against that baseline -- or older than a
baseline that is the subject's own requirements, which is the settlement of the
reply that bought the reviewer's round rather than an edit anybody owes. A
report gone, edited, or out of step with its handoff is a subject nobody can
hand a reviewer, and one nobody could re-read holds.

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
    report_delivery as _report_delivery,
    report_evidence_models as _evidence_models,
    review_subjects as _review_subjects,
    stage_targets as _stage_targets,
    verification_records as _records,
)
from orchestrator.workflow.late_split import payloads as _payloads

log = logging.getLogger("orchestrator.workflow")

# The pull request this issue records as its own, the canonical identity every
# piece of evidence has to name.
_PR_NUMBER = "pr_number"

# The requirements baseline the drift check holds the issue to.
_BASELINE = "user_content_hash"

# The recorded review subject each witness's evidence answers for.
_APPLICABLE_SUBJECT = MappingProxyType({
    EvidenceSource.ORCHESTRATOR_EXECUTED: _review_subjects.REVIEW_SUBJECT,
    EvidenceSource.REVIEWER_REPORTED: _review_subjects.RETURNED_SUBJECT,
})


def applicable_subject(
    state: PinnedState, source: EvidenceSource,
) -> tuple[str, object]:
    """The record naming the subject evidence from `source` answers for, and what it holds."""
    applicable = _APPLICABLE_SUBJECT[source]
    return applicable, state.get(applicable)


def subject_verdict(
    state: PinnedState, binding: _records.EvidenceBinding,
) -> _evidence_models.ReportEvidence | None:
    """Refuse evidence whose subject is not the applicable recorded one about its head, or None."""
    refusal = _issue_refusal(state, binding) or _recorded_refusal(state, binding)
    if not refusal:
        return None
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER, refusal,
    )


def _issue_refusal(state: PinnedState, binding: _records.EvidenceBinding) -> str:
    """Why this issue's own records leave the evidence nothing to answer for yet, or ""."""
    if _payloads.as_identity(state.get(_PR_NUMBER)) != binding.target.publication.pr_number:
        return "the evidence names another pull request than the one this issue records"
    if _report_delivery.owes_a_report(state):
        return "a developer report the review subject would describe is still owed"
    return ""


def _recorded_refusal(state: PinnedState, binding: _records.EvidenceBinding) -> str:
    """Why the bound subject is not the applicable recorded one about its head, or "".

    About the head the evidence answers for -- or, for evidence carried across
    the rewrite of an approved head, about the commit that was tested, where
    the subject is the one the approval record covers: the world proof holds
    both commits to the tested tree.
    """
    applicable, recorded = applicable_subject(state, binding.source)
    if _review_subjects.ReviewSubject.identity_recorded_in(recorded) is None:
        return f"no readable {applicable} is recorded for the evidence to answer for"
    reviewed = binding.target.subject_commit
    approved = reviewed == binding.tested_sha and binding.target.subject == state.get(
        _review_subjects.APPROVED_SUBJECT,
    )
    if reviewed != binding.target.target_head and not approved:
        return "the review subject is not about the head the evidence answers for"
    if recorded != binding.target.subject:
        return f"the evidence answers for another subject than the recorded {applicable}"
    return ""


def report_verdict(
    gh: GitHubClient, state: PinnedState, target: _records.EvidenceTarget,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a subject that is not about the settled report as re-read now, or None.

    The report has to be the revision and words the subject names, and the
    subject has to pass the validating reader's own rules, in its order: the
    requirements the round was due (`review_report._outran_the_drift_check`),
    then staleness (`review_report._stale_refusal`) -- about the very commit
    the subject's head is, and written against the requirements baseline the
    drift check holds the issue to, or older than a baseline that is the
    subject's own requirements, which only the settlement of the reply that
    bought the round leaves (`_handing_refusal`). A report about another
    commit on the same tree is one no reviewer would be handed with this
    subject.
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
        refusal = _handing_refusal(state, _review_subjects.ReviewSubject(
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


def _handing_refusal(state: PinnedState, subject: _review_subjects.ReviewSubject) -> str:
    """Why the validating reader would not hand `subject` to a reviewer now, or "".

    Asked after the round that was handed `subject` has returned, and a round
    a reply bought settles that reply as it returns, moving the drift baseline
    onto the requirements its reviewer read -- past the report, which the
    reader handed over as written against the baseline before that. A report
    older than a baseline that is the subject's own requirements is that
    round's own settlement rather than an edit the developer owes an answer:
    the reader cannot hand over requirements past the report any other way.
    """
    review_report = importlib.import_module(_stage_targets._VALIDATING_REVIEW_REPORT_OWNER)
    if review_report._outran_the_drift_check(state, subject):
        return "the review subject's requirements are not the revision its reviewer was due"
    refusal = review_report._stale_refusal(state, subject)
    settled_onto = subject.requirements_revision == state.get(_BASELINE)
    if refusal == review_report._MOVED_REQUIREMENTS and settled_onto:
        return ""
    return refusal


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
