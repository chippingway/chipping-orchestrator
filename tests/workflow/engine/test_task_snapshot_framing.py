# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where an attachment line sits beside a reply's outcome, and the verdict the workflow and the recorder both reach.

The recorder is told where the reply as written opens its outcome, which of
its lines a fence may enclose, and the verdict the report reader reaches on
the reply the workflow reads. A line past the outcome is held by the
placeholder, so the reply is still refused and no notice quotes the line. A
fenced example is code the report quotes and stays in it, beside the
snapshot read above, and a marker line a fence encloses is an example
rather than where the outcome begins. A line a fence encloses is never
taken out, so it can never close the fence before the markers and make a
refused report publishable; and a READY block holding nothing else is the
empty block the reader refuses -- the verdict the recorder is told too.
"""
from __future__ import annotations

import unittest

from orchestrator.observability.analytics.observations import attachments, recorder as _recorder
from orchestrator.workflow.engine import (
    report_fences as _fences,
    report_outcome_models as _report_models,
    report_outcomes as _outcomes,
    task_snapshot_replies as _replies,
)
from tests.observability.analytics.observations.observation_test_support import snapshot_line

_LINE = snapshot_line("Add a foo flag so users can turn foo on.")

_READY_REPLY = "Done.\n\nREPORT: READY\nAdds the foo flag.\nREPORT: END\n"

_MALFORMED = "malformed"

_VERIFIED_REPLY = (
    "REPORT: VERIFIED https://github.com/owner/repo/pull/7 "
    "sha256:abababababababababababababababababababababababababababababababab\n"
)

# Replies, and what the report reader reads each one's outcome as.
_FRAMED = (
    (_READY_REPLY, "ready"),
    (_VERIFIED_REPLY, "verified"),
    (f"{_READY_REPLY}One more thing.\n", _MALFORMED),
    ("Should the flag default to on?", "no_marker"),
)

# A report quoting an attachment line as code, which a fence encloses.
_QUOTING = f"Updated the example.\n\n```text\n{snapshot_line('An example the report quotes.')}\n```"


def _category(reply: str) -> attachments.Problem:
    """The one problem `reply`'s snapshot reads as, framed as the workflow frames it."""
    framing = _replies.framing(reply)
    reading = attachments.read_task_snapshot(reply, framing.outcome_at, framing.fenced)
    return reading.problems[0].category


class ReportFramingTest(unittest.TestCase):
    """Where a line sits beside the outcome, and the verdict the workflow and the recorder both reach."""

    def test_the_recorder_gets_the_readers_framing(self) -> None:
        for reply, outcome in _FRAMED:
            with self.subTest(outcome=outcome):
                fenced = _fences._fenced_line_starts(reply)
                expected = _recorder.Framing(_replies._outcome_start(reply, fenced), outcome, fenced)
                self.assertEqual(_replies.framing(reply), expected)

    def test_text_after_an_outcome_stays_refused(self) -> None:
        # Held at its own indentation and before its own break.
        trailing = f"{_READY_REPLY}  {_LINE}\r\n"
        workflow_reply = _replies.workflow_reply(trailing)
        self.assertEqual(workflow_reply, f"{_READY_REPLY}  {_replies.PLACEHOLDER}\r\n")
        self.assertIs(_outcomes._parse_report_outcome(workflow_reply), _report_models._ReportRefusal.MALFORMED)
        self.assertIs(_category(trailing), attachments.Problem.MISPLACED)

    def test_a_fenced_example_stays_in_the_report(self) -> None:
        reply = f"{_LINE}\n\nREPORT: READY\n{_QUOTING}\nREPORT: END"
        self.assertEqual(_outcomes._parse_report_outcome(_replies.workflow_reply(reply)).report, _QUOTING)
        framing = _replies.framing(reply)
        reading = attachments.read_task_snapshot(reply, framing.outcome_at, framing.fenced)
        self.assertEqual((reading.found, reading.problems), (1, ()))

    def test_a_fenced_marker_is_no_outcome(self) -> None:
        # A report example the reply quotes above the snapshot leaves the
        # outcome malformed, never the snapshot misplaced: the outcome begins
        # at the first marker line no fence may enclose.
        reply = f"The format reads:\n```text\nREPORT: READY\n```\n{_LINE}\n{_READY_REPLY}"
        framing = _replies.framing(reply)
        self.assertEqual(framing.outcome_at, reply.rindex("REPORT: READY"))
        self.assertEqual(framing.report_outcome, _MALFORMED)
        reading = attachments.read_task_snapshot(reply, framing.outcome_at, framing.fenced)
        self.assertEqual(reading.description, "Add a foo flag so users can turn foo on.")

    def test_no_line_moves_a_fence(self) -> None:
        # Taken out, the line would let the fence close above the markers,
        # which the reader reads as fenced; a fence may enclose it, so it stays.
        reply = f"- ```text\n{_LINE}\n  ```\nREPORT: READY\nImplemented.\nREPORT: END"
        self.assertEqual(_replies.workflow_reply(reply), reply)
        self.assertEqual(_replies.framing(reply).report_outcome, _MALFORMED)
        self.assertIs(_category(reply), attachments.Problem.MISSING)

    def test_a_block_of_nothing_else_is_refused(self) -> None:
        reply = f"REPORT: READY\n{_LINE}\nREPORT: END"
        workflow_reply = _replies.workflow_reply(reply)
        self.assertIs(_outcomes._parse_report_outcome(workflow_reply), _report_models._ReportRefusal.MALFORMED)
        self.assertEqual(_replies.framing(reply).report_outcome, _MALFORMED)
        self.assertIs(_category(reply), attachments.Problem.MISPLACED)


if __name__ == "__main__":
    unittest.main()
