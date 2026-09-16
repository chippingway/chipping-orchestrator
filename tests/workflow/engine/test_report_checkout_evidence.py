# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a checkout that cannot vouch for the commit answers a report with.

Every case here refuses, and what differs is the ANSWER -- which is the contract
worth pinning. A reading nobody could take HOLDS, so the next tick asks again,
while everything structural DEFERS and lets the route that would actually fix it
run.

Held where a refusal should defer, the issue sits behind the very handler that
clears the condition -- the dirty-worktree park, the publication gate. Deferred
where it should hold, a report is one reading away from being published over a
world nobody saw.
"""
from __future__ import annotations

import unittest

from orchestrator.git.verification.status import _WorktreeStatus
from tests.workflow.engine import report_evidence_test_support as support

_DIRTY = _WorktreeStatus(readable=True, paths=("stray.py",))

_UNREADABLE = _WorktreeStatus(readable=False)


class CheckoutEvidenceTest(unittest.TestCase, support.ReportEvidenceCase):
    """A checkout that cannot vouch for the commit proves nothing."""

    def setUp(self) -> None:
        support.ReportEvidenceCase.setUp(self)

    def test_a_dirty_tree_defers(self) -> None:
        self.checkout.status = _DIRTY

        self.assertEqual(self.evidence().verdict, support.DEFER)

    def test_an_unreadable_tree_holds(self) -> None:
        # A `git status` that failed names no paths, and so does a tree with
        # nothing in it -- only a reading that HAPPENED is a clean tree.
        self.checkout.status = _UNREADABLE

        self.assertEqual(self.evidence().verdict, support.HOLD)

    def test_a_headless_checkout_holds(self) -> None:
        self.checkout.head = ""

        self.assertEqual(self.evidence().verdict, support.HOLD)

    def test_a_moved_head_defers(self) -> None:
        self.checkout.head = support.MOVED_SHA

        self.assertEqual(self.evidence().verdict, support.DEFER)

    def test_an_absent_checkout_defers(self) -> None:
        # The commit is on whichever host made it, and the stage behind this
        # evidence has its own answer for a checkout that is not here.
        self.checkout.path = self.checkout.path / "gone"

        self.assertEqual(self.evidence().verdict, support.DEFER)


if __name__ == "__main__":
    unittest.main()
