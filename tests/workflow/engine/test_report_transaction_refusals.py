# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a checkout that cannot vouch for the commit does to a transaction.

Every case here ends the same way -- nothing posted, the transaction still
recorded, no handoff written -- because a handoff on anything less than proof is
a claim that an unpublished report reached the pull request. What differs is the
ANSWER the tick gives, and that split is the contract worth pinning: a reading
nobody could take holds the tick so the next one asks again, while everything
structural stands down and lets the route that would actually fix it run.

Held where a refusal should stand down, the issue sits behind the very handler
that clears the condition -- the dirty-worktree park, the publication gate.
Stood down where it should hold, nothing changes and the tick is spent.
"""
from __future__ import annotations

import unittest

from orchestrator.git.verification.status import _WorktreeStatus
from tests.workflow.engine import report_transaction_test_support as support

_DIRTY = _WorktreeStatus(readable=True, paths=("stray.py",))

_UNREADABLE = _WorktreeStatus(readable=False)


class CheckoutRefusalTest(unittest.TestCase, support.ReportTransactionCase):
    """A checkout that cannot vouch for the commit completes nothing."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_a_dirty_tree_stands_down(self) -> None:
        self.checkout.status = _DIRTY

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_an_unreadable_tree_holds(self) -> None:
        # A `git status` that failed names no paths, and so does a tree with
        # nothing in it -- only a reading that HAPPENED is a clean tree.
        self.checkout.status = _UNREADABLE

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_a_headless_checkout_holds(self) -> None:
        self.checkout.head = ""

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_a_moved_head_stands_down(self) -> None:
        self.checkout.head = support.MOVED_SHA

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)

    def test_an_absent_checkout_stands_down(self) -> None:
        # The commit is on whichever host made it, and the stage behind this
        # guard has its own answer for a checkout that is not here.
        self.checkout.path = self.checkout.path / "gone"

        self.assertFalse(self.reconcile())
        support.assert_still_owed(self)


if __name__ == "__main__":
    unittest.main()
