# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the pinned report records and the issue say about the subject evidence answers for.

Evidence is written for a review subject, and a review subject names the
developer report the pull request carried when it was resolved. So evidence
can only be current while that report still is: no report transaction owed,
and the settled report the same revision and the same words the subject names
-- compared by `review_subjects.current_report_identity`, the identity every
approval reader already compares, rather than by a second reading of it. And
it can only be current while the issue still carries the requirements the
evidence was bound to, read by the same fingerprint the drift owner and every
report transaction read.

Both refusals DEFER: what clears them is a route behind the reconciliation --
the report transaction settling, a fresh reviewer round, a drift resume, or
fresher evidence superseding this. Only a requirements reading nobody could
take holds.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    report_evidence_models as _evidence_models,
    report_record_state as _report_record_state,
    review_subjects as _review_subjects,
    verification_records as _records,
)

log = logging.getLogger("orchestrator.workflow")


def subject_verdict(
    state: PinnedState, target: _records.EvidenceTarget,
) -> _evidence_models.ReportEvidence | None:
    """Refuse a review subject that is not about the report standing now, or None.

    A developer report transaction still owed is a subject about to move, so
    it defers to that transaction, which the dispatcher reconciles first. A
    settled report nobody can read matches no subject, and neither does a
    subject naming another revision, other words, or a report where the
    settled records carry none.
    """
    refusal = ""
    if _report_record_state.carries_pending_report(state):
        refusal = "a developer report the review subject would describe is still owed"
    elif target.subject_identity != _review_subjects.current_report_identity(state):
        refusal = "the review subject is not about the report the pull request carries"
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
