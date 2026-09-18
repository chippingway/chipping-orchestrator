# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The delivered reports, comments, and runs the delivery cases are written against.

One report a run wrote for publication, one asserting a report is already on
the thread, the record a second report leaves standing, and the comments each
case crowds to the point its own refusal is about. Spelled once so a case that
is about the room left reads as being about the room rather than about the
fixture around it.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.github import comments as _trust
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine import report_record_test_support as support
from tests.workflow.fixtures import LABEL_IMPLEMENTING

ISSUE_NUMBER = 7

RECEIPT = "issue-7-report-1"

BASELINE = "user_content_hash"

PARK_REASON = "park_reason"

AWAITING_HUMAN = "awaiting_human"

# What a comment is crowded with, and the key it is crowded under, where the
# case is about the room left rather than about what is in it.
FILLER = "x"

CROWDING = "crowded"

# How much room past the report's own length a comment is left with in the two
# crowded cases. The wider one has room for the delivered record and not for
# the transaction RESERVED against it, whose subject is sized at the width
# every member of one is recorded at; the narrower one has no room for the
# transaction an actual subject builds either.
CROWDED_FOR_RESERVATION = 1000

CROWDED_FOR_BINDING = 400

# The same room, for the two comments whose reservation is about the exchange
# rather than about the transaction's own size. At the first, a comment that
# has never carried a delivery has no room for the `null` the binding's drop
# writes beside the transaction; at the second, a comment already carrying one
# has room only once that record is counted as the room the drop gives back.
CROWDED_FOR_TOMBSTONE = 4200

CROWDED_FOR_REDELIVERY = 4350

# The same room again, for the two comments the BRANCH's own width decides. At
# the first there is room for a transaction whose branch is 256 ASCII
# characters and none for one whose branch is 256 codepoints the comment
# renders as twelve characters each, so the record is refused here rather than
# after the push; at the second there is room for the wider one, and the
# binding that arrives on such a branch takes it.
CROWDED_FOR_ASCII_BRANCH = 2000

CROWDED_FOR_RESERVED_SUBJECT = 4300

# The room left where what decides the refusal is the write the PUSH makes: the
# comment holds the delivered record and not the code-publication receipt the
# gate puts beside it.
CROWDED_FOR_RECEIPT = 1000

# The subject an acceptance reserves against, spelled from the widths the
# record values publish: a report is accepted before its publication exists,
# so what it reserves has to be no narrower than any subject that can arrive.
# The requirements revision is the exception the binding holds it to, since
# that member belongs to the run rather than to the publication.
WIDEST_SUBJECT = replace(
    _delivery_state._WIDEST_SUBJECT,
    requirements_revision=support.REQUIREMENTS,
)

# One branch at the reader's own bound, filled with a codepoint outside the
# BMP: the field is bounded in CODEPOINTS, while the comment that has to carry
# it is measured in the characters a JSON escape renders them as, and one of
# these is a surrogate pair -- twelve characters for one. A ref of 256 emoji is
# one git creates without complaint. Spelled from that bound here rather than
# read off the reservation, so a reservation taken at a narrower width fails
# the case that uses it instead of being copied into it.
WIDEST_BRANCH = "\U0001f600" * _record_values.MAX_BRANCH

# What an issue parked over a report this workflow could not deliver carries.
# The reason is the debt there -- the roads that take this park have no record to
# leave -- beside the `developer_report_owed` flag the park itself writes.
OWED = ((PARK_REASON, _delivery.UNDELIVERABLE_REPORT),)

# The reports this workflow will not record, and why each is one: past what a
# comment holds, quoting a receipt marker of this orchestrator's, spelled in
# text UTF-8 cannot carry, and saying nothing at all.
UNPUBLISHABLE_REPORTS = (
    ("oversized", FILLER * (_record_values.MAX_REPORT_TEXT + 1)),
    (
        "a quoted receipt marker",
        f"quoting {_trust.RECEIPT_MARKER_PREFIX}developer-report",
    ),
    ("text UTF-8 cannot carry", support.LONE_SURROGATE),
    ("nothing at all", "   "),
)

# What a delivered report reads back as when the run wrote one for publication,
# and when it says a report is already on the thread.
DELIVERED = _records.DeliveredReport(
    receipt=RECEIPT,
    report_revision=1,
    mode=_records.ReportMode.PUBLISH,
    route=WorkflowLabel.IMPLEMENTING,
    requirements_revision=support.REQUIREMENTS,
    report="The branch adds the gate.\n\nVerified with the suite.",
)

ASSERTED = _records.DeliveredReport(
    receipt=RECEIPT,
    report_revision=1,
    mode=_records.ReportMode.VERIFY,
    route=WorkflowLabel.IMPLEMENTING,
    requirements_revision=support.REQUIREMENTS,
    location=ReportLocation(
        pr_number=support.PR_NUMBER, comment_id=support.COMMENT_ID,
    ),
    content_revision=support.CONTENT_DIGEST,
)

# The record a second report leaves standing. What a caller may still be
# holding then is the one it replaced, which is a binding the owner refuses
# rather than one that drops the newer report.
REDELIVERED = replace(
    DELIVERED,
    receipt=f"issue-{ISSUE_NUMBER}-report-2",
    report_revision=2,
)

# How long the outstanding transaction's own report is: large enough that what
# the comment can still hold is decided by the records ALREADY on it rather
# than by the transaction a new delivery reserves against it.
OUTSTANDING_REPORT = 20000

# One transaction an earlier publication left outstanding.
OUTSTANDING = replace(support.PUBLISHED, report="r" * OUTSTANDING_REPORT)


def delivered_object(
    delivered: _records.DeliveredReport = DELIVERED,
) -> dict:
    """The pinned object one delivered report is written as."""
    state = PinnedState()
    _delivery_state.record_delivered_report(state, delivered)
    return state.get(_records.DELIVERED_REPORT)


def outstanding_comment() -> dict:
    """The comment one issue with a transaction still outstanding carries."""
    state = PinnedState()
    _record_state.record_pending_report(state, OUTSTANDING)
    return dict(state.data)


def crowded_comment(slack: int, carried: dict | None = None) -> PinnedState:
    """One comment with `slack` characters left past the report's own length.

    Built from what the report itself takes rather than from a total, so a
    case says how much room its refusal is about instead of restating the
    ceiling.
    """
    room = MAX_PINNED_BODY - len(DELIVERED.report) - slack
    return PinnedState(state_data={
        **(carried or {}), CROWDING: FILLER * room,
    })


def ready(report: str) -> str:
    """A finished run's message, ending on a report ready for publication."""
    return f"done\n\nREPORT: READY\n{report}\nREPORT: END"


def seeded_issue():
    """One open issue this delivery is recorded against."""
    github = FakeGitHubClient()
    issue = make_issue(ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
    github.add_issue(issue)
    return github, issue


def unreachable_repository(github) -> None:
    """Leave this client's own-repository reading failing the way a request can.

    The reading completes a repository PyGithub may hold only a URL for, so it
    reaches GitHub -- and a case about what a finished run's report survives
    has to be able to take that away.
    """
    github.is_own_repository = _refuses_to_read


def _refuses_to_read(slug: str | None) -> bool:
    """Stand in for the reading nobody could take."""
    raise ConnectionError(f"the repository behind {slug} could not be read")
