# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The intervals and window a maintenance pass and a dependency poll are owed at."""

import datetime
import unittest

from tests.config import config_reload_helpers as _reload, config_test_values as _config_cases


def _clock(spelling: str) -> datetime.time:
    return datetime.time.fromisoformat(spelling)


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


class ArtifactCleanupWindowConfigTest(unittest.TestCase):
    """The local window a maintenance pass is scheduled in, and its timezone.

    Optional: unset or blank, the window is disabled and the timezone is not
    read, so the interval keeps its own default and validation. A set window
    is strict 24-hour `HH:MM-HH:MM`, may cross midnight, cannot start where it
    ends, and needs a timezone the host resolves; every refusal aborts at
    import with an error naming the setting it refuses.
    """

    def test_unset_or_blank_window_is_disabled(self) -> None:
        for environment in (
            {},
            {_config_cases._CLEANUP_WINDOW_ENV: _config_cases._BLANK_ENV},
            # A zone left beside a blanked window is not read, so even one the
            # host cannot resolve lets the start go on.
            {
                _config_cases._CLEANUP_WINDOW_ENV: "",
                _config_cases._CLEANUP_TIMEZONE_ENV: _config_cases._UNKNOWN_TIMEZONE,
            },
        ):
            with self.subTest(environment=environment):
                config = _reload.load_config(environment)
                self.assertIsNone(config.TERMINAL_ARTIFACT_CLEANUP_WINDOW)
                self.assertIsNone(config.TERMINAL_ARTIFACT_CLEANUP_TIMEZONE)

    def test_daytime_and_overnight_windows_normalize(self) -> None:
        for spelling, start, end in (
            ("09:30-17:45", "09:30", "17:45"),
            ("23:00-01:00", "23:00", "01:00"),
            (" 00:00-23:59 ", "00:00", "23:59"),
        ):
            with self.subTest(window=spelling):
                config = _reload.load_config(
                    {
                        _config_cases._CLEANUP_WINDOW_ENV: spelling,
                        _config_cases._CLEANUP_TIMEZONE_ENV: (
                            f" {_config_cases._CLEANUP_TIMEZONE} "
                        ),
                    }
                )
                self.assertEqual(
                    config.TERMINAL_ARTIFACT_CLEANUP_WINDOW,
                    (_clock(start), _clock(end)),
                )
                self.assertEqual(
                    config.TERMINAL_ARTIFACT_CLEANUP_TIMEZONE.key,
                    _config_cases._CLEANUP_TIMEZONE,
                )

    def test_window_coexists_with_the_interval(self) -> None:
        window_environment = {
            _config_cases._CLEANUP_WINDOW_ENV: _config_cases._NIGHTLY_WINDOW,
            _config_cases._CLEANUP_TIMEZONE_ENV: _config_cases._CLEANUP_TIMEZONE,
        }
        for interval, expected_interval in (
            ("", _config_cases._DEFAULT_CLEANUP_INTERVAL),
            (
                str(_config_cases._OVERRIDE_CLEANUP_INTERVAL),
                _config_cases._OVERRIDE_CLEANUP_INTERVAL,
            ),
        ):
            with self.subTest(interval=interval):
                config = _reload.load_config(
                    {**window_environment, _config_cases._CLEANUP_INTERVAL_ENV: interval},
                )
                self.assertEqual(
                    config.TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS,
                    expected_interval,
                )
                self.assertEqual(
                    config.TERMINAL_ARTIFACT_CLEANUP_WINDOW,
                    (_clock("03:00"), _clock("05:00")),
                )
        # A set window leaves the interval's own validation in force.
        error_message = _reload.config_error_message(
            {
                **window_environment,
                _config_cases._CLEANUP_INTERVAL_ENV: _config_cases._DISABLED_ENV,
            },
        )
        self.assertIn(_config_cases._CLEANUP_INTERVAL_ENV, error_message)

    def test_an_invalid_window_aborts_at_import(self) -> None:
        for spelling in (
            "nightly",
            "3:00-05:00",
            "03:00-5:00",
            "24:00-01:00",
            "03:60-05:00",
            "03:00",
            "03:00-05:00-07:00",
            "03:00 - 05:00",
            "0300-0500",
            "03:00\N{EN DASH}05:00",
            # `\d` would read this digit; the window's endpoints are ASCII.
            "0\N{ARABIC-INDIC DIGIT THREE}:00-05:00",
            "03:00-03:00",
            "00:00-00:00",
        ):
            with self.subTest(window=spelling):
                error_message = _reload.config_error_message(
                    {
                        _config_cases._CLEANUP_WINDOW_ENV: spelling,
                        _config_cases._CLEANUP_TIMEZONE_ENV: _config_cases._CLEANUP_TIMEZONE,
                    },
                )
                self.assertIn(_config_cases._CLEANUP_WINDOW_ENV, error_message)
                self.assertNotIn(_config_cases._CLEANUP_TIMEZONE_ENV, error_message)
                self.assertIn(spelling, error_message)

    def test_a_window_without_a_timezone_aborts(self) -> None:
        for timezone in (
            "",
            _config_cases._BLANK_ENV,
            _config_cases._UNKNOWN_TIMEZONE,
            "Asia/",
            "../etc/passwd",
        ):
            with self.subTest(timezone=timezone):
                error_message = _reload.config_error_message(
                    {
                        _config_cases._CLEANUP_WINDOW_ENV: _config_cases._NIGHTLY_WINDOW,
                        _config_cases._CLEANUP_TIMEZONE_ENV: timezone,
                    },
                )
                self.assertIn(_config_cases._CLEANUP_TIMEZONE_ENV, error_message)
                self.assertIn(repr(timezone), error_message)
        # Unset reads as blank rather than as some default zone.
        error_message = _reload.config_error_message(
            {_config_cases._CLEANUP_WINDOW_ENV: _config_cases._NIGHTLY_WINDOW},
        )
        self.assertIn(_config_cases._CLEANUP_TIMEZONE_ENV, error_message)


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
