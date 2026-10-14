# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finish's own write whose answer was lost, or a settlement made under its abandonment, reconciled before retiring.

The retirement case (`receipt_retirement_support`) and the captured case
(`rewrite_captured_test_support.CapturedEvidenceCase`), each primitive asked
directly over a finish held to the dormant settled-evidence policy. The
attempt a retirement whose answer was lost took off the comment is put back
exactly as the finish read it, every other field kept, so the movement read
under the run is still invalidated over it -- or, with no room for it, marked
in the handoff's place -- and nothing is put back beside a successor another
road settled. The bookkeeping an announcement whose answer was lost left on
the attempt is taken in for the landed head alone. A settlement another
finish made of a captured run this finish abandons is taken in and
invalidated whole in its place, where a finish the policy does not hold
holds over it. Nothing runs, launches, or relabels, and nothing is posted
but by the other finish.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_evidence as _evidence,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_unconfirmed as _unconfirmed,
    rewrite_finish_writes as _writes,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    receipt_retirement_support as retirement,
    rewrite_captured_test_support as settled_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
    settled_finish_support as settled,
    verification_evidence_test_support as support,
)

# A record another road writes beside the evidence, which nothing here owns.
_UNKNOWN = "another_roads_record"

# The attempt members a legacy attempt carries none of, beside the mark and
# the record of the event no finish of this landing has put down yet.
_LEGACY = (readings.KEY_EVIDENCE_RECEIPT, readings.KEY_REWRITE_BASE)

# What the announcement's members may hold: the landed head, another head, or
# a JSON object or list no head is -- and whether it is this landing's own.
_ANNOUNCED = (
    (settled_support.REBASED, True),
    (support.SQUASHED_SHA, False),
    ({"sha": settled_support.REBASED}, False),
    ([settled_support.REBASED], False),
)


class LostAnswerTest(retirement.RetirementCase, unittest.TestCase):
    """A write of the finish's own whose answer was lost is reconciled before the movement under it is recorded."""

    def test_the_retired_attempt_is_put_back(self) -> None:
        # The finish's retirement landed with its answer lost, another road
        # wrote a record of its own behind it, and the review moved: the
        # attempt is put back spelled exactly as the finish read it -- every
        # member it read missing, a legacy attempt's among them, missing
        # again rather than null -- that record and the reset round kept, and
        # the run is invalidated over it.
        for missing in ((), _LEGACY):
            with self.subTest(missing=missing):
                self.setUp()
                self._forgets(missing)
                finish = self._loses_the_retirement()
                read = _commit_models.PinnedCommit.capture(finish.state, prerequisites=readings.ATTEMPT_KEYS)

                self.assertTrue(self.asks(_unconfirmed.stands_back, finish, self.settled))
                self.assertEqual(read.moved(self.pinned()), ())
                self.assertTrue(self.asks(_readiness.invalidates, finish, self.settled, as_it_stands=False))

                self.assertEqual(read.moved(self.pinned()), ())
                self._assert_kept_beside()
                self.assert_whole()
                self.assert_untouched()

    def test_no_room_marks_the_movement(self) -> None:
        # The comment was filled behind that retirement, so the attempt does
        # not fit back: the movement is marked in the handoff's place.
        finish = self._loses_the_retirement()
        moves.fills_the_comment(self)

        self.assertFalse(self.asks(_unconfirmed.stands_back, finish, self.settled))

        self.assert_marked()
        self._assert_kept_beside()
        self.assert_untouched(readings.RETIRED)

    def test_a_successor_behind_it_is_kept(self) -> None:
        # Another road settled a newer run of the head behind that
        # retirement: nothing is put back beside the successor, and the
        # comment stays exactly as written.
        finish = self.dormant()
        self.gh.write_pinned_state(self.issue, _writes.retirement(finish))
        retirement.supersedes(self)
        written = self.pinned()
        self.artifacts_before += 1

        self.assertFalse(self.asks(_unconfirmed.stands_back, finish, self.settled))

        self.assertEqual(self.pinned(), written)
        self.assert_untouched(readings.RETIRED)

    def test_the_announcement_is_taken_in(self) -> None:
        # The record of the event and the checkpoint landed with their
        # answers lost: the mark and the record naming the landed head are
        # laid over the finish's state as read, and nothing else -- the
        # round the checkpoint reset among it; a mark naming another head, or
        # holding an object or a list, is no announcement of this landing's.
        for head, taken in _ANNOUNCED:
            with self.subTest(head=head):
                self.setUp()
                finish = self.dormant()
                read = dict(finish.state.data)
                retirement.announces(self, head)
                settled_moves.writes_over(self, readings.KEY_REVIEW_ROUND, 0)

                self.asks(_unconfirmed.takes_in_the_announcement, finish)

                announced = {readings.KEY_ANNOUNCED: head, readings.KEY_ANNOUNCED_EVENT: head}
                self.assertEqual(finish.state.data, {**read, **announced} if taken else read)
                self.assert_untouched()

    def _loses_the_retirement(self):
        """A dormant finish whose retirement landed, answer lost, with another road's record and a review behind it."""
        finish = self.dormant()
        self.gh.write_pinned_state(self.issue, _writes.retirement(finish))
        settled_moves.writes_over(self, _UNKNOWN, _UNKNOWN)
        settled_moves.reviews_again(self)
        return finish

    def _forgets(self, missing: tuple) -> None:
        """Take the attempt members `missing` off the comment, as an attempt pinned before they existed carries none."""
        pinned = self.pinned()
        for member in missing:
            pinned.pop(member)
        self.puts_back(pinned)

    def _assert_kept_beside(self) -> None:
        """Another road's record and the round the retirement reset, as the comment carried them."""
        pinned = self.pinned()
        self.assertEqual(pinned[_UNKNOWN], _UNKNOWN)
        self.assertEqual(pinned[readings.KEY_REVIEW_ROUND], 0)


class AbandonedSettlementTest(settled_support.CapturedEvidenceCase, unittest.TestCase):
    """A settlement another finish made of the run this finish abandons is retired in its place, or held over."""

    def test_a_settlement_while_abandoning_is_retired(self) -> None:
        # Another finish settled the run after this one read it captured,
        # and this one abandons it over a base advanced past its head: the
        # policy takes that settlement in and invalidates it whole, so the
        # continuation carries none of it; a finish the policy does not hold
        # cannot abandon it and holds, the settlement left current.
        for held, answer in ((True, None), (False, FinishOutcome.HELD)):
            with self.subTest(held=held):
                self.setUp()
                finish = settled.dormant(self.landed()) if held else self.landed()
                self._settles_elsewhere()
                posted = support.posted_artifacts(self)

                self.assertEqual(self.asks(_evidence.continues, finish), answer)

                self.assertEqual(support.posted_artifacts(self), posted)
                self.assertEqual((self.verify.call_count, self.developer.call_count), (0, 0))
                self._assert_retired(held)

    def _settles_elsewhere(self) -> None:
        """Post the captured run's artifact and settle it, as another finish of the landing would."""
        state = self.gh.read_pinned_state(self.issue)
        posted = self.gh.publish_verification_artifact(self.pull_request, self.captured.artifact)
        self.gh.write_pinned_state(self.issue, _settlement.settled_state(
            state, self.captured, posted.landed_id, finish_support.REVIEWING,
        ))

    def _assert_retired(self, held: bool) -> None:
        """The run invalidated whole, its revision and binding kept, where `held`; current as settled otherwise."""
        pending, current, history = self.records()
        self.assertIsNone(pending)
        if not held:
            self.assertEqual(current.receipt, self.captured.receipt)
            return
        self.assertIsNone(current)
        self.assertEqual(history[-1], (self.captured.receipt, readings.INVALIDATED))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual(entry.revision, self.captured.revision)
        self.assertEqual(entry.binding, self.captured.binding)


if __name__ == "__main__":
    unittest.main()
