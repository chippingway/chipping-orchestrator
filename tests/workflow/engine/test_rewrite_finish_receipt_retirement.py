# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence read moving, retired under its own receipt however the attempt or the comment moved since.

The retirement case (`receipt_retirement_support`): issue #7's run settled
under the anchor, each retirement primitive asked directly over a finish held
to the dormant settled-evidence policy while another road or another finish of
the landing moves the attempt or the comment. An announcement another finish
put on the attempt is taken in and the invalidation made over it, retried once
over the comment read afresh where it landed under the first write; a route or
another attempt that took the attempt has the same receipt retired as the
comment stands, that attempt kept; a successor settled under another receipt
is never written over. With no room the movement is marked in the evidence's
handoff place, a later finish finding no attempt retires the marked evidence
whole once room is made, and where even the mark has no room the evidence is
retired whole at once. A routed head with nothing current is held to a base
its attempt can prove, the base the tick counted where its tip is blank or
missing. A readable revision spent past the run outranks it beside a pending
record too, which still holds. A finish the policy does not hold refuses every
one of these moves, reading the comment no more often than it always has.
Nothing runs, posts, launches, relabels, or charges.
"""
from __future__ import annotations

import contextlib
import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_marks as _marks,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_settled as _settled,
    rewrite_finish_unconfirmed as _unconfirmed,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    receipt_retirement_support as retirement,
    rewrite_captured_test_support as settled_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
)

_HANDOFF = _records.EVIDENCE_HANDOFF

_HELD = FinishOutcome.HELD

# A record another road writes beside the evidence, which nothing here owns.
_UNKNOWN = "another_roads_record"

# What took the attempt off the comment: another finish's route, or another
# road's attempt, its anchor a head or a JSON object or list no head is.
_TAKEN = (
    ("routed", retirement.routes),
    ("replaced", retirement.replaces),
    ("replaced by an object", partial(retirement.replaces, written={"sha": settled_support.REBASED})),
    ("replaced by a list", partial(retirement.replaces, written=[settled_support.REBASED])),
)

# What refuses the first write of an invalidation for a finish the policy does
# not hold, how many times it reads the comment -- once afresh, never again,
# then whatever the tick's own copy's write reads -- and whether it landed: the
# comment full, its movement recorded on the tick's copy instead, or the
# comment unread once, the tick's copy taking the invalidation.
_UNSELECTED = (
    ("the comment full", lambda case: contextlib.nullcontext(moves.fills_the_comment(case)), (4, False)),
    (
        "the comment unread once",
        lambda case: patch.object(case.gh, "read_pinned_state", settled_support.FailsOnce(case.gh.read_pinned_state)),
        (2, True),
    ),
)

# The report and review records a later review moves, as the pinned comment spells them.
_REPORT_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# How the attempt records the base tip its replay was made onto, how the base
# the tick counted the head against reads now, and what the policy answers.
_BASES = (
    ("blank", _BaseStanding.STANDING, None),
    ("blank", _BaseStanding.MOVED, _HELD),
    ("missing", _BaseStanding.MOVED, _HELD),
    ("recorded", _BaseStanding.MOVED, _HELD),
)


def _drops_one_first(case) -> object:
    """Record a newer transaction and drop it with no history entry, then record another; the one pending."""
    settled_moves.records_a_newer_one(case)
    settled_moves.writes_over(case, _records.PENDING_EVIDENCE, None)
    return settled_moves.records_a_newer_one(case)


def _raises_the_floor_past(case) -> object:
    """Record a newer transaction, then raise the revision floor past it, as another road spending one would; it."""
    pending = settled_moves.records_a_newer_one(case)
    settled_moves.writes_over(case, readings.KEY_REVISION_FLOOR, pending.revision + 1)
    return pending


class _PutsBackWhileCompacting:
    """Another road putting the report and review records back as they read now, right behind a compaction's staging.

    Only where it `races`, and only once: the compact retirement is staged on
    the comment read afresh, and that road's write lands before the edit, so
    the edit finds the comment moved under it.
    """

    def __init__(self, case, races: bool) -> None:
        self._case = case
        self._races = races
        self._owed = races
        pinned = case.pinned()
        self._kept = {key: pinned[key] for key in _REPORT_RECORDS}
        self._stage = _settlement.retire_current_evidence

    def racing(self):
        """The staging racing where this does, or as it always stages."""
        if not self._races:
            return contextlib.nullcontext()
        return patch.object(_settlement, "retire_current_evidence", self._stages)

    def assert_kept(self) -> None:
        """The report and review records as that road put them back, where it raced."""
        pinned = self._case.pinned()
        if self._races:
            self._case.assertEqual({key: pinned[key] for key in _REPORT_RECORDS}, self._kept)

    def _stages(self, state, *, compact: bool = False) -> bool:
        staged = self._stage(state, compact=compact)
        if compact and self._owed:
            self._owed = False
            restored = self._case.gh.read_pinned_state(self._case.issue)
            for key, kept in self._kept.items():
                restored.set(key, kept)
            self._case.gh.write_pinned_state(self._case.issue, restored)
        return staged


class ReconciledRetirementTest(retirement.RetirementCase, unittest.TestCase):
    """Movement under the run is retired over the attempt as reconciled, or as the comment stands; never twice."""

    def test_an_announcement_is_taken_in(self) -> None:
        # Another finish of the landing announced the head before the
        # invalidation read the comment, or just behind that read, refusing
        # its first write: the policy takes the mark and the event's record
        # in and invalidates the run over them, read afresh once more. A
        # finish the policy does not hold reads another attempt and refuses.
        for behind_the_read, held in product((False, True), (True, False)):
            with self.subTest(behind_the_read=behind_the_read, held=held):
                self.setUp()
                finish = self.dormant() if held else self.landed()
                settled_moves.reviews_again(self)

                with self._announcing(behind_the_read):
                    invalidated = self.asks(_readiness.invalidates, finish, self.settled)

                self.assertEqual(invalidated, held)
                self.assertEqual(self.pinned()[readings.KEY_ANNOUNCED], settled_support.REBASED)
                self.assert_untouched()
                if held:
                    self.assert_whole()
                else:
                    self.assertEqual(self.records(), self.kept())

    def test_it_is_retired_as_the_comment_stands(self) -> None:
        # Another finish's route retired the attempt, or another road pinned
        # its own -- however its anchor is spelled -- before the invalidation:
        # the route is held, but the run read moving is retired over the
        # comment as it stands, whatever attempt it carries kept as written.
        for name, takes in _TAKEN:
            with self.subTest(name):
                self.setUp()
                finish = self.dormant()
                settled_moves.reviews_again(self)
                takes(self)
                attempt = readings.attempt(self.pinned())

                self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))

                self.assert_whole()
                self.assert_untouched(attempt)

    def test_a_successor_is_kept(self) -> None:
        # Another road settled a newer run of the head under its own receipt:
        # no primitive retires, marks, or puts back anything under the run
        # that receipt superseded, and the comment stays exactly as written.
        finish = self.dormant()
        settled_moves.reviews_again(self)
        retirement.supersedes(self)
        attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=readings.ATTEMPT_KEYS)
        written = self.pinned()
        self.artifacts_before += 1

        answers = (
            self.asks(_readiness.invalidates, finish, self.settled),
            self.asks(_marks.retires_as_it_stands, finish, self.settled.receipt, attempt),
            self.asks(_unconfirmed.stands_back, finish, self.settled),
        )
        self.asks(_marks.marks, finish, self.settled, "the run moved")

        self.assertEqual(answers, (False, False, False))
        self.assertEqual(self.pinned(), written)
        superseded = self.records()[2][-1]
        self.assertEqual(superseded, (self.settled.receipt, "superseded"))
        self.assert_untouched()

    def test_an_unselected_one_reads_as_before(self) -> None:
        # A finish the policy does not hold reads the comment once afresh and,
        # where that write does not land, falls back to the tick's own copy
        # with nothing read again: no announcement taken in, no retry.
        for name, refuses, answers in _UNSELECTED:
            with self.subTest(name):
                self.setUp()
                finish = self.landed()
                settled_moves.reviews_again(self)

                with refuses(self):
                    counted = self.calls_to("read_pinned_state", _readiness.invalidates, finish, self.settled)

                self.assertEqual((counted, self.records()[1] is None), answers)
                self.assert_untouched()

    def _announcing(self, behind_the_read: bool):
        """Another finish's announcement, made now or just behind the next reading of the comment; its context."""
        if behind_the_read:
            return settled_moves.raced_past(self, "read_pinned_state", retirement.announces)
        return contextlib.nullcontext(retirement.announces(self))


class RecordedMovementTest(retirement.RetirementCase, unittest.TestCase):
    """Movement with no room is marked under its receipt, retired whole later, or retired compactly at once."""

    def test_the_mark_waits_for_room(self) -> None:
        # Another finish's route took the attempt and the comment is full:
        # the movement is marked in the handoff's place, and with the room
        # that freed filled again, a later finish finding no attempt cannot
        # retire the run and leaves it marked.
        self._marks_over_a_route()
        moves.fills_the_comment(self)

        self.asks(_unconfirmed.retires_the_marked, self.dormant())

        self.assert_marked()
        self.assert_untouched(readings.RETIRED)

    def test_the_mark_is_retired_whole_later(self) -> None:
        # Once room is made, the next finish finding no attempt reads the
        # mark under the run's very receipt and retires the run whole.
        self._marks_over_a_route()
        moves.fills_the_comment(self)
        moves.makes_room(self)

        self.asks(_unconfirmed.retires_the_marked, self.dormant())

        self.assert_whole()
        self.assert_untouched(readings.RETIRED)

    def test_no_mark_leaves_the_run_current(self) -> None:
        # A later finish finding no attempt beside a handoff that names the
        # run, or one left null, reads no movement recorded and retires
        # nothing.
        for name, leaves in (("named", moves.unmoved), ("null", retirement.drops_the_handoff)):
            with self.subTest(name):
                self.setUp()
                retirement.routes(self)
                leaves(self)
                written = self.pinned()

                self.asks(_unconfirmed.retires_the_marked, self.dormant())

                self.assertEqual(self.pinned(), written)

    def test_no_room_for_the_mark_retires_it_whole(self) -> None:
        # The handoff was left null, so the mark would grow the full
        # comment: the run is retired whole at once, its current record, the
        # null pending record, and the null handoff removed to make room,
        # every other record kept -- also where another road puts the moved
        # report and review back while that retirement is sent, refusing it:
        # read afresh, it is made once more, the records put back kept.
        for races in (False, True):
            with self.subTest(races=races):
                self.setUp()
                restores = _PutsBackWhileCompacting(self, races)
                finish = self.dormant()
                settled_moves.reviews_again(self)
                retirement.drops_the_handoff(self)
                settled_moves.writes_over(self, _UNKNOWN, _UNKNOWN)
                retirement.routes(self)
                moves.fills_the_comment(self)

                with restores.racing():
                    self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))

                self._assert_compacted()
                restores.assert_kept()

    def _assert_compacted(self) -> None:
        """The run retired whole, the current, pending, and handoff records removed, another road's record kept."""
        written = (_records.CURRENT_EVIDENCE, _records.PENDING_EVIDENCE, _HANDOFF, _UNKNOWN)
        pinned = self.pinned()
        left = [key for key in written if key in pinned]
        self.assertEqual(left, [_UNKNOWN])
        self.assert_whole()
        self.assert_untouched(readings.RETIRED)

    def _marks_over_a_route(self) -> None:
        """The review moved, another finish's route, a full comment: the invalidation held, the movement marked."""
        finish = self.dormant()
        settled_moves.reviews_again(self)
        retirement.routes(self)
        moves.fills_the_comment(self)
        self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))
        self.assert_marked()


class OutrankingTest(retirement.RetirementCase, unittest.TestCase):
    """A readable revision spent past the run outranks it beside a pending record, which still holds the route."""

    def test_a_pending_record_hides_no_outranking(self) -> None:
        # Beside the transaction now pending, another road spent a revision
        # past the run that no history entry keeps: one it recorded and
        # dropped first, or the floor it raised past the pending one's own.
        # That revision outranks the run, which is invalidated whole while
        # the pending record holds the route, kept as that road wrote it. A
        # newer transaction recorded right past the run outranks nothing.
        for spends, outranked in (
            (_drops_one_first, True),
            (_raises_the_floor_past, True),
            (settled_moves.records_a_newer_one, False),
        ):
            with self.subTest(spent=spends.__name__):
                self.setUp()
                pending = spends(self)

                answered = self._proves_ready()

                kept = None if outranked else self.settled
                self.assertEqual(answered, (_HELD, (pending, kept)))
                self.assert_untouched()
                if outranked:
                    self._assert_retired_whole()

    def _proves_ready(self) -> tuple:
        """What the readiness proof over a dormant finish answers, and the pending and current records it leaves."""
        held = self.asks(_readiness.stands_ready, self.dormant(), self.settled)
        return held, self.records()[:2]

    def _assert_retired_whole(self) -> None:
        """The run invalidated into history whole, its revision, transcript, and provenance kept."""
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        invalidated = _records.HistoricalEvidence.of(self.settled, _records.Retirement.INVALIDATED)
        self.assertEqual(history[-1], invalidated)


class BaseProofTest(retirement.RetirementCase, unittest.TestCase):
    """A routed head with no evidence current is held to a base its attempt's record of the replay can prove."""

    def test_a_blank_or_missing_tip_holds_to_the_base(self) -> None:
        # Nothing is current for the head, and the attempt's base tip is
        # blank, missing as a legacy attempt leaves it, or recorded: the base
        # the tick counted the head against standing lets the route go on,
        # and one moved since holds it. A finish the policy does not hold
        # reads nothing.
        for recorded, base, answer in _BASES:
            with self.subTest(recorded=recorded, base=base.name):
                self.setUp()
                settled_moves.retires_it(self)
                self._records_the_tip(recorded)
                self.world.base = base

                proved = self.asks(_settled.stands_ready_if_settled, self.dormant(), or_the_base=True)
                unselected = self.asks(_settled.stands_ready_if_settled, self.landed(), or_the_base=True)

                self.assertEqual((proved, unselected), (answer, None))
                self.assert_untouched()

    def _records_the_tip(self, recorded: str) -> None:
        """Leave the attempt's base tip `recorded`: as the attempt pinned it, blank, or missing altogether."""
        pinned = self.pinned()
        if recorded != "recorded":
            pinned[readings.KEY_REWRITE_BASE] = None
        if recorded == "missing":
            pinned.pop(readings.KEY_REWRITE_BASE)
        self.puts_back(pinned)


if __name__ == "__main__":
    unittest.main()
