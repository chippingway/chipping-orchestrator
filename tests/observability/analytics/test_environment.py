# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for what each analytics knob parses to out of the environment."""
from __future__ import annotations

import os
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from orchestrator import config as orchestrator_config
from orchestrator.observability.analytics import environment as analytics_environment

# The spellings that turn a knob off, in the casings and padding an operator
# writes them with. Shared by the three knobs that carry the vocabulary; an
# explicit empty assignment in .env is a documented disable alongside them.
_DISABLING = ("", "off", "OFF", " off ", "disabled", "none", "None")

_DEFAULT_RETENTION_DAYS = 90

_OVERRIDDEN_RETENTION_DAYS = 30

_OVERRIDDEN_RETENTION_SPELLING = "30"

# The retention spelling that keeps records indefinitely.
_KEEP_FOREVER = "0"

# One retention window per case: the spelling an operator writes and the
# window it parses to. Both knobs read the same pair of answers.
_RETENTION_CASES = (
    (_KEEP_FOREVER, 0),
    (_OVERRIDDEN_RETENTION_SPELLING, _OVERRIDDEN_RETENTION_DAYS),
)

_EXPLICIT_LOG_PATH = "/var/log/orch/a.jsonl"

_EXPLICIT_TRAJECTORY_PATH = "/var/log/orch/t.jsonl"

_DB_URL = "postgresql://u:p@db.example.com:5432/orchestrator_analytics"


@contextmanager
def _environment(**knobs: str) -> Iterator[None]:
    """Run the body against exactly the knobs it names.

    Cleared rather than layered: an operator who exported one of these before
    running the suite would otherwise decide what an unset case parses to.
    """
    with patch.dict(os.environ, knobs, clear=True):
        yield


class AnalyticsSinkKnobTest(unittest.TestCase):
    """`ANALYTICS_LOG_PATH` / `ANALYTICS_RETENTION_DAYS`: the sink is
    default-enabled under `config.LOG_DIR`, the disable sentinels turn it off,
    retention defaults to 90 days, and 0 keeps raw data indefinitely.
    """

    def test_default_path_under_log_dir(self) -> None:
        with _environment():
            self.assertEqual(
                analytics_environment.parse_log_path(),
                orchestrator_config.LOG_DIR / "analytics.jsonl",
            )

    def test_explicit_path_overrides_default(self) -> None:
        with _environment(ANALYTICS_LOG_PATH=_EXPLICIT_LOG_PATH):
            self.assertEqual(
                analytics_environment.parse_log_path(), Path(_EXPLICIT_LOG_PATH),
            )

    def test_disabling_values_turn_the_sink_off(self) -> None:
        for spelling in _DISABLING:
            with self.subTest(spelling=spelling), _environment(ANALYTICS_LOG_PATH=spelling):
                self.assertIsNone(analytics_environment.parse_log_path())

    def test_default_retention_is_ninety_days(self) -> None:
        with _environment():
            self.assertEqual(
                analytics_environment.parse_retention_days(),
                _DEFAULT_RETENTION_DAYS,
            )

    def test_retention_reads_the_environment(self) -> None:
        for raw, expected in _RETENTION_CASES:
            with self.subTest(raw=raw), _environment(ANALYTICS_RETENTION_DAYS=raw):
                self.assertEqual(
                    analytics_environment.parse_retention_days(), expected,
                )


class TrajectorySinkKnobTest(unittest.TestCase):
    """`TRAJECTORY_LOG_PATH` / `TRAJECTORY_RETENTION_DAYS`: unlike the
    analytics sink the trajectory one is opt-in, so an unset path disables it.
    Retention mirrors the analytics knob (default 90, non-positive keeps
    forever).
    """

    def test_unset_disables(self) -> None:
        with _environment():
            self.assertIsNone(analytics_environment.parse_trajectory_log_path())

    def test_disabling_values_turn_the_sink_off(self) -> None:
        for spelling in _DISABLING:
            with self.subTest(spelling=spelling), _environment(TRAJECTORY_LOG_PATH=spelling):
                self.assertIsNone(
                    analytics_environment.parse_trajectory_log_path(),
                )

    def test_explicit_path_enables(self) -> None:
        with _environment(TRAJECTORY_LOG_PATH=_EXPLICIT_TRAJECTORY_PATH):
            self.assertEqual(
                analytics_environment.parse_trajectory_log_path(),
                Path(_EXPLICIT_TRAJECTORY_PATH),
            )

    def test_retention_matches_the_analytics_default(self) -> None:
        with _environment():
            self.assertEqual(
                analytics_environment.parse_trajectory_retention_days(),
                _DEFAULT_RETENTION_DAYS,
            )

    def test_retention_reads_the_environment(self) -> None:
        for raw, expected in _RETENTION_CASES:
            with self.subTest(raw=raw), _environment(TRAJECTORY_RETENTION_DAYS=raw):
                self.assertEqual(
                    analytics_environment.parse_trajectory_retention_days(),
                    expected,
                )


class DatabaseUrlKnobTest(unittest.TestCase):
    """`ANALYTICS_DB_URL`: empty / sentinel disables the Postgres surfaces; a
    real URL passes through verbatim so a libpq URL is the single-knob
    endpoint contract.
    """

    def test_default_is_disabled(self) -> None:
        with _environment():
            self.assertIsNone(analytics_environment.parse_db_url())

    def test_disabling_values_turn_the_surfaces_off(self) -> None:
        for spelling in _DISABLING:
            with self.subTest(spelling=spelling), _environment(ANALYTICS_DB_URL=spelling):
                self.assertIsNone(analytics_environment.parse_db_url())

    def test_real_url_passes_through(self) -> None:
        with _environment(ANALYTICS_DB_URL=_DB_URL):
            self.assertEqual(analytics_environment.parse_db_url(), _DB_URL)

    def test_whitespace_is_stripped(self) -> None:
        with _environment(ANALYTICS_DB_URL=f"  {_DB_URL}  "):
            self.assertEqual(analytics_environment.parse_db_url(), _DB_URL)


class SkillTriggerKnobTest(unittest.TestCase):
    """`TRACK_SKILL_TRIGGERS` defaults off and honors the same truthy
    spellings as the other boolean knobs in `orchestrator.config`.
    """

    def test_defaults_off(self) -> None:
        # Default-off is a deliberate, revisited decision (#515): even after
        # codex skill-trigger coverage landed (#513), the file-open path's
        # production noise stays unmeasured, so the default holds off until it
        # proves low-noise live. Flipping this assertion is the flip.
        with _environment():
            self.assertFalse(analytics_environment.parse_track_skill_triggers())

    def test_truthy_spellings_enable(self) -> None:
        for spelling in ("1", "true", "on", "yes", "On", " YES "):
            with self.subTest(spelling=spelling), _environment(TRACK_SKILL_TRIGGERS=spelling):
                self.assertTrue(
                    analytics_environment.parse_track_skill_triggers(),
                )

    def test_falsey_and_unknown_values_stay_off(self) -> None:
        for spelling in ("0", "false", "off", "no", "", "maybe"):
            with self.subTest(spelling=spelling), _environment(TRACK_SKILL_TRIGGERS=spelling):
                self.assertFalse(
                    analytics_environment.parse_track_skill_triggers(),
                )


if __name__ == "__main__":
    unittest.main()
