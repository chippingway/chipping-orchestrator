# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A tracked Codex run hands what its launch looked like to the exit, so its native requests are placed by it."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.agents.models import AgentResult
from orchestrator.observability.analytics import settings as analytics_settings
from orchestrator.observability.analytics.trajectories import codex_launch, codex_sessions
from orchestrator.workflow.engine import usage as engine_usage
from tests.observability.analytics.trajectories import codex_session_support as sessions
from tests.observability.usage import usage_codex_native_capture as capture
from tests.workflow.engine import usage_test_support as support

_ISSUE_NUMBER = 306
_CODEX_HOME = "CODEX_HOME"
_REQUEST_USAGE = "request_usage"
_LOOKUP = "discovered_log"
_RESUMED_LINES = capture.log_lines(capture.RESUMED.end)[capture.RESUMED.start:]
_RESUMED_TEXT = "".join(f"{line}\n" for line in _RESUMED_LINES)
_RESUMED_RUN = AgentResult(capture.SESSION_ID, "", 0, False, capture.RESUMED.stdout, "")
_FRESH_RUN = AgentResult(
    session_id=capture.SESSION_ID,
    last_message="",
    exit_code=0,
    timed_out=False,
    stdout=capture.FRESH.stdout,
    stderr="",
)


class CodexLaunchHandoffTest(unittest.TestCase):
    """The launch is observed before the process starts, against its effective environment, only with the sink on."""

    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory()))
        sessions.write_log(self.home, capture.log_text(capture.FRESH.end))
        environment = patch.dict(os.environ, {_CODEX_HOME: str(self.home)})
        self.enterContext(environment)
        runner = patch.object(support.agent_runner, support._RUN_AGENT_ATTR, return_value=_FRESH_RUN)
        self.enterContext(runner)

    def test_the_launch_places_the_runs_requests(self) -> None:
        # The process's environment names the Codex home, and the launch moment -- the one the fresh log began after
        # -- reaches the exit, which reads the run's own requests out of the log there.
        trajectory_path = support._analytics_path(self, "codex-launch-", "trajectory.jsonl")
        with (
            patch.object(analytics_settings, support._TRAJECTORY_PATH_ATTR, trajectory_path),
            patch.object(codex_launch, "datetime") as clock,
        ):
            clock.now.return_value = capture.FRESH.launched_at
            self._run()
        request_usage = support._analytics_records(trajectory_path)[0][_REQUEST_USAGE]
        positions = [sample["position"] for sample in request_usage["samples"]]
        self.assertEqual(positions, [13, 18, 22])
        self.assertEqual(request_usage["coverage"]["status"], "complete")

    def test_a_resume_is_counted_at_launch(self) -> None:
        # The launch counts the lines the session's log already holds; the resumed process appends past them, and the
        # exit reads only those, the earlier invocation's requests never among them.
        trajectory_path = support._analytics_path(self, "codex-resume-", "trajectory.jsonl")
        with (
            patch.object(analytics_settings, support._TRAJECTORY_PATH_ATTR, trajectory_path),
            patch.object(codex_launch, "datetime") as clock,
            patch.object(support.agent_runner, support._RUN_AGENT_ATTR, side_effect=self._resumed),
        ):
            clock.now.return_value = capture.RESUMED.launched_at
            self._run(capture.SESSION_ID)
        request_usage = support._analytics_records(trajectory_path)[0][_REQUEST_USAGE]
        positions = [sample["position"] for sample in request_usage["samples"]]
        self.assertEqual(positions, [32])
        self.assertEqual(request_usage["coverage"]["status"], "complete")

    def test_nothing_observed_or_read_with_sink_off(self) -> None:
        with (
            patch.object(analytics_settings, support._TRAJECTORY_PATH_ATTR, None),
            patch.object(codex_launch, "_observed") as observed,
            patch.object(codex_sessions, _LOOKUP) as lookup,
        ):
            agent_result = self._run()
            observed.assert_not_called()
            lookup.assert_not_called()
        self.assertEqual(agent_result.session_id, capture.SESSION_ID)

    def _run(self, resume_session_id: str | None = None) -> AgentResult:
        gh = support.FakeGitHubClient()
        return engine_usage._run_agent_tracked(
            gh, support._tracked_budget(gh, _ISSUE_NUMBER),
            agent_role=support.ROLE_DEVELOPER,
            stage=support.STAGE_IMPLEMENTING,
            backend=support.BACKEND_CODEX,
            prompt="p",
            cwd=support._FAKE_WT,
            agent_spec=support.BACKEND_CODEX,
            resume_session_id=resume_session_id,
        )

    def _resumed(self, *_: object, **_options: object) -> AgentResult:
        """The resumed process: it appends its own lines to the session's log, then returns."""
        log = Path(self.home, sessions.SESSIONS, *capture.DAY, capture.LOG_NAME)
        with log.open("a", encoding="utf-8") as stream:
            stream.write(_RESUMED_TEXT)
        return _RESUMED_RUN


if __name__ == "__main__":
    unittest.main()
