# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Asynchronous polling-dispatch behavior of a pass over live schedulers."""

from __future__ import annotations

import time
import unittest

from tests.runtime import (
    polling_scheduler_probes as _probes,
    polling_signal_probes as _signal_probes,
    polling_test_support as _support,
    tick_test_support as _execution,
)


class AsyncPollingDispatchTest(unittest.TestCase):
    """A pass hands per-issue work to the scheduler and returns; it never
    waits for a handler, never relaunches an issue already in flight, and
    stops tracking one whose worker has finished.
    """

    def test_long_handler_does_not_block_next_poll(self) -> None:
        with _execution.dispatch_context(
            [_support.ALPHA_REPO, _support.BETA_REPO],
        ) as dispatch:
            poll_probe = _probes.CrossPollProbe()
            self.addCleanup(poll_probe.alpha_release.set)
            poll_probe.current_pass = 1
            started_at = time.monotonic()
            dispatch.run(poll_probe.tick)
            first_pass_elapsed = time.monotonic() - started_at

            self.assertTrue(
                poll_probe.alpha_started.wait(
                    timeout=_support.FAST_WAIT_SECONDS,
                ),
                "alpha worker should have started during pass 1",
            )
            self.assertLess(first_pass_elapsed, _support.FAST_WAIT_SECONDS)

            poll_probe.current_pass = 2
            dispatch.run(poll_probe.tick)
            self.assertTrue(
                poll_probe.beta_done.wait(timeout=_support.FAST_WAIT_SECONDS),
                "beta worker did not run while alpha remained in flight",
            )
            self.assertTrue(
                dispatch.scheduler.is_active(_support.ALPHA_REPO, 1),
            )

    def test_issue_not_relaunched_across_polls(self) -> None:
        with _execution.dispatch_context([_support.REPO]) as dispatch:
            active_probe = _probes.DuplicateActiveProbe()
            self.addCleanup(active_probe.release.set)
            dispatch.run(active_probe.tick)
            self.assertTrue(
                active_probe.started.wait(timeout=_support.FAST_WAIT_SECONDS),
            )
            dispatch.run(active_probe.tick)

            self.assertEqual(active_probe.submit_results, [True, False])
            with active_probe.lock:
                self.assertEqual(active_probe.run_count, 1)

    def test_worker_finish_clears_in_flight_marker(self) -> None:
        with _execution.dispatch_context([_support.REPO]) as dispatch:
            finish_probe = _probes.FinishedWorkerProbe()
            dispatch.run(finish_probe.tick)
            self.assertTrue(
                finish_probe.done_events[-1].wait(
                    timeout=_support.FAST_WAIT_SECONDS,
                ),
            )
            _probes.wait_until_inactive(dispatch.scheduler, _support.REPO, 3)
            self.assertFalse(dispatch.scheduler.is_active(_support.REPO, 3))

            dispatch.run(finish_probe.tick)
            self.assertTrue(
                finish_probe.done_events[-1].wait(
                    timeout=_support.FAST_WAIT_SECONDS,
                ),
            )
            self.assertEqual(finish_probe.submit_results, [True, True])
            with finish_probe.lock:
                self.assertEqual(finish_probe.run_count, 2)


class SignalledDispatchTest(unittest.TestCase):
    """A shutdown raised mid-tick closes the submit path immediately.

    `running=False` alone only stops at the next tick boundary, so a
    `workflow.engine.tick.tick` still iterating its eligible-issue list would keep landing
    fresh `scheduler.submit` calls for the rest of the dispatch loop and grow
    the in-flight set after the user asked to stop. With the submit path
    closed mid-tick, those late submits are refused and the drain only waits
    on workers that already started.
    """

    def test_late_submit_refused_in_the_same_tick(self) -> None:
        with (
            _signal_probes.isolated_shutdown(),
            _execution.dispatch_context([_support.REPO]) as dispatch,
        ):
            tick_probe = _signal_probes.SignalSubmitTick(dispatch.state)
            dispatch.run(tick_probe)

            self.assertEqual(tick_probe.submit_results, [True, False])

    def test_late_submit_refused_on_another_repo(self) -> None:
        # Same invariant where both repos are already iterating when the
        # signal fires. The cross-repo barrier ensures alpha and beta are BOTH
        # past their per-repo `running` short-circuit before the shutdown
        # lands, so beta's post-signal submit is the observable canary.
        with (
            _signal_probes.isolated_shutdown(),
            _execution.dispatch_context(
                [_support.ALPHA_REPO, _support.BETA_REPO],
            ) as dispatch,
        ):
            tick_probe = _signal_probes.MultiRepoSignalTick(dispatch.state)
            dispatch.run(tick_probe)

            self.assertEqual(tick_probe.beta_results, [False])


if __name__ == "__main__":
    unittest.main()
