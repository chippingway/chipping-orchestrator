# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Movement read under settled evidence where the comment has no room, recorded so nothing put back revives it.

The retirement case (`receipt_retirement_support`): issue #7's run settled
under the anchor, each primitive asked directly over a finish held to the
dormant settled-evidence policy -- or the evidence phase over such a finish
-- while another road or another finish of the landing fills the comment and
moves the attempt or the evidence's records. With no room for the run's
history entry the movement is marked in its handoff's place -- over the
comment read afresh where no write over the tick's own copy lands -- and every
later phase reads the mark as that movement, as a later finish finding no
attempt does, retiring the run whole once room is made; a handoff naming the
run, or left null, is no mark. Where even the mark has no room the run is
retired whole at once, the records left null removed to make it fit, made
once more where another road wrote under that edit; and where not even that
fits, a revision is spent past the run on the floor, its record kept current
and whole, so putting everything back makes nothing current again and the
next phase with room retires it whole -- a floor never raised past a
transaction that would settle outranked. Nothing runs, posts, launches,
relabels, or charges.
"""
from __future__ import annotations

import contextlib
import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    rewrite_finish_outranking as _outranking,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_settlement as _settlement_step,
    rewrite_finish_unconfirmed as _unconfirmed,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    receipt_retirement_support as retirement,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
)

_HANDOFF = _records.EVIDENCE_HANDOFF

_FLOOR = readings.KEY_REVISION_FLOOR

_HELD = FinishOutcome.HELD

# A record another road writes beside the evidence, which nothing here owns.
_UNKNOWN = "another_roads_record"

# What another road puts back once the run's record was dropped: the attempt, and the handoff.
_PUT_BACK = (*readings.ATTEMPT_KEYS, _HANDOFF)

# The report and review records a later review moves, as the pinned comment spells them.
_REPORT_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")


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


class MarkedMovementTest(retirement.RetirementCase, unittest.TestCase):
    """Movement with no room for history is marked under its receipt and read as movement until it retires the run."""

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

    def test_movement_is_marked_over_a_fresh_reading(self) -> None:
        # Behind the finish's reading of the comment, another road leaves a
        # pending record nobody can read and fills the comment, and the issue
        # is edited: the phase reads the movement, but neither write over the
        # tick's own copy lands beside that record, so the movement is marked
        # under the run's receipt over the comment read afresh. With the issue
        # put back and room made, the next phase reads the mark as the
        # movement it is and retires the run whole, the pending record still
        # holding every phase and kept as that road wrote it.
        finish = self.dormant()
        body = self.issue.body
        settled_moves.writes_over(self, _records.PENDING_EVIDENCE, "unreadable")
        moves.fills_the_comment(self)
        settled_moves.edits_the_requirements(self)

        self.assertEqual(self.asks(_settlement_step.resolves, finish), _HELD)
        self.assert_marked()
        self.issue.body = body
        moves.makes_room(self)
        retired = self.asks(_settlement_step.resolves, self.dormant())
        again = self.asks(_settlement_step.resolves, self.dormant())

        left = self.pinned()[_records.PENDING_EVIDENCE]
        self.assertEqual((retired, again, left), (_HELD, _HELD, "unreadable"))
        self.assert_whole()
        self.assert_untouched()

    def _marks_over_a_route(self) -> None:
        """The review moved, another finish's route, a full comment: the invalidation held, the movement marked."""
        finish = self.dormant()
        settled_moves.reviews_again(self)
        retirement.routes(self)
        moves.fills_the_comment(self)
        self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))
        self.assert_marked()


class WholeRetirementTest(retirement.RetirementCase, unittest.TestCase):
    """Where not even the mark has room, the run is retired whole at once -- or, with none at all, outranked."""

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

    def test_no_room_at_all_outranks_the_run(self) -> None:
        # The comment is full and carries no history, pending record, or
        # handoff to make room with, another finish's route took the attempt,
        # and the issue is edited: not even the whole retirement fits, so a
        # revision is spent past the run on the floor, its record kept current
        # and whole, which the policy every road selects and the dormant one
        # both read outranked. With the issue, the attempt, and the handoff
        # put back and room made, the next phase reads that as movement,
        # retires the run whole into history, and goes on with nothing current.
        kept = self._strips_the_evidence_records()
        finish = self.dormant()
        body = self.issue.body
        settled_moves.edits_the_requirements(self)
        retirement.routes(self)
        moves.fills_the_comment(self)

        first = self.asks(_settlement_step.resolves, finish)
        self._assert_outranked()
        self.issue.body = body
        moves.makes_room(self)
        self.puts_back({**self.pinned(), **kept})
        again = self.asks(_settlement_step.resolves, self.dormant())

        self.assertEqual((first, again), (_HELD, None))
        self.assert_whole()
        self.assert_untouched()

    def test_a_spent_revision_is_not_spent_again(self) -> None:
        # Beside a newer transaction recorded past the run, whose settlement a
        # floor raised past it would leave outranked, nothing is staged; nor
        # where nobody can say what was spent.
        settled_moves.records_a_newer_one(self)
        beside = self.gh.read_pinned_state(self.issue)
        written = dict(beside.data)
        unreadable = self.gh.read_pinned_state(self.issue)
        unreadable.set(_FLOOR, None)

        self.assertTrue(_outranking.spends_past(beside, self.settled))
        self.assertFalse(_outranking.spends_past(unreadable, self.settled))

        self.assertEqual((beside.data, unreadable.get(_FLOOR)), (written, None))

    def _strips_the_evidence_records(self) -> dict:
        """Take the history, pending record, and handoff off the comment and the case; the attempt and handoff read."""
        pinned = self.pinned()
        kept = {key: pinned[key] for key in _PUT_BACK if key in pinned}
        for key in (_records.EVIDENCE_HISTORY, _records.PENDING_EVIDENCE, _HANDOFF):
            pinned.pop(key)
        self.puts_back(pinned)
        self.history = ()
        return kept

    def _assert_outranked(self) -> None:
        """The run current and whole beside a revision spent past it, which both policies read as outranking it."""
        spent = self.gh.read_pinned_state(self.issue)
        self.assertEqual(_settlement.read_current_evidence(spent), self.settled)
        self.assertEqual(spent.get(_FLOOR), self.settled.revision + 1)
        self.assertTrue(_outranking.outranks(spent, self.settled, settled=False))
        self.assertTrue(_outranking.outranks(spent, self.settled, settled=True))

    def _assert_compacted(self) -> None:
        """The run retired whole, the current, pending, and handoff records removed, another road's record kept."""
        written = (_records.CURRENT_EVIDENCE, _records.PENDING_EVIDENCE, _HANDOFF, _UNKNOWN)
        pinned = self.pinned()
        left = [key for key in written if key in pinned]
        self.assertEqual(left, [_UNKNOWN])
        self.assert_whole()
        self.assert_untouched(readings.RETIRED)


if __name__ == "__main__":
    unittest.main()
