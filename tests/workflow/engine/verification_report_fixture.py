# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The settled developer report, and the review of it, that evidence answers for.

Settled the way a report transaction settles one: the report is published onto
the pull request under its receipt, the comment it landed as is recorded as
the current report's location beside the handoff naming that receipt, and a
reviewer round records the subject it was handed -- once as it launched and
once as it returned. So the evidence proof re-reads a real comment where the
settlement says it is, and holds the bound subject to records a reviewer
actually wrote.
"""
from __future__ import annotations

from orchestrator.github import developer_reports as _reports, pull_request_reports as _pr_reports
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    report_records as _report_records,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
)
from tests.workflow.engine import verification_world_fixture as _world

REPORT_TEXT = "Implemented the change.\n\nChecks: `uv run pytest tests` passed."

LATER_REPORT_TEXT = "Implemented the change and covered the empty configuration."

_RECEIPT = "issue-{issue}-report-{revision}"

BASELINE = "user_content_hash"


def settles_report(
    case, revision: int, text: str = REPORT_TEXT, *, reviewed: bool = True,
) -> _review_subjects.ReviewSubject:
    """Publish and settle one report revision for `case`, and record a review of it.

    Returns the subject a reviewer is handed for it, which is what fresh
    evidence on the tested commit answers for. `reviewed` False leaves the
    review records where they stood: a report that settled after the review.
    """
    report = _published(case, revision, text)
    # The drift baseline the report was written against, which the validating
    # reader holds a settled report to.
    case.state.set(BASELINE, report.requirements_revision)
    location = _pr_reports.ReportLocation(
        pr_number=case.pull_request.number,
        comment_id=_comments._publish_developer_report(
            case.gh, case.pull_request, case.state, report,
        ).landed_id,
    )
    _settles(case.state, case.gh.repo_slug, report, location)
    subject = _review_subjects.ReviewSubject(
        pr_number=report.pr_number,
        commit=report.source_sha,
        requirements_revision=report.requirements_revision,
        report=_review_subjects.ReviewReport(
            text=text,
            report_revision=revision,
            content_revision=_reports.content_digest(text),
            source_sha=report.source_sha,
            requirements_revision=report.requirements_revision,
            location=location,
        ),
    )
    if reviewed:
        _review_subjects.record_reviewed(case.state, subject)
        case.state.set(_review_subjects.RETURNED_SUBJECT, subject.recorded())
    return subject


def _published(case, revision: int, text: str) -> _reports.DeveloperReport:
    """The report revision `case` publishes on the tested commit."""
    return _reports.DeveloperReport(
        pr_number=case.pull_request.number,
        source_sha=_world.TESTED_SHA,
        requirements_revision=_content_hash._compute_user_content_hash(case.issue, set()),
        report_revision=revision,
        receipt=_RECEIPT.format(issue=case.issue.number, revision=revision),
        text=text,
    )


def _settles(
    state,
    repo_slug: str,
    report: _reports.DeveloperReport,
    location: _pr_reports.ReportLocation,
) -> None:
    """Record the current report and its handoff, as a settlement writes them."""
    _report_settlement.record_current_report(state, _report_records.CurrentReport(
        subject=_report_records.ReportSubject(
            repo_slug=repo_slug,
            pr_number=report.pr_number,
            branch=_world.BRANCH,
            source_sha=report.source_sha,
            requirements_revision=report.requirements_revision,
        ),
        report_revision=report.report_revision,
        content_revision=_reports.content_digest(report.text),
        location=location,
        mode=_report_records.ReportMode.PUBLISH,
    ))
    _report_settlement.record_handoff(state, _report_records.ReportHandoff(
        receipt=report.receipt,
        pr_number=report.pr_number,
        report_revision=report.report_revision,
        source_sha=report.source_sha,
    ))
