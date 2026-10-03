# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The same observation hold, on the two ticks that run without a scheduler.

`parallel_limit` picks one of three paths: the scheduler's submit, a
sequential stream on the polling thread, and a bounded fan-out. All three run
the same cleanup route over a closed late-split owner, so all three have to
keep the same thing when that pass fails -- the OBSERVATION, which is the
reading a human who reopens the issue before the next tick takes off the
remote for good.

Neither direct path has the scheduler's wrapper to do it, and the failure they
have to survive is the first thing a cleanup spends: the refetch it opens with.

The sequential path classifies for itself rather than taking a hand-off, so it
is also where a CLOSED issue on any of the four cleanup labels is told apart
from an open one, which goes to the handler its refetched label names.
"""
from __future__ import annotations

import unittest

from tests.workflow.engine.cleanup_deferral_support import (
    OWNER_NUMBER,
    REPO_SLUG,
    WORKFLOW_LOG,
    DeferralCase,
    ticked_directly,
)
from tests.workflow.engine.unfinished_cleanup_support import (
    UnfinishedCleanupCase,
)
from tests.workflow.fixtures import LABEL_READY, LABEL_REJECTED

_OWED = frozenset((OWNER_NUMBER,))

# The two supported direct modes: the legacy in-thread stream, and the fan-out
# anything above one worker takes.
_DIRECT_LIMITS = (1, 2)


class DirectCleanupFailureTest(DeferralCase, unittest.TestCase):
    """A cleanup that broke on a schedulerless tick still owes its reading."""

    def test_the_failed_pass_marks_nothing(self) -> None:
        for limit in _DIRECT_LIMITS:
            with self.subTest(limit=limit):
                self.setUp()

                with self.assertLogs(WORKFLOW_LOG):
                    ticked_directly(self, limit, failing=True)

                self.assertFalse(self._cancelled())

    def test_the_observation_is_owed_again(self) -> None:
        for limit in _DIRECT_LIMITS:
            with self.subTest(limit=limit):
                self.setUp()

                with self.assertLogs(WORKFLOW_LOG):
                    ticked_directly(self, limit, failing=True)

                self.assertEqual(self._observed(REPO_SLUG), _OWED)

    def test_a_reopen_after_the_failure_still_ends_it(self) -> None:
        # The whole of it: nothing ever reads this issue closed again, and
        # its label names the handler that walks a dependency graph and
        # activates children. Without the hold the reopened owner would reach
        # exactly that handler over a cycle a close already ended.
        for limit in _DIRECT_LIMITS:
            with self.subTest(limit=limit):
                self.setUp()

                with self.assertLogs(WORKFLOW_LOG):
                    ticked_directly(self, limit, failing=True)
                self._reopened()
                with self.assertLogs(WORKFLOW_LOG):
                    ticked_directly(self, limit)

                self.assertTrue(self._cancelled())
                self.stage.assert_not_called()
                self.assertEqual(self._observed(REPO_SLUG), frozenset())

    def test_a_pass_that_lands_settles_it(self) -> None:
        # The baseline both paths are measured against, so the hold is not
        # simply "never settled here".
        for limit in _DIRECT_LIMITS:
            with self.subTest(limit=limit):
                self.setUp()

                with self.assertLogs(WORKFLOW_LOG):
                    ticked_directly(self, limit)

                self.assertTrue(self._cancelled())
                self.assertEqual(self._observed(REPO_SLUG), frozenset())


class DirectRecoveryLabelTest(UnfinishedCleanupCase, unittest.TestCase):
    """The sequential path's own reading of an interrupted ending's label.

    It classifies for itself, so it decides alone whether a closed `ready`
    owner is a cleanup or the handler that hands an issue to a developer. Its
    open counterpart is not a cleanup: an ending is not something an open
    `ready` issue is in the middle of.
    """

    def setUp(self) -> None:
        super().setUp()
        self._every_tick_sweeps()
        self._relabelled(LABEL_READY)

    def test_a_closed_owner_there_is_a_cleanup(self) -> None:
        with self.assertLogs(WORKFLOW_LOG):
            ticked_directly(self, 1)

        self.assertTrue(self._cancelled())
        self.assertEqual(self._label(), LABEL_REJECTED)
        self.stage.assert_not_called()

    def test_the_refetch_it_opens_with_is_taken(self) -> None:
        # The route is the one with a refetch INSIDE the observation hold,
        # not the poll's own object handed straight to a handler: a read that
        # raises marks nothing and leaves the reading for the next tick.
        with self.assertLogs(WORKFLOW_LOG):
            ticked_directly(self, 1, failing=True)

        self.assertFalse(self._cancelled())
        self.assertEqual(self._observed(REPO_SLUG), _OWED)


if __name__ == "__main__":
    unittest.main()
