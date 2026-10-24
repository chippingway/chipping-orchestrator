# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The launch that reclaims artifacts and does nothing else.

Composed the same way the polling run is -- one state, the handler, one
scheduler, the guaranteed drain -- because a run that deletes checkouts is
stopped by a signal exactly as a polling one is. What it must NOT do is the
whole point of the mode: no label bootstrap on the way in, no tick, and no
workflow write to any repository it was pointed at.

Nor may it act at all on a host another orchestrator process is live on. That
claim is real in every case here, because it is the only coordination in this
tree that reaches a process this one cannot see -- and the scheduler barrier
inside it, being one process's own, would grant the quiet of an empty process
however busy the other one is. The checkout root it is taken under is the
composed run's own, which is also why a test that contends for the claim takes
its own from INSIDE that run: outside it, the two would be claiming different
hosts and would agree about everything.

The pass itself is intercepted. What it does is settled in
`tests/runtime/test_artifacts.py` against stood-in collaborators; letting the
real one run from this composition would put a live discovery over the
operator's own clones inside a unit test.
"""

from __future__ import annotations

import signal
import unittest
from unittest.mock import patch

from orchestrator import cli, config
from orchestrator.git.worktrees.maintenance_results import MaintenanceOutcome, MaintenanceReason
from orchestrator.runtime import artifacts, exclusion, shutdown, startup
from tests.cli.composition_test_support import RUN, composed_run
from tests.runtime import polling_test_support as _support, refused_pass_support as _refused

_PASS_ATTR = "run_maintenance_pass"
_CLIENT_ATTR = "GitHubClient"
_CLEANUP_ARGS = (*RUN, "--cleanup-terminal-artifacts")
_BOTH_REPOS = (_support.ALPHA_REPO, _support.BETA_REPO)


class MaintenanceOnlyRunTest(unittest.TestCase):
    """One pass over every configured repository, and no workflow at all."""

    def test_it_reclaims_without_polling_or_writing(self) -> None:
        with composed_run(list(_BOTH_REPOS)) as run, patch.object(
            artifacts, _PASS_ATTR,
        ) as reclaimed:
            exit_code = run.main(_CLEANUP_ARGS)

            self.assertEqual(exit_code, 0)
            self.assertEqual(set(run.clients.by_slug), set(_BOTH_REPOS))
            for github_client in run.clients.by_slug.values():
                github_client.ensure_workflow_labels.assert_not_called()
            # Nothing polled and nothing relabelled: the mode reads issues and
            # pull requests, and an issue that has ended keeps every record of
            # how it ended.
            self.assertEqual(run.recorder.calls, [])
            reclaimed.assert_called_once_with(
                run.state,
                [
                    (spec, run.clients.by_slug[spec.slug])
                    for spec in _support.repo_specs(_BOTH_REPOS)
                ],
                run.scheduler,
            )

    def test_the_scheduler_is_drained_before_return(self) -> None:
        # The mode submits nothing, but it publishes a scheduler the signal
        # handler may close and holds the pass under its barrier -- so it owes
        # the same drain, which is what sets the event the watchdog waits on.
        with composed_run([_support.REPO]) as run, patch.object(
            artifacts, _PASS_ATTR,
        ):
            run.main(_CLEANUP_ARGS)

            self.assertTrue(run.state.shutdown_complete.is_set())
            self.assertFalse(
                run.scheduler.submit(
                    _support.REPO,
                    _support.UNUSED_ISSUE_NUMBER,
                    lambda: None,
                ),
                "scheduler was not shut down before main() returned",
            )

    def test_a_signal_yields_the_signal_exit_code(self) -> None:
        with composed_run([_support.REPO]) as run, patch.object(
            artifacts,
            _PASS_ATTR,
            side_effect=lambda state, *rest: shutdown.request_shutdown(
                state, signal.SIGTERM, None,
            ),
        ):
            exit_code = run.main(_CLEANUP_ARGS)

            # 128 + SIGTERM(15) = 143, which is what `run.sh` keys on to skip
            # its restart loop.
            self.assertEqual(
                exit_code, _support.SIGNAL_EXIT_BASE + signal.SIGTERM,
            )


class ProbingClients:
    """The client factory, with what the host looked like at connect time.

    Connecting is the one step of this mode whose duration nothing bounds: a
    client that lands in a rate-limit backoff sleeps until the reset, and
    PyGithub's retry does it inside the constructor's own session. Every second
    of that inside the claim is a second another process waits for this host
    with its own admission closed -- so what this records is whether the host
    was still anybody's to take while the connect ran.
    """

    def __init__(self, clients) -> None:
        self.host_free: list[bool] = []
        self._clients = clients

    def __call__(self, *, repo_spec):
        with exclusion.artifact_exclusivity() as host:
            self.host_free.append(host.taken)
        return self._clients(repo_spec=repo_spec)


class SharedHostTest(unittest.TestCase):
    """A host with a live polling process on it is one this mode leaves alone.

    The work that process owns is in its own scheduler and its own claims, so
    nothing this run could ask would find it: the barrier would be granted the
    quiet of an empty process, and the per-candidate claim guard would report
    nothing running. So the host claim is what decides, and a refusal is a run
    that connects nothing and reads nothing.
    """

    def test_a_live_polling_process_defers_it(self) -> None:
        with (
            composed_run([_support.REPO]) as run,
            patch.object(artifacts, _PASS_ATTR) as reclaimed,
            exclusion.polling_presence(),
        ):
            exit_code = run.main(_CLEANUP_ARGS)

            # Deferring is what it was asked to do, so the timer unit sees a
            # success rather than a failure to investigate. Nothing was swept
            # and nothing was built to sweep with; the clients it connected on
            # the way in were never asked anything.
            self.assertEqual(exit_code, 0)
            reclaimed.assert_not_called()
            self.assertEqual(run.schedulers.built, [])
            for github_client in run.clients.by_slug.values():
                self.assertEqual(github_client.method_calls, [])

    def test_the_connect_is_outside_the_claim(self) -> None:
        # Nothing whose duration this mode cannot bound may run while it holds
        # the host: the connect is done first, so the host is still free while
        # it happens and the exclusive window is only the pass.
        with composed_run([_support.REPO]) as run, patch.object(
            artifacts, _PASS_ATTR,
        ):
            probing = ProbingClients(run.clients)
            with patch.object(startup, _CLIENT_ATTR, side_effect=probing):
                self.assertEqual(run.main(_CLEANUP_ARGS), 0)

            self.assertEqual(probing.host_free, [True])
            self.assertEqual(set(run.clients.by_slug), {_support.REPO})

    def test_a_polling_run_holds_the_host(self) -> None:
        # The other side of the same contract, asked from inside a tick: while
        # a polling run is live, no maintenance pass on this host may act.
        exclusive: list[bool] = []
        with composed_run([_support.REPO]) as run:
            run.on_tick = lambda gh, spec: exclusive.append(
                _exclusivity_granted(),
            )
            self.assertEqual(run.main(), 0)

        self.assertEqual(exclusive, [False])


class RefusedRecordRunTest(_refused.RefusedPassCase):
    """The maintenance-only run keeps what admission or a writer claim refuses, on a real host.

    The one case here that lets the pass run: the composed run is pointed at
    the host the git fixtures built and connected to their client, so the run
    reaches the teardown through every gate a launch puts in front of it. The
    unpinned issue is held by another poller on this host throughout.
    """

    def test_it_keeps_the_refused_and_the_contended(self) -> None:
        standing, on_github = self.issues.standing(), self.issues.on_github()
        with (
            composed_run([self.spec.slug]),
            patch.object(config, "default_repo_specs", return_value=[self.spec]),
            patch.object(config, "WORKTREES_DIR", self.world.worktrees),
            patch.object(startup, _CLIENT_ATTR, return_value=self.gh),
            self.contended(),
        ):
            run = self.recorded(cli.main, list(_CLEANUP_ARGS))

        self.assertEqual(run.answer, 0)
        self.assertEqual(run.records, {
            _refused.REFUSED: (MaintenanceOutcome.RETAINED, MaintenanceReason.UNPROVEN),
            _refused.ADMITTED: (MaintenanceOutcome.CLEANED, MaintenanceReason.RECLAIMED),
            _refused.UNPINNED: (MaintenanceOutcome.RETAINED, MaintenanceReason.WRITER_CLAIM_REFUSED),
        })
        self.assertEqual(self.issues.standing(), {
            **standing, _refused.ADMITTED: _refused.GONE,
        })
        self.assertEqual(self.issues.on_github(), on_github)
        self.assertEqual(self.issues.said(run.output), 1, run.output)


def _exclusivity_granted() -> bool:
    """Whether a maintenance pass could take this host right now."""
    with exclusion.artifact_exclusivity() as host:
        return host.taken


if __name__ == "__main__":
    unittest.main()
