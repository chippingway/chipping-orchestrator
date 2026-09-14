# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The exemption an interrupted squash still carries when it is finished.

The evidence a transfer is granted on is destroyed by the very rewrite it is
about: the head that was collapsed is off the branch and the base it was read
over is not derivable from the object that replaced it. A squash that died
before it reached the gate therefore has no plan left to offer one, and the
record it wrote beforehand is what the resumed publication offers instead --
the same pair, over the same base.

Both readings here are the real ones, at a ceiling the accepted candidate is
already past: without the transfer either case is the oversized reading that
routes an approved pull request back into adjudication on the last push before
the merge button.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import (
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)
from tests.git.publication import squash_git_support as squash_support
from tests.git.publication.squash_crash_doubles import REVISION
from tests.git.publication.squash_exemption_support import (
    LABEL_DECOMPOSING,
    _AdjudicatedSquashMixin,
)
from tests.git.publication.squash_recovery_support import LEASE, SquashRecoveryMixin


class _AdjudicatedRecoveryMixin(
    _AdjudicatedSquashMixin, SquashRecoveryMixin,
):
    """An adjudicated issue, and the crashes one squash of it survives.

    The seeding and the crash boundaries come from the two support modules
    that own them; what is composed here is the pairing this module is about,
    so the case below reads as one subject rather than as four bases.
    """


class ResumedTransferRealGitTest(
    _AdjudicatedRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A transfer decided from the record rather than from a plan."""

    def test_a_resumed_collapse_carries_it_over(self) -> None:
        gate = self._adjudicated()
        self._crashes_after_the_commit(gate)
        squashed = self._head_sha()

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success)
        self._assert_exempts(gate, squashed)
        self._assert_not_adjudicated(gate)

    def test_an_authorized_collapse_is_finished(self) -> None:
        # The narrow window the grant opens: the permission that licenses the
        # push is durable and the push itself never went out. The retry is
        # answered from that permission rather than from a plan -- re-asked in
        # full over the record it left -- so the commit publishes unmeasured
        # and the receipt behind it carries the verdict over.
        gate = self._adjudicated()
        self._crashes_before_the_push(gate)
        squashed = self._head_sha()
        outstanding = _rewrite_reading.read_rewrite_authorization(
            gate.gh.read_pinned_state(gate.issue),
        )
        self.assertEqual(
            outstanding.phase, _rewrite_values.LateRewritePhase.AUTHORIZED,
        )
        self.assertEqual(outstanding.rewrite.to_sha, squashed)

        resumed = self._next_tick(gate)
        squash_run = self._squashes(resumed)

        self.assertTrue(squash_run.success)
        self.assertEqual(
            squash_run.push_mock.call_args.kwargs[REVISION], squashed,
        )
        self._assert_exempts(resumed, squashed)
        self._assert_settled(gate)
        self._assert_not_adjudicated(gate)

    def test_a_landed_collapse_is_not_readjudicated(self) -> None:
        # The push landed and the write that would have carried the verdict
        # over was lost, so the permission is still outstanding and the
        # exemption is still on the commit a human ruled on. Finishing it is a
        # leased no-op whose receipt makes the move -- not a fresh reading of
        # a candidate this ceiling would route straight back.
        gate = self._adjudicated()
        self._crashes_after_the_push(gate)
        squashed = self._head_sha()

        resumed = self._next_tick(gate)
        squash_run = self._squashes(
            resumed, push_result=self._publishes(gate),
        )

        self.assertTrue(squash_run.success)
        self.assertEqual(
            squash_run.push_mock.call_args.kwargs[LEASE], squashed,
        )
        self._assert_exempts(resumed, squashed)
        self._assert_settled(gate)
        self._assert_not_adjudicated(gate)

    def _assert_settled(self, gate) -> None:
        """The permission the push was licensed by is spent, not standing."""
        self.assertEqual(
            _rewrite_reading.read_rewrite_authorization(
                gate.gh.read_pinned_state(gate.issue),
            ).phase,
            _rewrite_values.LateRewritePhase.PUBLISHED,
        )

    def _assert_not_adjudicated(self, gate) -> None:
        """The issue never reached the adjudication the ceiling implies."""
        self.assertNotIn(
            (gate.issue.number, LABEL_DECOMPOSING), gate.gh.label_history,
        )


if __name__ == "__main__":
    unittest.main()
