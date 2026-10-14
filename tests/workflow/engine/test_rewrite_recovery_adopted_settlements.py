# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A settlement another road made while the recovery published the run, adopted out of step with the records beside it.

A finish recorded its run and died posting its artifact; as the recovery
posts it, another road settles that very run and leaves the records beside
it out of step -- a newer transaction recorded and retired past it, or its
handoff dropped. The adopted records hold the route, poll after poll, with
nothing announced or retired.

Under the dormant settled-evidence policy (`settled_finish_support`) the
dropped handoff holds the same way, a revision spent past the run outranks
it, and a run read moving under report 3 is invalidated whole however soon
report 2 is put back -- also where another finish of the landing announced
or routed it meanwhile, over the comment as it stands; a run settled and
announced with nothing else moving stays current. Nothing runs again.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    verification_carries as _carries,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad
from orchestrator.workflow.engine.verification_settlement_state import settled_state
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall


def _settles_the_run(case: support.CapturedRunCase, captured):
    """Settle `captured` over the artifact just posted, as another road would; the comment it left, unwritten."""
    state = case.gh.read_pinned_state(case.issue)
    posted = case.pull_request.issue_comments[-1]
    settled_comment = settled_state(state, captured, posted.id, git_support.REVIEWING)
    case.assertIsNotNone(settled_comment)
    return settled_comment


def _spends_a_revision_past(case: support.CapturedRunCase, captured) -> None:
    """Settle `captured`, then record a newer transaction and retire it, raising the floor past the run."""
    state = _settles_the_run(case, captured)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, case.source.binding, captured.commands)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.assertTrue(_carries.abandons(state, newer))
    case.gh.write_pinned_state(case.issue, state)


def _drops_the_handoff(case: support.CapturedRunCase, captured) -> None:
    """Settle `captured`, then drop the handoff that names it."""
    state = _settles_the_run(case, captured)
    state.set(_records.EVIDENCE_HANDOFF, None)
    case.gh.write_pinned_state(case.issue, state)


# What another road leaves beside the run it settled, and the revision floor
# that leaves: one past the run's, or the run's own.
_OUT_OF_STEP = (
    ("a revision spent past it", _spends_a_revision_past, 1),
    ("its handoff dropped", _drops_the_handoff, 0),
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# The proof's observation of a refusal, read before any case stands in for it.
_OBSERVES = _proof.ProofReading.observes

# The handoff's place on the pinned comment, which the movement mark takes.
_HANDOFF = "verification_evidence_handoff"

# Whether another finish routes the run before report 3 moves, what is made
# behind that route, and how the run then reads (`_assert_invalidated`).
_ROUTED_ELSEWHERE = (
    (True, None, readings.INVALIDATED),
    (False, None, readings.INVALIDATED),
    (True, finish_moves.fills_the_comment, None),
    (False, finish_moves.fills_the_comment, None),
    (True, partial(settled.records_a_newer_run, settles=True), "superseded"),
)


class _MovesTheReport:
    """Another road settling the run and then report 3 of its head, report 2 put back once the proof read it."""

    def __init__(self) -> None:
        self._case = None
        self._replaced: dict = {}
        self._behind = None

    def __call__(self, reading, refused) -> None:
        _OBSERVES(reading, refused)
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
        case.state = _settles_the_run(case, captured)
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
    """A captured run another road settles just as the recovery posts it, and three recoveries behind it."""

    def polls_beside(self, settles) -> tuple:
        """A fresh case's captured run, `settles` made just as the recovery posts it, then three recoveries.

        The head and the run.
        """
        self.setUp()
        head, captured = self.captures()
        races = _RacesPastTheCall(self.gh.publish_verification_artifact, 1, partial(settles, self, captured))
        self.enterContext(patch.object(self.gh, support.POST, races))
        self.recovers()
        self.recovers()
        self.recovers()
        return head, captured

    def announces_elsewhere(self, captured, died: handoff.Boundary | None = handoff.BEFORE_THE_RELABEL) -> None:
        """Have another finish of the landing settle `captured` and announce it, dying at `died` or routing it whole."""
        finishing = partial(self.finishes, captured.binding.target.target_head, FinishRoad.RECOVERY)
        handoff.dies_at(self.gh, died, finishing)

    def polls_beside_a_route(self, *, first: bool, then=None) -> tuple:
        """`polls_beside` another finish routing the run whole around report 3 (`_MovesTheReport.finishes_around`)."""
        moves = _MovesTheReport()
        with patch.object(_proof.ProofReading, "observes", side_effect=moves, autospec=True):
            return self.polls_beside(partial(moves.finishes_around, first=first, then=then))

    def assert_routed_once(self, head: str) -> None:
        """`head` routed, announced, relabelled, and entered once, its attempt retired; the run made once."""
        self.assert_recovered(head)
        self.assertEqual(handoff.stage_entries(self.gh, git_support.ISSUE), ["validating"])
        self.assertEqual(self.runs(), 1)

    def assert_held_as_settled(self, captured, past: int = 0) -> None:
        """`captured` current as the other road settled it, the floor `past` it, the attempt standing, nothing made."""
        pinned = readings.pinned(self)
        self.assertEqual(readings.records(pinned)[1].receipt, captured.receipt)
        self.assertEqual(pinned[readings.KEY_REVISION_FLOOR], captured.revision + past)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
        self.assert_unannounced()
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


class AdoptedSettlementRecoveryTest(_AdoptionCase, unittest.TestCase):
    """Records another road settled out of step while the run was published hold the route, poll after poll."""

    def test_an_adopted_settlement_out_of_step_holds(self) -> None:
        # The run is current as that road settled it, the records beside it
        # are left as it wrote them, and the attempt stands with nothing
        # announced, however often the recovery polls.
        for beside, settles, past in _OUT_OF_STEP:
            with self.subTest(beside=beside):
                captured = self.polls_beside(settles)[1]

                self.assert_held_as_settled(captured, past)


class SettledAdoptionTest(_AdoptionCase, settled.SettledRunCase, unittest.TestCase):
    """Under the settled-evidence policy, a dropped handoff holds; an outranked or moved settlement is invalidated."""

    def test_an_adopted_settlement_out_of_step_holds(self) -> None:
        # The run is current as that road settled it, its handoff dropped
        # and left so, and the attempt stands with nothing announced,
        # however often the recovery polls.
        captured = self.polls_beside(_drops_the_handoff)[1]

        self.assert_held_as_settled(captured)

    def test_an_adopted_settlement_outranked_routes(self) -> None:
        # That road spent a revision past the run it settled: the recovery
        # invalidates the run whole, keeping its revision and binding, and
        # routes the head once, with nothing run or pushed again.
        head, captured = self.polls_beside(_spends_a_revision_past)

        records = readings.pinned_records(self)
        self.assertEqual(records[:2], (None, None))
        outranked, newer = records[2][-2:]
        self.assertEqual(outranked, (captured.receipt, readings.INVALIDATED))
        self.assertEqual(newer[1], readings.ABANDONED)
        self.assert_recovered(head)

    def test_a_settlement_read_moving_is_invalidated(self) -> None:
        # That road settles the run and then report 3 of its head, and report
        # 2 is put back right behind the proof that read it moving, before the
        # settlement is adopted: the run is invalidated whole all the same,
        # and the head routed once to the fresh reviewer with nothing current.
        moves = _MovesTheReport()
        with patch.object(_proof.ProofReading, "observes", side_effect=moves, autospec=True):
            head, captured = self.polls_beside(moves.settles)

        self._assert_invalidated(captured)
        self.assert_recovered(head)

    def test_an_announced_settlement_is_invalidated(self) -> None:
        # Another finish of the landing settles the run, announces it, and
        # dies at its relabel; report 3 then moves, report 2 put back right
        # behind the proof that read it. The mark and the event's record that
        # finish left are this attempt advanced, not replaced, so the run is
        # invalidated whole over the movement read, and the head routed once.
        moves = _MovesTheReport()
        with patch.object(_proof.ProofReading, "observes", side_effect=moves, autospec=True):
            head, captured = self.polls_beside(moves.finishes_then_settles)

        self._assert_invalidated(captured)
        self.assert_recovered(head)

    def test_an_announced_settlement_stays_current(self) -> None:
        # Another finish settles and announces the run just as the recovery
        # posts it, dying at its relabel or its retirement or routing it
        # whole; nothing else moves, so the run stays current and the head is
        # routed once -- one relabel and one stage-entry event.
        for died in (handoff.BEFORE_THE_RELABEL, handoff.BEFORE_THE_RETIREMENT, None):
            with self.subTest(died=getattr(died, "name", "routed")):
                head, captured = self.polls_beside(partial(_AdoptionCase.announces_elsewhere, died=died))

                left = readings.pinned_records(self)
                self.assertEqual(left[::2], (None, git_support.invalidated(self)))
                self.assertEqual(left[1].receipt, captured.receipt)
                self.assert_routed_once(head)

    def test_a_run_routed_elsewhere_is_invalidated(self) -> None:
        # Another finish routes the run whole before report 3 moves, or right
        # behind the proof that read it, report 2 put back: the movement
        # outlives that route, so the run is invalidated as the comment
        # stands -- or, the comment full, marked in its handoff -- and a
        # successor settled under its own receipt is kept.
        for first, then, retired in _ROUTED_ELSEWHERE:
            with self.subTest(first=first, retired=retired):
                head, captured = self.polls_beside_a_route(first=first, then=then)

                self._assert_invalidated(captured, retired)
                self.assert_routed_once(head)

    def _assert_invalidated(self, captured, retired: str | None = readings.INVALIDATED) -> None:
        """`captured` retired into history as `retired` with nothing pending, report 2 current as put back.

        Invalidated, nothing is current; superseded, the successor is. None is
        `captured` still current with the mark naming it in its handoff's
        place: the movement read under it, recorded where history had no room.
        """
        pending, current, history = readings.pinned_records(self)
        self.assertIsNone(pending)
        if retired is None:
            self.assertEqual(current.receipt, captured.receipt)
            self.assertEqual(readings.pinned(self)[_HANDOFF], {"moved": captured.receipt})
        else:
            self.assertEqual(history[-1], (captured.receipt, retired))
            self.assertEqual(current is None, retired == readings.INVALIDATED)
        report = readings.pinned(self)[_MOVED_RECORDS[0]]
        self.assertEqual(report["revision"], 2)


if __name__ == "__main__":
    unittest.main()
