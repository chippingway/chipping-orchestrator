# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A run settled for the landed head, outranked by a newer transaction its evidence phase abandons, is invalidated.

The evidence phase of a finish held to the dormant settled-evidence policy,
asked directly (`settled_finish_support`): issue #7's run settled under the
anchor, then another road records a newer transaction beside it, spending a
revision past it, and the settled report both are bound to moves, so the
phase abandons the newer one. The run it outranked is invalidated whole and
the route goes on to the fresh reviewer, rather than routing the run as
current or holding over the spent revision -- also beside a floor nobody can
read, which holds that phase once behind the invalidation, beside a pending
record nobody can read, which holds every phase and is kept as written, and
where the newer transaction was dropped with only the floor left raised
behind an announcement already made. A phase asked again changes nothing.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall


def _settles_a_later_report(case: support.CapturedRunCase, head: str) -> None:
    """Settle report 3 of `head` and hand a reviewer it, over the comment as it stands."""
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


class OutrankedRunTest(settled.SettledRunCase, unittest.TestCase):
    """A run a newer, abandoned transaction outranks is invalidated and the route goes on, never held for good."""

    def test_abandoned_before_its_proof(self) -> None:
        # The report moves before the phase proves the newer transaction,
        # which it abandons unposted; the run it outranked is invalidated.
        head, run, newer = self._outranks()
        _settles_a_later_report(self, head)

        self._assert_goes_on_over(head, run, newer)
        self.assertEqual(self.posted(newer), [])

    def test_abandoned_while_it_is_published(self) -> None:
        # The report moves just as the phase posts the newer transaction's
        # artifact, so its settlement is refused and it is abandoned behind
        # that post: the run beside it is invalidated, where every later
        # phase would otherwise hold over the revision spent.
        head, run, newer = self._outranks()
        moved = partial(_settles_a_later_report, self, head)
        moves = _RacesPastTheCall(self.gh.publish_verification_artifact, 1, moved)
        with patch.object(self.gh, support.POST, moves):
            self._assert_goes_on_over(head, run, newer)

        self.assertEqual(self.posted(newer), [newer.commands])

    def test_outranked_beside_an_unreadable_floor(self) -> None:
        # The newer transaction is abandoned into history and the revision
        # floor stops reading: the entry still outranks the run, which the
        # phase invalidates before it holds over that floor, and the next
        # phase, with nothing current left beside it, goes on.
        head, run, newer = self._outranks()
        state = self.gh.read_pinned_state(self.issue)
        self.assertTrue(_carries.abandons(state, newer))
        state.set(readings.KEY_REVISION_FLOOR, "unreadable")
        self.gh.write_pinned_state(self.issue, state)

        self._assert_goes_on_over(head, run, newer, (FinishOutcome.HELD, None))
        self.assertEqual(self.posted(newer), [])

    def test_outranked_beside_an_unreadable_pending(self) -> None:
        # The newer transaction is abandoned into history and a pending
        # record nobody can read takes its place: that record holds every
        # phase, but the readable entry still outranks the run, which the
        # first phase invalidates whole, the unreadable record kept exactly
        # as written for whoever can answer it.
        head, run, newer = self._outranks()
        state = self.gh.read_pinned_state(self.issue)
        self.assertTrue(_carries.abandons(state, newer))
        state.set(_records.PENDING_EVIDENCE, "unreadable")
        self.gh.write_pinned_state(self.issue, state)

        self._assert_goes_on_over(head, run, newer, (FinishOutcome.HELD, FinishOutcome.HELD))
        self.assertEqual(readings.pinned(self)[_records.PENDING_EVIDENCE], "unreadable")
        self.assertEqual(self.posted(newer), [])

    def test_a_floor_past_the_run_outranks_it(self) -> None:
        # A recovery settles the run and announces it, dying at its relabel,
        # and a revision past it is spent with nothing left recorded beside it
        # -- a newer transaction dropped. That revision outranks the run for
        # good, so the phase invalidates it whole rather than take it as the
        # last word on the head or hold every later phase over it.
        head, captured = self.captures()
        self.dies_at(support.RELABEL, self.recovers)
        settled.charges(self)
        state = self.gh.read_pinned_state(self.issue)
        state.set(readings.KEY_REVISION_FLOOR, captured.revision + 1)
        self.gh.write_pinned_state(self.issue, state)

        self.assertIsNone(self.resolves(head))

        retired = (*git_support.invalidated(self), (captured.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (captured.revision, captured.binding))
        self.assert_phase_left(head)

    def _outranks(self) -> tuple:
        """Settle a captured run under the anchor, unannounced, and record a newer one beside it; head and both.

        The newer transaction carries the run's own binding and transcript, as
        another road answering the same review would record it.
        """
        head, captured = self.captures()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, self.recovers)
        run = readings.pinned_records(self)[1]
        self.assertEqual(run.receipt, captured.receipt)
        settled.charges(self)
        state = self.gh.read_pinned_state(self.issue)
        newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, captured.binding, captured.commands)
        self.assertTrue(_record_state.record_pending_evidence(state, newer))
        self.gh.write_pinned_state(self.issue, state)
        return head, run, newer

    def _assert_goes_on_over(self, head: str, run, newer, answers: tuple = (None, None)) -> None:
        """Two phases answering `answers`, `run` invalidated whole and `newer` abandoned; nothing made.

        The invalidated entry keeps the run's revision and whole binding, so
        the history names the one execution the run was, and nothing is
        current for the fresh reviewer, who owes the evidence.
        """
        self.assertEqual((self.resolves(head), self.resolves(head)), answers)
        retired = (
            *git_support.invalidated(self),
            (run.receipt, readings.INVALIDATED),
            (newer.receipt, readings.ABANDONED),
        )
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        invalidated = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-2]
        self.assertEqual((invalidated.revision, invalidated.binding), (run.revision, run.binding))
        self.assertEqual(len(self.posted(run)), 1)
        self.assert_phase_left()


if __name__ == "__main__":
    unittest.main()
