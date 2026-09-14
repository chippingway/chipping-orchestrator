# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One polling pass: repository fan-out, failure isolation, and its drains."""

from __future__ import annotations

import threading
import unittest

from orchestrator.runtime.state import RuntimeState
from tests.runtime import (
    polling_scheduler_probes as _probes,
    polling_test_support as _support,
    tick_test_support as _execution,
)

_ALPHA_FAILURE = "simulated alpha failure"


class RepositoryFanOutTest(unittest.TestCase):
    """A pass reaches every configured repository exactly once, pairs each
    spec with the client built for it, and lets the repos overlap. One repo
    wedged in an unhandled error must not stop the others from advancing.
    """

    def test_every_repo_ticks_with_its_own_client(self) -> None:
        # Recording the (spec.slug, gh.slug) pairing surfaces a regression
        # that crossed wires (spec for alpha paired with beta's gh).
        with _execution.dispatch_context(
            [_support.ALPHA_REPO, _support.BETA_REPO],
        ) as dispatch:
            recorder = _support.TickRecorder()
            dispatch.run(recorder)

            # Parallel fan-out makes the call order non-deterministic; the
            # invariant is that every (spec, paired client) tuple appears
            # exactly once and the pairing is correct.
            self.assertEqual(
                set(recorder.calls),
                {
                    (_support.ALPHA_REPO, _support.ALPHA_REPO),
                    (_support.BETA_REPO, _support.BETA_REPO),
                },
            )
            self.assertEqual(len(recorder.calls), 2)

    def test_single_repo_stays_in_thread(self) -> None:
        # A regression that always spawned a worker thread (even for one
        # repo) would show a different tid here, and would change behavior
        # for every deployment that polls a single repository.
        with _execution.dispatch_context([_support.REPO]) as dispatch:
            recorder = _support.TickRecorder()
            dispatch.run(recorder)

            self.assertEqual(recorder.slugs, [_support.REPO])
            self.assertEqual(recorder.threads, [threading.get_ident()])

    def test_repo_failure_does_not_block_others(self) -> None:
        slugs = [_support.ALPHA_REPO, _support.BETA_REPO, _support.GAMMA_REPO]
        with _execution.dispatch_context(slugs) as dispatch:
            recorder = _support.TickRecorder(
                on_tick=lambda gh, spec: _support.raise_on_slug(
                    spec,
                    _support.ALPHA_REPO,
                    _ALPHA_FAILURE,
                ),
            )
            dispatch.run(recorder)

            self.assertEqual(set(recorder.slugs), set(slugs))
            self.assertEqual(len(recorder.slugs), 3)

    def test_repos_run_concurrently(self) -> None:
        # The whole point of fan-out: configured repos must overlap. A
        # `Barrier(N)` requires every worker to arrive before any can leave,
        # so it deadlocks under sequential iteration and the bounded timeout
        # surfaces that regression as a test failure.
        slugs = [_support.ALPHA_REPO, _support.BETA_REPO, _support.GAMMA_REPO]
        with _execution.dispatch_context(slugs) as dispatch:
            tick_probe = _probes.BarrierTick(len(slugs))
            dispatch.run(tick_probe)

            self.assertEqual(set(tick_probe.completed), set(slugs))

    def test_requested_shutdown_skips_the_pass(self) -> None:
        # A shutdown that already arrived (between poll iterations, or while
        # the fan-out was still queueing repos) must skip the tick entirely
        # rather than run one more before the process exits.
        stopped = RuntimeState(running=False)
        with _execution.dispatch_context(
            [_support.ALPHA_REPO, _support.BETA_REPO],
            state=stopped,
        ) as dispatch:
            recorder = _support.TickRecorder()
            dispatch.run(recorder)

            self.assertEqual(recorder.slugs, [])


class PassDrainTest(unittest.TestCase):
    """Both drains a pass ends with -- the scheduler's completion reap and
    the analytics prune -- run exactly once per pass regardless of how many
    repositories are configured, because both are process-wide rather than
    per-repo.
    """

    def test_drains_run_once_per_pass(self) -> None:
        for slugs in (
            [_support.REPO],
            [_support.ALPHA_REPO, _support.BETA_REPO],
        ):
            with self.subTest(repos=len(slugs)):
                with _execution.dispatch_context(slugs) as dispatch:
                    reap, prune = dispatch.run_and_capture_drains()

                self.assertEqual(reap.call_count, 1)
                prune.assert_called_once_with()

    def test_real_dispatch_reaps_once(self) -> None:
        # The mocked-tick paths above cannot see a reap the engine itself
        # might add, so one pass runs through the real `workflow.engine.tick.tick` over
        # empty issue lists: `_dispatch_via_scheduler` deliberately does not
        # reap, leaving the pass as the only site that does.
        with _execution.dispatch_context(
            [_support.ALPHA_REPO, _support.BETA_REPO],
        ) as dispatch:
            reap = dispatch.run_real_and_capture_reap()

            self.assertEqual(reap.call_count, 1)


if __name__ == "__main__":
    unittest.main()
