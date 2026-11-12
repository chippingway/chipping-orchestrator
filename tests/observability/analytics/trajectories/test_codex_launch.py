# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the trajectory sink observes of a Codex launch: the home its effective environment names, and the moment."""

import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from orchestrator.agents import environment as agent_environment
from orchestrator.observability.analytics import settings as analytics_settings, sink as analytics_sink
from orchestrator.observability.analytics.trajectories import codex_launch

_TRAJECTORY_LOG_PATH = "TRAJECTORY_LOG_PATH"
_SINK_PATH = Path("/sink/trajectory.jsonl")
_CWD = Path("/worktrees/issue-1")
_CODEX = "codex"
_CODEX_HOME = "CODEX_HOME"
_PROCESS_HOME = "/state/process-codex"
_OVERRIDE_HOME = "/state/override-codex"
_MILLISECOND = timedelta(milliseconds=1)
# Each environment a launch is built from -- the run's override, the process's own, and neither -- and the home the
# CLI is pointed at by it.
_HOMES = (
    ("an override in the run's options", {_CODEX_HOME: _OVERRIDE_HOME}, {_CODEX_HOME: _PROCESS_HOME}, _OVERRIDE_HOME),
    ("the process's own", None, {_CODEX_HOME: _PROCESS_HOME}, _PROCESS_HOME),
    ("one relative to the checkout", {_CODEX_HOME: "state"}, {}, str(_CWD / "state")),
    ("Codex's own default", None, {"HOME": "/home/agent"}, "/home/agent/.codex"),
)


def _observed(
    backend: str = _CODEX,
    extra_env: dict[str, str] | None = None,
) -> codex_launch.LaunchObservation | None:
    with patch.object(analytics_settings, _TRAJECTORY_LOG_PATH, _SINK_PATH):
        return codex_launch.observed_launch(backend, _CWD, extra_env)


class LaunchObservationTest(unittest.TestCase):
    """A launch is observed only for Codex with the trajectory sink on, against the environment it is launched with."""

    def test_observed_only_where_collected(self) -> None:
        # With the sink off, or for another backend, nothing is observed and no environment is built.
        with patch.object(agent_environment, "agent_env") as agent_env:
            with patch.object(analytics_settings, _TRAJECTORY_LOG_PATH, None):
                self.assertIsNone(codex_launch.observed_launch(_CODEX, _CWD, None))
            self.assertIsNone(_observed("claude"))
            agent_env.assert_not_called()

    def test_the_home_the_launch_environment_names(self) -> None:
        for name, extra_env, environ, expected in _HOMES:
            with self.subTest(name), patch.dict(os.environ, environ):
                if _CODEX_HOME not in environ:
                    os.environ.pop(_CODEX_HOME, None)
                observation = _observed(extra_env=extra_env)
                self.assertEqual(observation.codex_home, Path(expected))

    def test_the_moment_is_utc_to_the_millisecond(self) -> None:
        before = datetime.now(UTC)
        observation = _observed()
        after = datetime.now(UTC)
        self.assertEqual(observation.launched_at.tzinfo, UTC)
        self.assertEqual(observation.launched_at.microsecond % 1000, 0)
        self.assertLessEqual(before - _MILLISECOND, observation.launched_at)
        self.assertLessEqual(observation.launched_at, after)

    def test_a_failing_observation_costs_nothing(self) -> None:
        with (
            patch.object(agent_environment, "agent_env", side_effect=RuntimeError("env boom")),
            self.assertLogs(analytics_sink.log, level="ERROR"),
        ):
            self.assertIsNone(_observed())


if __name__ == "__main__":
    unittest.main()
