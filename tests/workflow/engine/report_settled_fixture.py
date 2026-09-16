# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The settled pair a case writes to disagree with the record in hand.

A settlement is two records written together off one pending record, so every
case about a pair this build did not write has to compose one by hand. Spelled
once, here, so that a case breaking one member is visibly about that member --
and so the two modules that write these pairs cannot drift into two spellings
of what a settlement looks like.
"""
from __future__ import annotations

from orchestrator.github.developer_reports import content_digest
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_records as _records,
    report_settlement_state as _settlement,
)
from tests.workflow.engine import report_transaction_test_support as support

# The comment a settled report is recorded at.
COMMENT_ID = 8080

# A second comment on the same pull request, which a verification's record may
# not be answered by: a location is exact in both halves.
ELSEWHERE_COMMENT_ID = 8081

# The receipt a PREVIOUS transaction on this issue settled under, which is what
# makes a pair written with it one nothing compares against the record in hand.
EARLIER_RECEIPT = "issue-7-report-0"

SETTLED_REVISION = 1

NEXT_REVISION = 2

# Text no transaction in these cases carries, so its digest belongs to no
# settlement any of them could have made.
ANOTHER_REPORT = "Some other report, published by some other transaction."


def another_digest() -> str:
    """The digest of a report no case here records, for a record nothing wrote."""
    return content_digest(ANOTHER_REPORT)


def records_current(
    state,
    subject: _records.ReportSubject,
    revision: int,
    *,
    digest: str = "",
    location: ReportLocation | None = None,
) -> None:
    """Record what the pull request is said to carry now."""
    _settlement.record_current_report(state, _records.CurrentReport(
        subject=subject,
        report_revision=revision,
        content_revision=digest or content_digest(support.REPORT_TEXT),
        location=location or ReportLocation(
            pr_number=subject.pr_number, comment_id=COMMENT_ID,
        ),
    ))


def records_handoff(
    state, receipt: str, revision: int, source_sha: str,
) -> None:
    """Record the receipt one transaction is said to have finished under."""
    _settlement.record_handoff(state, _records.ReportHandoff(
        receipt=receipt,
        pr_number=support.PR_NUMBER,
        report_revision=revision,
        source_sha=source_sha,
    ))
