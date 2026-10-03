# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report records every case here is written against.

One publication carrying a report, one verification carrying a location, the
settled pair either of them becomes, and the helpers that put any of those onto
a pinned comment and then damage or truncate exactly one member. Spelled once so
a case that breaks a member is visibly about that member rather than about the
fixture around it. The reports quoting a reserved receipt, and the ones
describing it in prose instead, are spelled here for the same reason: both
records carry a report, and each is refused for the same text.
"""
from __future__ import annotations

from orchestrator.github import comments as _trust
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_record_reading as _reading,
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.decomposition import split_receipts as _split_receipts
from orchestrator.workflow.state import WorkflowLabel

RECEIPT = "issue-7-report-1"

SOURCE_SHA = "3f786850e387550fdab836ed7e6dc881de23001b"

REQUIREMENTS = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

CONTENT_DIGEST = "5f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-7"

SLUG = "chippingway/chipping-orchestrator"

PR_NUMBER = 12

COMMENT_ID = 8080

# The bookkeeping fields the cases read and write, spelled once because WPS
# counts a literal repeated across a module as the drift risk it is.
PR_WATERMARK = "pr_last_comment_id"

BASELINE = "user_content_hash"

REVIEW_ROUND = "review_round"

PENDING_FIX_AT = "pending_fix_at"

# The location field a record carries on every place it names, whose ABSENCE
# the cases below tell apart from the `null` that means the description.
LOCATION_COMMENT = "location_comment"

REVISION = 2

# Text a JSON escape can spell and UTF-8 cannot carry: a lone surrogate reads
# back out of the pinned comment as a `str` nothing downstream can encode.
LONE_SURROGATE = "the gate is in \ud800 place"

# How many paragraphs a report the size of a real completion report runs to:
# thousands of characters, and still inside the budget every developer prompt
# teaches.
_PARAGRAPHS = 55

REPORT_BODY = "The branch adds the dormant split receipts and the seed hold.\n\n" * _PARAGRAPHS

# The parent issue the quoted split child's receipt names.
_SPLIT_PARENT = 2069

# The receipts a report may not quote: the one a split stamps its child with,
# read off the stage that stamps it so the case quotes what that stage's own
# search would match, the stamp on every comment this orchestrator posts, and
# the bare prefix every receipt begins with.
_RESERVED = (
    ("split child", _split_receipts.receipt(_SPLIT_PARENT, "0123456789abcdef", 1, None)),
    ("comment stamp", _trust.ORCHESTRATOR_COMMENT_MARKER),
    ("bare prefix", _trust.RECEIPT_MARKER_PREFIX),
)

# The Markdown a report can set a receipt apart in, none of which changes the
# raw body a receipt search reads.
_QUOTINGS = (
    ("inline code", "Each child is stamped with `{0}`."),
    ("fenced code", "Each child is stamped with:\n\n```html\n{0}\n```"),
    ("quotation", "Each child is stamped with:\n\n> {0}"),
)

# Every reserved receipt in every quoting, each closing a report of that size.
QUOTED_RECEIPTS = tuple(
    (f"{kind} in {quoting}", f"{REPORT_BODY}{template.format(receipt)}")
    for kind, receipt in _RESERVED
    for quoting, template in _QUOTINGS
)

# The same receipt described rather than quoted: named, even set in code, but
# never spelled with the prefix a search matches.
DESCRIBED_RECEIPTS = (
    ("in prose", f"{REPORT_BODY}Each child is stamped with a hidden receipt naming its parent and slice."),
    ("named in code", f"{REPORT_BODY}Each child is stamped with an `orchestrator-split-child` HTML comment."),
)

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
    report_revision=REVISION,
    mode=_records.ReportMode.PUBLISH,
    route=WorkflowLabel.FIXING,
    report="The branch adds the gate.\n\nVerified with the suite.",
    watermarks=((PR_WATERMARK, 41), (BASELINE, REQUIREMENTS)),
    spends=((REVIEW_ROUND, 3), (PENDING_FIX_AT, None)),
)

VERIFIED = _records.PendingReport(
    receipt=RECEIPT,
    subject=SUBJECT,
    report_revision=REVISION,
    mode=_records.ReportMode.VERIFY,
    route=WorkflowLabel.IN_REVIEW,
    location=ReportLocation(pr_number=PR_NUMBER, comment_id=COMMENT_ID),
    content_revision=CONTENT_DIGEST,
)

CURRENT = _records.CurrentReport(
    subject=SUBJECT,
    report_revision=REVISION,
    content_revision=CONTENT_DIGEST,
    location=ReportLocation(pr_number=PR_NUMBER, comment_id=COMMENT_ID),
)

HANDOFF = _records.ReportHandoff(
    receipt=RECEIPT,
    pr_number=PR_NUMBER,
    report_revision=REVISION,
    source_sha=SOURCE_SHA,
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


def settled(**fields) -> dict:
    """The pinned object the current report is written as, members replaced."""
    state = PinnedState()
    _settlement.record_current_report(state, CURRENT)
    return state.get(_records.CURRENT_REPORT) | fields


def without(recorded: dict, member: str) -> dict:
    """One recorded object with a member gone, as a truncation leaves it."""
    return {key: held for key, held in recorded.items() if key != member}


def reads_back(state: PinnedState) -> _records.PendingReport | None:
    """What the pending record on this state reads back as."""
    return _record_state.read_pending_report(state)


def refusal_of(state: PinnedState) -> _record_values.RecordRefusal | None:
    """Why the pending record on this state reads back as nothing, or None."""
    read = _reading.pending_or_refusal(state.get(_records.PENDING_REPORT))
    return read if isinstance(read, _record_values.RecordRefusal) else None
