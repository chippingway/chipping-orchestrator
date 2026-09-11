# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the maintenance hold does about work it found already running.

Waits for it, within the bound it was given, and grants nothing it could not
wait out. What the hold closes while it waits is in `test_barrier.py`.
"""

from __future__ import annotations

import logging
import threading
import time
import unittest
from functools import partial

from orchestrator.scheduler import IssueScheduler
from tests.scheduler import barrier_helpers as _support
from tests.scheduler.barrier_helpers import _BarrierTestCase, _HeldClaim

_NO_QUIET_LOG = "found no quiet"
_CLOSED_REASON = "reason=closed"
# Well inside the generous bound, so an answer that came back under it proves
# the wait ended on what happened rather than on the clock running out.
_PROMPT_ANSWER_SECONDS = 2.0


def _shutdown_after(delay: float, scheduler: IssueScheduler) -> None:
    """Close the scheduler the way a signal handler does, once."""
    time.sleep(delay)
    scheduler.shutdown(wait=False)


class BarrierDrainTest(_BarrierTestCase):
    """Work already admitted is waited out rather than cancelled or hurried.

    Both kinds are waited on. A counted worker is what `submit` put in the
    pool; a tracked claim is held by a handler that is already running, and a
    hold that counted only the pool would call this host quiet with an agent
    mid-run inside one.

    Each is granted promptly rather than merely eventually: the release itself
    is what wakes the wait, so a host that goes quiet a moment in is acted on
    then and not when the bound expires.
    """

    def test_a_counted_worker_is_waited_out(self) -> None:
        release = self.gate()
        self.start_gated_worker(release)
        self.release_shortly(release)
        asked = time.monotonic()
        with self.held() as quiet:
            self.assertTrue(quiet)
            self.assertEqual(self.scheduler.active_count(), 0)
            self.assertLess(time.monotonic() - asked, _PROMPT_ANSWER_SECONDS)

    def test_a_tracked_claim_is_waited_out(self) -> None:
        claim = _HeldClaim(self.scheduler, _support.CLAIMED_ISSUE_NUMBER)
        claim.take(self)
        self.release_shortly(claim.release)
        asked = time.monotonic()
        with self.held() as quiet:
            self.assertTrue(quiet)
            self.assertFalse(self.scheduler.is_active(
                _support.PRIMARY_REPO, _support.CLAIMED_ISSUE_NUMBER,
            ))
            self.assertLess(time.monotonic() - asked, _PROMPT_ANSWER_SECONDS)

    def test_unfinished_work_refuses_the_hold(self) -> None:
        self.start_gated_worker(self.gate())
        with (
            self.assertLogs(_support.SCHEDULER_LOGGER, level=logging.INFO) as logs,
            self.held(timeout=_support.BRIEF_BARRIER_TIMEOUT_SECONDS) as quiet,
        ):
            # Refused, and the worker still holds its slot: nothing is
            # cancelled to make the hold succeed.
            self.assertFalse(quiet)
            self.assertEqual(self.scheduler.active_count(), 1)
            self.assertTrue(any(
                _NO_QUIET_LOG in message for message in logs.output
            ))


class BarrierRaceTest(_BarrierTestCase):
    """A claim taken after the counts were read is the race the hold closes.

    Nothing is admitted while it is held, so work already running cannot grow a
    claim behind the pass's back: the family bucket asking for its next issue
    mid-drain is turned down, and its next polling pass takes that issue up.
    """

    def test_admitted_work_claims_no_more(self) -> None:
        release = self.gate()
        start = threading.Event()
        claims: list[bool] = []
        self.assertTrue(self.scheduler.submit(
            _support.PRIMARY_REPO,
            _support.WORKER_ISSUE_NUMBER,
            partial(
                _support._claiming_worker,
                self.scheduler,
                _support.LATE_ISSUE_NUMBER,
                (start, release),
                claims,
            ),
        ))
        self.assertTrue(start.wait(timeout=_support.EVENT_TIMEOUT_SECONDS))
        self.release_shortly(release)
        with self.held() as quiet:
            self.assertTrue(quiet)
            self.assertEqual(claims, [False])


class BarrierShutdownTest(_BarrierTestCase):
    """A shutdown is the other answer that defers a pass.

    A process on its way out has a drain of its own to run, and the quiet a
    closing scheduler reaches is not the quiet this hold establishes -- so the
    hold is neither taken in front of one nor kept waiting once one starts.
    """

    def test_a_closed_scheduler_is_never_held(self) -> None:
        self.scheduler.shutdown()
        with (
            self.assertLogs(_support.SCHEDULER_LOGGER, level=logging.INFO) as logs,
            self.held(timeout=_support.BRIEF_BARRIER_TIMEOUT_SECONDS) as quiet,
        ):
            self.assertFalse(quiet)
            self.assertFalse(self.scheduler.submit(
                _support.PRIMARY_REPO, _support.WORKER_ISSUE_NUMBER, _support._forbidden_worker,
            ))
            # Refused as closed rather than as barred: the hold was never
            # taken, so it is not what a closing process turns work away with.
            self.assertTrue(any(
                _CLOSED_REASON in message for message in logs.output
            ))

    def test_a_shutdown_mid_wait_ends_the_wait(self) -> None:
        self.start_gated_worker(self.gate())
        threading.Thread(
            target=_shutdown_after,
            args=(_support.RELEASE_DELAY_SECONDS, self.scheduler),
            daemon=True,
        ).start()
        asked = time.monotonic()
        with self.held(timeout=_support.GENEROUS_BARRIER_TIMEOUT_SECONDS) as quiet:
            self.assertFalse(quiet)
            self.assertLess(time.monotonic() - asked, _PROMPT_ANSWER_SECONDS)


if __name__ == "__main__":
    unittest.main()
