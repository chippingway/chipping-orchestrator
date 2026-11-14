# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A tracked Codex run hands what its launch looked like to the exit, so its native requests are placed by it."""
import functools
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.agents.models import AgentResult
from orchestrator.observability.analytics import settings as analytics_settings
from orchestrator.observability.analytics.trajectories import codex_launch, codex_sessions
from orchestrator.workflow.engine import usage as engine_usage
from tests.observability.usage import usage_codex_native_capture as capture
from tests.workflow.engine import usage_test_support as support

_ISSUE_NUMBER = 306
_CODEX_HOME = "CODEX_HOME"
_COVERAGE = "coverage"
_COMPLETE = "complete"
_WHOLE = "invocation"
# Every invocation of the captured session in turn: how its process exited, the log lines its exit reads as its own
# requests, how its collection ends, and how much of the invocation it covered -- a resume the provider failed
# settling none, and an interrupted one keeping the request it settled.
_SESSION = (
    (capture.FRESH, 0, ([13, 18, 22], _COMPLETE, _WHOLE)),
    (capture.RESUMED, 0, ([32], _COMPLETE, _WHOLE)),
    (capture.SWITCHED, 0, ([40, 52], _COMPLETE, _WHOLE)),
    (capture.FAILED, 1, ([], "complete-empty", _WHOLE)),
    (capture.INTERRUPTED, -15, ([69], "incomplete", _WHOLE)),
    (capture.LAST, 0, ([78], _COMPLETE, _WHOLE)),
)


def _collected(record: dict) -> tuple[list[int], str, str]:
    """The log lines a written record holds samples of, its collection's status, and the scope its scan covered."""
    request_usage = record["request_usage"]
    samples = request_usage.get("samples", ())
    summary = request_usage[_COVERAGE]
    return [sample["position"] for sample in samples], summary["status"], summary["scan_scope"]


class CodexLaunchHandoffTest(unittest.TestCase):
    """The launch is observed before the process starts, against its effective environment, only with the sink on."""

    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory()))
        environment = patch.dict(os.environ, {_CODEX_HOME: str(self.home)})
        self.enterContext(environment)

    def test_a_session_across_its_invocations(self) -> None:
        # The process's environment names the Codex home. Each launch counts the lines the session's log already holds
        # before its process appends its own past them, and hands that count and the launch moment to the exit, which
        # reads only that process's requests -- no earlier invocation's among them.
        records = self._session_records()
        for record, (invocation, _, expected) in zip(records, _SESSION, strict=True):
            with self.subTest(end=invocation.end):
                self.assertEqual(_collected(record), expected)

    def test_nothing_observed_or_read_with_sink_off(self) -> None:
        with (
            patch.object(analytics_settings, support._TRAJECTORY_PATH_ATTR, None),
            patch.object(codex_launch, "_observed") as observed,
            patch.object(codex_sessions, "discovered_log") as lookup,
        ):
            agent_result = self._run(capture.FRESH, 0)
            observed.assert_not_called()
            lookup.assert_not_called()
        self.assertEqual(agent_result.session_id, capture.SESSION_ID)

    def _session_records(self) -> list[dict]:
        """Run each invocation of the session in turn, each launched at its own moment; the records the exits wrote."""
        trajectory_path = support._analytics_path(self, "codex-session-", "trajectory.jsonl")
        with (
            patch.object(analytics_settings, support._TRAJECTORY_PATH_ATTR, trajectory_path),
            patch.object(codex_launch, "datetime") as clock,
        ):
            for invocation, exit_code, _ in _SESSION:
                clock.now.return_value = invocation.launched_at
                self._run(invocation, exit_code)
        return support._analytics_records(trajectory_path)

    def _run(self, invocation: capture.Invocation, exit_code: int) -> AgentResult:
        """Run `invocation` through the tracked spawn, its process appending its own lines to the session's log."""
        gh = support.FakeGitHubClient()
        returned = AgentResult(capture.SESSION_ID, "", exit_code, False, invocation.stdout, "")
        process = functools.partial(self._process, invocation, returned)
        with patch.object(support.agent_runner, support._RUN_AGENT_ATTR, side_effect=process):
            return engine_usage._run_agent_tracked(
                gh, support._tracked_budget(gh, _ISSUE_NUMBER),
                agent_role=support.ROLE_DEVELOPER,
                stage=support.STAGE_IMPLEMENTING,
                backend=support.BACKEND_CODEX,
                prompt="p",
                cwd=support._FAKE_WT,
                agent_spec=support.BACKEND_CODEX,
                resume_session_id=capture.SESSION_ID if invocation.resumed else None,
            )

    def _process(
        self,
        invocation: capture.Invocation,
        returned: AgentResult,
        *_: object,
        **_options: object,
    ) -> AgentResult:
        """The process: it appends its own lines to the session's log, then returns."""
        appended = capture.log_lines(invocation.end)[invocation.start:]
        day = Path(self.home, "sessions", *capture.DAY)
        day.mkdir(parents=True, exist_ok=True)
        with Path(day, capture.LOG_NAME).open("a", encoding="utf-8") as log:
            log.writelines(f"{line}\n" for line in appended)
        return returned


if __name__ == "__main__":
    unittest.main()
