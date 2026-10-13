# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence proved ready again, invalidated into history where it moved, and held where nobody can tell.

The settled case (`rewrite_captured_test_support.SettledEvidenceCase`): issue
#7's landed head, its evidence settled under the anchor -- the run the finish
made on the rebased head, or the anchor's run carried onto a squash whose tree
is the tested one -- and the finish dead before it announced the landing. Each
case asks one readiness primitive directly over the finish a later tick's
recovery holds, while another road moves something (`rewrite_settled_moves`).

The proof (`settled_word`) tells evidence that stands from movement, and both
from a reading nobody could take or a record beside it nobody can resolve;
`stands_ready` routes, invalidates, or holds over that answer, a readable
revision spent past the evidence invalidating it rather than holding every
poll. The invalidation (`invalidates`) keeps the evidence whole in history
beside whatever another road wrote, over the comment read afresh or the
tick's own copy, and leaves an attempt or evidence another road put in place
alone; where no history entry fits, the base tip is blanked instead, so
putting back what moved and making room still invalidates it.
`invalidates_behind` invalidates over a refusal that read a binding record
moved, put back or not. Nothing runs, launches, or relabels.
"""
from __future__ import annotations

import contextlib
import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.workflow.engine import (
    rewrite_finish_readiness as _readiness,
    rewrite_finish_writes as _writes,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_captured_test_support as settled_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
    verification_evidence_test_support as support,
    verification_world_fixture as world,
)

_HELD = FinishOutcome.HELD

_REFUSED = FinishOutcome.REFUSED

# The head whose run the finish settled, and the squash it carried a run onto.
_HEADS = (settled_support.REBASED, support.SQUASHED_SHA)

_PR_NUMBER = "pr_number"

_HANDOFF = "verification_evidence_handoff"

_HISTORY = "verification_evidence_history"

# A revision floor no reader can take a number from.
_UNREADABLE = "x"

# The client's steps a move races past: the pinned comment's reading, and the
# proof's re-read of the settled report.
_READS_THE_COMMENT = "read_pinned_state"

_READS_THE_REPORT = "reread_report_location"

# The pull request another road repoints the issue at.
_REPOINTED = support.PR_NUMBER + 1

# A record another road writes beside the evidence, which nothing here owns.
_UNKNOWN = "another_roads_record"


class _Move(NamedTuple):
    """What another road does under the settled evidence, and what the route reading it comes to."""

    name: str
    makes: Callable
    outcome: FinishOutcome | None = None


# Movement: the route goes on with nothing current, or holds behind the
# invalidation where the base went elsewhere.
_MOVEMENTS = (
    _Move("the requirements edited", settled_moves.edits_the_requirements),
    _Move("a later review", settled_moves.reviews_again),
    _Move("another command configured", settled_moves.reconfigures),
    _Move("the settled report edited on the pull request", lambda case: case.edits_the_report()),
    _Move("the base moved", lambda case: setattr(case.world, "base", _BaseStanding.MOVED), _HELD),
)

# A reading nobody could take, or a record beside the evidence nobody can
# resolve: each holds the route, and none is movement. The pull request is
# read by the proof alone, so its hold is the first reading's, kept beside
# whatever the last word reads.
_HOLDS = (
    _Move("the pinned comment unread", moves.unreadable, _HELD),
    _Move(
        "the pull request unread",
        lambda case: case.enterContext(
            patch.object(case.gh, "get_pr", side_effect=RuntimeError("GitHub did not answer")),
        ),
        _HELD,
    ),
    _Move("the base unread", lambda case: setattr(case.world, "base", _BaseStanding.UNREAD), _HELD),
    _Move("a newer transaction pending beside it", settled_moves.records_a_newer_one, _HELD),
    _Move(
        "a handoff not naming it",
        lambda case: settled_moves.writes_over(case, _HANDOFF, None),
        _HELD,
    ),
    _Move(
        "a revision floor nobody can read",
        lambda case: settled_moves.writes_over(case, readings.KEY_REVISION_FLOOR, _UNREADABLE),
        _HELD,
    ),
)

# What another road put in place of what the invalidation was decided on.
_REPLACEMENTS = (
    _Move("the attempt replaced", lambda case: settled_moves.writes_over(
        case, readings.KEY_PENDING_PUSH, support.SQUASHED_SHA,
    )),
    _Move("the evidence retired", settled_moves.retires_it),
)

# The comment filled to its limit ahead of the proof, or just behind its
# reading of the comment; each answers the context the proof is asked inside.
_FILLINGS = (
    ("ahead of the proof", lambda case: contextlib.nullcontext(moves.fills_the_comment(case))),
    (
        "behind the proof's reading of it",
        lambda case: settled_moves.raced_past(case, _READS_THE_COMMENT, moves.fills_the_comment),
    ),
)


# The pull request read as GitHub answers it, or left unanswered.
_PULL_REQUESTS = (
    ("the pull request read", lambda _case: contextlib.nullcontext()),
    (
        "the pull request unread",
        lambda case: patch.object(case.gh, "get_pr", side_effect=RuntimeError("GitHub did not answer")),
    ),
)


# What goes unanswered once records the proof's first reading heard moved are
# put back: the pull request, or the last word's own reading of the comment,
# which holds the route behind the invalidation.
_UNANSWERED_BEHIND_A_RESTORE = (
    _Move(
        "the pull request",
        lambda case: case.enterContext(
            patch.object(case.gh, "get_pr", side_effect=RuntimeError("GitHub did not answer")),
        ),
    ),
    _Move(
        "the last word's reading of the comment",
        lambda case: case.gh.pinned_failures.unanswered_once.add(case.issue.number),
        _HELD,
    ),
)


# Records that hold beside a newer transaction abandoned past the evidence.
_BESIDE_AN_OUTRANKING_ONE = (
    _Move("the handoff gone", lambda case: settled_moves.writes_over(case, _HANDOFF, None)),
    _Move(
        "the revision floor unreadable",
        lambda case: settled_moves.writes_over(case, readings.KEY_REVISION_FLOOR, _UNREADABLE),
    ),
)

# What moves while the proof's last request -- the last word's own reading of
# the comment -- is answered, and the route the readings behind it come to:
# held behind the invalidation where the checkout left the landed head.
_BEHIND_THE_LAST_READ = (
    _Move(
        "the checkout moved off the head",
        lambda case: setattr(case.world, "checkout_head", support.TESTED_SHA),
        _HELD,
    ),
    _Move("another command configured", settled_moves.reconfigures),
)


class _Road(NamedTuple):
    """Which copy an invalidation lands over, and the report revision the review then carries."""

    name: str
    reads: Callable
    reviewed: int = 2


_ROADS = (
    _Road("the comment read afresh", lambda _case: contextlib.nullcontext()),
    _Road("the comment unread", lambda case: patch.object(
        case.gh, _READS_THE_COMMENT, settled_support.FailsOnce(case.gh.read_pinned_state),
    )),
    _Road(
        "its write refused over a review",
        lambda case: settled_moves.raced_past(case, _READS_THE_COMMENT, settled_moves.reviews_again),
        reviewed=3,
    ),
)


class _Stop(NamedTuple):
    """Where a finish's write stopped, what its refusal read, whether the issue was edited, and the answer."""

    stopped: FinishOutcome | None
    observed: tuple
    edited: bool
    invalidated: bool


# The binding record a refusal read moved is put back before anything asks.
_STOPS = (
    _Stop(_REFUSED, (_writes.BINDING_MOVED,), edited=False, invalidated=True),
    _Stop(_REFUSED, (), edited=True, invalidated=True),
    _Stop(_REFUSED, (), edited=False, invalidated=False),
    _Stop(FinishOutcome.UNCONFIRMED, (_writes.BINDING_MOVED,), edited=True, invalidated=False),
    _Stop(None, (_writes.BINDING_MOVED,), edited=True, invalidated=False),
)


class ReadinessTest(settled_support.SettledEvidenceCase, unittest.TestCase):
    """The proof tells ready evidence from movement and from what nobody can read, and the route follows it."""

    def test_ready_evidence_routes_as_it_stands(self) -> None:
        for head in _HEADS:
            with self.subTest(head=head):
                self.settles(head)
                finish = self.landed()

                word = self.asks(_readiness.settled_word, finish, self.settled)
                outcome = self.asks(_readiness.stands_ready, finish, self.settled)

                self.assertEqual((word, outcome), ((None, None), None))
                self.assert_dormant()

    def test_movement_invalidates_it_whole(self) -> None:
        for head, movement in product(_HEADS, _MOVEMENTS):
            with self.subTest(head=head, moved=movement.name):
                self.settles(head)
                finish = self.landed()
                movement.makes(self)

                moved = self.asks(_readiness.settled_word, finish, self.settled)[0]
                outcome = self.asks(_readiness.stands_ready, finish, self.settled)

                self.assertEqual((moved.proved, outcome), (False, movement.outcome))
                self.assert_invalidated()

    def test_an_outranking_revision_invalidates_it(self) -> None:
        # A newer transaction recorded beside it and abandoned spent a
        # revision past it for good, which a pull request nobody could read
        # hides nothing of: no route carries it and no poll holds.
        for name, pull_request in _PULL_REQUESTS:
            with self.subTest(name):
                self.setUp()
                finish = self.landed()
                newer = settled_moves.records_a_newer_one(self, abandoned=True)
                outranked = self.gh.read_pinned_state(self.issue)

                with pull_request(self):
                    self.assertIsNone(self.asks(_readiness.stands_ready, finish, self.settled))

                self.assertEqual(_readiness.beside_current(outranked, self.settled), "")
                self.assert_invalidated((newer.receipt, readings.ABANDONED))

    def test_a_damaged_history_hides_no_outranking(self) -> None:
        # A newer transaction abandoned past the evidence, its history entry
        # readable beside another that is not, and a revision floor nobody
        # can read: the history will not read whole, but the entry that reads
        # on its own still outranks the evidence, which is invalidated with
        # the floor holding the route.
        finish = self.landed()
        settled_moves.records_a_newer_one(self, abandoned=True)
        pinned = self.gh.pinned_data(self.issue.number)
        pinned[readings.KEY_REVISION_FLOOR] = _UNREADABLE
        pinned[_HISTORY] = [*pinned[_HISTORY], {}]
        self.puts_back(pinned)

        moved = self.asks(_readiness.settled_word, finish, self.settled)[0]
        outcome = self.asks(_readiness.stands_ready, finish, self.settled)

        self.assertEqual((moved, outcome), (_readiness._OUTRANKED, _HELD))
        self.assertEqual(self.records()[:2], (None, None))
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        self.assertIn(_records.HistoricalEvidence.of(self.settled, _records.Retirement.INVALIDATED), history)

    def test_a_hold_beside_moved_records_still_moves(self) -> None:
        # The review moves beside a revision floor nobody can read, and is put
        # back just behind the proof's reading of the comment: the floor still
        # holds the route, but the evidence is invalidated over what that
        # reading established, so a readable floor afterwards revives nothing.
        finish = self.landed()
        floor = self.gh.pinned_data(self.issue.number)[readings.KEY_REVISION_FLOOR]
        settled_moves.writes_over(self, readings.KEY_REVISION_FLOOR, _UNREADABLE)
        kept = self.gh.pinned_data(self.issue.number)
        settled_moves.reviews_again(self)

        with settled_moves.raced_past(self, _READS_THE_COMMENT, lambda case: case.puts_back(kept)):
            outcome = self.asks(_readiness.stands_ready, finish, self.settled)

        self.assertEqual(outcome, _HELD)
        self.assert_invalidated()
        settled_moves.writes_over(self, readings.KEY_REVISION_FLOOR, floor)
        retried = self.asks(_readiness.stands_ready, self.landed(), self.settled)
        self.assertEqual(retried, _HELD)
        self.assert_invalidated()

    def test_a_hold_beside_an_outranking_one_moves(self) -> None:
        # A newer transaction abandoned beside the evidence outranks it, its
        # history entry readable, beside a handoff gone or a revision floor
        # nobody can read: that record holds the route, but the outranked
        # evidence is invalidated rather than held over for good.
        for hold in _BESIDE_AN_OUTRANKING_ONE:
            with self.subTest(held=hold.name):
                self.setUp()
                finish = self.landed()
                newer = settled_moves.records_a_newer_one(self, abandoned=True)
                hold.makes(self)

                outcome = self.asks(_readiness.stands_ready, finish, self.settled)

                self.assertEqual(outcome, _HELD)
                self.assert_invalidated((newer.receipt, readings.ABANDONED))

    def test_what_nobody_can_read_holds(self) -> None:
        for hold in _HOLDS:
            with self.subTest(held=hold.name):
                self.setUp()
                finish = self.landed()
                hold.makes(self)

                moved, held = self.asks(_readiness.settled_word, finish, self.settled)
                outcome = self.asks(_readiness.stands_ready, finish, self.settled)

                self.assertEqual((moved, held.holds, outcome), (None, True, hold.outcome))
                self.gh.pinned_failures.unreadable.clear()
                self.assertEqual(self.records()[1], self.settled)


class WhileProvedTest(settled_support.SettledEvidenceCase, unittest.TestCase):
    """What another road moves while the proof's requests are answered is read behind them."""

    def test_one_recorded_while_proved_holds(self) -> None:
        # Another road records a newer transaction while the proof re-reads
        # the settled report: the evidence records read behind every request
        # see it pending, so the route holds with the evidence current and
        # the transaction left for the next finish to answer.
        finish = self.landed()

        with settled_moves.raced_past(self, _READS_THE_REPORT, settled_moves.records_a_newer_one):
            outcome = self.asks(_readiness.stands_ready, finish, self.settled)

        pending, *left = self.records()
        self.assertEqual((outcome, left), (_HELD, [self.settled, self.history]))
        self.assertEqual(pending.revision, self.settled.revision + 1)

    def test_one_abandoned_while_proved_moves(self) -> None:
        # Another road records a newer transaction and abandons it while the
        # proof re-reads the settled report: its revision outranks the
        # evidence for good, so the evidence is invalidated and the route
        # goes on with nothing current.
        finish = self.landed()
        abandons = partial(settled_moves.records_a_newer_one, abandoned=True)

        with settled_moves.raced_past(self, _READS_THE_REPORT, abandons):
            self.assertIsNone(self.asks(_readiness.stands_ready, finish, self.settled))

        abandoned = self.records()[2][-1]
        self.assertEqual(abandoned[1], readings.ABANDONED)
        self.assert_invalidated(abandoned)

    def test_a_redescribed_handoff_moves(self) -> None:
        # Another road rewrites the handoff's pull request or head while the
        # proof re-reads the settled report, its receipt and revision still
        # naming the evidence: the handoff describes it no more, as the proof
        # itself reads it, so the evidence is invalidated -- and the handoff
        # put back before the next proof revives nothing.
        for field, written in (("pr", _REPOINTED), ("head", support.TESTED_SHA)):
            with self.subTest(field=field):
                self.setUp()
                finish = self.landed()
                handoff = self.gh.pinned_data(self.issue.number)[_HANDOFF]
                moved = {**handoff, field: written}

                with settled_moves.raced_past(self, _READS_THE_REPORT, partial(
                    settled_moves.writes_over, key=_HANDOFF, written=moved,
                )):
                    self.assertIsNone(self.asks(_readiness.stands_ready, finish, self.settled))

                self.assert_invalidated()
                settled_moves.writes_over(self, _HANDOFF, handoff)
                finish = self.landed()
                self.assertEqual(self.asks(_readiness.stands_ready, finish, self.settled), _HELD)
                self.assert_invalidated()

    def test_first_read_requirements_beside_a_hold(self) -> None:
        # The handoff is gone, and the issue was edited when the proof first
        # read it and put back just behind its reading of the comment: the
        # missing handoff holds, but the requirements that snapshot read moved
        # all the same, so the evidence is invalidated, and the handoff put
        # back afterwards revives nothing.
        finish = self.landed()
        handoff = self.gh.pinned_data(self.issue.number)[_HANDOFF]
        settled_moves.writes_over(self, _HANDOFF, None)
        written = self.issue.body
        settled_moves.edits_the_requirements(self)
        restores = settled_moves.raced_past(
            self, _READS_THE_COMMENT, lambda case: setattr(case.issue, "body", written),
        )

        with self.snapshots_the_issue(), restores:
            self.assertEqual(self.asks(_readiness.stands_ready, finish, self.settled), _HELD)

        self.assert_invalidated()
        settled_moves.writes_over(self, _HANDOFF, handoff)
        finish = self.landed()
        self.assertEqual(self.asks(_readiness.stands_ready, finish, self.settled), _HELD)
        self.assert_invalidated()

    def test_restored_records_still_invalidate(self) -> None:
        # The review moves ahead of the proof's read of the comment and is put
        # back just behind it, and then the pull request or the last word's
        # own reading of the comment goes unanswered: the records the first
        # reading heard are movement all the same, and a retry over
        # everything put back finds nothing current to revive.
        for unanswered in _UNANSWERED_BEHIND_A_RESTORE:
            with self.subTest(unanswered=unanswered.name):
                self.setUp()
                self._restores_behind_the_first_read(unanswered)

    def test_a_move_behind_the_last_read_is_seen(self) -> None:
        # However many times the proof reads the comment, a move made while
        # the last of those readings is answered is still read: the evidence
        # is invalidated, and nothing current is left to route.
        for movement in _BEHIND_THE_LAST_READ:
            with self.subTest(moved=movement.name):
                self.setUp()
                finish = self.landed()
                last = self.calls_to(_READS_THE_COMMENT, _readiness.settled_word, finish, self.settled)

                with settled_moves.raced_past(self, _READS_THE_COMMENT, movement.makes, last):
                    outcome = self.asks(_readiness.stands_ready, finish, self.settled)

                self.assertEqual(outcome, movement.outcome)
                self.assert_invalidated()

    def _restores_behind_the_first_read(self, unanswered: _Move) -> None:
        """The review moved, put back behind the proof's first read with `unanswered` made, then a retry."""
        finish = self.landed()
        kept = readings.pinned(self)
        settled_moves.reviews_again(self)
        restores = settled_moves.raced_past(self, _READS_THE_COMMENT, lambda case: (
            case.puts_back(kept), unanswered.makes(case),
        ))

        with restores:
            self.assertEqual(self.asks(_readiness.stands_ready, finish, self.settled), unanswered.outcome)

        self.assert_invalidated()
        retried = self.asks(_readiness.stands_ready, self.landed(), self.settled)
        self.assertEqual(retried, _HELD)
        self.assert_invalidated()


class InvalidationTest(settled_support.SettledEvidenceCase, unittest.TestCase):
    """The invalidation lands whole beside another road's records, or records the movement where it cannot."""

    def test_it_lands_beside_another_roads_records(self) -> None:
        # Over the comment read afresh, or over the tick's own copy where that
        # comment would not read or another road's review refused the write.
        for head, road in product(_HEADS, _ROADS):
            with self.subTest(head=head, road=road.name):
                self.settles(head)
                finish = self.landed()
                settled_moves.writes_over(self, _UNKNOWN, "kept")

                with road.reads(self):
                    self.assertTrue(self.asks(_readiness.invalidates, finish, self.settled))

                self.assert_invalidated()
                pinned = readings.pinned(self)
                kept = (pinned[_UNKNOWN], pinned["review_subject"]["report_revision"])
                self.assertEqual(kept, ("kept", road.reviewed))

    def test_what_another_road_replaced_stays(self) -> None:
        # Whichever copy it would land over, nothing is written over that road.
        for replacement, road in product(_REPLACEMENTS, _ROADS[:2]):
            with self.subTest(replaced=replacement.name, road=road.name):
                self.setUp()
                finish = self.landed()
                replacement.makes(self)
                left = readings.pinned(self)

                with road.reads(self):
                    self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))

                self.assertEqual(readings.pinned(self), left)

    def test_a_successor_is_never_marked_moved(self) -> None:
        # Another road settles a successor in place of the evidence over a
        # history its abandoned newer transactions filled, so the superseded
        # entry falls out and the history reads as the tick read it: with the
        # comment unread, neither the invalidation nor the blank tip lands.
        for _ in range(_settlement._HISTORY_KEPT):
            settled_moves.records_a_newer_one(self, abandoned=True)
        finish = self.landed()
        newer = settled_moves.records_a_newer_one(self)
        state = self.gh.read_pinned_state(self.issue)
        state = _settlement.settled_state(state, newer, newer.revision, None)
        self.gh.write_pinned_state(self.issue, state)
        left = self.gh.pinned_data(self.issue.number)
        self.assertEqual(_settlement.read_evidence_history(state), _settlement.read_evidence_history(finish.state))

        with _ROADS[1].reads(self):
            self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))

        self.assertEqual(self.gh.pinned_data(self.issue.number), left)

    def test_a_repointed_publication_still_takes_it(self) -> None:
        # Another road repoints the issue's pull request while the comment
        # will not read: the tick's own copy still takes the invalidation, or
        # the blank tip where history has no room, the repoint kept as that
        # road wrote it, so putting the pull request back revives nothing.
        for fills in (moves.unmoved, moves.fills_the_comment):
            with self.subTest(fills=fills.__name__):
                self.setUp()
                room = fills is moves.unmoved
                finish = self.landed()
                settled_moves.writes_over(self, _PR_NUMBER, _REPOINTED)
                fills(self)

                with _ROADS[1].reads(self):
                    landed = self.asks(_readiness.invalidates, finish, self.settled)

                pinned = readings.pinned(self)
                self.assertEqual((landed, pinned[_PR_NUMBER]), (room, _REPOINTED))
                self.assertEqual(pinned[readings.KEY_REWRITE_BASE], world.BASE_TIP if room else None)
                settled_moves.writes_over(self, _PR_NUMBER, support.PR_NUMBER)
                if not room:
                    moves.makes_room(self)
                self.asks(_readiness.stands_ready, self.landed(), self.settled)
                self.assert_invalidated()

    def test_no_room_blanks_the_base_tip(self) -> None:
        # The blank tip records the movement the proof read, so the
        # requirements put back and room made leave nothing current to revive.
        for name, filling in _FILLINGS:
            with self.subTest(filled=name):
                self.setUp()
                finish = self.landed()
                written = self.issue.body
                settled_moves.edits_the_requirements(self)

                with filling(self):
                    self.assertEqual(self.asks(_readiness.stands_ready, finish, self.settled), _HELD)

                self.assertEqual(self.records(), self.kept())
                self.assertIsNone(readings.pinned(self)[readings.KEY_REWRITE_BASE])
                self.issue.body = written
                moves.makes_room(self)
                self.assertIsNone(self.asks(_readiness.stands_ready, self.landed(), self.settled))
                self.assert_invalidated()

    def test_a_write_that_did_not_land_holds(self) -> None:
        # Its answer lost, the invalidation is on the comment all the same;
        # refused outright, nothing is.
        for failing in ("lost", "refused"):
            with self.subTest(failing=failing):
                self.setUp()
                finish = self.landed()
                failures = getattr(self.gh.pinned_failures, failing)
                failures.add(self.issue.number)

                self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))

                failures.clear()
                landed = self.invalidated_whole() if failing == "lost" else self.kept()
                self.assertEqual(self.records(), landed)
                self.assertEqual(readings.pinned(self)[readings.KEY_REWRITE_BASE], world.BASE_TIP)


class InvalidationBehindTest(settled_support.SettledEvidenceCase, unittest.TestCase):
    """A refused write that read a binding record moved invalidates; any other stop proves again or passes."""

    def test_each_stop_comes_to_its_reading(self) -> None:
        for stop in _STOPS:
            with self.subTest(stop=stop):
                self.setUp()
                finish = self.landed()
                if stop.edited:
                    settled_moves.edits_the_requirements(self)

                answered = self.asks(_readiness.invalidates_behind, finish, stop.stopped, list(stop.observed))

                left = self.invalidated_whole() if stop.invalidated else self.kept()
                self.assertEqual((answered, self.records()), (stop.stopped, left))


if __name__ == "__main__":
    unittest.main()
