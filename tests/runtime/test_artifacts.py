# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When the finished issues' artifacts are reclaimed, and under what.

The cadence, the hold the pass is only allowed to run under, and the split of
one host-wide discovery back into the repository each candidate belongs to.
"""

from __future__ import annotations

import logging
import time
import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.git.worktrees import discovery, maintenance
from orchestrator.git.worktrees.maintenance_results import MaintenanceOutcome, MaintenanceReason
from orchestrator.runtime import artifacts, exclusion
from orchestrator.runtime.state import RuntimeState
from tests.runtime import (
    artifact_test_support as _artifacts,
    handover_test_support as _handover,
    polling_test_support as _support,
)

_INTERVAL_ATTR = "TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS"
_MONOTONIC_ATTR = "monotonic"
_DAY_SECONDS = 86400
_SHORT_INTERVAL_SECONDS = 60
_BARRIER_ATTR = "_QUIESCENCE_TIMEOUT_SECONDS"
_BUDGET_ATTR = "_HOST_HOLD_BUDGET_SECONDS"
_SPENT_BUDGET_SECONDS = 0
_DISCOVERY_FAILURE = "the host could not be scanned"
_DEFERRED_LOG = "deferred"
_UNCLAIMED_LOG = "not this process's to take"
_CONTENDED_LOG = "took this host while this one was going quiet"
_OVERRAN_LOG = "giving it back"
_RAISED_LOG = "raised"


class DueGateTest(unittest.TestCase):
    """A pass is owed once an interval, on the clock that cannot jump.

    The first ask of a run is always owed one, which is what makes a restart
    cost at most one extra pass rather than a missed one. Every ask inside the
    interval after that is refused, so a poll every minute does not turn into a
    host-wide teardown every minute.
    """

    def test_a_fresh_gate_is_owed_a_pass_at_once(self) -> None:
        # Nothing is persisted, so the first ask of a run is always owed one
        # and the run that comes back after a restart owes another: repeating
        # a pass costs one discovery and reports what is already gone as done.
        gate = artifacts.DueGate()
        self.assertEqual([gate.due(), gate.due()], [True, False])
        self.assertTrue(artifacts.DueGate().due())

    def test_asks_inside_the_interval_are_refused(self) -> None:
        gate = artifacts.DueGate()
        # A day of polling at the default interval, spelled as the clock
        # readings the asks along the way would take.
        readings = (0, 60, 3600, _DAY_SECONDS - 1)
        with patch.object(time, _MONOTONIC_ATTR, side_effect=readings):
            self.assertEqual(
                [gate.due() for _ask in readings],
                [True, False, False, False],
            )

    def test_the_interval_elapsing_owes_another_pass(self) -> None:
        gate = artifacts.DueGate()
        readings = (0, _DAY_SECONDS, 2 * _DAY_SECONDS)
        with patch.object(time, _MONOTONIC_ATTR, side_effect=readings):
            self.assertEqual(
                [gate.due() for _ask in readings],
                [True, True, True],
            )

    def test_the_configured_interval_is_read_per_ask(self) -> None:
        # Read at the ask rather than captured when the gate was created, so
        # what decides the cadence is the setting in force when the question
        # is put and nothing about when this run started.
        gate = artifacts.DueGate()
        readings = (0, 2 * _SHORT_INTERVAL_SECONDS)
        with (
            patch.object(config, _INTERVAL_ATTR, _SHORT_INTERVAL_SECONDS),
            patch.object(time, _MONOTONIC_ATTR, side_effect=readings),
        ):
            self.assertEqual(
                [gate.due() for _ask in readings],
                [True, True],
            )


class MaintenancePassTest(_artifacts._MaintenanceTestCase):
    """The pass runs under the hold and nowhere else.

    A host that could not be proved quiet is not scanned, let alone acted on:
    the deferral is decided before the first reading, because a reading taken
    on a busy host is what a later deletion would be spent on.
    """

    def test_an_unclaimed_host_is_not_even_held(self) -> None:
        # The outer gate, and the one about the processes this one cannot see:
        # a run that does not hold this host does not scan it, and does not
        # get as far as asking its own scheduler for quiet.
        with (
            patch.object(discovery, _artifacts.CANDIDATES_ATTR) as discovered,
            self.assertLogs(
                _artifacts.LIFECYCLE_LOGGER, level=logging.INFO,
            ) as logs,
        ):
            artifacts.run_maintenance_pass(
                RuntimeState(), self.clients, self.scheduler,
            )

            discovered.assert_not_called()
            self.assertTrue(any(
                _UNCLAIMED_LOG in message for message in logs.output
            ))
        self.assertEqual(self.scheduler.holds, 0)

    def test_a_busy_host_is_not_even_scanned(self) -> None:
        self.scheduler.quiet = False
        with (
            patch.object(discovery, _artifacts.CANDIDATES_ATTR) as discovered,
            patch.object(maintenance, _artifacts.MAINTAINED_ATTR) as maintained,
            self.assertLogs(
                _artifacts.LIFECYCLE_LOGGER, level=logging.INFO,
            ) as logs,
        ):
            artifacts.run_maintenance_pass(
                self.state(), self.clients, self.scheduler,
            )

            discovered.assert_not_called()
            maintained.assert_not_called()
            self.assertTrue(any(
                _DEFERRED_LOG in message for message in logs.output
            ))
        self.assertEqual(self.scheduler.holds, 1)

    def test_each_repository_asks_its_own_client(self) -> None:
        alpha_spec, beta_spec = self.specs
        discovered = _artifacts.scan([
            _artifacts.candidate(beta_spec, _artifacts.BETA_ISSUE_NUMBER),
            _artifacts.candidate(alpha_spec, _artifacts.ALPHA_ISSUE_NUMBER),
        ])
        with (
            patch.object(
                discovery, _artifacts.CANDIDATES_ATTR, return_value=discovered,
            ) as scanned,
            patch.object(
                maintenance,
                _artifacts.MAINTAINED_ATTR,
                side_effect=self.recorded,
            ),
        ):
            artifacts.run_maintenance_pass(
                self.state(), self.clients, self.scheduler,
            )

            # One discovery over every configured spec at once, because
            # attribution is a question about all of them together; then each
            # repository's own candidates to the client built for it.
            scanned.assert_called_once_with([alpha_spec, beta_spec])
        self.assertEqual(self.recorded.asked, [
            (_support.ALPHA_REPO, (_artifacts.ALPHA_ISSUE_NUMBER,)),
            (_support.BETA_REPO, (_artifacts.BETA_ISSUE_NUMBER,)),
        ])
        self.assertEqual(
            {turn.claimed for turn in self.recorded.turns},
            {self.scheduler.is_active},
        )

    def test_a_stop_ends_the_pass(self) -> None:
        state = self.state()
        stopped = _artifacts.StoppingPass(state)
        with (
            patch.object(
                discovery,
                _artifacts.CANDIDATES_ATTR,
                return_value=_artifacts.scan([]),
            ),
            patch.object(
                maintenance, _artifacts.MAINTAINED_ATTR, side_effect=stopped,
            ),
        ):
            artifacts.run_maintenance_pass(state, self.clients, self.scheduler)

        # The repository whose turn came after the stop is skipped rather than
        # started, and what the pass had not reached stays where it was.
        self.assertEqual(
            [turn.github_client.slug for turn in stopped.turns],
            [_support.ALPHA_REPO],
        )

    def test_a_raising_pass_costs_the_loop_nothing(self) -> None:
        with (
            patch.object(
                discovery,
                _artifacts.CANDIDATES_ATTR,
                side_effect=RuntimeError(_DISCOVERY_FAILURE),
            ),
            self.assertLogs(
                _artifacts.LIFECYCLE_LOGGER, level=logging.ERROR,
            ) as logs,
        ):
            artifacts.run_maintenance_pass(
                self.state(), self.clients, self.scheduler,
            )

            self.assertTrue(any(
                _RAISED_LOG in message for message in logs.output
            ))

    def test_a_host_with_no_repository_takes_no_hold(self) -> None:
        artifacts.run_maintenance_pass(self.state(), [], self.scheduler)
        self.assertEqual(self.scheduler.holds, 0)


class ContinuationTest(_artifacts._MaintenanceTestCase):
    """The pass carries a stop reading of its own, not just the hold's grant.

    A hold is a snapshot: it was true when it was given, and a signal can land
    the line after. So what the pass is handed is a question rather than an
    answer -- asked again before every candidate -- and it says no on either of
    the two things that mean a stop has begun in this process.
    """

    def going_of(self, state: RuntimeState):
        """Run one pass, and hand back the continuation it passed down."""
        with (
            patch.object(
                discovery,
                _artifacts.CANDIDATES_ATTR,
                return_value=_artifacts.scan([]),
            ),
            patch.object(
                maintenance,
                _artifacts.MAINTAINED_ATTR,
                side_effect=self.recorded,
            ),
        ):
            artifacts.run_maintenance_pass(
                state, self.clients, self.scheduler,
            )

        handed = {turn.going for turn in self.recorded.turns}
        self.assertEqual(len(handed), 1)
        return self.recorded.turns[0].going

    def test_a_stopped_run_says_no(self) -> None:
        state = self.state()
        going = self.going_of(state)

        self.assertTrue(going())
        state.running = False
        self.assertFalse(going())

    def test_a_spent_hold_budget_says_no(self) -> None:
        # The third reading, and the one a process waiting for this host is
        # owed: a pass gives the host back at a candidate boundary rather than
        # holding it until it has worked through everything it found.
        going = self.going_of(self.state())

        self.assertTrue(going())
        with (
            patch.object(artifacts, _BUDGET_ATTR, _SPENT_BUDGET_SECONDS),
            self.assertLogs(
                _artifacts.LIFECYCLE_LOGGER, level=logging.INFO,
            ) as logs,
        ):
            self.assertFalse(going())
            self.assertTrue(any(
                _OVERRAN_LOG in message for message in logs.output
            ))

    def test_a_closed_scheduler_says_no(self) -> None:
        # The other half, and the one the grant itself rested on: a signal
        # closes the scheduler, and a hold nobody would be given now is not
        # one this pass may go on spending.
        state = self.state()
        going = self.going_of(state)

        self.assertTrue(going())
        self.scheduler.closed = True
        self.assertFalse(going())


class HandoverOrderTest(_handover._HandoverTestCase):
    """What was true of this process each time the host changed hands.

    Both edges are gaps a presence given up in the wrong order leaves open. At
    the moment it goes, this run must have nothing in flight and be admitting
    nothing: a presence says work may be running here, so dropping it while a
    worker is live hands the host to a process whose only evidence is its own
    empty scheduler. At the moment it comes back, admission must still be
    closed: reopening first would have this run submitting again while another
    process is still free to take the host.

    Which is why the barrier is outside the handover, and why this is the test
    that says so -- the scheduler and the lock are both real, and what is
    recorded is the pair of readings taken at the edges themselves.
    """

    def test_the_presence_goes_only_from_a_quiet_run(self) -> None:
        self.start_gated_worker()
        self.release_shortly()
        with (
            patch.object(
                artifacts, _BARRIER_ATTR, _handover.PATIENT_BARRIER_SECONDS,
            ),
            patch.object(
                discovery,
                _artifacts.CANDIDATES_ATTR,
                return_value=_artifacts.scan([]),
            ),
            exclusion.polling_presence() as presence,
        ):
            handover = _handover.WatchedHandover(presence, self.probe)
            artifacts.run_maintenance_pass(
                RuntimeState(host_claim=handover),
                self.clients,
                self.scheduler,
            )

            # The host changed hands twice, and at both edges this run had
            # drained and was admitting nothing.
            self.assertEqual(handover.edges, [(0, False), (0, False)])

    def test_a_contended_host_defers_the_pass(self) -> None:
        # A second poller's presence is what this run's own pass may not act
        # through: quiet or not, the host is not this process's alone, and the
        # handover is what makes that visible at all.
        with (
            exclusion.polling_presence(),
            patch.object(discovery, _artifacts.CANDIDATES_ATTR) as discovered,
            self.assertLogs(
                _artifacts.LIFECYCLE_LOGGER, level=logging.INFO,
            ) as logs,
            exclusion.polling_presence() as presence,
        ):
            artifacts.run_maintenance_pass(
                RuntimeState(host_claim=presence),
                self.clients,
                self.scheduler,
            )

            discovered.assert_not_called()
            self.assertTrue(any(
                _CONTENDED_LOG in message for message in logs.output
            ))

    def test_a_busy_run_hands_nothing_over(self) -> None:
        self.start_gated_worker()
        with (
            patch.object(
                artifacts, _BARRIER_ATTR, _handover.BRIEF_BARRIER_SECONDS,
            ),
            patch.object(discovery, _artifacts.CANDIDATES_ATTR) as discovered,
            exclusion.polling_presence() as presence,
        ):
            handover = _handover.WatchedHandover(presence, self.probe)
            artifacts.run_maintenance_pass(
                RuntimeState(host_claim=handover),
                self.clients,
                self.scheduler,
            )

            # Refused the quiet, the pass never reached the handover at all --
            # so nothing on this host could have taken the presence while that
            # worker ran, and nothing was read either.
            self.assertEqual(handover.edges, [])
            self.assertFalse(self.host_is_free())
            discovered.assert_not_called()


class LiveClaimTest(_artifacts._MaintenanceTestCase):
    """A candidate whose issue the scheduler still holds a claim on is kept.

    The guard the pass is handed is the live scheduler's own reading, and it is
    asked per candidate rather than once for the host: it is the check that
    survives a hold granted in error, and the one that keeps a live issue's
    artifacts even then. Nothing else about that candidate is read -- the
    client is asked nothing, so no ending is established and no teardown can
    follow from one.
    """

    def test_a_claimed_issue_is_retained_unasked(self) -> None:
        scheduler = self.live_scheduler()
        spec = self.specs[0]
        discovered = _artifacts.scan([
            _artifacts.candidate(spec, _artifacts.ALPHA_ISSUE_NUMBER),
        ])
        with (
            patch.object(
                discovery, _artifacts.CANDIDATES_ATTR, return_value=discovered,
            ),
            scheduler.track_active(
                spec.slug, _artifacts.ALPHA_ISSUE_NUMBER,
            ) as claimed,
        ):
            self.assertTrue(claimed)
            answers = artifacts._maintained(
                self.state(), self.clients, scheduler,
            )

            self.assertEqual(
                [(answer.outcome, answer.reason) for answer in answers],
                [(
                    MaintenanceOutcome.RETAINED,
                    MaintenanceReason.ACTIVE_CLAIM,
                )],
            )
            self.assertEqual(self.clients[0][1].mock_calls, [])


class DueMaintenanceTest(_artifacts._MaintenanceTestCase):
    """What the polling loop asks for between passes: a pass if one is owed."""

    def test_only_a_due_ask_reaches_the_hold(self) -> None:
        self.scheduler.quiet = False
        gate = artifacts.DueGate()
        for ask in range(3):
            with self.subTest(ask=ask):
                artifacts.run_maintenance_when_due(
                    self.state(), self.clients, self.scheduler, gate,
                )

        self.assertEqual(self.scheduler.holds, 1)

    def test_a_stopped_run_spends_no_turn(self) -> None:
        gate = artifacts.DueGate()
        artifacts.run_maintenance_when_due(
            self.state(running=False), self.clients, self.scheduler, gate,
        )

        # Neither attempted nor charged: the run that comes back is owed the
        # pass this one did not take.
        self.assertEqual(self.scheduler.holds, 0)
        self.assertTrue(gate.due())


if __name__ == "__main__":
    unittest.main()
