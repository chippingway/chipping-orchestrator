# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The intervals a maintenance pass and a dependency poll are owed at."""

import unittest

from tests.config import config_reload_helpers as _reload, config_test_values as _config_cases


class ArtifactCleanupIntervalConfigTest(unittest.TestCase):
    """How long a finished issue's worktrees and branches are left alone.

    A day by default, because what a pass reclaims is disk rather than
    anything the workflow waits on. A positive integer validated at import
    like the parallelism caps: zero or a negative interval would put a
    host-wide teardown between every pair of polling passes, each one holding
    scheduler admission closed while it proved the host quiet.
    """

    def test_default_is_one_day(self) -> None:
        config = _reload.load_config()
        self.assertEqual(
            config.TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS,
            _config_cases._DEFAULT_CLEANUP_INTERVAL,
        )

    def test_env_override_wins(self) -> None:
        config = _reload.load_config(
            {
                _config_cases._CLEANUP_INTERVAL_ENV: str(
                    _config_cases._OVERRIDE_CLEANUP_INTERVAL,
                ),
            }
        )
        self.assertEqual(
            config.TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS,
            _config_cases._OVERRIDE_CLEANUP_INTERVAL,
        )

    def test_blank_value_keeps_the_default(self) -> None:
        # An operator who commented the value out but left the key behind gets
        # the shipped cadence rather than an abort.
        config = _reload.load_config(
            {_config_cases._CLEANUP_INTERVAL_ENV: "  "},
        )
        self.assertEqual(
            config.TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS,
            _config_cases._DEFAULT_CLEANUP_INTERVAL,
        )

    def test_an_invalid_interval_aborts_at_import(self) -> None:
        for spelling in ("nightly", _config_cases._DISABLED_ENV, "-1", "1.5"):
            with self.subTest(value=spelling):
                error_message = _reload.config_error_message(
                    {_config_cases._CLEANUP_INTERVAL_ENV: spelling},
                )
                self.assertIn(
                    _config_cases._CLEANUP_INTERVAL_ENV, error_message,
                )
                self.assertIn(spelling, error_message)


class DependencyPollCadenceConfigTest(unittest.TestCase):
    """How many polling ticks apart an open dependency walk is dispatched.

    Every fifth by default, because what a skipped tick defers is a walk that
    spawns nothing and costs a label read per child; `1` keeps the every-tick
    dispatch. A positive integer validated at import like the cleanup
    interval: zero or a negative names no tick the walk would ever be due on.
    """

    def test_unset_or_blank_is_every_fifth_tick(self) -> None:
        for environment in ({}, {_config_cases._DEPENDENCY_POLL_ENV: "  "}):
            with self.subTest(environment=environment):
                config = _reload.load_config(environment)
                self.assertEqual(
                    config.DEPENDENCY_POLL_EVERY_N_TICKS,
                    _config_cases._DEFAULT_DEPENDENCY_POLL_CADENCE,
                )

    def test_env_override_wins(self) -> None:
        for cadence in (
            _config_cases._EVERY_TICK_CADENCE,
            _config_cases._OVERRIDE_DEPENDENCY_POLL_CADENCE,
        ):
            with self.subTest(cadence=cadence):
                config = _reload.load_config(
                    {_config_cases._DEPENDENCY_POLL_ENV: str(cadence)},
                )
                self.assertEqual(config.DEPENDENCY_POLL_EVERY_N_TICKS, cadence)

    def test_an_invalid_cadence_aborts_at_import(self) -> None:
        for spelling in ("hourly", _config_cases._DISABLED_ENV, "-1", "1.5"):
            with self.subTest(value=spelling):
                error_message = _reload.config_error_message(
                    {_config_cases._DEPENDENCY_POLL_ENV: spelling},
                )
                self.assertIn(_config_cases._DEPENDENCY_POLL_ENV, error_message)
                self.assertIn(spelling, error_message)


if __name__ == "__main__":
    unittest.main()
