# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence binding every record case here is written against.

One pull request on one branch, one reviewed developer report, and one run of
the configured suite on the commit and tree the pull request stands on --
spelled once so a case that moves a member is visibly about that member. The
records are written through their own owners and read back through the pinned
comment's own rendering and parser, as the next tick would read them, with no
GitHub world, proof, or transaction behind them.
"""
from __future__ import annotations

from orchestrator.git.verification import models as _verify_models
from orchestrator.github import (
    developer_reports as _reports,
    pinned_state as _pinned_state,
    verification_evidence as _evidence,
)
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_records as _report_records,
    review_subjects as _review_subjects,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeComment

ISSUE_NUMBER = 7

PR_NUMBER = 12

SLUG = "chippingway/orchestrator"

BRANCH = "orchestrator/chippingway__orchestrator/issue-7"

TESTED_SHA = "3f786850e387550fdab836ed7e6dc881de23001b"

TESTED_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

REBASED_SHA = "89e6c98d92887913cadf06b2adb97f26cde4849b"

REQUIREMENTS = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

SUITE = "uv run pytest tests"

TIMEOUT = 600

# The context the verify runner mints for the suite alone under that timeout.
CONTEXT = _verify_models._context_revision((SUITE,), TIMEOUT)

REPORT_TEXT = "Implemented the change.\n\nChecks: `uv run pytest tests` passed."

# The comment the reviewed report was published as.
REPORT_COMMENT = 8080

# The comment a settled artifact landed as, and the label it settled under.
ARTIFACT_COMMENT = 9090

SETTLED_UNDER = WorkflowLabel.VALIDATING

SUBJECT = _review_subjects.ReviewSubject(
    pr_number=PR_NUMBER,
    commit=TESTED_SHA,
    requirements_revision=REQUIREMENTS,
    report=_review_subjects.ReviewReport(
        text=REPORT_TEXT,
        report_revision=1,
        content_revision=_reports.content_digest(REPORT_TEXT),
        source_sha=TESTED_SHA,
        requirements_revision=REQUIREMENTS,
        location=ReportLocation(pr_number=PR_NUMBER, comment_id=REPORT_COMMENT),
    ),
)

TARGET = _records.EvidenceTarget(
    publication=_report_records.ReportSubject(
        repo_slug=SLUG,
        pr_number=PR_NUMBER,
        branch=BRANCH,
        source_sha=TESTED_SHA,
        requirements_revision=REQUIREMENTS,
    ),
    subject=SUBJECT.recorded(),
)


def binding(**overrides) -> _records.EvidenceBinding:
    """A fresh run's binding: tested on the head it answers for, any member replaced."""
    bound = {
        "target": TARGET,
        "source": _evidence.EvidenceSource.ORCHESTRATOR_EXECUTED,
        "tested_sha": TESTED_SHA,
        "tested_tree": TESTED_TREE,
        "context_revision": CONTEXT,
    }
    return _records.EvidenceBinding(**(bound | overrides))


def ran(output: str = "12 passed", exit_status: int = 0) -> _evidence.VerifiedCommand:
    """The suite, having printed `output` and exited with `exit_status`."""
    return _evidence.VerifiedCommand(
        command=SUITE, exit_status=exit_status, output=output,
    )


def minted(
    state: _pinned_state.PinnedState,
    bound: _records.EvidenceBinding | None = None,
    commands: tuple[_evidence.VerifiedCommand, ...] | None = None,
) -> _records.PendingEvidence | None:
    """A new transaction on `state` for `bound` and `commands`, not yet recorded.

    None where `state` cannot say which revisions it has spent.
    """
    return _record_state.mint_pending_evidence(
        state,
        ISSUE_NUMBER,
        bound or binding(),
        (ran(),) if commands is None else commands,
    )


def recorded(state: _pinned_state.PinnedState) -> _records.PendingEvidence:
    """Mint the default transaction on `state` and record it there, which has to be accepted."""
    pending = minted(state)
    if pending is None or not _record_state.record_pending_evidence(state, pending):
        raise AssertionError("the default transaction was refused")
    return pending


def settles(
    state: _pinned_state.PinnedState,
    pending: _records.PendingEvidence | None = None,
    comment_id: int = ARTIFACT_COMMENT,
) -> _records.PendingEvidence:
    """Install the one write settling `pending` at `comment_id`, as a publication would.

    With no `pending`, the default transaction is recorded first. Returns the
    transaction settled.
    """
    settling = pending or recorded(state)
    state.data = _settlement.settled_state(state, settling, comment_id, SETTLED_UNDER).data
    return settling


def current(
    pending: _records.PendingEvidence, comment_id: int = ARTIFACT_COMMENT,
) -> _records.CurrentEvidence:
    """The current evidence settling `pending` at `comment_id` leaves."""
    return _records.CurrentEvidence(
        receipt=pending.receipt,
        revision=pending.revision,
        binding=pending.binding,
        content_revision=pending.artifact.content_revision,
        comment_id=comment_id,
        passed=pending.passed,
    )


def reread(state: _pinned_state.PinnedState) -> _pinned_state.PinnedState:
    """`state` as the next tick reads it: rendered into the pinned comment and parsed back."""
    comment = FakeComment(
        id=state.comment_id or 1, body=_pinned_state.pinned_state_body(state.data),
    )
    return _pinned_state.pinned_state_from_comment(
        comment, trusted_login=None, issue_number=ISSUE_NUMBER,
    )
