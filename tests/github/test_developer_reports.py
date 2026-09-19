# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report a pull request carries, as one self-proving comment.

What a report comment says about itself, what it refuses to be, and why a
comment is a report only when it is ours and re-renders exactly from the
identity and text it claims.
"""
from __future__ import annotations

import unittest

from orchestrator.github import comments as _trust, developer_reports as _reports
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from tests.support.fakes import FakeComment, FakeUser, make_developer_report

_BOT_LOGIN = "orchestrator"
_PR_NUMBER = 12
_LATER_REVISION = 2
_HEADER_PREFIX = "<!--orchestrator-developer-report"
# How many characters an excerpt loses from the end of its text.
_CUT = 10
# A count of more digits than Python converts, in a comment GitHub still holds.
_DIGITS = 5000
_UNCONVERTIBLE = "1" * _DIGITS
_REPORT = make_developer_report(_PR_NUMBER)


def _comment(body: str | None, *, login: str = _BOT_LOGIN) -> FakeComment:
    """One conversation comment, posted under our own login unless named."""
    return FakeComment(id=1, body=body, user=FakeUser(login))


class ReportRenderingTest(unittest.TestCase):
    """What one report comment says about itself, visibly and in its header."""

    def test_it_names_what_it_reports_on(self) -> None:
        body = _reports.render_developer_report(_REPORT)

        visible = body[:body.index(_HEADER_PREFIX)]
        for claimed in (
            "Developer report, revision 1",
            f"commit `{_REPORT.source_sha}`",
            f"requirements revision `{_REPORT.requirements_revision}`",
            "supersedes any agent message in this pull request's description",
            "every lower-numbered developer report",
            _REPORT.text,
        ):
            with self.subTest(claimed=claimed):
                self.assertIn(claimed, visible)

    def test_the_header_carries_identity_and_digest(self) -> None:
        # Hidden, and followed by the ordinary marker every reader that passes
        # over our comments already looks for.
        body = _reports.render_developer_report(_REPORT)

        header = (
            f"{_HEADER_PREFIX}:receipt={_REPORT.receipt}:pr={_PR_NUMBER}"
            f":revision=1:commit={_REPORT.source_sha}"
            f":requirements={_REPORT.requirements_revision}"
            f":content={_reports.content_digest(_REPORT.text)}-->"
        )
        self.assertTrue(
            body.endswith(f"\n\n{header}\n\n{_trust.ORCHESTRATOR_COMMENT_MARKER}"),
        )
        self.assertTrue(header.startswith(_REPORT.receipt_scope))

    def test_retries_match_and_later_reports_differ(self) -> None:
        # A retry of one transaction renders the same body, so a thread search
        # finds it; the next report on the same commit is another transaction.
        later = make_developer_report(
            _PR_NUMBER, report_revision=_LATER_REVISION, receipt="issue-7-report-2",
        )
        render = _reports.render_developer_report

        self.assertEqual(render(make_developer_report(_PR_NUMBER)), render(_REPORT))
        self.assertEqual(later.source_sha, _REPORT.source_sha)
        self.assertNotEqual(render(later), render(_REPORT))
        self.assertNotIn(_REPORT.receipt_scope, render(later))


class ReportRefusalTest(unittest.TestCase):
    """A report no header can carry, or no comment can hold, is not made."""

    def test_an_uncarriable_identity_is_refused(self) -> None:
        for pr_number, report_fields in (
            (0, {}),
            (True, {}),
            (_PR_NUMBER, {"report_revision": "1"}),
            (_PR_NUMBER, {"source_sha": "3f78685"}),
            (_PR_NUMBER, {"source_sha": _REPORT.source_sha.upper()}),
            (_PR_NUMBER, {"requirements_revision": "two words"}),
            (_PR_NUMBER, {"receipt": "run:1"}),
            (_PR_NUMBER, {"receipt": "run-->"}),
            (_PR_NUMBER, {"receipt": ""}),
        ):
            with (
                self.subTest(pr_number=pr_number, **report_fields),
                self.assertRaises(_reports.ReportRefusedError),
            ):
                make_developer_report(pr_number, **report_fields)

    def test_empty_or_marked_text_is_refused(self) -> None:
        # A thread is searched for receipts by substring, so a report quoting
        # one would read to that search as the step it names.
        for text in (
            " \n\t",
            None,
            _trust.ORCHESTRATOR_COMMENT_MARKER,
            f"see {_REPORT.receipt_scope}",
        ):
            with (
                self.subTest(text=text),
                self.assertRaises(_reports.ReportRefusedError),
            ):
                make_developer_report(_PR_NUMBER, text=text)

    def test_an_oversized_report_is_refused_not_cut(self) -> None:
        # Refused one character past what a comment holds: an excerpt that
        # fits, published under the header, would pass for the whole report.
        overhead = len(_reports.render_developer_report(_REPORT)) - len(_REPORT.text)
        room = MAX_PINNED_BODY - overhead
        fitting = make_developer_report(_PR_NUMBER, text="x" * room)
        oversized = make_developer_report(_PR_NUMBER, text="x" * (room + 1))

        self.assertEqual(
            len(_reports.render_developer_report(fitting)), MAX_PINNED_BODY,
        )
        with self.assertRaises(_reports.ReportRefusedError):
            _reports.render_developer_report(oversized)


class ReportOwnershipTest(unittest.TestCase):
    """A comment is a report only when it is ours and re-renders exactly."""

    def test_our_exact_rendering_reads_back(self) -> None:
        # Verbatim, surrounding whitespace included, because the digest is
        # taken over exactly the text that was posted.
        report = make_developer_report(_PR_NUMBER, text="\n  indented summary\n\n")
        posted = _comment(_reports.render_developer_report(report))
        for bot_login in (_BOT_LOGIN, None):
            with self.subTest(bot_login=bot_login):
                self.assertEqual(
                    _reports.developer_report_from_comment(posted, bot_login=bot_login),
                    report,
                )

    def test_anything_else_is_not_a_report(self) -> None:
        body = _reports.render_developer_report(_REPORT)
        header_at = body.index(_HEADER_PREFIX)
        cases = (
            ("another author's paste", _comment(body, login="mallory")),
            ("an edited sentence", _comment(body.replace("Implemented", "Skipped"))),
            ("text after the marker", _comment(f"{body}\n\nappended")),
            (
                "an excerpt",
                _comment(body[:header_at - _CUT] + body[header_at:]),
            ),
            ("the header alone", _comment(body[header_at:])),
            (
                "a zero-padded revision",
                _comment(body.replace(":revision=1:", ":revision=01:")),
            ),
            ("no body", _comment(None)),
        )
        for label, comment in cases:
            with self.subTest(label):
                self.assertIsNone(
                    _reports.developer_report_from_comment(comment, bot_login=_BOT_LOGIN),
                )

    def test_an_unconvertible_count_is_not_a_report(self) -> None:
        # Either count of the header, claimed in more digits than Python
        # converts: no rendering wrote it, and reading it raises nothing.
        body = _reports.render_developer_report(_REPORT)
        for claimed in (f":pr={_PR_NUMBER}:", ":revision=1:"):
            with self.subTest(claimed=claimed):
                field = claimed.partition("=")[0]
                endless = body.replace(claimed, f"{field}={_UNCONVERTIBLE}:")
                self.assertNotEqual(endless, body)
                self.assertIsNone(_reports.developer_report_from_comment(
                    _comment(endless), bot_login=_BOT_LOGIN,
                ))


if __name__ == "__main__":
    unittest.main()
