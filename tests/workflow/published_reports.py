# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report a validating tick finds on the pull request it reviews.

Every road that brings an implementation to review publishes the report of it
first, and a reviewer is refused a pull request that carries none. So a case
set on `validating` over an open pull request stands in the world production
leaves: the pull request carries a report of its head, written against the
requirements the tick will measure, and the pinned comment records it settled.
A case that seeds its own report -- settled, in flight, or owed -- or none that
could be one -- no pull request this client holds, a head or a baseline no
report can name -- is left exactly as it stands, and the tick answers for that.
"""
from __future__ import annotations

from orchestrator.github import developer_reports as _reports
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    report_delivery as _report_delivery,
    report_records as _records,
    report_settlement_state as _settlement,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.late_split import payloads as _payloads
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.repo_values import _TEST_SPEC

# The requirements baseline the drift check holds an issue to.
_USER_CONTENT_HASH = "user_content_hash"

# What the delivery reported, which no case reads for its words.
DELIVERED_REPORT = "Implemented the change; the suite passes."

# Every record a report already on its way leaves: one in flight, one owed,
# or one settled. A pull request carrying any of them is left as it stands.
_REPORTED = (
    _records.PENDING_REPORT,
    _records.DELIVERED_REPORT,
    _records.CURRENT_REPORT,
    _records.REPORT_HANDOFF,
    _report_delivery.OWED_REPORT,
)


def publishes_the_report(github, issue) -> None:
    """Leave on the pinned pull request the report its delivery published.

    Added to the record the case seeded rather than written through the
    client, so the tick's own count of writes stays the tick's.
    """
    state = github.read_pinned_state(issue)
    if not _reported(state):
        _publishes(github, issue, state, (1, DELIVERED_REPORT))


def republishes_the_report(github, issue, text: str = DELIVERED_REPORT) -> None:
    """Settle the pull request's next report, of where it stands, over the last.

    What a round that settles a report leaves, by whichever road: the next
    revision, about the head the pull request carries now, in place of the one
    an earlier round settled.
    """
    state = github.read_pinned_state(issue)
    current = _settlement.read_current_report(state)
    revision = 1 if current is None else current.report_revision + 1
    _publishes(github, issue, state, (revision, text))


def _reported(state) -> bool:
    """Whether the pinned comment already records a report, in any state."""
    return any(state.get(record) is not None for record in _REPORTED)


def _publishes(github, issue, state, published: tuple[int, str]) -> None:
    """Post `published` -- a revision and its words -- and record it settled."""
    pull = github.pulls.get(_payloads.as_identity(state.get("pr_number")))
    report = None if pull is None else _report_of(github, issue, state, pull, published)
    if report is None:
        return
    landed = FakeComment(
        id=github._next_comment_id(pull),
        body=_reports.render_developer_report(report),
        user=FakeUser(github._bot_login),
    )
    settled = _settled(state, report, pull.head_branch, landed.id)
    if settled is not None:
        pull.issue_comments.append(landed)
        # The baseline the report was written against, where the case seeded
        # none: every road that settles a report runs behind the drift check
        # that records one.
        if state.get(_USER_CONTENT_HASH) is None:
            settled[_USER_CONTENT_HASH] = report.requirements_revision
        github._pinned[issue.number].data.update(settled)


def approves_the_report(github, issue) -> None:
    """Record an approval of the report the pull request carries.

    What the approval a case is set after left on the pinned comment: the
    subject it covered, and the stamps an approval retires gone.
    """
    publishes_the_report(github, issue)
    state = github.read_pinned_state(issue)
    current = _settlement.read_current_report(state)
    approved = _review_subjects.ReviewSubject(
        pr_number=current.subject.pr_number,
        commit=current.subject.source_sha,
        requirements_revision=current.subject.requirements_revision,
        report=_review_subjects.ReviewReport(
            text="",
            report_revision=current.report_revision,
            content_revision=current.content_revision,
            source_sha=current.subject.source_sha,
            requirements_revision=current.subject.requirements_revision,
            location=current.location,
        ),
    )
    _review_subjects.record_approved(state, approved)
    github._pinned[issue.number].data.update(state.data)


def _report_of(github, issue, state, pull, published) -> _reports.DeveloperReport | None:
    """The report `published` names, of `pull`'s head, or None unnameable."""
    revision, text = published
    baseline = state.get(_USER_CONTENT_HASH) or _prompt_context._delivered_thread(
        github, issue, state,
    ).requirements_revision
    try:
        return _reports.DeveloperReport(
            pr_number=pull.number,
            source_sha=pull.head.sha,
            requirements_revision=baseline,
            report_revision=revision,
            receipt=f"issue-{issue.number}-report-{revision}",
            text=text,
        )
    except _reports.ReportRefusedError:
        return None


def _settled(
    state, report: _reports.DeveloperReport, branch: str, comment_id: int,
) -> dict | None:
    """The settled pair a publication of `report` leaves, or None unrecordable."""
    written = type(state)(state_data={})
    current = _records.CurrentReport(
        subject=_records.ReportSubject(
            repo_slug=_TEST_SPEC.slug,
            pr_number=report.pr_number,
            branch=state.get("branch") or branch,
            source_sha=report.source_sha,
            requirements_revision=report.requirements_revision,
        ),
        report_revision=report.report_revision,
        content_revision=_reports.content_digest(report.text),
        location=ReportLocation(pr_number=report.pr_number, comment_id=comment_id),
        mode=_records.ReportMode.PUBLISH,
    )
    handoff = _records.ReportHandoff(
        receipt=report.receipt,
        pr_number=report.pr_number,
        report_revision=report.report_revision,
        source_sha=report.source_sha,
        settled_under=WorkflowLabel.VALIDATING,
    )
    if not (
        _settlement.record_current_report(written, current)
        and _settlement.record_handoff(written, handoff)
    ):
        return None
    return written.data
