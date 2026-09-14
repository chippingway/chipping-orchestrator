# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Process stops interrupt maintenance before candidate deletion."""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.git.worktrees import (
    eligibility,
    maintenance_results as _maintenance_results,
)
from tests.git.worktrees import (
    maintenance_guard_support as _guard_support,
    maintenance_payloads as _maintenance_payloads,
    maintenance_stop_support as _maintenance_stop,
    maintenance_test_support as _support,
)
from tests.git.worktrees.artifact_test_support import WIDGET_SLUG, _namespaced_branch
from tests.git.worktrees.candidate_refs import _branch_at


class InterruptedPassTest(_support._MaintenanceTestCase):
    """A pass that may no longer act stops where it is, having taken nothing.

    The candidate would otherwise be cleaned: its tip is one the base carries,
    its checkout has been quiet, and nothing holds a claim on the issue. What
    keeps every artifact is the run being on its way out, which is asked before
    the candidate rather than after it -- and asked again for each candidate
    behind it, so a stop lands between two of them rather than a repository
    later.
    """

    def setUp(self) -> None:
        super().setUp()
        self.tip = self.landed()
        self.worktree = self.settled_checkout()

    def assert_nothing_taken(self, swept) -> None:
        """No answer for the candidate, and every artifact still in place."""
        self.assertEqual(swept, ())
        self.assertTrue(self.worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_run_without_continuation_takes_nothing(self) -> None:
        # An unreadable continuation gives no permission to delete artifacts.
        for going, level in (
            (_guard_support._stopping, _maintenance_payloads.INFO_LEVEL),
            (_guard_support._unanswerable_continuation, _maintenance_payloads.WARNING),
        ):
            with self.subTest(going=going.__name__), self.assertLogs(
                _support.LIFECYCLE_LOGGER, level=level,
            ):
                swept = self.swept(going=going)

            self.assert_nothing_taken(swept)


    def test_a_stop_while_classifying_takes_nothing(self) -> None:
        # The window the per-candidate reading alone would leave open: the
        # candidate clears every gate, the run is stopped while its readings
        # are being taken, and the teardown behind them is what must not run.
        stopping = _maintenance_stop.Stopping()
        with (
            patch.object(
                eligibility,
                _maintenance_payloads._CLASSIFY_ATTR,
                _maintenance_stop.StopsWhileClassifying(stopping),
            ),
            self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.INFO_LEVEL),
        ):
            swept = self.swept(going=stopping)

        self.assert_nothing_taken(swept)

    def test_the_answer_is_taken_per_candidate(self) -> None:
        # Two candidates of one repository and two readings each -- once
        # before the candidate, once before it is acted on -- with the stop
        # arriving after the first candidate was taken: the second is left
        # exactly as the discovery found it.
        second = _namespaced_branch(WIDGET_SLUG, _maintenance_payloads.OTHER_ISSUE_NUMBER)
        _branch_at(self.clone, second, self.tip)
        self.world.publish(self.clone, second, self.tip)
        going = _maintenance_stop.StoppedAfter(2)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.INFO_LEVEL):
            swept = self.swept(going=going)

        self.assertEqual(
            [answer.outcome for answer in swept],
            [_maintenance_results.MaintenanceOutcome.CLEANED],
        )
        self.assertEqual(going.asked, [True, True, False])
        self.assertEqual(self.remote_branches(), (second,))
