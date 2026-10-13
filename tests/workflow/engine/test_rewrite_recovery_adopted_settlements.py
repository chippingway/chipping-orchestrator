# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A settlement another road made while the recovery published the run, adopted out of step with the records beside it.

A finish recorded its run for the landed head and died posting its artifact,
so the recovery publishes and settles it with the attempt still standing. Just
as the artifact is posted, another road settles that very run itself and
leaves the records beside it out of step with it: it drops the handoff that
names the run, or it records a newer transaction and retires it, spending a
revision past the run. The recovery's own settlement is refused over that
moved comment, and the ledger entry it then commits alone takes the comment in
as it stands. Those records are held to the same agreement the finish asks of
settled evidence before it resolves anything. A handoff that does not name the
run leaves nobody able to say which evidence is the latest, so the route is
held: nothing announced, relabelled, or retired, the round as it was spent,
and the records exactly as that road left them -- poll after poll. A revision
spent past it outranks the run for good instead: the run is invalidated whole,
its revision and binding kept, and the head routed to the fresh reviewer
rather than held over evidence no reader will be handed. So is a run that
road settled and then moved report 3 under: the recovery's proof reads the
report moving, and putting report 2 back right behind that reading, before
the settlement is adopted, revives nothing -- the run is invalidated whole
over the movement the proof read. Nothing runs again, nothing is pushed, and
no developer is launched.
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
from orchestrator.workflow.engine.verification_settlement_state import settled_state
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall


def _settles_the_run(case: support.CapturedRunCase, captured):
    """Settle `captured` over the artifact just posted, as another road would; the comment it left, unwritten."""
    state = case.gh.read_pinned_state(case.issue)
    posted = case.pull_request.issue_comments[-1]
    settled = settled_state(state, captured, posted.id, git_support.REVIEWING)
    case.assertIsNotNone(settled)
    return settled


def _spends_a_revision_past(case: support.CapturedRunCase, captured) -> None:
    """Settle `captured`, then record a newer transaction and retire it, raising the floor past the run."""
    state = _settles_the_run(case, captured)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, case.source.binding, captured.commands)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.assertTrue(_carries.abandons(state, newer))
    case.gh.write_pinned_state(case.issue, state)


# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# The proof's observation of a refusal, read before any case stands in for it.
_OBSERVES = _proof.ProofReading.observes


class _MovesTheReport:
    """Another road settling the run and then report 3 of its head, report 2 put back once the proof read it."""

    def __init__(self) -> None:
        self._case = None
        self._replaced: dict = {}

    def __call__(self, reading, refused) -> None:
        _OBSERVES(reading, refused)
        if self._replaced and refused is not None and _MOVED_RECORDS[0] in refused.refusal:
            state = self._case.gh.read_pinned_state(self._case.issue)
            for key, recorded in self._replaced.items():
                state.set(key, recorded)
            self._case.gh.write_pinned_state(self._case.issue, state)
            self._replaced = {}

    def settles(self, case: support.CapturedRunCase, captured) -> None:
        """Settle `captured` over the artifact just posted, then report 3 of its head, as another road would."""
        self._case = case
        case.state = _settles_the_run(case, captured)
        self._replaced = {key: case.state.get(key) for key in _MOVED_RECORDS}
        head = captured.binding.target.target_head
        _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=head)
        case.gh.write_pinned_state(case.issue, case.state)



def _drops_the_handoff(case: support.CapturedRunCase, captured) -> None:
    """Settle `captured`, then drop the handoff that names it."""
    state = _settles_the_run(case, captured)
    state.set(_records.EVIDENCE_HANDOFF, None)
    case.gh.write_pinned_state(case.issue, state)


class AdoptedSettlementRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """Records another road settled out of step while the run was published hold the route, or outrank the run."""

    def test_an_adopted_settlement_out_of_step_holds(self) -> None:
        # The run is current as that road settled it, its handoff dropped
        # and left so, and the attempt stands with nothing announced,
        # however often the recovery polls.
        captured = self._polls_beside(_drops_the_handoff)[1]

        self._assert_held_as_settled(captured)

    def test_an_adopted_settlement_outranked_routes(self) -> None:
        # That road spent a revision past the run it settled: the recovery
        # invalidates the run whole, keeping its revision and binding, and
        # routes the head once, with nothing run or pushed again.
        head, captured = self._polls_beside(_spends_a_revision_past)

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
            head, captured = self._polls_beside(moves.settles)

        self._assert_invalidated(captured)
        self.assert_recovered(head)

    def _polls_beside(self, settles) -> tuple:
        """A captured run, `settles` made just as the recovery posts it, then three recoveries; the head and the run."""
        head, captured = self.captures()
        races = _RacesPastTheCall(self.gh.publish_verification_artifact, 1, partial(settles, self, captured))
        self.enterContext(patch.object(self.gh, support.POST, races))
        self.recovers()
        self.recovers()
        self.recovers()
        return head, captured

    def _assert_invalidated(self, captured) -> None:
        """`captured` invalidated whole into history with nothing current or pending, report 2 current as put back."""
        records = readings.pinned_records(self)
        self.assertEqual(records[:2], (None, None))
        retired = records[2][-1]
        self.assertEqual(retired, (captured.receipt, readings.INVALIDATED))
        report = readings.pinned(self)[_MOVED_RECORDS[0]]
        self.assertEqual(report["revision"], 2)

    def _assert_held_as_settled(self, captured) -> None:
        """`captured` current as the other road settled it, the floor its own, the attempt standing, nothing made."""
        pinned = readings.pinned(self)
        self.assertEqual(readings.records(pinned)[1].receipt, captured.receipt)
        self.assertEqual(pinned[readings.KEY_REVISION_FLOOR], captured.revision)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
        self.assert_unannounced()
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))

if __name__ == "__main__":
    unittest.main()
