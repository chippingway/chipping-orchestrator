# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed base rewrite's head is routed with, made durable before the relabel.

Driven whole through the finish every landing gets, over an issue holding
settled evidence of the head the rewrite replaced. A changed tree is verified
afresh and recorded as a pending transaction -- the replaced head's evidence
invalidated into history in the same write -- before the relabel, and only the
dispatcher's reconciliation publishes it and makes it current; an exact tree
carries that evidence with its provenance. Nothing configured, no review of
the rewritten head to bind to, a transcript the comment cannot record, or a
failure records nothing, and the head goes to the fresh reviewer -- a failure
posted on the pull request first.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import verification_settlement_state as _settlement
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_evidence_test_support as rewrite_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_readings as readings,
    verification_evidence_test_support as support,
)

REBASED = support.REBASED_SHA

SQUASHED = support.SQUASHED_SHA

ROUTED = FinishOutcome.ROUTED

TO_VALIDATING = readings.ROUTED

# A transcript the artifact can carry and the pinned comment, beside
# everything else it records, cannot.
_OVERSIZED_LENGTH = 63_000

_OVERSIZED = "x" * _OVERSIZED_LENGTH

# What the notice of a failed run quotes of it.
_FAILED_DETAIL = f"`{support.SUITE}` exited with code {rewrite_support.FAILED_EXIT}"

_FAILED_TAIL = "> FAILED tests/test_widget.py::test_rebased - AssertionError\n> 1 failed, 12 passed"


class FreshEvidenceTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """A changed tree is verified afresh, recorded before its route, and published by the transaction."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)

    def test_a_changed_tree_is_recorded_first(self) -> None:
        # Both runs passed and printed different transcripts. The fresh run is
        # recorded with exactly what it printed and the settled evidence goes
        # into history whole -- both durable when the relabel comes, with no
        # artifact posted yet. The next dispatch's reconciliation proves the
        # report and review of the rebased head it is bound to, publishes it,
        # and only then makes it current.
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.outputs[support.SUITE] = rewrite_support.FRESH_OUTPUT
        posted = len(self.artifacts())

        self.assertEqual(self.finishes(REBASED), ROUTED)

        pending, current, retired = self.at_the_relabel()
        self.assertEqual(
            (current, retired, len(self.artifacts())),
            (None, self.invalidated(), posted),
        )
        self._assert_fresh(pending)
        self.assertFalse(self.reconcile())
        self._assert_settled(pending)

    def test_a_fresh_result_with_no_room_is_refused(self) -> None:
        # The artifact could carry the transcript, but the pinned comment
        # cannot record it beside everything else: nothing is recorded, the
        # replaced head's evidence is still invalidated, and the head routed.
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.outputs[support.SUITE] = _OVERSIZED

        with self.assertLogs(support.WORKFLOW_LOG, "ERROR") as logged:
            self.assertEqual(self.finishes(REBASED), ROUTED)
            self.assertIn("the fresh reviewer owes it", support.logged_refusal(logged))

        self.assertEqual(self.at_the_relabel(), (None, None, self.invalidated()))

    def _assert_fresh(self, pending) -> None:
        """`pending` is the run of the rebased head, executed here and recorded exactly as it printed."""
        binding = pending.binding
        self.assertEqual(
            (binding.source.value, binding.tested_sha, binding.tested_tree, binding.target.target_head),
            ("orchestrator-executed", REBASED, support.REBASED_TREE, REBASED),
        )
        transcript = [(ran.command, ran.exit_status, ran.output) for ran in pending.commands]
        self.assertEqual(transcript, [(support.SUITE, 0, rewrite_support.FRESH_OUTPUT)])
        self.assertNotEqual(pending.commands, self.source.commands)
        self.assertEqual(
            (readings.attempt(readings.pinned(self)), readings.relabels(self)),
            (readings.RETIRED, TO_VALIDATING),
        )

    def _assert_settled(self, pending) -> None:
        """`pending` is the current evidence, published as the artifact it records."""
        settled = _settlement.read_current_evidence(self.state)
        self.assertEqual((settled.receipt, settled.binding), (pending.receipt, pending.binding))
        self.assertEqual(self.artifacts()[-1].commands, pending.commands)


class CarriedEvidenceTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """An exact tree carries the settled evidence onto the rewritten head with its provenance."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)

    def test_an_exact_tree_carries_its_provenance(self) -> None:
        # Nothing runs. The carry keeps the commit and tree the commands ran
        # on and names the artifact it copied, and the settled evidence stays
        # current until the carry settles over it.
        self.attempts(SQUASHED)
        self.rewrites(SQUASHED)

        self.assertEqual(self.finishes(SQUASHED), ROUTED)

        pending, current, retired = self.at_the_relabel()
        binding = pending.binding
        self.assertEqual(
            (current.receipt, retired, self.handed),
            (self.source.receipt, (), []),
        )
        self.assertEqual(
            (binding.tested_sha, binding.tested_tree, binding.target.target_head),
            (support.TESTED_SHA, support.TESTED_TREE, SQUASHED),
        )
        self.assertEqual(
            (pending.copied_from, pending.commands),
            (self.source.receipt, self.source.commands),
        )
        self.assertFalse(self.reconcile())
        settled = readings.pinned_records(self)[1:]
        self.assertEqual(settled[0].receipt, pending.receipt)
        self.assertEqual(settled[1], ((self.source.receipt, "superseded"),))


class ReviewerEvidenceTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """With nothing configured or nothing to bind to, nothing is recorded and the reviewer owes the evidence."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)

    def test_empty_commands_record_nothing(self) -> None:
        # The evidence was taken under the suite, so an empty configuration
        # is a moved context even over the tested tree: it is invalidated, and
        # no local run is recorded as passing.
        for head in (REBASED, SQUASHED):
            with self.subTest(head=head):
                self.setUp()
                self.attempts(head)
                self.rewrites(head)
                with patch.object(config, "VERIFY_COMMANDS", ()):
                    self.assertEqual(self.finishes(head), ROUTED)

                self.assertEqual(self.at_the_relabel(), (None, None, self.invalidated()))
                self.assertEqual((self.handed, readings.relabels(self)), ([], TO_VALIDATING))

    def test_the_replaced_review_is_not_carried(self) -> None:
        # The report refresh the rewrite owes has not happened, so the review
        # recorded is of the replaced head: nothing runs or is recorded. A
        # changed tree invalidates the settled evidence before the route, and
        # an exact one leaves it on the replaced head's subject, which no
        # reviewer of the rewritten head is handed (`test_rewrite_finish_journey`).
        for head, invalidated in ((REBASED, True), (SQUASHED, False)):
            with self.subTest(head=head):
                self.setUp()
                self.attempts(head)
                self.rewrites(head, reported=False)

                self.assertEqual(self.finishes(head), ROUTED)

                self.assertEqual(self.at_the_relabel(), self._deferred(invalidated))
                self.assertEqual(self.handed, [])

    def _deferred(self, invalidated: bool) -> tuple:
        """What a finish that recorded nothing leaves: the settled evidence invalidated, or still current."""
        if invalidated:
            return None, None, self.invalidated()
        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(current.receipt, self.source.receipt)
        return None, current, ()


class FailedEvidenceTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """A failing run records nothing, stays actionable on the pull request, and goes to the fresh reviewer."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)

    def test_a_failure_is_posted_before_its_route(self) -> None:
        # The failing command, its exit status, and the tail of its output
        # are recorded with the invalidation before anything is posted, then
        # posted behind the announcement before the relabel. The retirement
        # behind the relabel enters the notice in the ledger and clears the
        # record the pull request no longer needs.
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.exits[support.SUITE] = rewrite_support.FAILED_EXIT
        self.outputs[support.SUITE] = rewrite_support.FAILED_OUTPUT

        self.assertEqual(self.finishes(REBASED), ROUTED)

        announced, failed = readings.notices(self)
        self.assertIn(":mag: PR was 0 commit(s) behind", announced)
        self.assertIn(_FAILED_DETAIL, failed)
        self.assertIn(_FAILED_TAIL, failed)
        self.assertEqual(self.at_the_relabel(), (None, None, self.invalidated()))
        self._assert_recorded_then_cleared(failed)

    def _assert_recorded_then_cleared(self, failed: str) -> None:
        """`failed` was recorded about the rebased head at the relabel; after, it is ledgered and the record cleared."""
        recorded = readings.failure(self.durable[0])
        self.assertEqual(recorded["head"], REBASED)
        self.assertTrue(failed.startswith(recorded["notice"]))
        posted = self.pull_request.issue_comments[-1]
        pinned = readings.pinned(self)
        self.assertIn(posted.id, pinned[support.LEDGER])
        self.assertIsNone(readings.failure(pinned))

if __name__ == "__main__":
    unittest.main()
