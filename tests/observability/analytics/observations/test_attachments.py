# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The task snapshot attachment a reply split at its report outcome reads as.

One line above the outcome, of the current kind and version over its one
field, is the snapshot; every other shape is a named problem carrying the
line it was read off, and nothing is guessed: two lines are a duplicate, a
line at or past the outcome is misplaced, a line past the attachment limit
is refused before it is decoded, and a reply beside an outcome with no line
at all is missing one. A reply with no outcome was asked for nothing.
"""
from __future__ import annotations

import json
import unittest

from orchestrator.observability.analytics.observations import attachments
from tests.observability.analytics.observations import observation_test_support as _support

_PROBLEM = attachments.Problem
_READING = attachments.SnapshotReading
_FOUND = attachments.AttachmentProblem

_DESCRIPTION = _support.DESCRIPTION
_OUTCOME = _support.OUTCOME
_PREFIX = "ANALYTICS: task-snapshot v1"
_PLACEHOLDER = "<one or two sentences>"
_ANY = "x"

# Deeper than the JSON decoder recurses through, within the attachment limit.
_DEPTH = 3000

_BRACKETS = "[" * _DEPTH

_NESTED = f'{_PREFIX} {{"description": {_BRACKETS}}}'

# Lines that are no snapshot, and what each one is.
_REFUSED = (
    ("ANALYTICS:", _PROBLEM.MALFORMED),
    (_PREFIX, _PROBLEM.MALFORMED),
    ("ANALYTICS: task-snapshot v1 {not json", _PROBLEM.MALFORMED),
    (f"{_PREFIX} {json.dumps(['a list'])}", _PROBLEM.MALFORMED),
    ("ANALYTICS: task-snapshot v1 {}", _PROBLEM.MALFORMED),
    (f"{_PREFIX} {json.dumps({'description': _ANY, 'score': _ANY})}", _PROBLEM.MALFORMED),
    (f"{_PREFIX} {json.dumps({'description': None})}", _PROBLEM.MALFORMED),
    (_support.snapshot_line(" \n "), _PROBLEM.MALFORMED),
    (_NESTED, _PROBLEM.MALFORMED),
    (_support.snapshot_line(_ANY).replace(" v1 ", " v2 "), _PROBLEM.UNSUPPORTED),
    (_support.snapshot_line(_ANY).replace(" v1 ", " v01 "), _PROBLEM.UNSUPPORTED),
    (_support.snapshot_line(_ANY).replace("task-snapshot", "review-finding"), _PROBLEM.UNSUPPORTED),
)


def _read(preamble: str, outcome: str = _OUTCOME) -> attachments.SnapshotReading:
    return attachments.read_task_snapshot(preamble, outcome)


def _padded(length: int) -> str:
    """A snapshot line exactly `length` characters long."""
    stem = len(_support.snapshot_line(""))
    return _support.snapshot_line("d" * (length - stem))


class SnapshotReadingTest(unittest.TestCase):
    """A reply's attachment, read or refused."""

    def test_one_line_above_the_outcome_reads(self) -> None:
        # Indented or not, among prose, a line break inside the description
        # escaped by its JSON: one string, decoded whole.
        line = _support.snapshot_line()
        cases = (
            (f"Done.\n\n{line}\n\n", _DESCRIPTION),
            (f"   {line}\r\n", _DESCRIPTION),
            (f"{_support.snapshot_line('two\nlines')}\n", "two\nlines"),
        )
        for preamble, description in cases:
            with self.subTest(preamble=preamble):
                self.assertEqual(_read(preamble), _READING(description, (), 1))

    def test_the_taught_template_reads_back(self) -> None:
        filled = attachments.TASK_SNAPSHOT_TEMPLATE.replace(_PLACEHOLDER, _DESCRIPTION)
        self.assertEqual(_read(f"{filled}\n").description, _DESCRIPTION)

    def test_a_refused_line_names_its_problem(self) -> None:
        for line, problem in _REFUSED:
            with self.subTest(line=line[:60]):
                expected = _READING(None, (_FOUND(problem, line),), 1)
                self.assertEqual(_read(f"prose\n{line}\n"), expected)

    def test_the_attachment_limit_bounds_the_line(self) -> None:
        # At the limit the line is read; one character past it, it is refused
        # whole, its JSON never decoded.
        at_limit = _padded(attachments.ATTACHMENT_CHARS)
        past_limit = _padded(attachments.ATTACHMENT_CHARS + 1)
        self.assertEqual(len(at_limit), attachments.ATTACHMENT_CHARS)
        self.assertEqual(_read(at_limit).problems, ())
        oversized = (_FOUND(_PROBLEM.OVERSIZED, past_limit),)
        self.assertEqual(_read(past_limit).problems, oversized)

    def test_two_lines_above_the_outcome_conflict(self) -> None:
        # Even where one of them reads, which one was meant is a guess.
        both = f"{_support.snapshot_line('first')}\n{_support.snapshot_line('second')}"
        expected = _READING(None, (_FOUND(_PROBLEM.DUPLICATE, both),), 2)
        self.assertEqual(_read(f"{both}\n"), expected)

    def test_a_line_past_the_outcome_is_misplaced(self) -> None:
        # Inside the report block or after the outcome, the line is in what
        # the workflow publishes or past what ends the reply: never read, and
        # never mistaken for a missing one -- while a placed line still is.
        line = _support.snapshot_line()
        misplaced = (_FOUND(_PROBLEM.MISPLACED, line),)
        after = f"{_OUTCOME}{line}\n"
        for outcome in (f"REPORT: READY\n{line}\nREPORT: END\n", after):
            with self.subTest(outcome=outcome):
                self.assertEqual(_read("Done.\n", outcome), _READING(None, misplaced, 1))
        self.assertEqual(_read(f"{line}\n", after), _READING(_DESCRIPTION, misplaced, 2))

    def test_none_is_missing_only_beside_an_outcome(self) -> None:
        missing = _READING(None, (_FOUND(_PROBLEM.MISSING),), 0)
        self.assertEqual(_read("Done.\n"), missing)
        self.assertEqual(_read("A question for you?", ""), _READING(None, (), 0))
        asked = f"Question?\n{_support.snapshot_line()}"
        self.assertEqual(_read(asked, "").description, _DESCRIPTION)


if __name__ == "__main__":
    unittest.main()
