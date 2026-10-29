# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A run a landed rewrite's finish captured, proved again and held to the last word, or abandoned.

Each case asks the helpers directly over the run a finish captured and
never routed. A run that proves goes on as it was recorded; anything that moved
under it -- the landing, the base, the configuration, the requirements, or the
review -- abandons it into history, a reading nobody could take beside the
movement included, and nothing put back revives it. A reading nobody could
take alone holds it for a later proof. The last word reads the pinned records
alone, so a settled report rewritten at its location moves the run only under
a word asked whole, which proves it again first. The abandonment is a
checkpoint over the reading the tick last confirmed: it keeps every record it
does not own as the comment carries it, holds where the comment would not
read, refuses the run for good where the comment has no room for it, and is
held rather than written over an attempt that no longer reads as the finish
holds it.
Nothing is ever run again, no developer is launched, and nothing is routed.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.workflow.engine import (
    rewrite_evidence_proof as _proof,
    rewrite_finish_captured as _captured,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_captured_test_support as captured_support,
    rewrite_evidence_test_support as rewrite_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    verification_evidence_test_support as support,
    verification_world_fixture as _world,
)
from tests.workflow.interleaving import _RacesPastTheStep

_HELD = FinishOutcome.HELD

# A base tip nothing replayed onto.
_ELSEWHERE = "e15e0e1e" * 5

# A field another road writes that no finish decides on.
_UNKNOWN = "a_field_no_binary_writes_yet"

# A configuration that moved under the captured run.
_RECONFIGURED = (support.SUITE, rewrite_support.LINT)

# The world's readings of where the base stands.
_BASE = "base"

_BASE_REF = "base_ref"

_CHECKOUT_HEAD = "checkout_head"

_SUBJECT = "review_subject"


def _set(attribute: str, set_to):
    """Move one reading of the case's world."""
    return lambda case: setattr(case.world, attribute, set_to)


def _edits_the_issue(case) -> None:
    case.issue.body = "Also cover a moved base."


def _unreads_the_comment(case) -> None:
    case.gh.pinned_failures.unreadable.add(case.issue.number)


def _unreads_the_report(case) -> None:
    case.gh.report_failures.unreadable.add(support.PR_NUMBER)


def _unreads_the_local_base(case) -> None:
    """Leave the local base ref unreadable from the moment the issue is fetched again, behind the base's reading."""
    unreads = partial(setattr, case.world, _BASE_REF, _BranchDivergence())
    case.gh.get_issue = _RacesPastTheStep(case.gh.get_issue, unreads)


# Movement under the captured run, and what its route comes to once it is
# abandoned: a landing or a base gone elsewhere holds it too, and anything else
# lets it go on, carrying nothing, to the reviewer who owes the evidence.
_MOVEMENTS = (
    ("the checkout committed past the head", _set(_CHECKOUT_HEAD, _world.STRAY_SHA), _HELD),
    ("a push moved the branch", lambda case: case.moves_the_head(support.SQUASHED_SHA), _HELD),
    ("the remote base went elsewhere", _set(_BASE, _BaseStanding.MOVED), _HELD),
    (
        "the local base advanced past the head",
        _set(_BASE_REF, _BranchDivergence(tip=_ELSEWHERE, behind=1, readable=True)),
        _HELD,
    ),
    ("the base was rewound under the head", _set(_BASE, _BaseStanding.DROPPED), None),
    ("the issue body was edited", _edits_the_issue, None),
    ("a later review was handed another report", moves.later_review, None),
    (
        "the configuration moved",
        lambda case: case.enterContext(patch.object(config, "VERIFY_COMMANDS", _RECONFIGURED)),
        None,
    ),
)

# Readings nobody could take, each of which holds the run for a later proof.
_UNREAD = (
    ("the remote branch would not read", _set("remote_answers", False)),
    ("the base would not read", _set(_BASE, _BaseStanding.UNREAD)),
    ("the settled report would not re-read", _unreads_the_report),
    ("the pinned comment would not read again", _unreads_the_comment),
    ("the local base would not read behind a request", _unreads_the_local_base),
)

# A reading nobody could take beside movement another reading took, and what
# the route comes to: the unread reading holds it whatever the movement.
_BESIDE = (
    (_set("remote_answers", False), _set(_CHECKOUT_HEAD, _world.STRAY_SHA), _HELD),
    (_set(_BASE, _BaseStanding.UNREAD), _edits_the_issue, _HELD),
    (_unreads_the_report, moves.later_review, None),
)

# Whether the last word is asked whole over a settled report rewritten at its
# location, and the records it leaves: the run kept, or abandoned.
_WHOLE = (
    (False, captured_support.CapturedEvidenceCase.kept),
    (True, captured_support.CapturedEvidenceCase.abandoned),
)

# A write the route already stopped at, over a run nothing moved under and one
# the checkout left, and the records each leaves.
_STOPS = (
    (moves.unmoved, captured_support.CapturedEvidenceCase.kept),
    (_set(_CHECKOUT_HEAD, _world.STRAY_SHA), captured_support.CapturedEvidenceCase.abandoned),
)


class CapturedRouteTest(captured_support.CapturedEvidenceCase, unittest.TestCase):
    """A captured run is routed as recorded, held, or abandoned -- never run again."""

    def test_a_run_that_proves_goes_on_as_recorded(self) -> None:
        finish = self.landed()
        proof = self.asks(_captured.proved_again, finish, self.captured)

        self.assertEqual(
            (proof.proved, self.asks(_captured.stands_before_the_route, finish, proof=proof)), (True, None),
        )
        recorded = _captured.recorded(finish)
        self.assertEqual((recorded, _captured.retired(finish)), (self.captured, False))
        self.assert_dormant()

    def test_movement_abandons_the_run(self) -> None:
        for moved, moves_it, outcome in _MOVEMENTS:
            with self.subTest(moved=moved):
                self.setUp()
                moves_it(self)

                self.assertEqual(self._last_word(), outcome)

                finish = self.landed()
                self.assertIsNone(_captured.recorded(finish))
                self.assertTrue(_captured.retired(finish))
                self.assert_dormant(self.abandoned())

    def test_an_unread_reading_holds_the_run(self) -> None:
        for unread, unreads_it in _UNREAD:
            with self.subTest(unread=unread):
                self.setUp()

                self.assertEqual(self._last_word(meanwhile=unreads_it), _HELD)

                self.assert_dormant()

    def test_no_unread_reading_hides_movement(self) -> None:
        # Put back afterwards, everything reads as it did: the run stays
        # abandoned, and nothing is held or carried over it.
        for unreads_it, moves_it, outcome in _BESIDE:
            with self.subTest(unread=unreads_it, moved=moves_it):
                self.setUp()
                world, body = replace(self.world), self.issue.body
                unreads_it(self)
                moves_it(self)

                self.assertEqual(self._last_word(), outcome)

                self.world = world
                self.issue.body = body
                self.gh.report_failures.unreadable.clear()
                self.assertIsNone(self.asks(_captured.stands_before_the_route, self.landed()))
                self.assert_dormant(self.abandoned())

    def test_a_stop_stays_the_answer(self) -> None:
        # The run is still proved behind a write that did not land, and
        # abandoned there where it moved; the stop is what the route comes to.
        for moves_it, records in _STOPS:
            with self.subTest(records=records.__name__):
                self.setUp()
                moves_it(self)
                finish = self.landed()
                refused = FinishOutcome.REFUSED

                stopped = self.asks(_captured.stands_before_the_route, finish, behind=refused)

                self.assertEqual(stopped, refused)
                self.assert_dormant(records(self))

    def test_a_whole_word_proves_the_run_again(self) -> None:
        # The settled report is rewritten by hand at its location on the pull
        # request, every pinned record left as it was: the last word alone
        # reads those records and keeps the run, as it always has, while one
        # asked whole proves the run again first, reads the report moved
        # under it, and abandons it into history, its binding kept whole.
        for whole, records in _WHOLE:
            with self.subTest(whole=whole):
                self.setUp()
                self.edits_the_report()

                self.assertIsNone(self.asks(_captured.stands_before_the_route, self.landed(), whole=whole))

                self.assert_dormant(records(self))
                if whole:
                    recorded = self.captured
                    entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
                    self.assertEqual((entry.revision, entry.binding), (recorded.revision, recorded.binding))

    def _last_word(self, meanwhile=moves.unmoved) -> FinishOutcome | None:
        """The route once the captured run is proved again and held to the last word, `meanwhile` behind the read."""
        finish = self.landed()
        meanwhile(self)
        proof = self.asks(_captured.proved_again, finish, self.captured)
        return self.asks(_captured.stands_before_the_route, finish, proof=proof)


# A field the tick staged and has not written, and what it staged it as.
_STAGED = "dev_session_id"
_STAGED_SESSION = "staged-by-the-tick"


class AbandonmentWriteTest(unittest.TestCase, captured_support.CapturedEvidenceCase):
    """The abandonment is a write of its own, kept off every record it does not retire."""

    def setUp(self) -> None:
        captured_support.CapturedEvidenceCase.setUp(self)

    def test_it_keeps_what_another_road_wrote(self) -> None:
        finish = self.landed()
        moves.later_review(self)
        self.state.set(_UNKNOWN, "kept")
        self.gh.write_pinned_state(self.issue, self.state)
        written = readings.pinned(self)

        self.assertIsNone(self.asks(_captured.stands_before_the_route, finish))

        durable = readings.pinned(self)
        kept = (durable[_UNKNOWN], durable[_SUBJECT])
        self.assertEqual(kept, (written[_UNKNOWN], written[_SUBJECT]))
        self.assert_dormant(self.abandoned())

    def test_it_lands_what_the_tick_staged(self) -> None:
        # The tick staged a field it has not written when the checkout
        # left the landed head: the abandonment lands it once beside the
        # retired run, and the tick goes on holding it as written.
        finish = self.landed()
        finish.state.set(_STAGED, _STAGED_SESSION)
        self.world.checkout_head = _world.STRAY_SHA

        self.assertEqual(self.asks(_captured.stands_before_the_route, finish), _HELD)

        durable = readings.pinned(self)
        staged = (finish.state.get(_STAGED), durable.get(_STAGED))
        self.assertEqual(staged, (_STAGED_SESSION, _STAGED_SESSION))
        self.assert_dormant(self.abandoned())

    def test_a_replaced_attempt_keeps_its_records(self) -> None:
        # Another road replaced the attempt once the finish read the comment,
        # which has no room for the abandonment: the stale run is held rather
        # than dropped over the replacement, whose base tip stands as written.
        moves.fills_the_comment(self)
        finish = self.landed()
        self.world.checkout_head = _world.STRAY_SHA
        self.attempts(support.SQUASHED_SHA)
        written = readings.pinned(self)

        self.assertEqual(self.asks(_captured.stands_before_the_route, finish), _HELD)

        self.assertEqual(readings.pinned(self), written)
        self.assert_dormant()

    def test_an_unread_comment_holds_until_it_reads(self) -> None:
        # A head the base advanced past is set aside in a checkpoint whose
        # reading of the comment fails once: the continuation holds with the
        # run kept as recorded, and the next finish sets it aside.
        finish = self.landed()
        self.gh.read_pinned_state = captured_support.FailsOnce(self.gh.read_pinned_state)

        self.assertEqual(self.asks(_captured.sets_aside, finish), _HELD)
        self.assert_dormant()

        self.assertIsNone(self.asks(_captured.sets_aside, self.landed()))
        self.assert_dormant(self.abandoned())

    def test_no_room_refuses_the_run_for_good(self) -> None:
        # The run is dropped with no history entry, and the base tip its replay
        # was made onto blanked with it, so no later reading of the base proves
        # anything a run or carry could be made or routed on.
        moves.fills_the_comment(self)
        self.world.checkout_head = _world.STRAY_SHA

        self.assertEqual(self.asks(_captured.stands_before_the_route, self.landed()), _HELD)

        finish = self.landed()
        refused = _proof.standing_refusal(finish)
        self.assertIsNone(finish.state.get(readings.KEY_REWRITE_BASE))
        self.assertEqual(
            (refused.holds, refused.refusal), (False, "the attempt recorded no base tip its replay was made onto"),
        )
        self.assert_dormant(captured_support.dropped(self))

    def test_a_comment_taking_no_write_keeps_the_run(self) -> None:
        self.world.checkout_head = _world.STRAY_SHA
        self.gh.pinned_failures.refused.add(self.issue.number)

        self.assertEqual(self.asks(_captured.stands_before_the_route, self.landed()), _HELD)

        self.assert_dormant()


if __name__ == "__main__":
    unittest.main()
