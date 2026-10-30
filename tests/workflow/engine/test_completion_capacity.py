# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How much a capture may hold, measured as the comment would carry it, and what its refusal leaves alone.

A report is refused for its own reading -- a quoted receipt marker, a text
past its ceiling -- before anything is measured, and for room only as the
comment GitHub would be sent renders, escaped. A capture is taken only where
its transfer into the delivery still fits beside the binding and settlement
that delivery reserves, so a capture at the very edge is always one that can
be handed on, and the comment carries the report once on either side of the
handoff. A refused capture writes nothing, so the run's usage accounting --
its own checkpoint -- lands or not on its own, and where neither fits both are
refused rather than either claimed.
"""
from __future__ import annotations

import json
import unittest

from orchestrator.github.comments import RECEIPT_MARKER_PREFIX
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import (
    completion_handoff as _handoff,
    completion_spelling as _spelling,
    issue_usage as _issue_usage,
    report_record_room as _room,
    usage_checkpoint as _usage_checkpoint,
)
from orchestrator.workflow.engine.pinned_commit_models import CommitRefusal
from orchestrator.workflow.engine.report_record_values import MAX_REPORT_TEXT, RecordRefusal
from tests.workflow.engine import completion_test_support as support

_STATUS = support.STATUS
_FILLER = "operator_note"

# A report short in codepoints and long once the comment's JSON escapes it:
# each of these is a surrogate pair, twelve characters of the body.
_WIDE = "\U0001f600"
_WIDE_REPORT = _WIDE * (MAX_REPORT_TEXT // 8)

# A report the comment carries in full only with each of its terminators
# escaped, five characters more an occurrence: unescaped, it fits.
_TERMINATOR = "-->"
_TERMINATED_REPORT = _TERMINATOR * (MAX_REPORT_TEXT // 4)

# How close to the ceiling a comment is filled where nothing more fits.
_CROWDED = 16

# The captured report as the comment's JSON spells it.
_SPELLED_REPORT = json.dumps(support.REPORT)[1:-1]

# Reports refused for their own reading, and what each is refused as.
_OWN_READING = (
    (f"Quoted {RECEIPT_MARKER_PREFIX}state here.", RecordRefusal.RESERVED_RECEIPT),
    ("x" * (MAX_REPORT_TEXT + 1), RecordRefusal.REPORT_TOO_LONG),
)


def _ready(report: str) -> str:
    """A completed run's message handing `report` over READY."""
    return f"REPORT: READY\n{report}\nREPORT: END"


def _filled(width: int) -> support.CompletionWorld:
    """An issue whose comment carries a note `width` characters long beside its record."""
    return support.seeded(**{_FILLER: "x" * width})


def _filled_to(body: int) -> support.CompletionWorld:
    """An issue whose comment renders to `body` characters before anything is captured."""
    bare = len(pinned_state_body(_filled(0).record()))
    return _filled(body - bare)


def _lands(width: int) -> bool:
    """Whether a capture lands on a comment carrying a note `width` characters long."""
    world = _filled(width)
    return world.captures(world.completion()).status is _STATUS.LANDED


def _widest_note() -> int:
    """The longest note beside which a capture still lands, found by halving the range."""
    landing, refused = 0, MAX_PINNED_BODY
    while refused - landing > 1:
        middle = (landing + refused) // 2
        if _lands(middle):
            landing = middle
        else:
            refused = middle
    return landing


class CaptureRoomTest(unittest.TestCase):
    """What a capture is refused for, and where its edge is."""

    def accounted(self, world: support.CompletionWorld) -> _usage_checkpoint.AccountingStatus:
        """What accounting the usage of the run captured under charge 1 comes to."""
        returned = support.returned(world.invocation())
        return _usage_checkpoint.checkpoint(world.github, world.issue, world.state, returned).status

    def report_copies(self, world: support.CompletionWorld) -> int:
        """How many times the comment, as rendered, spells the captured report."""
        rendered = pinned_state_body(world.record())
        return rendered.count(_SPELLED_REPORT)

    def test_a_report_is_refused_for_its_own_reading(self) -> None:
        """A quoted receipt marker and a report past its ceiling are the report's refusals, writing nothing."""
        for report, refusal in _OWN_READING:
            world = support.seeded()
            before = world.snapshot()
            outcome = world.captures(world.completion(message=_ready(report)))
            with self.subTest(refusal=refusal):
                self.assertEqual((outcome.refusal, world.snapshot()), (refusal, before))

    def test_a_report_is_measured_as_spelled(self) -> None:
        """A report well inside its ceiling in codepoints is refused for the room its escaped spelling takes."""
        world = support.seeded()
        before = world.snapshot()
        outcome = world.captures(world.completion(message=_ready(_WIDE_REPORT)))
        refusal = outcome.refusal
        self.assertIsInstance(refusal, _room.CommentOverflow)
        self.assertEqual(
            (refusal.write, refusal.size > refusal.limit, world.snapshot()),
            (_room.MeasuredWrite.RECORD, True, before),
        )

    def test_a_report_is_measured_escaped_in_full(self) -> None:
        """A report that fits only as the writer would fall back to rendering it unescaped is refused for room.

        Nothing is written, and the run's usage is still accounted on the same
        comment.
        """
        world = support.seeded()
        completion = world.completion(message=_ready(_TERMINATED_REPORT))
        candidate = {**world.record(), support.FIELD: _spelling.spelled(completion)}
        refusal = world.captures(completion).refusal
        accounted = self.accounted(world)
        self.assertLessEqual(len(pinned_state_body(candidate)), MAX_PINNED_BODY)
        self.assertIsInstance(refusal, _room.CommentOverflow)
        self.assertIs(refusal.write, _room.MeasuredWrite.RECORD)
        self.assertGreater(refusal.size, refusal.limit)
        self.assertIs(accounted, _usage_checkpoint.AccountingStatus.ACCOUNTED)
        self.assertNotIn(support.FIELD, world.record())

    def test_a_capture_at_its_edge_is_handed_on(self) -> None:
        """At the widest comment a capture lands on, its transfer lands too, and the report is held once."""
        world = _filled(_widest_note())
        completion = world.completion()
        captured = world.captures(completion)
        copies = self.report_copies(world)
        transferred = world.asks(_handoff.transfer, completion.invocation)
        self.assertEqual(
            (captured.status, copies, transferred.status, self.report_copies(world)),
            (_STATUS.LANDED, 1, _STATUS.LANDED, 1),
        )

    def test_past_its_edge_the_transfer_refuses(self) -> None:
        """One character past that edge, the capture still fits; the transfer it reserves does not."""
        world = _filled(_widest_note() + 1)
        completion = world.completion()
        candidate = {**world.record(), support.FIELD: _spelling.spelled(completion)}
        before = world.snapshot()
        refusal = world.captures(completion).refusal
        self.assertLess(len(pinned_state_body(candidate)), MAX_PINNED_BODY)
        self.assertIsInstance(refusal, _room.CommentOverflow)
        self.assertEqual(world.snapshot(), before)
        self.assertFalse(world.state.withheld, "a comment simply too full leaves its caller writable")


class IndependentAccountingTest(unittest.TestCase):
    """A capture refused for room leaves the run's usage accounting to its own checkpoint."""

    def accounts(self, world: support.CompletionWorld) -> _usage_checkpoint.AccountingOutcome:
        """Account the usage of the run captured under charge 1."""
        returned = support.returned(world.invocation())
        return _usage_checkpoint.checkpoint(world.github, world.issue, world.state, returned)

    def refused_beside(self, *, accounted_first: bool) -> tuple:
        """A capture refused for its transfer's room, the run accounted before or after it.

        Answers both statuses, the runs the record counts, and whether it
        carries any capture.
        """
        world = _filled(_widest_note() + 1)
        first = self.accounts(world) if accounted_first else None
        refused = world.captures(world.completion())
        accounted = first or self.accounts(world)
        record = world.record()
        return (
            refused.status,
            accounted.status,
            record.get(_issue_usage.AGENT_RUNS),
            support.FIELD in record,
        )

    def test_accounting_lands_beside_a_refusal(self) -> None:
        """Before or after the capture's refusal, the run's usage is accounted once on the same comment."""
        for accounted_first in (False, True):
            with self.subTest(accounted_first=accounted_first):
                self.assertEqual(
                    self.refused_beside(accounted_first=accounted_first),
                    (_STATUS.REFUSED, _usage_checkpoint.AccountingStatus.ACCOUNTED, 1, False),
                )

    def test_where_neither_fits_both_are_refused(self) -> None:
        """A comment with no room for either refuses the capture and the accounting, writing and claiming nothing."""
        world = _filled_to(MAX_PINNED_BODY - _CROWDED)
        before = world.snapshot()
        captured = world.captures(world.completion())
        accounted = self.accounts(world)
        self.assertIsInstance(captured.refusal, _room.CommentOverflow)
        self.assertEqual(
            (accounted.status, accounted.refusal, world.snapshot()),
            (_usage_checkpoint.AccountingStatus.REFUSED, CommitRefusal.OVERFLOW, before),
        )


if __name__ == "__main__":
    unittest.main()
