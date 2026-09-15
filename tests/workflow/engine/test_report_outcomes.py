# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report outcomes a stage may complete on, and nothing else.

Two outcomes succeed: a complete report between READY and END lines, and a
VERIFIED line naming where on a pull request the developer read one and which
revision it read. Every other ending stays apart from both -- a question, a
disagreement, an ordinary `ACK:`, no-change prose, a malformed marker or one
that may render as code -- and no message is read at all from a run that never
started, was interrupted, timed out, was refused by its provider, or exited
nonzero.
"""
from __future__ import annotations

import dataclasses
import unittest

from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import messages, report_outcomes
from orchestrator.workflow.engine.report_outcome_models import (
    _ReadyReport,
    _ReportLocation,
    _ReportRefusal,
    _VerifiedReport,
)
from tests.workflow.agent_failure_values import PROVIDER_OVERLOAD_MESSAGE

_REPORT = "## Summary\n\nAdds the foo flag.\n\n- verified with `pytest tests/foo`"
_READY_MESSAGE = f"All done.\n\nREPORT: READY\n{_REPORT}\nREPORT: END\n"
_FENCED_COMMAND = "```sh\npytest tests/foo\n```"
_LISTED_COMMAND = "- ```sh\n  pytest tests/foo\n  ```"
# A report that opens on an indented code block and ends on a hard line break.
_INDENTED_REPORT = "    pytest tests/foo\n\nAdds the flag.  "
# Text to Markdown, never a blank.
_NO_BREAK_SPACE = " "
_SLUG = "chippingway/orchestrator"
_PULL_NUMBER = 1697
_COMMENT_ID = 5579567555
# The largest id a signed 64-bit integer holds, nineteen digits wide.
_WIDEST_ID = "9223372036854775807"
# How many digits `int` converts from a string by default.
_INT_MAX_STR_DIGITS = 4300
_OVERLONG_ID = "9" * (_INT_MAX_STR_DIGITS + 1)
_DIGEST = "0123456789abcdef" * 4
_UPPERCASE_DIGEST = _DIGEST.upper()
_SHORT_DIGEST = _DIGEST[:-1]
_REVISION = f"sha256:{_DIGEST}"
_REPO_URL = f"https://github.com/{_SLUG}"
_PULL_URL = f"{_REPO_URL}/pull/{_PULL_NUMBER}"
_COMMENT_URL = f"{_PULL_URL}#issuecomment-{_COMMENT_ID}"
_VERIFIED_LINE = f"REPORT: VERIFIED {_COMMENT_URL} {_REVISION}"
_QUESTION = "Should the flag default to on?"
_ACK_LINE = "ACK: the branch already covers the edit"
_INTERRUPTED_EXIT = -15

# Messages that reach for the contract and miss it.
_MALFORMED_MESSAGES = (
    "REPORT: READY\nAdds the flag.",
    "Adds the flag.\nREPORT: END",
    f"{_READY_MESSAGE}\n{_QUESTION}",
    "REPORT: READY\n\n  \nREPORT: END",
    f"REPORT: READY\n{_REPORT}\nREPORT: READY\nmore\nREPORT: END",
    f"{_READY_MESSAGE}\n{_READY_MESSAGE}",
    f"REPORT: READY.\n{_REPORT}\nREPORT: END",
    f"REPORT:READY\n{_REPORT}\nREPORT:END",
    "REPORT: DONE",
    f"REPORT: VERIFIED {_PULL_URL}",
    f"REPORT: VERIFIED {_PULL_URL} {_DIGEST}",
    f"REPORT: VERIFIED {_PULL_URL} sha256:{_UPPERCASE_DIGEST}",
    f"REPORT: VERIFIED {_PULL_URL} sha256:{_SHORT_DIGEST}",
    f"REPORT: VERIFIED http://github.com/{_SLUG}/pull/{_PULL_NUMBER} {_REVISION}",
    f"REPORT: VERIFIED https://example.com/{_SLUG}/pull/{_PULL_NUMBER} {_REVISION}",
    f"REPORT: VERIFIED {_REPO_URL}/issues/{_PULL_NUMBER} {_REVISION}",
    f"REPORT: VERIFIED {_PULL_URL}#discussion_r{_COMMENT_ID} {_REVISION}",
    f"REPORT: VERIFIED {_REPO_URL}/pull/{_WIDEST_ID}9 {_REVISION}",
    f"REPORT: VERIFIED {_PULL_URL}#issuecomment-{_WIDEST_ID}9 {_REVISION}",
    f"REPORT: VERIFIED {_REPO_URL}/pull/{_OVERLONG_ID} {_REVISION}",
    f"REPORT: VERIFIED {_PULL_URL}#issuecomment-{_OVERLONG_ID} {_REVISION}",
    f"{_VERIFIED_LINE}.",
    f"{_VERIFIED_LINE}\n{_QUESTION}",
    f"{_VERIFIED_LINE}\n{_NO_BREAK_SPACE}",
    f"{_READY_MESSAGE}{_VERIFIED_LINE}",
    f"{_ACK_LINE}\n{_READY_MESSAGE}",
    f"{_ACK_LINE}\n{_VERIFIED_LINE}",
    f"REPORT: READY\n{_REPORT}\n{_ACK_LINE}\nREPORT: END",
    # A marker line inside a code fence, whether that fence closes or not.
    f"```\nREPORT: READY\n{_REPORT}\nREPORT: END\n```",
    f"```\nREPORT: READY\n```\n{_REPORT}\nREPORT: END",
    f"~~~\nREPORT: READY\n~~~\n{_REPORT}\nREPORT: END",
    f"REPORT: READY\n{_REPORT}\n```sh\nREPORT: END",
    f"```\n{_VERIFIED_LINE}",
    # Lines that close no fence: a shorter run, the other character, a run
    # with an info string, a run trailed by a no-break space, a run deeper than
    # the opening one, and a backtick line that is inline code.
    f"````\nnotes\n```\n{_VERIFIED_LINE}",
    f"```\nnotes\n~~~\n{_VERIFIED_LINE}",
    f"```\nnotes\n``` sh\n{_VERIFIED_LINE}",
    f"```\nnotes\n```{_NO_BREAK_SPACE}\n{_VERIFIED_LINE}",
    f"```\nnotes\n    ```\n{_VERIFIED_LINE}",
    f"```a`b\n```\n{_VERIFIED_LINE}",
    # A fence opened in a list item encloses the lines that continue the item.
    # A line leaving the item ends it, so a later run opens a fence of its own
    # -- and a line holding only a no-break space is not blank, so it leaves.
    f"Read it:\n- ```text\n  {_VERIFIED_LINE}",
    f"1. ```\n   notes\n2. ```\n   {_VERIFIED_LINE}",
    f"- notes\n  ```\nsh\n  ```\n{_VERIFIED_LINE}",
    f"- ```\n{_NO_BREAK_SPACE}\n  ```\n{_VERIFIED_LINE}",
    # Four columns in, or behind a tab, a marker line may be indented code.
    f"Read it.\n\n    {_VERIFIED_LINE}",
    f"\t{_VERIFIED_LINE}",
)

# Replies that never use the contract, left for the caller's own readers.
_UNMARKED_MESSAGES = (
    _QUESTION,
    "I disagree with item 2: the flag is already covered. Should I drop it?",
    _ACK_LINE,
    "No changes needed.",
    "",
    "Report: ready below\nAdds the flag.",
    "I will end with `REPORT: READY` once the tests pass.",
    "report: ready\nAdds the flag.\nreport: end",
)

# A run that finished on its own terms, carrying a ready report.
_COMPLETED_RUN = AgentResult(
    session_id="session",
    last_message=_READY_MESSAGE,
    exit_code=0,
    timed_out=False,
    stdout="",
    stderr="",
)


def _unfinished_run(exit_code: int = 1, **shortfalls) -> AgentResult:
    """The completed run's report, from a run that exited nonzero and fell
    short in whatever other way `shortfalls` names."""
    return dataclasses.replace(_COMPLETED_RUN, exit_code=exit_code, **shortfalls)


class ReadyReportTest(unittest.TestCase):
    """The report is the text between the lines, and only that text: the
    blank lines framing it go, and the whitespace inside it stays."""

    def test_block_yields_the_text_between_lines(self) -> None:
        expected = {
            _READY_MESSAGE: _ReadyReport(_REPORT),
            "  REPORT: READY\r\nAdds the flag.\r\n  REPORT: END  \r\n\r\n": _ReadyReport(
                "Adds the flag.",
            ),
            f"REPORT: READY\n{_FENCED_COMMAND}\nREPORT: END": _ReadyReport(
                _FENCED_COMMAND,
            ),
            f"REPORT: READY\n{_LISTED_COMMAND}\nREPORT: END": _ReadyReport(
                _LISTED_COMMAND,
            ),
            f"REPORT: READY\n\n{_INDENTED_REPORT}\n \t\nREPORT: END": _ReadyReport(
                _INDENTED_REPORT,
            ),
        }
        for message, outcome in expected.items():
            with self.subTest(message=message):
                self.assertEqual(
                    report_outcomes._parse_report_outcome(message), outcome,
                )


class VerifiedReportTest(unittest.TestCase):
    """A verified report names a pull request location and a revision."""

    def test_line_yields_location_and_revision(self) -> None:
        widest_url = f"{_REPO_URL}/pull/{_WIDEST_ID}#issuecomment-{_WIDEST_ID}"
        expected = {
            f"Read it.\n\nREPORT: VERIFIED {_PULL_URL} {_REVISION}": _ReportLocation(
                _SLUG, _PULL_NUMBER,
            ),
            _VERIFIED_LINE: _ReportLocation(_SLUG, _PULL_NUMBER, _COMMENT_ID),
            f"~~~\nRead it.\n~~~~\n{_VERIFIED_LINE}": _ReportLocation(
                _SLUG, _PULL_NUMBER, _COMMENT_ID,
            ),
            # A closing run may trail spaces, tabs, and a CRLF line break.
            f"```\r\nRead it.\r\n``` \t\r\n{_VERIFIED_LINE}": _ReportLocation(
                _SLUG, _PULL_NUMBER, _COMMENT_ID,
            ),
            # A blockquote's fence ends with the first line that leaves it.
            f"> ```\n> Read it.\n{_VERIFIED_LINE}": _ReportLocation(
                _SLUG, _PULL_NUMBER, _COMMENT_ID,
            ),
            f"REPORT: VERIFIED {widest_url} {_REVISION}": _ReportLocation(
                _SLUG, int(_WIDEST_ID), int(_WIDEST_ID),
            ),
        }
        for message, location in expected.items():
            with self.subTest(message=message):
                self.assertEqual(
                    report_outcomes._parse_report_outcome(message),
                    _VerifiedReport(location, _DIGEST),
                )


class RefusedMessageTest(unittest.TestCase):
    """Anything short of exactly one outcome is refused, and the refusal says
    whether the reply used the contract at all."""

    def test_near_misses_are_malformed(self) -> None:
        for message in _MALFORMED_MESSAGES:
            with self.subTest(message=message):
                self.assertIs(
                    report_outcomes._parse_report_outcome(message),
                    _ReportRefusal.MALFORMED,
                )

    def test_unmarked_replies_carry_no_marker(self) -> None:
        for message in _UNMARKED_MESSAGES:
            with self.subTest(message=message):
                self.assertIs(
                    report_outcomes._parse_report_outcome(message),
                    _ReportRefusal.NO_MARKER,
                )

    def test_ack_and_report_never_share_a_reply(self) -> None:
        self.assertIsNotNone(messages._drift_ack_reason(_ACK_LINE))
        for message in (_READY_MESSAGE, _VERIFIED_LINE):
            with self.subTest(message=message):
                self.assertIsNone(messages._drift_ack_reason(message))


class CompletedRunTest(unittest.TestCase):
    """Only a run that completed on its own terms has its message read."""

    def test_a_completed_run_yields_its_outcome(self) -> None:
        self.assertEqual(
            report_outcomes._report_outcome_of_run(_COMPLETED_RUN),
            _ReadyReport(_REPORT),
        )

    def test_unfinished_run_is_refused_unread(self) -> None:
        # Each run still carries a well-formed report, and each earlier
        # shortfall wins over the ones listed after it.
        unfinished = (
            (_ReportRefusal.NOT_INVOKED, _unfinished_run(invoked=False)),
            (
                _ReportRefusal.INTERRUPTED,
                _unfinished_run(_INTERRUPTED_EXIT, interrupted=True, timed_out=True),
            ),
            (_ReportRefusal.TIMED_OUT, _unfinished_run(timed_out=True)),
            (
                _ReportRefusal.PROVIDER_FAILURE,
                _unfinished_run(
                    last_message=f"{PROVIDER_OVERLOAD_MESSAGE}\n{_READY_MESSAGE}",
                ),
            ),
            (_ReportRefusal.NONZERO_EXIT, _unfinished_run()),
        )
        for refusal, run in unfinished:
            with self.subTest(refusal=refusal):
                self.assertIs(report_outcomes._report_outcome_of_run(run), refusal)


if __name__ == "__main__":
    unittest.main()
