# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two report transactions every record case is written against.

One publication carrying a report, one verification carrying a location, and the
two helpers that put either onto a pinned comment and then damage exactly one
member of it. Spelled once so a case that breaks a member is visibly about that
member rather than about the fixture around it.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
)
from orchestrator.workflow.state import WorkflowLabel

RECEIPT = "issue-7-report-1"

SOURCE_SHA = "3f786850e387550fdab836ed7e6dc881de23001b"

REQUIREMENTS = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

CONTENT_DIGEST = "5f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

BRANCH = "orchestrator/chippingway__orchestrator/issue-7"

SLUG = "chippingway/orchestrator"

PR_NUMBER = 12

COMMENT_ID = 8080

# The bookkeeping fields the cases read and write, spelled once because WPS
# counts a literal repeated across a module as the drift risk it is.
PR_WATERMARK = "pr_last_comment_id"

BASELINE = "user_content_hash"

REVIEW_ROUND = "review_round"

PENDING_FIX_AT = "pending_fix_at"

SUBJECT = _records.ReportSubject(
    repo_slug=SLUG,
    pr_number=PR_NUMBER,
    branch=BRANCH,
    source_sha=SOURCE_SHA,
    requirements_revision=REQUIREMENTS,
)

PUBLISHED = _records.PendingReport(
    receipt=RECEIPT,
    subject=SUBJECT,
    report_revision=2,
    mode=_records.ReportMode.PUBLISH,
    route=WorkflowLabel.FIXING,
    report="The branch adds the gate.\n\nVerified with the suite.",
    watermarks=((PR_WATERMARK, 41), (BASELINE, REQUIREMENTS)),
    spends=((REVIEW_ROUND, 3), (PENDING_FIX_AT, None)),
)

VERIFIED = _records.PendingReport(
    receipt=RECEIPT,
    subject=SUBJECT,
    report_revision=2,
    mode=_records.ReportMode.VERIFY,
    route=WorkflowLabel.IN_REVIEW,
    location=ReportLocation(pr_number=PR_NUMBER, comment_id=COMMENT_ID),
    content_revision=CONTENT_DIGEST,
)


def recorded(pending: _records.PendingReport) -> dict:
    """The pinned object one transaction is written as."""
    state = PinnedState()
    _record_state.record_pending_report(state, pending)
    return state.get(_records.PENDING_REPORT)


def damaged(pending: _records.PendingReport, **fields) -> PinnedState:
    """One recorded transaction with members replaced by what nothing wrote."""
    return PinnedState(state_data={
        _records.PENDING_REPORT: recorded(pending) | fields,
    })


def reads_back(state: PinnedState) -> _records.PendingReport | None:
    """What the pending record on this state reads back as."""
    return _record_state.read_pending_report(state)
