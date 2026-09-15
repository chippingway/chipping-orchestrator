# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When a polling run owes itself an artifact maintenance pass.

Two cadences and the precedence between them: the interval, on the clock that
cannot jump, and the local window that replaces it wherever one is set.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.runtime import artifact_schedule
from tests.runtime import artifact_schedule_test_support as _schedule

_INTERVAL_ATTR = "TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS"
_MONOTONIC_ATTR = "monotonic"
_SHORT_INTERVAL_SECONDS = 60
_NEW_YORK = "America/New_York"
_FALL_BACK_WINDOW = "01:00-02:00"
_NIGHT_UNDER_WAY = "2026-09-15T03:10:00"
_MIDDAY = "2026-09-15T12:00:00"


def _started(gate: artifact_schedule.DueGate) -> bool:
    """One attempt whose pass got past every hold, asked as the pass asks."""
    if not gate.due():
        return False
    started = gate.admitted()
    gate.settle()
    return started


class IntervalCadenceTest(unittest.TestCase):
    """With no window set, a pass is owed once an interval, on the clock that cannot jump.

    The first ask of a run is always owed one, which is what makes a restart
    cost at most one extra pass rather than a missed one. Every ask inside the
    interval after that is refused, so a poll every minute does not turn into a
    host-wide teardown every minute.
    """

    def setUp(self) -> None:
        self.enterContext(_schedule.windowed(None))

    def test_a_fresh_gate_is_owed_a_pass_at_once(self) -> None:
        # Nothing is persisted, so the first ask of a run is always owed one
        # and the run that comes back after a restart owes another: repeating
        # a pass costs one discovery and reports what is already gone as done.
        gate = artifact_schedule.DueGate()
        self.assertEqual([gate.due(), gate.due()], [True, False])
        self.assertTrue(artifact_schedule.DueGate().due())

    def test_asks_inside_the_interval_are_refused(self) -> None:
        gate = artifact_schedule.DueGate()
        # A day of polling at the default interval, spelled as the clock
        # readings the asks along the way would take.
        readings = (0, 60, 3600, _schedule.DAY_SECONDS - 1)
        with patch.object(time, _MONOTONIC_ATTR, side_effect=readings):
            self.assertEqual(
                [gate.due() for _ask in readings],
                [True, False, False, False],
            )

    def test_the_interval_elapsing_owes_another_pass(self) -> None:
        gate = artifact_schedule.DueGate()
        readings = (0, _schedule.DAY_SECONDS, 2 * _schedule.DAY_SECONDS)
        with patch.object(time, _MONOTONIC_ATTR, side_effect=readings):
            self.assertEqual(
                [gate.due() for _ask in readings],
                [True, True, True],
            )

    def test_the_configured_interval_is_read_per_ask(self) -> None:
        # Read at the ask rather than captured when the gate was created, so
        # what decides the cadence is the setting in force when the question
        # is put and nothing about when this run started.
        gate = artifact_schedule.DueGate()
        readings = (0, 2 * _SHORT_INTERVAL_SECONDS)
        with (
            patch.object(config, _INTERVAL_ATTR, _SHORT_INTERVAL_SECONDS),
            patch.object(time, _MONOTONIC_ATTR, side_effect=readings),
        ):
            self.assertEqual(
                [gate.due() for _ask in readings],
                [True, True],
            )


class WindowCadenceTest(unittest.TestCase):
    """A set window owes one pass a night, read off the wall clock in its zone.

    A night is named by the local date its window opened on, so neither
    midnight nor an hour a fall-back repeats makes it owe a second pass; and
    only a pass that started spends it, so a deferral is retried inside the
    window -- but spaced by elapsed time, which a wall clock stepped by NTP or
    a suspend cannot bring forward.
    """

    def test_the_start_is_inside_and_the_end_is_not(self) -> None:
        for window, reading, owed in (
            (_schedule.NIGHTLY_WINDOW, "2026-09-15T02:59:59", False),
            (_schedule.NIGHTLY_WINDOW, "2026-09-15T03:00:00", True),
            (_schedule.NIGHTLY_WINDOW, "2026-09-15T04:59:59", True),
            (_schedule.NIGHTLY_WINDOW, "2026-09-15T05:00:00", False),
            (_schedule.OVERNIGHT_WINDOW, "2026-09-15T22:59:59", False),
            (_schedule.OVERNIGHT_WINDOW, "2026-09-15T23:00:00", True),
            (_schedule.OVERNIGHT_WINDOW, "2026-09-16T00:59:59", True),
            (_schedule.OVERNIGHT_WINDOW, "2026-09-16T01:00:00", False),
        ):
            clocks = _schedule.Clocks(_schedule.local(reading))
            with (
                self.subTest(window=window, reading=reading),
                _schedule.windowed(window),
                clocks.installed(),
            ):
                self.assertIs(artifact_schedule.DueGate().due(), owed)

    def test_the_clock_is_read_in_the_window_zone(self) -> None:
        # One instant: 20:30 in UTC, and 03:30 in Novosibirsk, which is seven
        # hours ahead the year round. Inside the window read in one zone, and
        # outside it read in the other.
        clocks = _schedule.Clocks(
            _schedule.local("2026-09-14T20:30:00", _schedule.UTC_ZONE),
        )
        for zone, owed in ((_schedule.NOVOSIBIRSK, True), (_schedule.UTC_ZONE, False)):
            with (
                self.subTest(zone=zone),
                _schedule.windowed(_schedule.NIGHTLY_WINDOW, zone),
                clocks.installed(),
            ):
                self.assertIs(artifact_schedule.DueGate().due(), owed)

    def test_one_night_is_one_window_across_midnight(self) -> None:
        clocks = _schedule.Clocks(_schedule.local("2026-09-15T23:30:00"))
        gate = artifact_schedule.DueGate()
        with _schedule.windowed(_schedule.OVERNIGHT_WINDOW), clocks.installed():
            self.assertTrue(_started(gate))
            # Another calendar day, and still the window that opened the
            # evening before.
            clocks.reach(_schedule.local("2026-09-16T00:30:00"))
            self.assertFalse(gate.due())
            clocks.reach(_schedule.local("2026-09-16T23:30:00"))
            self.assertTrue(gate.due())

    def test_a_repeated_fall_back_hour_is_one_window(self) -> None:
        # New York leaves daylight time at 02:00 on 2026-11-01 and reads
        # 01:00-02:00 twice: 05:15 and 06:15 UTC are both 01:15 there.
        clocks = _schedule.Clocks(
            _schedule.local("2026-11-01T05:15:00", _schedule.UTC_ZONE),
        )
        spent = artifact_schedule.DueGate()
        with _schedule.windowed(_FALL_BACK_WINDOW, _NEW_YORK), clocks.installed():
            self.assertTrue(_started(spent))
            clocks.advance(_schedule.HOUR_SECONDS)
            # Inside the window by the wall clock, as a gate that spent
            # nothing still says; the gate that spent it is not owed the hour
            # again.
            self.assertTrue(artifact_schedule.DueGate().due())
            self.assertFalse(spent.due())

    def test_a_deferral_waits_fifteen_elapsed_minutes(self) -> None:
        clocks = _schedule.Clocks(_schedule.local("2026-09-15T03:00:00"))
        gate = artifact_schedule.DueGate()
        with _schedule.windowed(_schedule.NIGHTLY_WINDOW), clocks.installed():
            self.assertTrue(gate.due())
            # The barrier's wait comes before a deferral is known, and the
            # spacing is counted from the deferral rather than from the ask.
            clocks.advance(_schedule.MINUTE_SECONDS)
            gate.settle()
            # A wall clock stepped forward is not time elapsed.
            clocks.step_wall(_schedule.RETRY_SECONDS)
            self.assertFalse(gate.due())
            clocks.advance(_schedule.RETRY_SECONDS - 1)
            self.assertFalse(gate.due())
            clocks.advance(1)
            self.assertTrue(gate.due())

    def test_restarts_wait_outside_and_repeat_inside(self) -> None:
        clocks = _schedule.Clocks(_schedule.local(_NIGHT_UNDER_WAY))
        with _schedule.windowed(_schedule.NIGHTLY_WINDOW), clocks.installed():
            self.assertTrue(_started(artifact_schedule.DueGate()))
            # A process that comes back inside the window knows nothing of the
            # pass the one before it made, and may repeat it.
            self.assertTrue(artifact_schedule.DueGate().due())
            # One that comes back by day waits for the night.
            clocks.reach(_schedule.local(_MIDDAY))
            self.assertFalse(artifact_schedule.DueGate().due())

    def test_a_window_takes_precedence_over_interval(self) -> None:
        # Asked by day, an interval apart: the interval alone owes both asks,
        # and beside a window it owes neither, since no window is caught up
        # on by day.
        for window, owed in (
            (None, [True, True]),
            (_schedule.NIGHTLY_WINDOW, [False, False]),
        ):
            clocks = _schedule.Clocks(_schedule.local(_MIDDAY))
            gate = artifact_schedule.DueGate()
            with (
                self.subTest(window=window),
                _schedule.windowed(window),
                patch.object(config, _INTERVAL_ATTR, _SHORT_INTERVAL_SECONDS),
                clocks.installed(),
            ):
                asked = [gate.due()]
                clocks.advance(_SHORT_INTERVAL_SECONDS)
                asked.append(gate.due())
                self.assertEqual(asked, owed)


if __name__ == "__main__":
    unittest.main()
