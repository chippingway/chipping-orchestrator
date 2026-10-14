# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite finished again and again under the dormant settled-evidence policy, saying and making all once.

The real-git finish case (`rewrite_verification_recovery_support`), every
finish held to the dormant settled-evidence policy (`settled_finish_support`)
and handed over directly: issue #7's rebased head reviewed beside the run ledger
another road's launch charged -- runs spent on both meters, and a launch
reserved and started under its fingerprint -- its finish running
and settling the configured command under the anchor and killed at one of the
final handoff boundaries (`rewrite_handoff_test_support`). Nothing the run
rests on moves. The direct finish behind it proves the settled run ready and
routes the head. Another road then records a later transaction for the head
under a receipt of its own, and the finish handed over once more finds no
attempt anchored to the head the landing replaced -- retired by that route, or
replaced by a later rebase's own -- and reads and writes nothing: the pinned
comment stays exactly as it was, the later transaction pending as its road
wrote it. Whichever boundary the first died at, the issue ends with one notice
and one `base_rebased` event, one artifact and one settlement of the run, its
whole binding current, the round reset and one relabel to
`workflow:validating`, the attempt retired, the command run once, nothing
pushed or launched, and the run ledger exactly as charged: no finish spends,
reserves, or releases an agent run.
"""
from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType

from orchestrator.workflow.engine import run_ledger_values as _run_ledger
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
)

# The run ledger another road's launch left on the comment: the runs spent on
# it and on the legacy usage meter beside it, and a launch reserved and
# started under its fingerprint, at the count it was owed at.
_CHARGED = MappingProxyType({
    _run_ledger.AGENT_RUNS_USED: 5,
    "issue_agent_runs": 4,
    _run_ledger.AGENT_RUN_RESERVATION: "started",
    _run_ledger.AGENT_RUN_FINGERPRINT: "developer:issue-7:round-3",
    _run_ledger.AGENT_RUN_OWED_STARTED: 4,
})


# The handoff's place on the pinned comment.
_HANDOFF = "verification_evidence_handoff"


class RepeatedFinishTest(settled.SettledRunCase, unittest.TestCase):
    """Direct finishes behind one killed at any boundary route the settled run once and repeat nothing."""

    def test_every_boundary_finishes_once(self) -> None:
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self._charges()
                handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
                run = readings.pinned_records(self)[1]
                self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.ROUTED)
                later = settled.records_a_newer_run(self)
                pinned = readings.pinned(self)

                self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)

                self.assertEqual(readings.pinned(self), pinned)
                self._assert_said_once(head)
                self._assert_settled_once(run, later)

    def test_a_replaced_attempt_is_left_as_it_stands(self) -> None:
        # The landing is routed, and a later rebase pins an attempt of its
        # own, anchored on the landed head, beside a transaction another road
        # records for that head: the earlier landing handed over again finds
        # another attempt anchored and touches neither.
        head = self.lands_a_reviewed_rebase()
        self._charges()
        self.assertEqual(self.finishes(head), FinishOutcome.ROUTED)
        state = self.gh.read_pinned_state(self.issue)
        state.set(readings.KEY_PENDING_PUSH, head)
        self.gh.write_pinned_state(self.issue, state)
        later = settled.records_a_newer_run(self)
        pinned = readings.pinned(self)

        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)

        self.assertEqual(readings.pinned(self), pinned)
        self.assertEqual(readings.pinned_records(self)[0], later)
        self._assert_charged_as_left()

    def test_a_handoff_out_of_step_is_no_mark(self) -> None:
        # The landing is routed and another road settles a newer run for the
        # head under its own receipt, whose handoff then reads missing or
        # damaged. Nothing marked movement under that run, so the landing
        # handed over again finds no attempt and leaves the successor current.
        for damaged in (None, "unreadable"):
            with self.subTest(handoff=damaged):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.assertEqual(self.finishes(head), FinishOutcome.ROUTED)
                later = settled.records_a_newer_run(self, settles=True)
                state = self.gh.read_pinned_state(self.issue)
                state.set(_HANDOFF, damaged)
                self.gh.write_pinned_state(self.issue, state)

                self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)

                self.assertEqual(self.gh.read_pinned_state(self.issue).data, state.data)
                self.assertEqual(readings.pinned_records(self)[1].receipt, later.receipt)

    def _charges(self) -> None:
        """Leave the run ledger another road's launch charged (`_CHARGED`) on the comment as it stands."""
        state = self.gh.read_pinned_state(self.issue)
        for key, charged in _CHARGED.items():
            state.set(key, charged)
        self.gh.write_pinned_state(self.issue, state)

    def _assert_charged_as_left(self) -> None:
        """The run ledger exactly as `_charges` left it, and no push or agent launch made."""
        pinned = readings.pinned(self)
        charged = {key: pinned.get(key) for key in _CHARGED}
        self.assertEqual(charged, dict(_CHARGED))
        self.assertEqual(self.pushes.call_count, 0)
        self.assertEqual(self.developer.call_count, 0)

    def _assert_said_once(self, head: str) -> None:
        """`head` announced, filed, and relabelled once, its attempt retired and its round reset; nothing made."""
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, ([head], 1))
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        pinned = readings.pinned(self)
        self.assertEqual(readings.attempt(pinned), readings.RETIRED)
        self.assertEqual(pinned[readings.KEY_REVIEW_ROUND], 0)
        self.assertEqual(self.runs(), 1)
        self._assert_charged_as_left()

    def _assert_settled_once(self, run, later) -> None:
        """`run` current whole beside the evidence the rewrite moved past, posted once, and `later` pending unposted."""
        pending, current, retired = readings.pinned_records(self)
        self.assertEqual((pending, retired), (later, git_support.invalidated(self)))
        whole = (current.receipt, current.revision, current.binding)
        self.assertEqual(whole, (run.receipt, run.revision, run.binding))
        self.assertEqual(len(self.posted(run)), 1)
        self.assertEqual(self.posted(later), [])


if __name__ == "__main__":
    unittest.main()
