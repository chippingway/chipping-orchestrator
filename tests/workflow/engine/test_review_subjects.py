# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an approval covers, as every later reader of it asks.

An approval is recorded against the pull request and the developer report the
reviewer was handed, and it covers the issue only while the report recorded as
current is that same revision -- on the same commit or any other. An approval
with no record covers only an issue with no report either, and a record nobody
can read covers nothing: a subject is read back whole -- every member in the
shape its writer spells, a head that is a commit, both report members or
neither -- or not at all. Recording an approval retires the head-keyed
docs verdict and ready ping an earlier approval left, and gives an issue that
never carried them no key; recording the subject a reviewer is handed retires
neither.
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

# The members a recorded subject is written with -- pinned keys live issues
# will carry, so spelled here rather than read off the module.
_PR = "pr"

_SHA = "sha"

_REQUIREMENTS_KEY = "requirements"

_REVISION_KEY = "report_revision"

_CONTENT_KEY = "report_content"

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
        # has none, and not an approval whose head is no commit, or none under
        # its pull request, though the report it names is the current one.
        approved_first = _subject(_report(1, _FIRST_DIGEST)).recorded()
        cases = (
            ("approval is null", _state(**{_APPROVED: None})),
            ("a head that is no commit", _state((1, _FIRST_DIGEST), **{
                _APPROVED: {**approved_first, _SHA: "not-a-commit"},
            })),
            ("a pull request with no head", _state((1, _FIRST_DIGEST), **{
                _APPROVED: {**approved_first, _SHA: ""},
            })),
            ("current report is damaged", _state(**{
                _APPROVED: _subject(None).recorded(),
                _records.CURRENT_REPORT: {"revision": "one"},
            })),
        )
        for name, state in cases:
            with self.subTest(name):
                self.assertFalse(review_subjects.approval_covers_current(state))


class RecordSubjectTest(unittest.TestCase):
    """What a recorded subject is written as, read back as, and retires."""

    def test_it_retires_the_head_keyed_stamps(self) -> None:
        state = _state(**{_DOCS_VERDICT: "no_change", _READY_PING_SHA: _HEAD})

        _approved(state, _subject(_report(1, _FIRST_DIGEST)))

        self.assertEqual(
            (state.get(_DOCS_VERDICT), state.get(_READY_PING_SHA)), (None, None),
        )
        self.assertEqual(state.get(_APPROVED), {
            _PR: _PR_NUMBER,
            _SHA: _HEAD,
            _REQUIREMENTS_KEY: _REQUIREMENTS,
            _REVISION_KEY: 1,
            _CONTENT_KEY: _FIRST_DIGEST,
        })

    def test_it_adds_no_stamp_an_issue_never_carried(self) -> None:
        state = _approved(_state(), _subject(None))

        self.assertFalse(state.carries(_DOCS_VERDICT))
        self.assertFalse(state.carries(_READY_PING_SHA))

    def test_a_reviewed_subject_retires_nothing(self) -> None:
        # Handing a reviewer a subject is no approval: it is recorded apart,
        # and the stamps an earlier approval left stand until one is given.
        stamps = {_DOCS_VERDICT: "no_change", _READY_PING_SHA: _HEAD}
        state = _state(**stamps)
        handed = _subject(_report(2, _SECOND_DIGEST))

        review_subjects.record_reviewed(state, handed)

        self.assertEqual(state.get(review_subjects.REVIEW_SUBJECT), handed.recorded())
        self.assertFalse(state.carries(_APPROVED))
        self.assertEqual(
            (state.get(_DOCS_VERDICT), state.get(_READY_PING_SHA)),
            (stamps[_DOCS_VERDICT], stamps[_READY_PING_SHA]),
        )

    def test_a_written_subject_reads_back(self) -> None:
        # Every shape the writer spells: a report or none, a head of either
        # object-id width, and a subject with no pull request, head, or
        # requirements at all.
        cases = (
            (
                "a report",
                _subject(_report(1, _FIRST_DIGEST)).recorded(),
                (_PR_NUMBER, 1, _FIRST_DIGEST),
                _REQUIREMENTS,
            ),
            ("no report", _subject(None).recorded(), (_PR_NUMBER, None, None), _REQUIREMENTS),
            (
                "a sha256 head",
                {**_subject(None).recorded(), _SHA: _FIRST_DIGEST},
                (_PR_NUMBER, None, None),
                _REQUIREMENTS,
            ),
            (
                "nothing named",
                review_subjects.ReviewSubject(
                    pr_number=None, commit="", requirements_revision="",
                ).recorded(),
                (None, None, None),
                "",
            ),
        )
        for name, recorded, identity, requirements in cases:
            with self.subTest(name):
                self.assertEqual(
                    review_subjects.ReviewSubject.identity_recorded_in(recorded), identity,
                )
                self.assertEqual(
                    review_subjects.ReviewSubject.requirements_recorded_in(recorded),
                    requirements,
                )

    def test_a_malformed_record_reads_as_nothing(self) -> None:
        # A member missing or one nothing writes, any member in a shape its
        # writer never spells, half a report, a pull request with no head, or
        # a head or report with no pull request to be read off: neither the
        # identity nor the requirements are read off what is left.
        written = _subject(_report(1, _FIRST_DIGEST)).recorded()
        no_report = _subject(None).recorded()
        cases = (
            ("not an object", [written]),
            ("without its head", _without(written, _SHA)),
            ("without its requirements", _without(written, _REQUIREMENTS_KEY)),
            ("a member nothing writes", {**written, "verdict": "approved"}),
            ("a head that is no commit", {**written, _SHA: "not-a-commit"}),
            ("an abbreviated head", {**written, _SHA: _HEAD[:7]}),
            ("a head spelled as null", {**written, _SHA: None}),
            ("a pull request with no head", {**written, _SHA: ""}),
            ("a pull request with no head or report", {**no_report, _SHA: ""}),
            ("requirements that are no digest", {**written, _REQUIREMENTS_KEY: "stale-hash"}),
            ("requirements spelled as null", {**written, _REQUIREMENTS_KEY: None}),
            ("a pull request of zero", {**written, _PR: 0}),
            ("a pull request spelled as text", {**written, _PR: str(_PR_NUMBER)}),
            ("a pull request spelled true", {**written, _PR: True}),
            ("a revision without its digest", {**no_report, _REVISION_KEY: 1}),
            ("a digest without its revision", {**no_report, _CONTENT_KEY: _FIRST_DIGEST}),
            ("a revision spelled true", {**written, _REVISION_KEY: True}),
            ("a digest cut short", {**written, _CONTENT_KEY: _FIRST_DIGEST[:len(_HEAD)]}),
            ("a head with no pull request", {**no_report, _PR: None}),
            ("a report with no pull request", {**written, _PR: None, _SHA: ""}),
        )
        for name, recorded in cases:
            with self.subTest(name):
                self.assertIsNone(
                    review_subjects.ReviewSubject.identity_recorded_in(recorded),
                )
                self.assertIsNone(
                    review_subjects.ReviewSubject.requirements_recorded_in(recorded),
                )


if __name__ == "__main__":
    unittest.main()
