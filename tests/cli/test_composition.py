# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `cli.main` composes, in the order a startup depends on."""

from __future__ import annotations

import signal
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import processes as _agent_processes
from orchestrator.runtime import artifacts, loop, shutdown
from tests.cli.composition_test_support import composed_run
from tests.runtime import polling_test_support as _support

_TERMINATE_ATTR = "terminate_all_running"
_WORKTREES_ATTR = "WORKTREES_DIR"
_DRIVE_POLLING_ATTR = "drive_polling"
_MAINTENANCE_PASS_ATTR = "run_maintenance_pass"
_DEBUG_ARGS = ("--once", "--log-level", "DEBUG")
_MISSING_ALLOWLIST = (
    "ALLOWED_ISSUE_AUTHORS must contain at least one GitHub login. "
    "Configure it before starting the orchestrator, for example: "
    "ALLOWED_ISSUE_AUTHORS=alice,bob"
)
_LAUNCH_ARGS = ((), _support.ONCE_ARGS, ("--cleanup-terminal-artifacts",))


def _restart_after_signal(state, _options, _clients, _scheduler) -> int:
    """Stand in for a loop that recorded a signal and still asks to restart."""
    state.received_signal = signal.SIGTERM
    return 0


class ComposedStartupTest(unittest.TestCase):
    """A run connects each configured repository once, shares one scheduler
    across every tick, and publishes it before the first tick can hand it
    work -- the signal handler closes the submit path through exactly that
    reference.
    """

    def test_repos_connect_and_share_one_scheduler(self) -> None:
        with composed_run([_support.ALPHA_REPO, _support.BETA_REPO]) as run:
            exit_code = run.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                set(run.clients.by_slug),
                {_support.ALPHA_REPO, _support.BETA_REPO},
            )
            # One scheduler for every spec -- a per-repo scheduler would let
            # each repo independently saturate the global cap.
            self.assertEqual(len(run.schedulers.built), 1)
            self.assertEqual(
                run.recorder.schedulers,
                [run.scheduler, run.scheduler],
            )

    def test_scheduler_published_before_first_tick(self) -> None:
        published: list[object] = []
        with composed_run([_support.REPO]) as run:
            run.on_tick = lambda gh, spec: published.append(
                run.state.active_scheduler,
            )
            run.main()

            self.assertEqual(published, [run.scheduler])

    def test_logging_and_handlers_settled_for_the_run(self) -> None:
        # Both are installed before the first GitHub call, so a stop that
        # arrives during a slow connect is honoured and the connect's own
        # failures reach the operator's log.
        with composed_run([_support.REPO]) as run:
            run.main(_DEBUG_ARGS)

            run.seams.configured_logging.assert_called_once_with("DEBUG")
            run.seams.installed_handlers.assert_called_once_with(run.state)


class AuthorAllowlistStartupTest(unittest.TestCase):
    """A run starts only on an author allowlist that names somebody.

    An empty one would trust every author, so each launch mode stops on it
    with the error an operator can act on and before any GitHub client,
    scheduler, poll, or maintenance pass exists. The loop and the pass are
    stood in for so that a launch which ever got past the stop would end
    here instead of polling forever or reading the operator's own clones.
    """

    def test_an_empty_allowlist_stops_each_launch(self) -> None:
        for argv in _LAUNCH_ARGS:
            with self.subTest(argv=argv), composed_run(
                [_support.ALPHA_REPO], allowed_authors=(),
            ) as run, patch.object(
                loop, _DRIVE_POLLING_ATTR,
            ) as polled, patch.object(
                artifacts, _MAINTENANCE_PASS_ATTR,
            ) as reclaimed:
                stopped = self.assertRaises(SystemExit)
                with stopped:
                    run.main(argv)

                # A string code is what exits the process with status 1 and
                # the message on stderr.
                self.assertEqual(stopped.exception.code, _MISSING_ALLOWLIST)
                self.assertEqual(run.clients.by_slug, {})
                self.assertEqual(run.schedulers.built, [])
                polled.assert_not_called()
                reclaimed.assert_not_called()

    def test_a_populated_allowlist_starts_the_run(self) -> None:
        with composed_run(
            [_support.ALPHA_REPO], allowed_authors=("alice", "bob"),
        ) as run:
            exit_code = run.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(set(run.clients.by_slug), {_support.ALPHA_REPO})
            self.assertEqual(run.recorder.slugs, [_support.ALPHA_REPO])


class HermeticHostTest(unittest.TestCase):
    """A composed run claims a host of its own rather than the operator's.

    The claim a polling run takes is a real `flock` on a real file under
    `WORKTREES_DIR`. Left pointing at the operator's checkout root, every test
    here would leave a lock file in it -- and, far worse than the litter, a
    real maintenance pass holding that host would have all of them waiting on
    it, which is precisely what that claim is built to make a process do.
    """

    def test_the_run_claims_a_root_of_its_own(self) -> None:
        configured = getattr(config, _WORKTREES_ATTR)
        with composed_run([_support.REPO]) as run:
            run.main()

            claimed = getattr(config, _WORKTREES_ATTR)
            self.assertNotEqual(claimed, configured)

        # And it goes when the run does, so nothing one test claimed is still
        # standing for the next.
        self.assertFalse(claimed.exists())


class ComposedExitTest(unittest.TestCase):
    """Every exit drains the scheduler before `main` returns, and the code it
    returns is what `run.sh` keys its restart loop on.
    """

    def test_scheduler_shut_down_before_main_returns(self) -> None:
        # Without the drain the daemon executor threads could be torn down
        # mid-handler at process exit; a submit refused afterwards is the
        # observable half of it.
        with composed_run([_support.REPO]) as run:
            run.main()

            self.assertFalse(
                run.scheduler.submit(
                    _support.REPO,
                    _support.UNUSED_ISSUE_NUMBER,
                    lambda: None,
                ),
                "scheduler was not shut down before main() returned",
            )

    def test_tick_signal_yields_the_signal_exit_code(self) -> None:
        with composed_run([_support.REPO]) as run:
            run.on_tick = lambda gh, spec: shutdown.request_shutdown(
                run.state,
                signal.SIGINT,
                None,
            )
            with patch.object(_agent_processes, _TERMINATE_ATTR) as terminated:
                exit_code = run.main()

                terminated.assert_called_once_with()

            # 128 + SIGINT(2) = 130. `run.sh` keys on this to skip restart,
            # and the drain kills in-flight groups up front so the process is
            # gone well inside the stop deadline.
            self.assertEqual(
                exit_code,
                _support.SIGNAL_EXIT_BASE + signal.SIGINT,
            )

    def test_clean_exit_leaves_in_flight_agents_alone(self) -> None:
        # The non-signal paths (`--once` finishing, a self-modifying-merge
        # restart) keep the "let in-flight work finish" drain.
        with composed_run([_support.REPO]) as run:
            with patch.object(_agent_processes, _TERMINATE_ATTR) as terminated:
                exit_code = run.main()

                terminated.assert_not_called()

            self.assertEqual(exit_code, 0)

    def test_requested_restart_outranks_signal_code(self) -> None:
        # A restart is the loop's own answer, so it is returned as given: the
        # wrapper relaunches on 0 and would skip the restart on 143.
        with composed_run([_support.REPO]) as run:
            with patch.object(
                loop,
                _DRIVE_POLLING_ATTR,
                side_effect=_restart_after_signal,
            ):
                exit_code = run.main([])

            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
