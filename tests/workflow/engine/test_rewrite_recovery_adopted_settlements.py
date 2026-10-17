# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A settlement another road made while the recovery published the run, adopted out of step with the records beside it.

A finish recorded its run for the landed head and died posting its artifact,
so the recovery publishes and settles it with the attempt still standing. Just
as the artifact is posted, another road settles that very run itself and
leaves the records beside it out of step with it: it records a newer
transaction and retires it, spending a revision past the run, or it drops the
handoff that names the run. The recovery's own settlement is refused over that
moved comment, and the ledger entry it then commits alone takes the comment in
as it stands. A dropped handoff is held to the same agreement the finish asks
of settled evidence before it resolves anything, so the route is held:
nothing announced, relabelled, or retired, the round as it was spent, and the
records exactly as that road left them -- poll after poll. Nothing runs
again, nothing is pushed, and no developer is launched.

The evidence phase asked directly (`settled_finish_support`) holds over the
dropped handoff the same way, reads a revision spent past the run as
outranking it, and
invalidates a run read moving under report 3 whole however soon report 2 is
put back -- also where another finish of the landing announced the run
meanwhile, or routed it, over the comment as it stands: marked in its
handoff's place where the comment is full, retired whole once room is made,
and a successor settled under its own receipt kept. A run settled and
announced with nothing else moving stays current. The whole coordinator asked
directly holds over the dropped handoff with nothing
announced, and invalidates an outranked or moved settlement ahead of the
announcement, routing the head once to the fresh reviewer.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    rewrite_finish_unconfirmed as _unconfirmed,
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
    settled_route_support as route,
    verification_report_fixture as _report,
)
from tests.workflow.engine.adopted_settlement_support import drops_the_handoff, settles_the_run, spends_a_revision_past
from tests.workflow.interleaving import _RacesPastTheCall

# What another road leaves beside the run it settled, and the revision floor
# that leaves: one past the run's, or the run's own.
# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# The proof's observation of a refusal, read before any case stands in for it.
_OBSERVED = "observes"
_OBSERVES = getattr(_proof.ProofReading, _OBSERVED)

# Whether another finish routes the run before report 3 moves, what is made
# behind that route, and how the run then reads (`_assert_invalidated`).
_ROUTED_ELSEWHERE = (
    (True, None, readings.INVALIDATED),
    (False, None, readings.INVALIDATED),
    (True, finish_moves.fills_the_comment, None),
    (False, finish_moves.fills_the_comment, None),
    (True, partial(settled.records_a_newer_run, settles=True), "superseded"),
)

# How the other finish's announcement of the run ends, what the phase behind
# it answers, and whether that finish relabelled the issue.
_ANNOUNCED_ELSEWHERE = (
    (handoff.BEFORE_THE_RELABEL, None, False),
    (handoff.BEFORE_THE_RETIREMENT, None, True),
    (None, FinishOutcome.HELD, True),
)


class _MovesTheReport:
    """Another road settling the run and then report 3 of its head, report 2 put back once the proof read it."""

    def __init__(self) -> None:
        self._case = None
        self._replaced: dict = {}
        self._behind = None

    def __call__(self, reading, refused, over=None) -> None:
        _OBSERVES(reading, refused, over)
        if self._replaced and refused is not None and _MOVED_RECORDS[0] in refused.refusal:
            state = self._case.gh.read_pinned_state(self._case.issue)
            for key, recorded in self._replaced.items():
                state.set(key, recorded)
            self._case.gh.write_pinned_state(self._case.issue, state)
            self._replaced = {}
            behind = self._behind
            self._behind = None
            if behind is not None:
                behind()

    def settles(self, case: support.CapturedRunCase, captured) -> None:
        """Settle `captured` over the artifact just posted, then report 3 of its head, as another road would."""
        case.state = settles_the_run(case, captured)
        self._moves(case, captured.binding.target.target_head)

    def finishes_then_settles(self, case: _AdoptionCase, captured) -> None:
        """Have another finish of the landing settle `captured` and announce it, dying at its relabel; then report 3."""
        case.announces_elsewhere(captured)
        case.state = case.gh.read_pinned_state(case.issue)
        self._moves(case, captured.binding.target.target_head)

    def finishes_around(self, case: _AdoptionCase, captured, first: bool = True, then=None) -> None:
        """Have another finish route `captured` whole, `then` behind it, before report 3 moves or once it is read."""
        routes = partial(self._routes, case, captured, then)
        if first:
            routes()
        else:
            self._behind = routes
        case.state = case.gh.read_pinned_state(case.issue)
        self._moves(case, captured.binding.target.target_head)

    def _routes(self, case: _AdoptionCase, captured, then) -> None:
        """Route `captured` whole as another finish of the landing would, `then` made behind it."""
        case.announces_elsewhere(captured, None)
        if then is not None:
            then(case)

    def _moves(self, case: support.CapturedRunCase, head: str) -> None:
        """Settle and review report 3 of `head` over `case.state`, keeping the records it replaces."""
        self._case = case
        self._replaced = {key: case.state.get(key) for key in _MOVED_RECORDS}
        _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=head)
        case.gh.write_pinned_state(case.issue, case.state)


class _AdoptionCase(support.CapturedRunCase):
    """A captured run another road settles just as a recovery's finish posts it."""

    def races_the_post(self, settles):
        """A fresh case's captured run, `settles` made just behind the next post of its artifact; the run.

        The landed head is kept as `head`.
        """
        self.setUp()
        head, captured = self.captures()
        self.head = head
        races = _RacesPastTheCall(self.gh.publish_verification_artifact, 1, partial(settles, self, captured))
        self.enterContext(patch.object(self.gh, support.POST, races))
        return captured

    def polls_beside(self, settles):
        """`races_the_post`, then three whole recoveries; the run."""
        captured = self.races_the_post(settles)
        self.recovers()
        self.recovers()
        self.recovers()
        return captured

    def announces_elsewhere(self, captured, died: handoff.Boundary | None = handoff.BEFORE_THE_RELABEL) -> None:
        """Have another finish of the landing settle `captured` and announce it, dying at `died` or routing it whole."""
        finishing = partial(self.finishes, captured.binding.target.target_head, FinishRoad.RECOVERY)
        handoff.dies_at(self.gh, died, finishing)

    def assert_held_as_settled(self, captured) -> None:
        """`captured` current as the other road settled it, the floor at it, the attempt standing, nothing made."""
        pinned = readings.pinned(self)
        self.assertEqual(readings.records(pinned)[1].receipt, captured.receipt)
        self.assertEqual(pinned[readings.KEY_REVISION_FLOOR], captured.revision)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
        self.assert_unannounced()
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))

    def routes_elsewhere(self, first: bool, then):
        """Race another finish's whole route of the run around report 3 (`_MovesTheReport.finishes_around`); the run.

        The evidence phase is asked once behind that race, and holds.
        """
        moves = _MovesTheReport()
        with patch.object(_proof.ProofReading, _OBSERVED, side_effect=moves, autospec=True):
            captured = self.races_the_post(partial(moves.finishes_around, first=first, then=then))
            self.assertEqual(self.resolves(self.head), FinishOutcome.HELD)
        return captured

    def assert_whole(self, captured) -> None:
        """The entry under `captured`'s receipt keeps its revision and whole binding, its artifact posted once."""
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        entry = next(entry for entry in history if entry.receipt == captured.receipt)
        self.assertEqual((entry.revision, entry.binding), (captured.revision, captured.binding))
        self.assertEqual(self.posted(captured), [captured.commands])

    def assert_invalidated(self, captured, retired: str | None = readings.INVALIDATED) -> None:
        """`captured` retired into history as `retired` with nothing pending, report 2 current as put back.

        Invalidated, nothing is current and the entry is whole; superseded,
        the successor is. None is `captured` still current with the mark
        naming it in its handoff's place: the movement read under it,
        recorded where history had no room.
        """
        pinned = readings.pinned(self)
        pending, current, history = readings.records(pinned)
        self.assertIsNone(pending)
        self.assertEqual(pinned[_MOVED_RECORDS[0]]["revision"], 2)
        if retired is None:
            self.assertEqual(current.receipt, captured.receipt)
            self.assertEqual(pinned[_records.EVIDENCE_HANDOFF], {"moved": captured.receipt})
            return
        self.assertEqual(history[-1], (captured.receipt, retired))
        self.assertEqual(current is None, retired == readings.INVALIDATED)
        if retired == readings.INVALIDATED:
            self.assert_whole(captured)


class AdoptedSettlementRecoveryTest(_AdoptionCase, unittest.TestCase):
    """Records another road settled out of step while the run was published hold the route, poll after poll."""

    def test_an_adopted_settlement_out_of_step_holds(self) -> None:
        # The run is current as that road settled it, its handoff dropped and
        # left so, and the attempt stands with nothing announced, however
        # often the recovery polls.
        captured = self.polls_beside(drops_the_handoff)

        self.assert_held_as_settled(captured)


class SettledAdoptionTest(_AdoptionCase, settled.SettledRunCase, unittest.TestCase):
    """The evidence phase holds over a dropped handoff, and invalidates an outranked or moved settlement."""

    def test_an_adopted_settlement_out_of_step_holds(self) -> None:
        # The run is current as that road settled it, its handoff dropped
        # and left so, and the attempt stands with nothing announced, however
        # often the phase is asked; the artifact was posted once.
        captured = self.races_the_post(drops_the_handoff)
        settled.charges(self)

        answers = tuple(self.resolves(self.head) for _ in range(3))

        self.assertEqual(answers, (FinishOutcome.HELD, FinishOutcome.HELD, FinishOutcome.HELD))
        self.assert_held_as_settled(captured)
        self.assertIsNone(readings.pinned(self)[_records.EVIDENCE_HANDOFF])
        self.assertEqual(self.posted(captured), [captured.commands])
        settled.assert_charged_as_left(self)

    def test_an_adopted_settlement_outranked_goes_on(self) -> None:
        # That road spent a revision past the run it settled: the phase
        # invalidates the run whole, its revision and binding kept, and lets
        # the route go on to the fresh reviewer, the next one changing nothing.
        captured = self.races_the_post(spends_a_revision_past)
        settled.charges(self)

        self.assertIsNone(self.resolves(self.head))
        left = readings.pinned(self)
        self.assertIsNone(self.resolves(self.head))

        self.assertEqual(readings.pinned(self), left)
        records = readings.records(left)
        self.assertEqual(records[:2], (None, None))
        outranked, newer = records[2][-2:]
        self.assertEqual(outranked, (captured.receipt, readings.INVALIDATED))
        self.assertEqual(newer[1], readings.ABANDONED)
        self.assert_whole(captured)
        self.assert_phase_left()

    def test_a_settlement_read_moving_is_invalidated(self) -> None:
        # That road settles the run and then report 3 of its head, and report
        # 2 is put back right behind the proof that read it moving, before the
        # settlement is adopted: the run is invalidated whole all the same,
        # and the route goes on with nothing current for the fresh reviewer.
        moves = _MovesTheReport()
        with patch.object(_proof.ProofReading, _OBSERVED, side_effect=moves, autospec=True):
            captured = self.races_the_post(moves.settles)
            settled.charges(self)
            self.assertIsNone(self.resolves(self.head))

        self.assert_invalidated(captured)
        self.assert_phase_left()

    def test_an_announced_settlement_is_invalidated(self) -> None:
        # Another finish of the landing settles the run, announces it, and
        # dies at its relabel; report 3 then moves, report 2 put back right
        # behind the proof that read it. The mark and the event's record that
        # finish left are this attempt advanced, not replaced, so the run is
        # invalidated whole over the movement read, that mark kept.
        moves = _MovesTheReport()
        with patch.object(_proof.ProofReading, _OBSERVED, side_effect=moves, autospec=True):
            captured = self.races_the_post(moves.finishes_then_settles)
            settled.charges(self)
            self.assertIsNone(self.resolves(self.head))

        self.assert_invalidated(captured)
        self.assertEqual(readings.pinned(self)[readings.KEY_ANNOUNCED], self.head)
        self.assert_phase_left(self.head)

    def test_an_announced_settlement_stays_current(self) -> None:
        # Another finish settles and announces the run just as the phase
        # posts it, dying at its relabel or its retirement or routing it
        # whole; nothing else moves, so the run stays current. A route that
        # took the attempt holds this one; nothing is said or relabelled twice.
        for died, answer, relabelled in _ANNOUNCED_ELSEWHERE:
            with self.subTest(died=getattr(died, "name", "routed")):
                captured = self.races_the_post(partial(_AdoptionCase.announces_elsewhere, died=died))

                self.assertEqual(self.resolves(self.head), answer)

                self.assertEqual(readings.pinned_records(self)[1].receipt, captured.receipt)
                self._assert_said_once(captured, readings.ROUTED if relabelled else ())

    def test_a_run_routed_elsewhere_is_retired(self) -> None:
        # Another finish routes the run whole before report 3 moves, or right
        # behind the proof that read it, report 2 put back: the movement
        # outlives that route, so the phase holds and the run is invalidated
        # as the comment stands -- or, the comment full, marked in its
        # handoff's place, and retired whole once room is made by the next
        # finish of the landing to find no attempt -- and a successor settled
        # under its own receipt is kept.
        for first, then, retired in _ROUTED_ELSEWHERE:
            with self.subTest(first=first, retired=retired):
                captured = self.routes_elsewhere(first, then)

                self.assert_invalidated(captured, retired)
                self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
                entered = (handoff.stage_entries(self.gh, git_support.ISSUE), self.runs())
                self.assertEqual(entered, (["validating"], 1))
                if retired is None:
                    finish_moves.makes_room(self)
                    self.asks_directly(_unconfirmed.retires_the_marked, self.head)
                    self.assert_invalidated(captured)

    def _assert_said_once(self, captured, relabels: tuple) -> None:
        """Nothing pending beside `captured`, posted and announced once, relabelled as `relabels` has it; run once."""
        pending, _, retired = readings.pinned_records(self)
        self.assertEqual((pending, retired), (None, git_support.invalidated(self)))
        self.assertEqual(self.posted(captured), [captured.commands])
        self.assertEqual(support.announced(self), [self.head])
        self.assertEqual(len(readings.notices(self)), 1)
        self.assertEqual(readings.relabels(self), relabels)
        self.assertEqual(self.runs(), 1)


class FinalizedAdoptionTest(_AdoptionCase, route.SettledRouteCase, unittest.TestCase):
    """The coordinator over a settlement another road made while the run was published."""

    def test_an_adopted_settlement_out_of_step_holds(self) -> None:
        # The run is current as that road settled it, its handoff dropped:
        # every finish holds with nothing announced, relabelled, or retired,
        # and the artifact was posted once.
        captured = self.races_the_post(drops_the_handoff)

        self.assertEqual(self.finalizes(self.head), FinishOutcome.HELD)
        self.assertEqual(self.finalizes(self.head), FinishOutcome.HELD)

        self.assert_held_as_settled(captured)
        self.assertEqual(self.posted(captured), [captured.commands])

    def test_an_outranked_settlement_is_routed_past(self) -> None:
        # That road spent a revision past the run it settled: the run is
        # invalidated whole ahead of the announcement, and the head is said
        # and routed once to the fresh reviewer.
        captured = self.races_the_post(spends_a_revision_past)

        self.assertEqual(self.finalizes(self.head), FinishOutcome.ROUTED)

        self.assert_routed_past(captured)

    def test_a_settlement_read_moving_is_routed_past(self) -> None:
        # That road settled the run and then report 3 of its head, report 2
        # put back right behind the proof that read it: the run is
        # invalidated whole all the same, and the head is routed once.
        moves = _MovesTheReport()
        with patch.object(_proof.ProofReading, _OBSERVED, side_effect=moves, autospec=True):
            captured = self.races_the_post(moves.settles)
            self.assertEqual(self.finalizes(self.head), FinishOutcome.ROUTED)

        self.assert_invalidated(captured)
        self.assert_routed_past(captured)

    def assert_routed_past(self, captured) -> None:
        """`captured` invalidated whole with nothing current or pending, and the head said and routed once."""
        self.assertEqual(readings.pinned_records(self)[:2], (None, None))
        self.assert_whole(captured)
        self.assert_routed_once(self.head)


if __name__ == "__main__":
    unittest.main()
