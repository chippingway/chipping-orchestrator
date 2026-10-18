# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A recovery hold or park whose evidence another road puts back late, or replaces behind its readings.

The guarded recovery case (`guarded_recovery_support`): issue #7's rebased
head reviewed and its run settled -- or only captured -- under the anchor, and
the finish killed short of its route, so the attempt stands. The recovery
context read off the comment is handed straight to the guarded hold or
park (`rewrite_recovery_parks.lands_a_hold`, `lands_a_park`), as a recovery
road does.

- The settled run, taken off beside a blank of the base tip under the
  record's strict edit, is put back in two steps -- the tip behind that edit,
  the run behind the reconciliation's reading: the blank the refusal read
  invalidates it whole, nothing parked. So it does a newer run settled at the
  hold's record and put back the same way, at a hold or a park, the tick
  holding no evidence at all, or the proof's own reading failing once.
- Behind a park notice that raised over a captured run, a newer run bound to
  report 3, settled right behind the reconciliation's reading, is proved on
  its own binding and invalidated before the error goes on.
- A run invalidated over report 3 and put back current behind that write --
  its history written back, its own entry left, or the readings behind
  refused -- is retired again, indexed once, and the next poll routes the
  head with nothing current.

Nothing is run again, pushed, or launched.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.workflow.engine import (
    rewrite_recovery_parks as _parks,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_readings as readings,
    settled_finish_support as settled_support,
    verification_report_fixture as _report,
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# The client step a pinned-comment edit is, and the owner's reading of the comment afresh.
_EDITS = "edit_pinned_state"
_READS = "durable_comment"

# A record a publication gate staged for the hold to land, as one holding over a reading of its own does, so the
# hold's record has an edit to send; staged for a park too, it picks out that park's record the same way.
_GATE = "late_gate_hold"

# The guarded records a case races, and how a recovery context lands each.
_PARKS = partial(_parks.lands_a_park, message="The auto rebase needs a human.", reason="auto_base_rebase_push_failed")
_LANDED_BY = (("hold", _parks.lands_a_hold), ("park", _PARKS))

# The run's records -- current, its handoff, and the history it was not yet in -- as another road puts them back,
# writing the comment back as it read before the run was invalidated.
_THE_RUN = (_records.CURRENT_EVIDENCE, _records.EVIDENCE_HANDOFF, _records.EVIDENCE_HISTORY)

# How the run is put back behind its invalidation: its records, and how many readings of the comment behind are refused.
_REVIVALS = (
    (_THE_RUN, 0),
    (_THE_RUN[:2], 0),
    (_THE_RUN, 2),
)

# Each side of a case's yes-or-no question.
_EITHER = (True, False)


def _writes(case, records: dict) -> dict:
    """Write `records` onto `case`'s comment as it stands; what they replaced."""
    state = case.gh.read_pinned_state(case.issue)
    replaced = {key: state.get(key) for key in records}
    for key, recorded in records.items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)
    return replaced


def _settles_report_three(case, head: str) -> tuple:
    """Settle report 3 of `head` over `case`'s comment as it stands, as another road would; what it replaced, and it."""
    case.state = case.gh.read_pinned_state(case.issue)
    replaced = {key: case.state.get(key) for key in _MOVED_RECORDS}
    subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)
    return replaced, subject


def _records_the_gate(issue, state, **options) -> bool:
    """Whether a pinned-comment edit is the record that lands the gate's staging, which the comment lacks."""
    over = options["over"]
    return bool(state.get(_GATE)) and not over.get(_GATE)


class _SplitsTheRestoration:
    """The client's strict edit and comment reading, the current evidence and the base tip moved around a record's edit.

    The record's edit is refused over the comment with `under` taken off --
    the tip blank, and the current evidence with it unless `under` names the
    tip alone; the tip is put back right behind that edit with the current
    evidence taken off, and that evidence put back right behind the next
    reading of the comment (`reads`). `settles`, a binding, has another road
    settle a newer run bound to it first, kept as `successor`, so that is the
    evidence moved; `unread` has the reading behind the one the evidence comes
    back behind fail once, as a request GitHub refused.
    """

    def __init__(
        self,
        case,
        under: tuple = (_records.CURRENT_EVIDENCE, readings.KEY_REWRITE_BASE),
        *,
        settles=None,
        unread: bool = False,
    ) -> None:
        self._case = case
        self._under = under
        self._settles = settles
        self._unread = unread
        self._edit = case.gh.edit_pinned_state
        self._read = _durable.durable_comment
        self._behind: dict = {}
        self.split = False
        self.successor = None

    def edits(self, issue, state, **options):
        """Answer the edit, the record's the first time with the evidence and the tip moved around it."""
        if self.split or not _records_the_gate(issue, state, **options):
            return self._edit(issue, state, **options)
        self.split = True
        if self._settles is not None:
            self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=self._settles)
        current, tip = _records.CURRENT_EVIDENCE, readings.KEY_REWRITE_BASE
        pinned = readings.pinned(self._case)
        self._behind = {key: pinned.get(key) for key in (current, tip)}
        _writes(self._case, dict.fromkeys(self._under))
        answered = self._edit(issue, state, **options)
        _writes(self._case, {tip: self._behind.pop(tip), current: None})
        return answered

    def reads(self, *read, **options):
        """The comment read afresh, the first reading behind the record's edit putting the run back right behind it."""
        if self._unread and not self._behind and self.split:
            self._unread = False
            with patch.object(self._case.gh, "read_pinned_state", side_effect=RuntimeError("GitHub refused the read")):
                return self._read(*read, **options)
        durable = self._read(*read, **options)
        if self._behind:
            _writes(self._case, self._behind)
            self._behind = {}
        return durable


class _SettlesBehindTheReading:
    """The park's notice raising, and a newer run settled right behind the next reading of the comment.

    Another road settles report 3, a newer run bound to it in place of the
    captured `run`, kept as `successor`, and puts report 2 back.
    """

    def __init__(self, case, head: str, run) -> None:
        self._case = case
        self._head = head
        self._run = run
        self._read = _durable.durable_comment
        self._raised = False
        self.successor = None

    def raises(self, *_posted, **_options):
        """The notice's post, raising as GitHub not answering it."""
        self._raised = True
        raise RuntimeError("GitHub did not answer the notice's post")

    def reads(self, *read, **options):
        """The comment read afresh, the first reading behind the raise having the newer run settled right behind it."""
        durable = self._read(*read, **options)
        if self._raised:
            self._raised = False
            replaced, subject = _settles_report_three(self._case, self._head)
            binding = self._run.binding
            bound = replace(binding, target=replace(binding.target, subject=subject.recorded()))
            self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=bound)
            _writes(self._case, replaced)
        return durable


class _RevivesTheRun:
    """The client's strict edit, report 3 settled under a record's edit, and the run revived behind its invalidation.

    Report 3 settles right ahead of the record's edit, which is refused over
    it, and report 2 is put back right behind; the run's `records` are put
    back as they stood -- current, with its handoff, and the history unless
    `records` leaves it out -- right behind the edit that invalidates it, and
    the next `unread` readings of the comment behind that refused (`reads`).
    """

    def __init__(self, case, head: str, records: tuple = _THE_RUN, *, unread: int = 0) -> None:
        self._case = case
        self._head = head
        self._edit = case.gh.edit_pinned_state
        self._read = case.gh.read_pinned_state
        self._run = {key: readings.pinned(case).get(key) for key in records}
        self._moved = False
        self._unread = unread
        self.revived = False

    def __call__(self, issue, state, **options):
        """Answer the edit around the moves this race makes at it."""
        if not self._moved and _records_the_gate(issue, state, **options):
            self._moved = True
            replaced = _settles_report_three(self._case, self._head)[0]
            answered = self._edit(issue, state, **options)
            _writes(self._case, replaced)
            return answered
        answered = self._edit(issue, state, **options)
        current = _records.CURRENT_EVIDENCE
        invalidates = options["over"].get(current) and not state.get(current)
        if invalidates and not self.revived:
            _writes(self._case, self._run)
            self.revived = True
        return answered

    def reads(self, issue):
        """The client's reading of the comment, the first `unread` behind the revival refused by GitHub."""
        if self.revived and self._unread:
            self._unread -= 1
            raise RuntimeError("GitHub refused the read behind the invalidation")
        return self._read(issue)


class LateRestorationTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """Evidence put back late, or replaced behind a reading, revives nothing a guarded record read moving."""

    def test_a_split_restoration_keeps_the_move(self) -> None:
        # The run and the tip go under a hold's or a park's record, refused
        # over them, and come back in two steps -- the tip right behind that
        # edit, the run right behind the reconciliation's reading: the blank
        # the refusal read invalidates the run whole, with nothing parked.
        for name, lands in _LANDED_BY:
            with self.subTest(record=name):
                self.setUp()
                run = self.settles_then_dies()[1]
                context = guarded.recovery_context(self)
                context.state.set(_GATE, run.receipt)
                splits = _SplitsTheRestoration(self)
                with (
                    patch.object(self.gh, _EDITS, splits.edits),
                    patch.object(_durable, _READS, splits.reads),
                ):
                    lands(context)

                self.assertTrue(splits.split)
                self.assertFalse(self.pinned_fields(guarded.AWAITING)[0])
                self.assert_invalidated(run)

    def test_a_successor_restored_late_is_retired(self) -> None:
        # Another road settles a newer run under its own receipt right at a
        # hold's or a park's record, read there beside a blank of the base tip
        # and refused over them; the tip comes back with the newer run taken
        # off right behind that edit, and the newer run comes back right behind
        # the reconciliation's reading: the movement read under its receipt
        # invalidates it, with nothing current or parked -- the tick holding
        # the run it superseded, or no evidence at all, that run retired before
        # the tick read the comment.
        for held, unread, (name, lands) in product(_EITHER, _EITHER, _LANDED_BY):
            with self.subTest(held=held, unread=unread, record=name):
                self.setUp()
                run = self.settles_then_dies()[1]
                if not held:
                    _writes(self, {_records.CURRENT_EVIDENCE: None})
                self._lands_under_a_split(lands, run, unread=unread)

    def test_a_late_successor_is_proved(self) -> None:
        # The park's notice raises over a captured run, and a newer run bound
        # to report 3 is settled right behind the reconciliation's reading,
        # report 2 put back: it is invalidated whole before the error goes on.
        head, run = self.captures()
        settles = _SettlesBehindTheReading(self, head, run)
        context = guarded.recovery_context(self)
        with (
            patch.object(self.gh, "comment", settles.raises),
            patch.object(_durable, _READS, settles.reads),
        ):
            self.assertRaises(RuntimeError, _PARKS, context)

        self.assertEqual(readings.pinned_records(self)[:2], (None, None))
        retired = readings.pinned_records(self)[2]
        self.assertEqual(retired[-1], (settles.successor.receipt, readings.INVALIDATED))
        self.assertFalse(self.pinned_fields(guarded.AWAITING)[0])

    def test_a_revived_run_is_retired_again(self) -> None:
        # Report 3 moves under the hold's record, so the run is invalidated,
        # and the run is put back current right behind that invalidation --
        # its history written back, or the invalidation's entry left standing:
        # it is retired again, indexed once with its revision and binding,
        # and the next poll routes the head with nothing current -- also where
        # the two readings of the comment behind that invalidation are refused.
        for records, unread in _REVIVALS:
            with self.subTest(history=_records.EVIDENCE_HISTORY in records, unread=unread):
                self.setUp()
                head, run = self.settles_then_dies()
                self._holds_over_a_revival(_RevivesTheRun(self, head, records, unread=unread), head)

                self._assert_indexed_once(run)
                self.assertTrue(self.proves())
                self.recovers()
                self.assert_recovered(head)
                self.assertIsNone(readings.pinned_records(self)[1])

    def _lands_under_a_split(self, lands, run, *, unread: bool) -> None:
        """Hand `lands` a context read off the comment, a newer run bound as `run` is settled and split around it."""
        context = guarded.recovery_context(self)
        context.state.set(_GATE, run.receipt)
        splits = _SplitsTheRestoration(self, under=(readings.KEY_REWRITE_BASE,), settles=run.binding, unread=unread)
        with (
            patch.object(self.gh, _EDITS, splits.edits),
            patch.object(_durable, _READS, splits.reads),
        ):
            lands(context)
        self.assertTrue(splits.split)
        self.assertNotEqual(splits.successor.receipt, run.receipt)
        pending, current, retired = readings.pinned_records(self)
        self.assertEqual((pending, current), (None, None))
        self.assertEqual(retired[-1], (splits.successor.receipt, readings.INVALIDATED))
        self.assertFalse(self.pinned_fields(guarded.AWAITING)[0])

    def _holds_over_a_revival(self, revives: _RevivesTheRun, head: str) -> None:
        """Hand the hold a context read off the comment, `revives` answering its edits; nothing left current."""
        context = guarded.recovery_context(self)
        context.state.set(_GATE, head)
        with (
            patch.object(self.gh, _EDITS, revives),
            patch.object(self.gh, "read_pinned_state", revives.reads),
        ):
            _parks.lands_a_hold(context)
        self.assertTrue(revives.revived)
        self.assertEqual(readings.pinned_records(self)[1:2], (None,))

    def _assert_indexed_once(self, run) -> None:
        """`run` the last record the history indexes, invalidated, once, with its revision and binding."""
        retired = readings.pinned_records(self)[2]
        invalidated = (run.receipt, readings.INVALIDATED)
        self.assertEqual(retired[-1], invalidated)
        self.assertEqual(retired.count(invalidated), 1)
        state = self.gh.read_pinned_state(self.issue)
        entry = _settlement.read_evidence_history(state)[-1]
        self.assertEqual((entry.revision, entry.binding), (run.revision, run.binding))


if __name__ == "__main__":
    unittest.main()
