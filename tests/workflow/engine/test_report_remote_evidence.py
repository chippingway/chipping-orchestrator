# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the remote branch answers a report with.

The checkout proves what is on this host, which is half a publication. These
are the other half: a local head equal to the recorded commit says nothing
about the ref the pull request is built from, so a report proved without this
reading can describe a state the remote does not have.

Ahead and behind defer, because the publication gate pushes an unpublished
commit and the base-sync and conflict routes answer a remote that has moved. A
fetch or a comparison that did not happen holds instead, since nobody could say
which of those it even was.
"""
from __future__ import annotations

import unittest

from orchestrator.git.publication.probes import _BranchDivergence
from tests.workflow.engine import report_evidence_test_support as support

_ONE_COMMIT = 1

# Unpushed work, a remote that has landed something since, and a branch
# rewritten onto some third commit. Each is structural and each is cleared by a
# route behind this evidence, so all three defer.
_DIVERGENT = (
    _BranchDivergence(tip=support.SOURCE_SHA, ahead=_ONE_COMMIT, readable=True),
    _BranchDivergence(tip=support.MOVED_SHA, behind=_ONE_COMMIT, readable=True),
    _BranchDivergence(tip=support.MOVED_SHA, readable=True),
)


class RemoteEvidenceTest(unittest.TestCase, support.ReportEvidenceCase):
    """A remote that is not standing on the recorded commit proves nothing."""

    def setUp(self) -> None:
        support.ReportEvidenceCase.setUp(self)

    def test_a_failed_fetch_holds(self) -> None:
        # The fetch is what makes the counts below about NOW, so a ref nobody
        # could refresh is a reading that did not happen.
        self.checkout.fetched = support.FETCH_REFUSED

        self.assertEqual(self.evidence().verdict, support.HOLD)

    def test_an_unreadable_divergence_holds(self) -> None:
        # Not the same question as zero-and-zero: a ref nothing could resolve
        # and a comparison git refused both count as nothing, and read as "in
        # sync" they would prove a report over a reading nobody took.
        self.checkout.remote = _BranchDivergence()

        self.assertEqual(self.evidence().verdict, support.HOLD)

    def test_a_divergent_remote_defers(self) -> None:
        # The three ways one readable divergence says the remote is not where
        # the report says it is. The last of them is in sync on a tip that is
        # not the report's commit -- the branch was rewritten under it, so what
        # the remote carries is not what the report describes.
        for reading in _DIVERGENT:
            with self.subTest(remote=reading):
                self.setUp()
                self.checkout.remote = reading

                self.assertEqual(self.evidence().verdict, support.DEFER)


if __name__ == "__main__":
    unittest.main()
