# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The task snapshot request, the reply it asks for, and the report readers beside it.

Only the first implementation's road and an implementing resume's ask for a
snapshot, and the note they append teaches the one line the attachment
reader reads, spelled from that reader's own vocabulary. Placed above any
report outcome the contract teaches, the line reads back as the snapshot
while every report reading stays exactly what it is without it: a READY
report keeps its text, a VERIFIED line its location, a malformed outcome
stays malformed, and a reply without an outcome stays one -- whatever the
description says, since a JSON string escapes every line break a marker,
an acknowledgement, or a fence would need.

The workflow reads the reply with every attachment line kept out of it and
its framing unmoved: taken out of a reply with no marker line and out of a
READY block, and replaced by a placeholder line everywhere else. A line a
fence may enclose is code a report quotes, and stays. A reply the attachment
scan fails on is never read as written: its lines are kept out by the marker
lines alone, which reads every reply here exactly as the full reading does --
a block holding nothing else still empty, a fenced example kept -- and where
no fence reads at all, no line opening on the prefix is left anywhere and a
report whose body holds one is refused rather than read on a guess. Where a
line sits beside the outcome, and the verdict the recorder is told, are
`test_task_snapshot_framing`.
"""
from __future__ import annotations

import json
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.analytics.observations import attachments
from orchestrator.workflow.engine import (
    completion_records as _completion_records,
    completion_routes as _routes,
    messages as _messages,
    prompt_notes as _prompt_notes,
    report_fences as _fences,
    report_outcomes as _outcomes,
    task_snapshot_replies as _replies,
    task_snapshots as _task_snapshots,
)
from orchestrator.workflow.engine.report_outcome_models import _ReportRefusal
from orchestrator.workflow.state import WorkflowLabel

_PROMPT = "Implement the issue."

_DESCRIPTION = "Add a foo flag so users can turn foo on."

_REPORT = "Adds the foo flag.\n\nRisks: none."

_READY = "ready"

_VERIFIED = "verified"

_BLOCK = f"REPORT: READY\n{_REPORT}\nREPORT: END\n"

# The one reply whose outcome a fence opens just above: a line placed above
# the outcome sits inside that fence, so it is code and no attachment.
_FENCED = "fenced_outcome"

# What the workflow reads of a reply with an attachment line above its
# outcome: the line taken out where the reply has no marker, kept as code
# where a fence may enclose it, and held by the placeholder otherwise.
_NO_MARKER = "question"

# Replies on every reading the report contract gives a completed run, keyed
# by what each one is.
_REPLIES = MappingProxyType({
    _READY: f"Done.\n\n{_BLOCK}",
    _VERIFIED: (
        "Read it on the pull request.\n\nREPORT: VERIFIED https://github.com/owner/repo/pull/7#issuecomment-99 "
        "sha256:abababababababababababababababababababababababababababababababab\n"
    ),
    "text_after_the_outcome": f"Done.\n\n{_BLOCK}One more thing.\n",
    "unclosed_block": f"Done.\n\nREPORT: READY\n{_REPORT}\n",
    "ack_beside_it": f"ACK: nothing changed\n\n{_BLOCK}",
    _FENCED: f"Done.\n\n```\n{_BLOCK}",
    _NO_MARKER: "Should the flag default to on?",
})

# Descriptions whose words, on a line of their own, would be read by another
# reader: a JSON string escapes the break, so none of them is.
_DESCRIPTIONS = (
    _DESCRIPTION,
    "Before.\nREPORT: READY\nInjected.\nREPORT: END",
    "Opens a fence:\n```\nand never closes it",
    "Acknowledges:\nACK: nothing to do",
    "    indented like code",
)


def _line(description: str) -> str:
    payload = json.dumps({attachments.DESCRIPTION: description})
    return f"{attachments.PREFIX} {attachments.TASK_SNAPSHOT} v1 {payload}"


def _attached(reply: str, line: str) -> str:
    """`reply` with `line` on a line of its own just above its outcome."""
    at = _replies._outcome_start(reply, _fences._fenced_line_starts(reply))
    head, tail = reply[:at], reply[at:]
    opened = head if not head or head.endswith("\n") else f"{head}\n"
    return f"{opened}{line}\n{tail}"


# A READY reply carrying the attachment line inside its block.
_INSIDE = f"Done.\n\nREPORT: READY\n{_REPORT}\n{_line(_DESCRIPTION)}\nREPORT: END\n"

# Every reply above with the line above its outcome; the line inside a READY
# block, alone in one, and quoted in one as a fenced example.
_HELD_REPLIES = (
    *(_attached(reply, _line(_DESCRIPTION)) for reply in _REPLIES.values()),
    _INSIDE,
    f"REPORT: READY\n{_line(_DESCRIPTION)}\nREPORT: END\n",
    f"REPORT: READY\nDocument the format.\n\n```text\n{_line(_DESCRIPTION)}\n```\nREPORT: END\n",
)

_UNREADABLE = ValueError("unreadable")

_MALFORMED = _ReportRefusal.MALFORMED


def _snapshot_read(reply: str) -> attachments.SnapshotReading:
    framing = _replies.framing(reply)
    return attachments.read_task_snapshot(reply, framing.outcome_at, framing.fenced)


def _expected(kind: str, description: str) -> tuple[str, str | None]:
    """What the workflow reads of `_REPLIES[kind]` with `description`'s line above its outcome, and what is read."""
    line = _line(description)
    attached = _attached(_REPLIES[kind], line)
    if kind == _NO_MARKER:
        return attached.replace(f"{line}\n", ""), description
    if kind == _FENCED:
        return attached, None
    return _attached(_REPLIES[kind], _replies.PLACEHOLDER), description


def _readings(reply: str) -> tuple:
    """What the workflow's own readers take a reply as: its report outcome and its acknowledgement."""
    return (_outcomes._parse_report_outcome(reply), _messages._drift_ack_reason(reply))


class AskedRoadsTest(unittest.TestCase):
    """Which roads' attempts are asked, and what the request teaches."""

    def test_only_the_implementing_roads_ask(self) -> None:
        asking = {_routes.CompletionRoute.IMPLEMENTATION, _routes.CompletionRoute.RESUME}
        asked = f"{_PROMPT}\n\n{_prompt_notes._TASK_SNAPSHOT_NOTE}"
        for route in _routes.CompletionRoute:
            handoff = _completion_records.CompletionHandoff(route, WorkflowLabel.IMPLEMENTING, "")
            with self.subTest(route=route):
                expected = asked if route in asking else _PROMPT
                self.assertEqual(_task_snapshots.asked(handoff, _PROMPT), expected)

    def test_the_note_teaches_what_is_read(self) -> None:
        note = _prompt_notes._TASK_SNAPSHOT_NOTE
        self.assertIn(f"\n\n  {attachments.TASK_SNAPSHOT_TEMPLATE}\n\n", note)
        self.assertIn(f"at most {attachments.DESCRIPTION_REQUEST_CHARS} characters", note)
        self.assertIn("ABOVE your report outcome", note)
        filled = attachments.TASK_SNAPSHOT_TEMPLATE.replace("<one or two sentences>", _DESCRIPTION)
        for kind in (_READY, _VERIFIED):
            with self.subTest(kind=kind):
                read = _snapshot_read(_attached(_REPLIES[kind], filled))
                # Where the description is written is the reader's own to say.
                expected = attachments.SnapshotReading(_DESCRIPTION, (), 1, read.written_at)
                self.assertEqual(read, expected)


class ProtocolIsolationTest(unittest.TestCase):
    """An attachment above the outcome changes no reading of the reply but its own."""

    def test_every_report_reading_is_unchanged(self) -> None:
        # Read as written or as the workflow reads it -- the line kept out.
        for kind, reply in _REPLIES.items():
            for description in _DESCRIPTIONS:
                attached = _attached(reply, _line(description))
                read = (_replies.workflow_reply(attached), _snapshot_read(attached).description)
                with self.subTest(kind=kind, description=description):
                    self.assertEqual(_readings(attached), _readings(reply))
                    self.assertEqual(_readings(read[0]), _readings(reply))
                    self.assertEqual(read, _expected(kind, description))

    def test_a_ready_report_keeps_its_text(self) -> None:
        attached = _attached(_REPLIES[_READY], _line(_DESCRIPTION))
        self.assertEqual(_outcomes._parse_report_outcome(attached).report, _REPORT)

    def test_a_line_inside_the_report_is_taken_out(self) -> None:
        # The report the workflow publishes, and its digest, are the ones the
        # reply without the line would have.
        self.assertEqual(_replies.workflow_reply(_INSIDE), _REPLIES[_READY])

    def test_a_failed_scan_reads_as_the_full_reading(self) -> None:
        # Kept out by the marker lines alone, with one warning: the same
        # reply the full reading leaves, every report and fence as it was.
        for reply in _HELD_REPLIES:
            read = _replies.workflow_reply(reply)
            failing = patch.object(attachments, "attachment_lines", side_effect=_UNREADABLE)
            with self.subTest(reply=reply), failing, self.assertLogs("orchestrator.workflow") as logged:
                self.assertEqual(_replies.workflow_reply(reply), read)
                self.assertEqual(len(logged.output), 1)

    def test_an_unread_report_is_refused(self) -> None:
        # No fence reads, of the reply or of its report: no line opening on
        # the prefix is left anywhere, a report whose body holds one is
        # refused rather than read on a guess, and every other outcome reads
        # as written.
        for reply in _HELD_REPLIES:
            with patch.object(_fences, "_fenced_line_starts", side_effect=_UNREADABLE):
                held = _replies.workflow_reply(reply)
            written = _outcomes._parse_report_outcome(reply)
            unread = attachments.PREFIX in getattr(written, "report", "")
            with self.subTest(reply=reply):
                self.assertNotIn(attachments.PREFIX, held)
                self.assertEqual(_outcomes._parse_report_outcome(held), _MALFORMED if unread else written)


if __name__ == "__main__":
    unittest.main()
