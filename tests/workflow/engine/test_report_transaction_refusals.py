# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the transaction does with a verdict short of proof, and with no record.

Which reading refuses, and whether that refusal is a HOLD or a DEFER, is the
evidence owners' contract and is proved against them next door. What is proved
here is the other half: what the reconciliation OWES each answer once it has
one. One world-move per verdict, taken through the real readings rather than
through a stubbed one, so the translation is pinned without the classification
being written out a second time.

Nothing short of proof publishes, and nothing short of proof writes a handoff,
because a handoff is a claim that a report reached the pull request. What
differs is the tick. Held where a refusal should stand down, the issue sits
behind the very handler that clears the condition; stood down where it should
hold, nothing changes and the tick is spent.

The issue owing nothing at all closes the module, since it is the shape every
dispatch takes: what the guard costs it has to be the pinned read the
dispatcher has already made.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import report_record_state as _record_state
from tests.workflow.engine import (
    report_settled_fixture as fixture,
    report_transaction_test_support as support,
)

# What a read GitHub would not answer raises.
_REFUSED = "GitHub did not answer the read"


class EvidenceRefusalTest(unittest.TestCase, support.ReportTransactionCase):
    """A verdict short of PROVED settles nothing, and answers the tick with it."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_a_reading_nobody_could_take_holds(self) -> None:
        # A `git status` that failed stands for every HOLD: nothing was
        # learned, so the tick stops and the next one asks again.
        self.checkout.status = _WorktreeStatus(readable=False)

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_a_structural_refusal_stands_down(self) -> None:
        # A head a later run moved off the recorded commit stands for every
        # DEFER: what would clear it is a route BEHIND this guard, so holding
        # would strand the issue in front of its own remedy.
        self.checkout.head = support.MOVED_SHA

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_an_unreadable_pull_request_parks_nothing(self) -> None:
        # A hold taken on the PULL REQUEST outranks every refusal this owner
        # takes over its own records. The damage is still damage, but whether
        # it stands in front of a terminal is exactly what could not be
        # established -- and a park is the one answer the tick that takes it
        # cannot take back.
        fixture.records_handoff(
            self.state, support.RECEIPT, 1, support.MOVED_SHA,
        )

        with patch.object(
            self.gh, "get_pr", side_effect=RuntimeError(_REFUSED),
        ):
            self.assertTrue(self.reconcile())

        self.assertIsNone(self.state.get(support.PARK_REASON))
        support.assert_nothing_published(self)

    def test_an_issue_owing_nothing_costs_nothing(self) -> None:
        # A settled transaction leaves the key holding `null`, so this is also
        # every issue that has ever published a report.
        _record_state.clear_pending_report(self.state)
        writes = self.gh.write_state_calls

        self.assertFalse(self.reconcile())

        self.assertEqual(support.report_comments(self), [])
        self.assertEqual(self.gh.write_state_calls, writes)


if __name__ == "__main__":
    unittest.main()
