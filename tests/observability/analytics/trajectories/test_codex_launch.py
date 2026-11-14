# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the trajectory sink observes of a Codex launch: the home its environment names, a resumed log, the moment."""

import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from orchestrator.agents import environment as agent_environment
from orchestrator.observability.analytics import settings as analytics_settings, sink as analytics_sink
from orchestrator.observability.analytics.trajectories import codex_launch
from orchestrator.observability.usage import request_scan
from tests.observability.analytics.trajectories import codex_session_support as sessions
from tests.observability.usage import usage_codex_native_capture as capture

_TRAJECTORY_LOG_PATH = "TRAJECTORY_LOG_PATH"
_SINK_PATH = Path("/sink/trajectory.jsonl")
_CWD = Path("/worktrees/issue-1")
_CODEX = "codex"
_CODEX_HOME = "CODEX_HOME"
_PROCESS_HOME = "/state/process-codex"
_OVERRIDE_HOME = "/state/override-codex"
_NEWER_DAY = ("2026", "11", "13")
_UNFINISHED = '{"timestamp":"2026-11-12T13:55:10.309Z","type":"event_m'
# The bytes of the log's first five whole lines, a read bound reaching no further.
_FIVE = 5
_FIVE_LINES = len(capture.log_text(_FIVE).encode())
_DEFAULT_HOME = "/home/agent/.codex"
# Each environment a launch is built from -- the run's override, the process's own, an empty one, and neither -- and
# the home the CLI is pointed at by it.
_HOMES = (
    ("an override in the run's options", {_CODEX_HOME: _OVERRIDE_HOME}, {_CODEX_HOME: _PROCESS_HOME}, _OVERRIDE_HOME),
    ("the process's own", None, {_CODEX_HOME: _PROCESS_HOME}, _PROCESS_HOME),
    ("one relative to the checkout", {_CODEX_HOME: "state"}, {}, str(_CWD / "state")),
    ("an empty one", {_CODEX_HOME: ""}, {_CODEX_HOME: _PROCESS_HOME, "HOME": "/home/agent"}, _DEFAULT_HOME),
    ("Codex's own default", None, {"HOME": "/home/agent"}, _DEFAULT_HOME),
)


def _observed(
    backend: str = _CODEX,
    extra_env: dict[str, str] | None = None,
    resume_session_id: str | None = None,
) -> codex_launch.LaunchObservation | None:
    with patch.object(analytics_settings, _TRAJECTORY_LOG_PATH, _SINK_PATH):
        return codex_launch.observed_launch(backend, _CWD, extra_env, resume_session_id)


class LaunchObservationTest(unittest.TestCase):
    """A launch is observed only for Codex with the trajectory sink on, against the environment it is launched with."""

    def test_observed_only_where_collected(self) -> None:
        # With the sink off, or for another backend, nothing is observed and no environment is built.
        with patch.object(agent_environment, "agent_env") as agent_env:
            with patch.object(analytics_settings, _TRAJECTORY_LOG_PATH, None):
                self.assertIsNone(codex_launch.observed_launch(_CODEX, _CWD, None, capture.SESSION_ID))
            self.assertIsNone(_observed("claude"))
            agent_env.assert_not_called()

    def test_the_home_the_launch_environment_names(self) -> None:
        for name, extra_env, environ, expected in _HOMES:
            with self.subTest(name), patch.dict(os.environ, environ):
                if _CODEX_HOME not in environ:
                    os.environ.pop(_CODEX_HOME, None)
                observation = _observed(extra_env=extra_env)
                self.assertEqual(observation.codex_home, Path(expected))

    def test_the_moment_is_utc_and_uncut(self) -> None:
        # The moment is kept as precisely as the clock gives it, never cut down to an earlier millisecond.
        before = datetime.now(UTC)
        observation = _observed()
        after = datetime.now(UTC)
        self.assertEqual(observation.launched_at.tzinfo, UTC)
        self.assertLessEqual(before, observation.launched_at)
        self.assertLessEqual(observation.launched_at, after)

    def test_a_failing_observation_costs_nothing(self) -> None:
        with (
            patch.object(agent_environment, "agent_env", side_effect=RuntimeError("env boom")),
            self.assertLogs(analytics_sink.log, level="ERROR"),
        ):
            self.assertIsNone(_observed())


class ResumedLogCountTest(unittest.TestCase):
    """A resume's launch counts the whole lines its session's log already holds; all it appends lies past them."""

    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory()))
        environment = patch.dict(os.environ, {_CODEX_HOME: str(self.home)})
        self.enterContext(environment)

    def test_a_resume_counts_its_log(self) -> None:
        path = sessions.write_log(self.home, capture.log_text(capture.RESUMED.start))
        prior = _observed(resume_session_id=capture.SESSION_ID).prior
        current = path.stat()
        self.assertEqual((prior.device, prior.inode), (current.st_dev, current.st_ino))
        self.assertEqual(prior.size, current.st_size)
        self.assertEqual(prior.lines, capture.RESUMED.start)
        self.assertIsNone(_observed().prior)

    def test_logs_that_leave_no_count(self) -> None:
        # A log whose last line is unfinished counts nothing, and one the lookup finds nowhere, or under two dates, is
        # no log.
        sessions.write_log(self.home, capture.log_text(capture.RESUMED.start) + _UNFINISHED)
        self.assertIsNone(_observed(resume_session_id=capture.SESSION_ID).prior.lines)
        self.assertIsNone(_observed(resume_session_id=sessions.OTHER_SESSION).prior)
        sessions.write_log(self.home, capture.log_text(capture.RESUMED.start), day=_NEWER_DAY)
        self.assertIsNone(_observed(resume_session_id=capture.SESSION_ID).prior)

    def test_a_log_past_the_read_bound(self) -> None:
        # Past the bound, the count is one more than the lines within it, so no line the exit reads is the run's own.
        sessions.write_log(self.home, capture.log_text(capture.RESUMED.start))
        with patch.object(request_scan, "MAX_LOG_BYTES", _FIVE_LINES):
            prior = _observed(resume_session_id=capture.SESSION_ID).prior
        self.assertEqual(prior.lines, _FIVE + 1)


if __name__ == "__main__":
    unittest.main()
