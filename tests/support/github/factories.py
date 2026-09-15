# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Constructors for the in-memory GitHub doubles."""
from __future__ import annotations

from orchestrator.github.developer_reports import DeveloperReport
from tests.support.github.models import FakeIssue, FakeLabel, FakeUser
from tests.support.github.state import _IssueSeed

# The identity and text a developer report is published under when a case
# names nothing else.
_REPORTED_SHA = "3f786850e387550fdab836ed7e6dc881de23001b"
_REQUIREMENTS_REVISION = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
_REPORT_RECEIPT = "issue-7-report-1"
_REPORT_TEXT = "Implemented the requested change.\n\nChecks: `uv run pytest tests` passed."


def make_developer_report(pr_number: int, **report_fields) -> DeveloperReport:
    """Build one complete developer report for `pr_number`, overriding any field."""
    defaults = {
        "source_sha": _REPORTED_SHA,
        "requirements_revision": _REQUIREMENTS_REVISION,
        "report_revision": 1,
        "receipt": _REPORT_RECEIPT,
        "text": _REPORT_TEXT,
    }
    return DeveloperReport(pr_number=pr_number, **(defaults | report_fields))


def make_issue(number: int, **issue_fields) -> FakeIssue:
    """Build an issue while preserving the historical keyword surface."""
    seed = _IssueSeed(**issue_fields)
    labels = [FakeLabel(seed.label)] if seed.label else []
    return FakeIssue(
        number=number,
        title=seed.title,
        body=seed.body,
        labels=labels,
        comments=list(seed.comments),
        closed=seed.closed,
        user=FakeUser(seed.author),
    )
