# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the maintenance hold closes, and that it always opens again.

The draining half -- what happens to work the hold found already running -- is
in `test_barrier_drain.py`.
"""

from __future__ import annotations

import logging
import unittest

from orchestrator.scheduler.models import SubmissionRequest
from tests.scheduler.barrier_helpers import (
    CLAIMED_ISSUE_NUMBER,
    GENEROUS_BARRIER_TIMEOUT_SECONDS,
    PRIMARY_REPO,
    SCHEDULER_LOGGER,
    WORKER_ISSUE_NUMBER,
    _BarrierTestCase,
    _forbidden_worker,
)

_MAINTENANCE_REASON = "reason=maintenance"
_BODY_FAILURE = "maintenance body failed"


class BarrierAdmissionTest(_BarrierTestCase):
    """While the hold is on, neither admission path lets anything in.

    Both paths, because the pass behind the hold is entitled to the absence of
    both: a counted worker would write in the checkout it is about to remove,
    and a tracked claim is what a family bucket takes for the issue it reaches
    next.
    """

    def test_a_submission_is_refused_and_says_why(self) -> None:
        with (
            self.assertLogs(SCHEDULER_LOGGER, level=logging.INFO) as logs,
            self.held() as quiet,
        ):
            self.assertTrue(quiet)
            self.assertFalse(self.scheduler.submit(SubmissionRequest(
                PRIMARY_REPO, WORKER_ISSUE_NUMBER, _forbidden_worker,
            )))
            self.assertTrue(any(
                _MAINTENANCE_REASON in message for message in logs.output
            ))

    def test_a_tracked_claim_is_refused(self) -> None:
        with (
            self.held() as quiet,
            self.scheduler.track_active(
                PRIMARY_REPO, CLAIMED_ISSUE_NUMBER,
            ) as claimed,
        ):
            self.assertTrue(quiet)
            # Refused, and nothing recorded for it either: a claim the
            # scheduler declined is not one the pass may be told about.
            self.assertFalse(claimed)
            self.assertFalse(self.scheduler.is_active(
                PRIMARY_REPO, CLAIMED_ISSUE_NUMBER,
            ))


class BarrierReversalTest(_BarrierTestCase):
    """Admission is given back around the body, whatever the body did.

    A hold is taken once a day by a pass that deletes things, so the failure
    that matters is not the pass going wrong: it is the pass going wrong and
    leaving this host refusing every issue until somebody restarts it.
    """

    def test_both_paths_reopen_after_the_hold(self) -> None:
        with self.held() as quiet:
            self.assertTrue(quiet)

        self.start_gated_worker(self.gate())
        with self.scheduler.track_active(
            PRIMARY_REPO, CLAIMED_ISSUE_NUMBER,
        ) as claimed:
            self.assertTrue(claimed)

    def test_admission_reopens_when_the_body_raises(self) -> None:
        with self.assertRaises(RuntimeError), self.held():
            raise RuntimeError(_BODY_FAILURE)

        with self.scheduler.track_active(
            PRIMARY_REPO, CLAIMED_ISSUE_NUMBER,
        ) as claimed:
            self.assertTrue(claimed)

    def test_a_hold_inside_a_hold_is_refused(self) -> None:
        # The pass under the first hold owns the window: a second hold would
        # reopen admission under it the moment it was given back.
        with self.held() as quiet:
            self.assertTrue(quiet)
            with self.held(timeout=0) as nested:
                self.assertFalse(nested)
            self.assertFalse(self.scheduler.submit(SubmissionRequest(
                PRIMARY_REPO, WORKER_ISSUE_NUMBER, _forbidden_worker,
            )))

    def test_a_second_hold_is_granted_after_the_first(self) -> None:
        # The hold is a pass's own, not a one-shot latch: the daemon takes one
        # every interval for the life of the process.
        for attempt in range(2):
            with self.subTest(attempt=attempt), self.held(
                timeout=GENEROUS_BARRIER_TIMEOUT_SECONDS,
            ) as quiet:
                self.assertTrue(quiet)


if __name__ == "__main__":
    unittest.main()
