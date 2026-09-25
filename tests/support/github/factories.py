# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Constructors for the in-memory GitHub doubles."""
from __future__ import annotations

from orchestrator.github.developer_reports import DeveloperReport
from orchestrator.github.verification_artifacts import VerificationArtifact
from orchestrator.github.verification_evidence import EvidenceSource, VerifiedCommand
from tests.support.github.models import FakeIssue, FakeLabel, FakeUser
from tests.support.github.state import _IssueSeed

# The identity and text a developer report is published under when a case
# names nothing else.
_REPORTED_SHA = "3f786850e387550fdab836ed7e6dc881de23001b"
_REQUIREMENTS_REVISION = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
_REPORT_RECEIPT = "issue-7-report-1"
_REPORT_TEXT = "Implemented the requested change.\n\nChecks: `uv run pytest tests` passed."

# The identity and evidence a verification artifact is published under when a
# case names nothing else. The tree, the head the pull request carries, and the
# subject the round answers are three object ids apart from the tested commit,
# because an artifact that named one of them for all four could not say that
# evidence has gone stale.
_TESTED_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_TARGET_HEAD = "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"
_REVIEW_SUBJECT = "1f40fc92da241694750979ee6cf582f2d5d7d28e"
_CONTEXT_REVISION = "verify.v1-9f86d081"
_ARTIFACT_RECEIPT = "issue-7-verification-1"
_VERIFIED_COMMANDS = (
    VerifiedCommand(command="uv run pytest tests", exit_status=0),
    VerifiedCommand(
        command="uv run ruff check orchestrator tests",
        exit_status=0,
        output="All checks passed!",
    ),
)


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


def make_verification_artifact(pr_number: int, **artifact_fields) -> VerificationArtifact:
    """Build one complete verification artifact for `pr_number`, overriding any field."""
    defaults = {
        "repository": "chippingway/orchestrator",
        "source": EvidenceSource.ORCHESTRATOR_EXECUTED,
        "tested_sha": _REPORTED_SHA,
        "tested_tree": _TESTED_TREE,
        "target_head": _TARGET_HEAD,
        "review_subject": _REVIEW_SUBJECT,
        "requirements_revision": _REQUIREMENTS_REVISION,
        "context_revision": _CONTEXT_REVISION,
        "artifact_revision": 1,
        "receipt": _ARTIFACT_RECEIPT,
        "commands": _VERIFIED_COMMANDS,
    }
    return VerificationArtifact(pr_number=pr_number, **(defaults | artifact_fields))


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
