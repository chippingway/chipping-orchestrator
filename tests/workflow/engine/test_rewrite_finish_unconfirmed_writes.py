# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finish's own write whose answer was lost, or a settlement made under its abandonment, reconciled before retiring.

The retirement case (`receipt_retirement_support`) and the captured case
(`rewrite_captured_test_support.CapturedEvidenceCase`), each primitive asked
directly over the finish a later recovery holds. The
attempt a retirement whose answer was lost took off the comment is put back
exactly as the finish read it, every other field kept, so the movement read
under the run is still invalidated over it -- or, with no room for it, marked
in the handoff's place -- and nothing is put back beside a successor another
road settled. Where the putting back lands with its own answer lost, the mark
beside the attempt it restored is read by the next phase as the movement it
is, which retires the run whole. The bookkeeping an announcement whose answer was lost left on
the attempt is taken in for the landed head alone. A settlement another
finish made of a captured run this finish abandons is taken in and
invalidated whole in its place -- and a settlement another finish made while this one's answer
was asked is kept current where nothing but the evidence records moved, the
phase holding where another road's attempt then stands in place of its own --
a readable base tip other than its own among it -- having adopted that
settlement and that attempt first, and invalidated it over a later review the
artifact's ledger entry took in beside that attempt, or over a blank of the
base tip, which records movement rather than another attempt.
Nothing runs, launches, or relabels, and nothing is posted but by the other
finish.
"""
from __future__ import annotations

import contextlib
import unittest
from collections.abc import Mapping
from functools import partial
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_evidence as _evidence,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_settlement as _settlement_step,
    rewrite_finish_unconfirmed as _unconfirmed,
    rewrite_finish_writes as _writes,
    verification_comments as _verification_comments,
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
    verification_evidence_test_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

# The report and review records a later review moves, as the pinned comment spells them.
_REPORT_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

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


def _settles_and_announces(case) -> None:
    """Settle the captured run and announce the landed head, as another finish of the landing would."""
    case._settles_elsewhere()
    retirement.announces(case)


def _settles_and_replaces(case, replaced: Mapping[str, Any]) -> None:
    """Settle the captured run as another finish of the landing would, and write the attempt's members as `replaced`."""
    case._settles_elsewhere()
    for member, written in replaced.items():
        settled_moves.writes_over(case, member, written)


def _replaces_and_reviews(case) -> None:
    """Put another road's attempt in place, and hand a later review over, as other roads would."""
    settled_moves.writes_over(case, readings.KEY_PENDING_PUSH, support.SQUASHED_SHA)
    settled_moves.reviews_again(case)


def _puts_back_and_settles(case, kept: dict) -> None:
    """Put `kept` back over the comment as it stands, then settle the run as another finish would."""
    state = case.gh.read_pinned_state(case.issue)
    for key, recorded in kept.items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)
    case._settles_elsewhere()


@contextlib.contextmanager
def _replaces_under_the_settlement(case):
    """Another road's attempt and a later review put in place right behind the phase's post of the run's artifact.

    The phase's settlement edit is refused over them, and the artifact's
    ledger entry it then commits alone takes that comment in; right behind
    that entry the review is put back as it read before, and another finish
    settles the run over the comment as it stands.
    """
    kept = {key: readings.pinned(case)[key] for key in _REPORT_RECORDS}
    puts_back = partial(_puts_back_and_settles, case, kept)
    takes_in = _RacesPastTheStep(_verification_comments.records_the_artifact, puts_back)
    with (
        settled_moves.raced_past(case, "publish_verification_artifact", _replaces_and_reviews),
        patch.object(_verification_comments, "records_the_artifact", takes_in),
    ):
        yield


# The answer's re-reading of the settled report, which another finish's
# settlement of the run lands beside.
_REREADS = "reread_report_location"

# What another road writes over the attempt's members beside that settlement:
# another push, a readable base tip other than the one captured, or a blank of
# that tip, which records movement rather than another attempt.
_ANOTHER_PUSH = MappingProxyType({readings.KEY_PENDING_PUSH: support.SQUASHED_SHA})
_ANOTHER_TIP = MappingProxyType({readings.KEY_REWRITE_BASE: support.SQUASHED_SHA})
_A_BLANK_TIP = MappingProxyType({readings.KEY_REWRITE_BASE: None})

# Where another road's attempt comes to stand in place of the one the phase
# captured, as another finish settles the run, the attempt's members as they
# then read, and whether the settlement the phase adopts is invalidated:
# beside the answer's reading of the settled report, nothing else moving --
# another push, or another base tip -- or behind the artifact's ledger entry,
# which took in a later review the phase's settlement edit was refused over.
# A blank of the base tip beside the answer is no other attempt but the
# movement it records, which invalidates the settlement whole.
_REPLACED = MappingProxyType({
    "another push beside the answer": (
        partial(settled_moves.raced_past, step=_REREADS, move=partial(_settles_and_replaces, replaced=_ANOTHER_PUSH)),
        _ANOTHER_PUSH,
        False,
    ),
    "another base tip beside the answer": (
        partial(settled_moves.raced_past, step=_REREADS, move=partial(_settles_and_replaces, replaced=_ANOTHER_TIP)),
        _ANOTHER_TIP,
        False,
    ),
    "a blank base tip beside the answer": (
        partial(settled_moves.raced_past, step=_REREADS, move=partial(_settles_and_replaces, replaced=_A_BLANK_TIP)),
        _A_BLANK_TIP,
        True,
    ),
    "behind the ledger's take-in": (_replaces_under_the_settlement, _ANOTHER_PUSH, True),
})


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
                self.forgets(missing)
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
        finish = self.landed()
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
                finish = self.landed()
                read = dict(finish.state.data)
                retirement.announces(self, head)
                settled_moves.writes_over(self, readings.KEY_REVIEW_ROUND, 0)

                self.asks(_unconfirmed.takes_in_the_announcement, finish)

                announced = {readings.KEY_ANNOUNCED: head, readings.KEY_ANNOUNCED_EVENT: head}
                self.assertEqual(finish.state.data, {**read, **announced} if taken else read)
                self.assert_untouched()

    def test_a_lost_restoration_is_retired_later(self) -> None:
        # The issue was edited behind the retirement whose answer was lost,
        # and the attempt is put back -- but that write's own answer is lost
        # too, so the movement is marked beside the attempt it restored, and
        # the edit is then put back. Every later phase reads the mark as the
        # movement it is: the next retires the run whole over the attempt
        # standing as read, and the one behind it goes on with nothing current.
        finish = self.landed()
        read = _commit_models.PinnedCommit.capture(finish.state, prerequisites=readings.ATTEMPT_KEYS)
        body = self.issue.body
        self.gh.write_pinned_state(self.issue, _writes.retirement(finish))
        settled_moves.edits_the_requirements(self)

        with patch.object(self.gh.pinned_failures, "lost", {self.issue.number}):
            self.assertFalse(self.asks(_unconfirmed.stands_back, finish, self.settled))
        self.issue.body = body
        self.assert_marked()
        retired = self.asks(_settlement_step.resolves, self.landed())
        again = self.asks(_settlement_step.resolves, self.landed())

        self.assertEqual((retired, again), (FinishOutcome.HELD, None))
        self.assertEqual(read.moved(self.pinned()), ())
        self.assert_whole()
        self.assert_untouched()

    def _loses_the_retirement(self):
        """A finish whose retirement landed, answer lost, with another road's record and a review behind it."""
        finish = self.landed()
        self.gh.write_pinned_state(self.issue, _writes.retirement(finish))
        settled_moves.writes_over(self, _UNKNOWN, _UNKNOWN)
        settled_moves.reviews_again(self)
        return finish

    def _assert_kept_beside(self) -> None:
        """Another road's record and the round the retirement reset, as the comment carried them."""
        pinned = self.pinned()
        self.assertEqual(pinned[_UNKNOWN], _UNKNOWN)
        self.assertEqual(pinned[readings.KEY_REVIEW_ROUND], 0)


class AbandonedSettlementTest(settled_support.CapturedEvidenceCase, unittest.TestCase):
    """A settlement another finish made of the run this finish abandons is retired in its place, or held over."""

    def test_a_settlement_while_abandoning_is_retired(self) -> None:
        # Another finish settled the run after this one read it captured,
        # and this one abandons it over a base advanced past its head: that
        # settlement is taken in and invalidated whole, so the continuation
        # carries none of it.
        finish = self.landed()
        self._settles_elsewhere()
        posted = support.posted_artifacts(self)

        self.assertIsNone(self.asks(_evidence.continues, finish))

        self.assertEqual(support.posted_artifacts(self), posted)
        self.assertEqual((self.verify.call_count, self.developer.call_count), (0, 0))
        self._assert_retired(held=True)

    def test_a_settlement_beside_the_answer_is_kept(self) -> None:
        # Another finish settles the run while this one's answer re-reads the
        # settled report -- announcing the landing too, or not -- so that
        # answer is refused over the evidence records and the announcement's
        # own members alone: nothing a binding rests on moved, so the run
        # stays current as that finish settled it, its artifact posted once
        # and nothing run. That settlement and announcement are taken in and
        # the phase goes on at once.
        for announced in (False, True):
            with self.subTest(announced=announced):
                self.setUp()

                self.assertEqual(self._races_the_answer(announced), (None, None))

                self._assert_retired(held=False)
                mark = readings.pinned(self).get(readings.KEY_ANNOUNCED)
                self.assertEqual(mark == settled_support.REBASED, announced)

    def test_a_replacement_beside_the_answer_holds(self) -> None:
        # Another road's attempt stands in place of the one this finish
        # captured once its answer is made -- another push, or a readable base
        # tip other than the one captured -- and another finish settles the
        # run: while the answer re-reads the settled report -- nothing else
        # moving -- or right behind the artifact's ledger entry, which took in
        # that attempt and a later review the phase's own settlement edit was
        # refused over, the review put back first. The phase holds over that
        # attempt rather than routing past it, the replacement left as
        # written and laid over the finish's state, but only once it has
        # adopted the settlement: kept current where nothing moved,
        # invalidated whole over the review it read. A blank of the base tip
        # is no replacement but movement recorded under the run, so the
        # settlement adopted is invalidated whole over it.
        for case, (races, replaced, invalidated) in _REPLACED.items():
            with self.subTest(case=case):
                self.setUp()
                finish = self.landed()

                with races(self):
                    self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.HELD)

                self._assert_retired(held=invalidated)
                self.assertLessEqual(replaced.items(), readings.pinned(self).items())
                self.assertLessEqual(replaced.items(), finish.state.data.items())

    def _races_the_answer(self, announced: bool) -> tuple:
        """Two phases, another finish settling the run -- and announcing it, where `announced` -- under the first."""
        moves = _settles_and_announces if announced else type(self)._settles_elsewhere
        with settled_moves.raced_past(self, "reread_report_location", moves):
            first = self.asks(_settlement_step.resolves, self.landed())
        return first, self.asks(_settlement_step.resolves, self.landed())

    def _settles_elsewhere(self) -> None:
        """Post the captured run's artifact and settle it, as another finish of the landing would."""
        state = self.gh.read_pinned_state(self.issue)
        posted = self.gh.publish_verification_artifact(self.pull_request, self.captured.artifact)
        self.gh.write_pinned_state(self.issue, _settlement.settled_state(
            state, self.captured, posted.landed_id, finish_support.REVIEWING,
        ))

    def _assert_retired(self, held: bool) -> None:
        """The run invalidated whole, its revision and binding kept, where `held`; current as settled otherwise.

        Either way its artifact was posted once, by the finish that settled
        it, and nothing ran.
        """
        receipts = [found.receipt for found in support.posted_artifacts(self)]
        self.assertEqual(receipts.count(self.captured.receipt), 1)
        self.assertEqual(self.verify.call_count, 0)
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
