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
missing. A finish the policy does not hold refuses every one of these moves
and reads nothing. Nothing runs, posts, launches, relabels, or charges.
"""
from __future__ import annotations

import contextlib
import unittest
from itertools import product

from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_marks as _marks,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_settled as _settled,
    rewrite_finish_unconfirmed as _unconfirmed,
    verification_records as _records,
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

# How the attempt records the base tip its replay was made onto, how the base
# the tick counted the head against reads now, and what the policy answers.
_BASES = (
    ("blank", _BaseStanding.STANDING, None),
    ("blank", _BaseStanding.MOVED, _HELD),
    ("missing", _BaseStanding.MOVED, _HELD),
    ("recorded", _BaseStanding.MOVED, _HELD),
)


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
        # its own, before the invalidation: the route is held, but the run
        # read moving is retired over the comment as it stands, whatever
        # attempt it carries kept as written.
        for name, takes in (("routed", retirement.routes), ("replaced", retirement.replaces)):
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
        # every other record kept.
        finish = self.dormant()
        settled_moves.reviews_again(self)
        retirement.drops_the_handoff(self)
        settled_moves.writes_over(self, _UNKNOWN, _UNKNOWN)
        retirement.routes(self)
        moves.fills_the_comment(self)

        self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))

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
