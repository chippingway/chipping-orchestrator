# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A newer transaction another road records beside a settlement the dormant evidence phase adopts, kept owed.

The captured case (`rewrite_captured_test_support.CapturedEvidenceCase`):
issue #7's run captured for the landed head, and the evidence phase asked
directly over a finish held to the dormant settled-evidence policy. Another
finish settles the run while this one's answer reads the pull request, and a
later review is handed over under it, so the run's binding moved; as this
finish adopts that settlement, another road records a newer transaction of
the head bound to that review, its binding proved as it is recorded. Only
the adopted settlement is invalidated over what the answer read, and the
route is held with the successor owed as recorded, for the next finish to
answer. So is a continuation over a head the base advanced past, whose
abandonment of the run takes in its settlement beside a successor that reads
or one nobody can read. Nothing runs, and the run is posted once.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator.workflow.engine import (
    rewrite_finish_settlement as _settlement_step,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_captured_test_support as settled_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
    settled_finish_support as settled,
    verification_evidence_test_support as support,
    verification_report_fixture as report,
)
from tests.workflow.interleaving import _RacesTheStep

# A pending record nobody can read, as another road may leave one.
_UNREADABLE = "unreadable"


def _fallen_behind(finish):
    """`finish` over a candidate that counted the base two commits past the landed head."""
    checkout = finish.landed.candidate.checkout
    checkout = replace(checkout, base=replace(checkout.base, behind=2))
    candidate = replace(finish.landed.candidate, checkout=checkout)
    return replace(finish, landed=replace(finish.landed, candidate=candidate))


class AdoptedSuccessorTest(settled_support.CapturedEvidenceCase, unittest.TestCase):
    """The successor recorded beside an adopted settlement stays owed; only that settlement is invalidated."""

    def test_the_successor_is_kept(self) -> None:
        # The run is settled elsewhere and reviewed again under the answer's
        # second reading of the pull request, and the successor is recorded
        # just ahead of the adoption that takes the comment in: the phase
        # holds, the adopted run invalidated whole and the successor pending.
        finish = settled.dormant(self.landed())
        adopts = _RacesTheStep(_durable.takes_in_a_settlement, self._records_a_successor)

        with (
            settled_moves.raced_past(self, "get_pr", type(self)._settles_and_reviews, nth=2),
            patch.object(_durable, "takes_in_a_settlement", adopts),
        ):
            self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.HELD)

        self._assert_invalidated()
        self.assertEqual(self.records()[0], self.successor)
        receipts = [found.receipt for found in support.posted_artifacts(self)]
        self.assertEqual(receipts.count(self.captured.receipt), 1)
        self.assertEqual(self.verify.call_count, 0)

    def test_the_continuation_holds_over_it(self) -> None:
        # The base advanced past the head, and another finish settled the run
        # after this one read it captured, a newer transaction recorded beside
        # that settlement -- one that reads, or one nobody can read: the
        # continuation's abandonment takes that settlement in and invalidates
        # it whole, and the continuation holds with the successor owed as
        # recorded rather than going on past it.
        for readable in (True, False):
            with self.subTest(readable=readable):
                self.setUp()
                finish = _fallen_behind(settled.dormant(self.landed()))
                self._settles_elsewhere()
                written = self._records_beside(readable=readable)

                self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.HELD)

                self._assert_invalidated()
                self.assertEqual(readings.pinned(self)[_records.PENDING_EVIDENCE], written)
                self.assertEqual(self.verify.call_count, 0)

    def _settles_and_reviews(self) -> None:
        """Settle the run as another finish of the landing would (`_settles_elsewhere`), then review it again."""
        self._settles_elsewhere()
        self.rereads()
        self.reviewed = report.settles_report(self, 3, head=self.head)
        self.gh.write_pinned_state(self.issue, self.state)

    def _settles_elsewhere(self) -> None:
        """Post the captured run's artifact and settle it, as another finish of the landing would."""
        state = self.gh.read_pinned_state(self.issue)
        posted = self.gh.publish_verification_artifact(self.pull_request, self.captured.artifact)
        self.gh.write_pinned_state(self.issue, _settlement.settled_state(
            state, self.captured, posted.landed_id, finish_support.REVIEWING,
        ))

    def _records_beside(self, *, readable: bool):
        """Another road's newer transaction of the head beside the settlement, or a record nobody can read; as left."""
        if not readable:
            settled_moves.writes_over(self, _records.PENDING_EVIDENCE, _UNREADABLE)
            return _UNREADABLE
        state = self.gh.read_pinned_state(self.issue)
        commands = self.captured.commands
        newer = _record_state.mint_pending_evidence(state, support.ISSUE_NUMBER, self.captured.binding, commands)
        self.assertTrue(_record_state.record_pending_evidence(state, newer))
        self.gh.write_pinned_state(self.issue, state)
        return readings.pinned(self)[_records.PENDING_EVIDENCE]

    def _records_a_successor(self) -> None:
        """Another road's newer transaction of the head, bound to that later review and proved, recorded once."""
        state = self.gh.read_pinned_state(self.issue)
        if _record_state.carries_pending_evidence(state):
            return
        target = replace(self.captured.binding.target, subject=self.reviewed.recorded())
        binding = replace(self.captured.binding, target=target)
        reading = _proof.ProofReading(self.gh, self.landed().spec, self.issue, state)
        self.assertTrue(_proof.binding_verdict(reading, binding).proved)
        commands = self.captured.commands
        self.successor = _record_state.mint_pending_evidence(state, support.ISSUE_NUMBER, binding, commands)
        self.assertTrue(_record_state.record_pending_evidence(state, self.successor))
        self.gh.write_pinned_state(self.issue, state)

    def _assert_invalidated(self) -> None:
        """The adopted run invalidated whole, its revision and binding kept, with nothing current."""
        current, history = self.records()[1:]
        self.assertIsNone(current)
        self.assertEqual(history[-1], (self.captured.receipt, readings.INVALIDATED))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual(entry.revision, self.captured.revision)
        self.assertEqual(entry.binding, self.captured.binding)


if __name__ == "__main__":
    unittest.main()
