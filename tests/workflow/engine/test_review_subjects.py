# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an approval covers, as every later reader of it asks.

An approval is recorded against the pull request and the developer report the
reviewer was handed, and it covers the issue only while the report recorded as
current is that same revision -- on the same commit or any other. An approval
with no record covers only an issue with no report either, and a record nobody
can read covers nothing. Recording an approval retires the head-keyed
docs verdict and ready ping an earlier approval left, and gives an issue that
never carried them no key.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_records as _records,
    report_settlement_state as _settlement,
    review_subjects,
)

_PR_NUMBER = 12

_OTHER_PR_NUMBER = 13

_HEAD = "3f786850e387550fdab836ed7e6dc881de23001b"

_REQUIREMENTS = "3a3be1d2c3b4a5968778695a4b3c2d1e0ff0e1d2c3b4a5968778695a4b3c2d1e"

_FIRST_DIGEST = "11a1e1d2c3b4a5968778695a4b3c2d1e0ff0e1d2c3b4a5968778695a4b3c2d1e"

_SECOND_DIGEST = "22b2e1d2c3b4a5968778695a4b3c2d1e0ff0e1d2c3b4a5968778695a4b3c2d1e"

_COMMENT_ID = 8_080

_APPROVED = review_subjects.APPROVED_SUBJECT

_DOCS_VERDICT = "docs_verdict"

_READY_PING_SHA = "ready_ping_sha"


def _report(revision: int, digest: str) -> review_subjects.ReviewReport:
    return review_subjects.ReviewReport(
        text=f"report {revision}",
        report_revision=revision,
        content_revision=digest,
        source_sha=_HEAD,
        requirements_revision=_REQUIREMENTS,
        location=ReportLocation(pr_number=_PR_NUMBER, comment_id=_COMMENT_ID),
    )


def _subject(
    report: review_subjects.ReviewReport | None,
    pr_number: int = _PR_NUMBER,
) -> review_subjects.ReviewSubject:
    return review_subjects.ReviewSubject(
        pr_number=pr_number,
        commit=_HEAD,
        requirements_revision=_REQUIREMENTS,
        report=report,
    )


def _state(current: tuple[int, str] | None = None, **fields) -> PinnedState:
    """An issue on `_PR_NUMBER`, settled on `current` -- revision and digest."""
    state = PinnedState(state_data={"pr_number": _PR_NUMBER, **fields})
    if current is not None:
        revision, digest = current
        _settlement.record_current_report(state, _records.CurrentReport(
            subject=_records.ReportSubject(
                repo_slug="chippingway/orchestrator",
                pr_number=_PR_NUMBER,
                branch="orchestrator/chippingway__orchestrator/issue-7",
                source_sha=_HEAD,
                requirements_revision=_REQUIREMENTS,
            ),
            report_revision=revision,
            content_revision=digest,
            location=ReportLocation(pr_number=_PR_NUMBER, comment_id=_COMMENT_ID),
        ))
    return state


def _without(recorded: dict, member: str) -> dict:
    """`recorded` with one member dropped, as a truncated write leaves it."""
    return {key: kept for key, kept in recorded.items() if key != member}


def _approved(state: PinnedState, subject: review_subjects.ReviewSubject) -> PinnedState:
    review_subjects.record_approved(state, subject)
    return state


class ApprovalCoverageTest(unittest.TestCase):
    """Whether the recorded approval still covers the report recorded now."""

    def test_the_report_revision_decides(self) -> None:
        first = _report(1, _FIRST_DIGEST)
        cases = (
            ("no approval, no report", _state(), True),
            ("no approval, but a report", _state((2, _SECOND_DIGEST)), False),
            (
                "the approved report is current",
                _approved(_state((1, _FIRST_DIGEST)), _subject(first)),
                True,
            ),
            (
                "no report, approved without one",
                _approved(_state(), _subject(None)),
                True,
            ),
            (
                "a later report on the same commit",
                _approved(_state((2, _SECOND_DIGEST)), _subject(first)),
                False,
            ),
            (
                "the same revision, other words",
                _approved(_state((1, _SECOND_DIGEST)), _subject(first)),
                False,
            ),
            (
                "a report settled after an approval of none",
                _approved(_state((1, _FIRST_DIGEST)), _subject(None)),
                False,
            ),
            (
                "an approval of another pull request",
                _approved(
                    _state((1, _FIRST_DIGEST)),
                    _subject(first, pr_number=_OTHER_PR_NUMBER),
                ),
                False,
            ),
        )
        for name, state, covers in cases:
            with self.subTest(name):
                self.assertIs(review_subjects.approval_covers_current(state), covers)

    def test_an_unreadable_record_covers_nothing(self) -> None:
        # Damage on either side, `null` included, is never agreement -- not
        # even with an approval that saw no report at all, over an issue that
        # has none. The approval is read whole: a subject short of its head or
        # its requirements, or carrying either in a shape nothing writes, or a
        # member nothing writes, is no approval.
        approved_none = _subject(None).recorded()
        cases = (
            ("approval is null", _state(**{_APPROVED: None})),
            ("approval names half a report", _state(**{
                _APPROVED: {**approved_none, "report_revision": 1},
            })),
            ("approval without its head", _state(**{
                _APPROVED: _without(approved_none, "sha"),
            })),
            ("a head spelled as null", _state(**{
                _APPROVED: {**approved_none, "sha": None},
            })),
            ("approval without its requirements", _state(**{
                _APPROVED: _without(approved_none, "requirements"),
            })),
            ("requirements that are no digest", _state(**{
                _APPROVED: {**approved_none, "requirements": "stale-hash"},
            })),
            ("a member nothing writes", _state(**{
                _APPROVED: {**approved_none, "verdict": "approved"},
            })),
            ("current report is damaged", _state(**{
                _APPROVED: approved_none,
                _records.CURRENT_REPORT: {"revision": "one"},
            })),
        )
        for name, state in cases:
            with self.subTest(name):
                self.assertFalse(review_subjects.approval_covers_current(state))


class RecordApprovedTest(unittest.TestCase):
    """What recording an approval writes and what it retires."""

    def test_it_retires_the_head_keyed_stamps(self) -> None:
        state = _state(**{_DOCS_VERDICT: "no_change", _READY_PING_SHA: _HEAD})

        _approved(state, _subject(_report(1, _FIRST_DIGEST)))

        self.assertEqual(
            (state.get(_DOCS_VERDICT), state.get(_READY_PING_SHA)), (None, None),
        )
        self.assertEqual(state.get(_APPROVED), {
            "pr": _PR_NUMBER,
            "sha": _HEAD,
            "requirements": _REQUIREMENTS,
            "report_revision": 1,
            "report_content": _FIRST_DIGEST,
        })

    def test_it_adds_no_stamp_an_issue_never_carried(self) -> None:
        state = _approved(_state(), _subject(None))

        self.assertFalse(state.carries(_DOCS_VERDICT))
        self.assertFalse(state.carries(_READY_PING_SHA))


if __name__ == "__main__":
    unittest.main()
