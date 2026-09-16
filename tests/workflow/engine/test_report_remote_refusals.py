# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the remote branch refuses a report over.

The checkout proves what is on this host, which is half a publication. These
are the other half: a local head equal to the recorded commit says nothing
about the ref the pull request is built from, so a report settled without this
reading can describe a state the remote does not have.

Ahead and behind stand down, because the publication gate pushes an unpublished
commit and the base-sync and conflict routes answer a remote that has moved. A
fetch or a comparison that did not happen holds instead, since nobody could say
which of those it even was.
"""
from __future__ import annotations

import unittest

from orchestrator.git.publication.probes import _BranchDivergence
from tests.workflow.engine import report_transaction_test_support as support

_FETCH_REFUSED = 128

_ONE_COMMIT = 1

# Unpushed work, a remote that has landed something since, and a branch
# rewritten onto some third commit. Each is structural and each is cleared by a
# route behind the guard, so all three stand down.
_DIVERGENT = (
    _BranchDivergence(tip=support.SOURCE_SHA, ahead=_ONE_COMMIT, readable=True),
    _BranchDivergence(tip=support.MOVED_SHA, behind=_ONE_COMMIT, readable=True),
    _BranchDivergence(tip=support.MOVED_SHA, readable=True),
)


class RemoteRefusalTest(unittest.TestCase, support.ReportTransactionCase):
    """A remote that is not standing on the recorded commit completes nothing."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_a_failed_fetch_holds(self) -> None:
        self.checkout.fetched = _FETCH_REFUSED

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_an_unreadable_divergence_holds(self) -> None:
        # Not the same question as zero-and-zero: a ref nothing could resolve
        # and a comparison git refused both count as nothing, and read as "in
        # sync" they would settle a report over a reading nobody took.
        self.checkout.remote = _BranchDivergence()

        self.assertTrue(self.reconcile())
        support.assert_still_owed(self)

    def test_a_divergent_remote_stands_down(self) -> None:
        # The three ways one readable divergence says the remote is not where
        # the report says it is. The last of them is in sync on a tip that is
        # not the report's commit -- the branch was rewritten under it, so what
        # the remote carries is not what the report describes.
        for reading in _DIVERGENT:
            with self.subTest(remote=reading):
                self.setUp()
                self.checkout.remote = reading

                self.assertFalse(self.reconcile())
                support.assert_still_owed(self)


if __name__ == "__main__":
    unittest.main()
