# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An attempt a terminal pull request ended settles or drops its whole handoff in one write.

That write is the attempt's checkpoint, and the transfer it settles is reported
only behind one that landed: a write refused reports nothing and leaves the
handoff standing, and one whose answer was lost leaves the settled transfer's
proof on the comment for a later tick's reconciliation to report there.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.base_sync import terminal_handoff as _terminal_handoff
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_publication_state as _late_publication_state,
)
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    transfers_test_support as seed,
)

LATE_TRANSFER = "late_transfer"

# How the write ending the handoff goes wrong, as the client names it, beside
# the anchor the comment then carries and whether it carries the shipped
# transfer's proof still owed its report.
_UNLANDED = (("refused", fixtures.PRE_REBASE_SHA, False), ("lost", None, True))


class TerminalHandoffTest(seed.TransferCase):
    """What a merged or closed pull request leaves of an attempt still in flight."""

    def setUp(self) -> None:
        super().setUp()
        self.state.set(fixtures.KEY_PENDING_PUSH_SHA, fixtures.PRE_REBASE_SHA)

    def test_a_shipped_rewrite_settles_its_transfer(self) -> None:
        # The push landed, its receipt was lost, and the merge carried the
        # rewrite away: the verdict follows it, with the receipt beside it.
        seed.granted(self.state)

        durable = self._retires(seed.REPLAYED_SHA)

        self.assertTrue(_exemption_reading.is_exempt(durable, seed.REPLAYED_SHA))
        self.assertEqual(
            _rewrite_reading.read_rewrite_authorization(durable).phase,
            _rewrite_values.LateRewritePhase.PUBLISHED,
        )
        self.assertEqual(
            _late_publication_state._publication_from(durable, seed.ACCEPTED_SHA, fixtures.PR_NUMBER),
            seed.REPLAYED_SHA,
        )
        self.assertEqual([record["transfer_proof"] for record in self._reports()], ["already_published"])
        self.assertIsNone(_rewrite_reading.unreported_transfer(durable))

    def test_a_permission_nothing_shipped_is_dropped(self) -> None:
        for described, published, granted in (
            ("the pull request ended on the anchor", seed.ACCEPTED_SHA, seed.GRANTED),
            ("a permission for another pull request", seed.REPLAYED_SHA,
             replace(seed.GRANTED, pr_number=seed.OTHER_PR_NUMBER)),
        ):
            with self.subTest(described):
                self._fresh()
                self.state.set(fixtures.KEY_PENDING_PUSH_SHA, fixtures.PRE_REBASE_SHA)
                seed.granted(self.state, granted)

                durable = self._retires(published)

                self.assertTrue(_exemption_reading.is_exempt(durable, seed.ACCEPTED_SHA))
                self.assertFalse(_rewrite_reading.carries_rewrite_authorization(durable))
                self.assertEqual(self._reports(), [])

    def test_a_settlement_is_kept_and_reported_once(self) -> None:
        seed.settled(self.state)

        durable = self._retires(seed.REPLAYED_SHA)

        self.assertTrue(_exemption_reading.is_exempt(durable, seed.REPLAYED_SHA))
        self.assertEqual([record["transfer_proof"] for record in self._reports()], ["pushed"])

    def test_an_unlanded_end_reports_nothing(self) -> None:
        for failure, anchored, owes_a_report in _UNLANDED:
            with self.subTest(failure=failure):
                self._fresh()
                self.state.set(fixtures.KEY_PENDING_PUSH_SHA, fixtures.PRE_REBASE_SHA)
                seed.granted(self.state)
                self.context.gh.write_pinned_state(self.context.issue, self.state)
                getattr(self.context.gh.pinned_failures, failure).add(self.context.issue.number)

                self.assertFalse(_terminal_handoff._retires_the_terminal_handoff(self.context, seed.REPLAYED_SHA))

                durable = self.context.gh.read_pinned_state(self.context.issue)
                self.assertEqual(self._reports(), [])
                self.assertEqual(durable.get(fixtures.KEY_PENDING_PUSH_SHA), anchored)
                self.assertIs(_rewrite_reading.unreported_transfer(durable) is not None, owes_a_report)

    def _retires(self, published: str):
        """End the attempt over a pull request that closed on this head."""
        _terminal_handoff._retires_the_terminal_handoff(self.context, published)
        durable = self.context.gh.read_pinned_state(self.context.issue)
        self.assertIsNone(durable.get(fixtures.KEY_PENDING_PUSH_SHA))
        self.assertFalse(_late_approval_reading._approved_commit(durable))
        return durable

    def _reports(self) -> list[dict]:
        return [
            record for record in self.context.gh.recorded_events
            if record.get("event") == LATE_TRANSFER
        ]
