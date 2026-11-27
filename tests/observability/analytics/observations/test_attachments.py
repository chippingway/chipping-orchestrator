# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The task snapshot attachment a reply reads as, beside where its report outcome begins.

One line ending before the outcome, of the current kind and version over
its one field written once, is the snapshot; every other shape is one named
problem carrying where its lines sit, and nothing is guessed: no line is
missing, two anywhere are a duplicate, the one line reaching past where the
outcome begins is misplaced, a line past the attachment limit is refused
before it is decoded, and a key written twice is malformed. The reply is read as written, and a line a
code fence may enclose is no attachment line at all.
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

# The published attachment limit, written out rather than read off the
# reader, so a limit that moves fails here instead of moving the boundary.
_ATTACHMENT_CHARS = 4000

# Deeper than the JSON decoder recurses through, within the attachment limit.
_DEPTH = 3000

_BRACKETS = "[" * _DEPTH

_NESTED = f'{_PREFIX} {{"description": {_BRACKETS}}}'

# Lines that are no snapshot, and what each one is: a carriage return inside a
# line, before a second header included, leaves the whole line to be read.
_REFUSED = (
    ("ANALYTICS:", _PROBLEM.MALFORMED),
    (_PREFIX, _PROBLEM.MALFORMED),
    ("ANALYTICS: task-snapshot v1 {not json", _PROBLEM.MALFORMED),
    (f"{_PREFIX} {json.dumps(['a list'])}", _PROBLEM.MALFORMED),
    ("ANALYTICS: task-snapshot v1 {}", _PROBLEM.MALFORMED),
    (f"{_PREFIX} {json.dumps({'description': _ANY, 'score': _ANY})}", _PROBLEM.MALFORMED),
    ('ANALYTICS: task-snapshot v1 {"description": "First", "description": "Second"}', _PROBLEM.MALFORMED),
    (f"{_PREFIX} {json.dumps({'description': None})}", _PROBLEM.MALFORMED),
    (f"{_PREFIX} {json.dumps({'summary': _ANY})}", _PROBLEM.MALFORMED),
    (r'ANALYTICS: task-snapshot v1 {"description": "an \q escape JSON has no spelling for"}', _PROBLEM.MALFORMED),
    (f"{_support.snapshot_line('first')}\r{_support.snapshot_line('second')}", _PROBLEM.MALFORMED),
    (_support.snapshot_line(" \n "), _PROBLEM.MALFORMED),
    (_NESTED, _PROBLEM.MALFORMED),
    (_support.snapshot_line(_ANY).replace(" v1 ", " v2 "), _PROBLEM.UNSUPPORTED),
    (_support.snapshot_line(_ANY).replace(" v1 ", " v01 "), _PROBLEM.UNSUPPORTED),
    (_support.snapshot_line(_ANY).replace("task-snapshot", "review-finding"), _PROBLEM.UNSUPPORTED),
)


# Snapshot lines among prose, and what each one reads as: indented or not, a
# line break inside the description escaped by its JSON -- one string, decoded
# whole -- in a reply with no outcome, anywhere, and with a carriage return,
# whitespace to JSON, between its tokens.
_LINE = _support.snapshot_line()
_READS = (
    (f"Done.\n\n{_LINE}\n\n", _OUTCOME, _DESCRIPTION),
    (f"   {_LINE}\r\n", _OUTCOME, _DESCRIPTION),
    (f"{_support.snapshot_line('two\nlines')}\n", _OUTCOME, "two\nlines"),
    (f"Should the flag default to on?\n{_LINE}", "", _DESCRIPTION),
    ('ANALYTICS: task-snapshot v1 {"description":\r"Read this."}\n', _OUTCOME, "Read this."),
)

# Replies whose one line reaches past where the outcome begins, and where it
# begins: the line inside the report block, after the outcome, and across it.
_DONE = "Done.\n"
_MISPLACED = (
    (f"{_DONE}REPORT: READY\n{_LINE}\nREPORT: END\n", len(_DONE)),
    (f"{_DONE}{_OUTCOME}{_LINE}\n", len(_DONE)),
    (_LINE, _LINE.index(_DESCRIPTION)),
)

# Two attachment lines, and the two ways a reply carries both.
_FIRST = _support.snapshot_line("first")
_SECOND = _support.snapshot_line("second")
_DUPLICATES = (
    (f"{_FIRST}\n{_SECOND}\n", _OUTCOME),
    (f"{_FIRST}\n", f"REPORT: READY\n{_SECOND}\nREPORT: END\n"),
)


def _read(preamble: str, outcome: str = _OUTCOME) -> attachments.SnapshotReading:
    """`preamble` then `outcome`, read with the outcome beginning where `outcome` does."""
    return attachments.read_task_snapshot(f"{preamble}{outcome}", len(preamble))


def _at(message: str, *lines: str) -> tuple[tuple[int, int], ...]:
    """Where each of `lines` sits in `message`, in order."""
    spans = []
    cursor = 0
    for line in lines:
        start = message.index(line, cursor)
        cursor = start + len(line)
        spans.append((start, cursor))
    return tuple(spans)


def _spelled(message: str, reading: attachments.SnapshotReading) -> str:
    """What the stretch of `message` the reading says its description is written in decodes to."""
    start, end = reading.written_at
    written = message[start:end]
    return json.loads(f'"{written}"')


def _padded(length: int) -> str:
    """A snapshot line exactly `length` characters long."""
    stem = len(_support.snapshot_line(""))
    return _support.snapshot_line("d" * (length - stem))


class SnapshotReadingTest(unittest.TestCase):
    """A reply's attachment, read or refused."""

    def test_one_line_above_the_outcome_reads(self) -> None:
        # The reading also says where the description is written, as the
        # spelling it was decoded from.
        for preamble, outcome, description in _READS:
            with self.subTest(preamble=preamble):
                read = _read(preamble, outcome)
                self.assertEqual(read, _READING(description, (), 1, read.written_at))
                self.assertEqual(_spelled(preamble, read), description)

    def test_the_taught_template_reads_back(self) -> None:
        filled = attachments.TASK_SNAPSHOT_TEMPLATE.replace(_PLACEHOLDER, _DESCRIPTION)
        self.assertEqual(_read(f"{filled}\n").description, _DESCRIPTION)

    def test_a_refused_line_names_its_problem(self) -> None:
        for line, problem in _REFUSED:
            preamble = f"prose\n{line}\n"
            with self.subTest(line=line[:60]):
                expected = _READING(None, (_FOUND(problem, _at(preamble, line)),), 1)
                self.assertEqual(_read(preamble), expected)

    def test_the_attachment_limit_bounds_the_line(self) -> None:
        # At the limit the line is read; one character past it, it is refused
        # whole, its JSON never decoded. The carriage return of a CRLF is its
        # line break's, and any other one the line's own, counted with it.
        at_limit = _padded(_ATTACHMENT_CHARS)
        past_limit = _padded(_ATTACHMENT_CHARS + 1)
        self.assertEqual(len(at_limit), _ATTACHMENT_CHARS)
        self.assertEqual(_read(f"{at_limit}\n").problems, ())
        self.assertEqual(_read(f"{at_limit}\r\n").problems, ())
        oversized = (_FOUND(_PROBLEM.OVERSIZED, _at(past_limit, past_limit)),)
        self.assertEqual(_read(f"{past_limit}\n").problems, oversized)
        carried = f"{at_limit}\r"
        carried_past = (_FOUND(_PROBLEM.OVERSIZED, _at(carried, carried)),)
        self.assertEqual(_read(f"{carried}\r\n").problems, carried_past)

    def test_two_lines_anywhere_conflict(self) -> None:
        # Above the outcome or across it, even where one of them reads: which
        # one was meant is a guess, so neither is read.
        for preamble, outcome in _DUPLICATES:
            spans = _at(f"{preamble}{outcome}", _FIRST, _SECOND)
            expected = _READING(None, (_FOUND(_PROBLEM.DUPLICATE, spans),), 2)
            with self.subTest(outcome=outcome):
                self.assertEqual(_read(preamble, outcome), expected)

    def test_a_line_past_the_outcome_is_misplaced(self) -> None:
        # Inside the report block or after the outcome, the line is in what
        # the workflow publishes or past what ends the reply: never read. So
        # is a line the outcome begins inside of: it has to end before.
        for message, outcome_at in _MISPLACED:
            found = (_FOUND(_PROBLEM.MISPLACED, _at(message, _LINE)),)
            read = attachments.read_task_snapshot(message, outcome_at)
            with self.subTest(message=message):
                self.assertEqual(read, _READING(None, found, 1))

    def test_no_line_is_missing_whatever_the_reply(self) -> None:
        missing = _READING(None, (_FOUND(_PROBLEM.MISSING),), 0)
        for preamble, outcome in (("Done.\n", _OUTCOME), ("A question for you?", ""), ("", "")):
            with self.subTest(preamble=preamble):
                self.assertEqual(_read(preamble, outcome), missing)


class FencedLineTest(unittest.TestCase):
    """A line a code fence may enclose is code a reply quotes, not an attachment."""

    def test_a_fenced_line_is_not_one(self) -> None:
        # Neither read nor counted.
        line = _support.snapshot_line()
        example = _support.snapshot_line("An example the report quotes.")
        message = f"{line}\n```text\n{example}\n```\n"
        fenced = frozenset((message.index(example),))
        self.assertEqual(attachments.attachment_lines(message, fenced), _at(message, line))
        read = attachments.read_task_snapshot(message, len(message), fenced)
        self.assertEqual(read, _READING(_DESCRIPTION, (), 1, read.written_at))
        self.assertEqual(_spelled(message, read), _DESCRIPTION)


if __name__ == "__main__":
    unittest.main()
