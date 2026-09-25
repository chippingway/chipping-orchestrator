# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for bounded tracked AGY recovery during fixing resumes."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.agents import models as _agent_models
from orchestrator.agents.backends import agy as _agy
from orchestrator.workflow.engine import (
    guards as _guards,
    prompt_notes as _prompt_notes,
)
from tests.support import agy_stream as _agy_stream
from tests.workflow.fixtures import _reported
from tests.workflow.stages.fixing import fixing_test_support as support

IssueScenario = support.IssueScenario
FakeComment = support.FakeComment
FakeUser = support.FakeUser

_ALICE_USER = FakeUser(support.ALICE)
_DIRTY_FILE_NAME = "orchestrator/uncommitted_work.py"
_DIRTY_CONTENT = "# uncommitted fix from interrupted session\n"
_LABEL_VALIDATING = (support.ISSUE, support.VALIDATING)
_CLEANUP_QUESTION_WT = "_cleanup_question_worktree"
_CLEANUP_TERMINAL_BRANCH = "_cleanup_terminal_branch"
_STEP_ONE = _agent_models.ToolLifecycle(
    step_index=1, tool_name="run_command", state="ACTIVE",
)
_SIGTERM_EXIT = -15
_ONE_HOUR = support.timedelta(hours=1)
_REGRESSION_COMMENT = "please fix the regression"
_FIX_NEEDED = "fix needed"


def _make_dirty_worktree(case: unittest.TestCase, prefix: str) -> tuple[Path, Path]:
    wt_dir = tempfile.mkdtemp(prefix=prefix)
    case.addCleanup(shutil.rmtree, wt_dir, ignore_errors=True)
    wt_path = Path(wt_dir)
    dirty_file = wt_path / _DIRTY_FILE_NAME
    dirty_file.parent.mkdir(parents=True, exist_ok=True)
    dirty_file.write_text(_DIRTY_CONTENT)
    return wt_path, dirty_file


def _incomplete_agy_run(
    stdout: str | None = None, timed_out: bool = False,
) -> _agent_models.AgentResult:
    stream_stdout = (
        _agy_stream.ToolStream.active_with_checks() if stdout is None else stdout
    )
    return _agy.agy_result(
        _agent_models.AgentRunOptions(resume_session_id=_agy_stream.SESSION_ID),
        _agent_models.SubprocessResult(
            stream_stdout, "", 1, timed_out, False,
        ),
    )


class _RecoveryFixtureMixin(support._FixingFixtureMixin):
    def _seed_fixing_scenario(
        self,
        *,
        issue_comments=(),
        pr_comments=(),
        extra_state=None,
    ) -> tuple[IssueScenario, support.FakePR]:
        pr = self._open_pr(issue_comments=list(pr_comments))
        state: dict = {
            "dev_agent": _agy_stream.BACKEND,
            support.DEV_SESSION_ID: _agy_stream.SESSION_ID,
        }
        if extra_state:
            state.update(extra_state)
        gh, issue = self._seed(
            pr=pr,
            issue_comments=issue_comments,
            extra_state=state,
        )
        return IssueScenario(gh, issue), pr

    def _seed_regression_scenario(
        self,
    ) -> tuple[IssueScenario, support.FakePR]:
        comment = FakeComment(
            id=support.TRIGGER_ID,
            body=_REGRESSION_COMMENT,
            user=_ALICE_USER,
            created_at=support.now_utc() - _ONE_HOUR,
        )
        return self._seed_fixing_scenario(issue_comments=[comment])

    def _seed_fix_needed_scenario(self, **kwargs) -> IssueScenario:
        comment = FakeComment(
            id=support.TRIGGER_ID,
            body=_FIX_NEEDED,
            user=_ALICE_USER,
            created_at=support.now_utc() - _ONE_HOUR,
        )
        scenario, _ = self._seed_fixing_scenario(
            issue_comments=[comment], **kwargs,
        )
        return scenario

    def _run_fixing_in_wt(
        self, scenario: IssueScenario, wt_path: Path, **kwargs,
    ) -> dict:
        with (
            patch.object(support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS),
            patch.object(support.worktree_paths, support.WORKTREE_PATH, return_value=wt_path),
        ):
            return self._run_fixing(scenario.github, scenario.issue, **kwargs)

    def _assert_failure_pinned(
        self, scenario: IssueScenario, pr: support.FakePR,
    ) -> None:
        pinned = scenario.github.pinned_data(support.ISSUE)
        self.assertTrue(pinned.get(support.AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(support.PARK_REASON),
            support.PARK_AGENT_EXECUTION_FAILED,
        )
        self.assertEqual(pinned.get("pr_number"), pr.number)
        self.assertEqual(pinned.get(support.PENDING_FIX_AT), support.PENDING_FIX_AT_TS)
        self.assertEqual(pinned.get(support.PENDING_FIX_ISSUE_MAX_ID), support.TRIGGER_ID)
        self.assertEqual(pinned.get(support.REVIEW_ROUND), 1)


class _RecoveryAssertionsMixin:
    def _assert_spawn_count(self, mocks: dict, count: int) -> None:
        self.assertEqual(mocks[support.RUN_AGENT].call_count, count)

    def _assert_recovery_call(self, agent_call: unittest.mock._Call) -> None:
        self.assertEqual(
            agent_call.args[1],
            _prompt_notes._DEVELOPER_AGY_RECOVERY_PROMPT,
        )
        self.assertEqual(
            agent_call.kwargs.get(support.RESUME_SESSION_ID),
            _agy_stream.SESSION_ID,
        )

    def _assert_dirty_preserved(self, dirty_file: Path, mocks: dict) -> None:
        mocks[_CLEANUP_QUESTION_WT].assert_not_called()
        mocks[_CLEANUP_TERMINAL_BRANCH].assert_not_called()
        self.assertTrue(dirty_file.exists())
        self.assertEqual(dirty_file.read_text(), _DIRTY_CONTENT)

    def _assert_execution_failed_park(self, scenario: IssueScenario) -> None:
        pinned = scenario.github.pinned_data(support.ISSUE)
        self.assertTrue(pinned.get(support.AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(support.PARK_REASON),
            support.PARK_AGENT_EXECUTION_FAILED,
        )

    def _assert_successful_publish(
        self, scenario: IssueScenario, pr: support.FakePR, mocks: dict,
    ) -> None:
        self._assert_spawn_count(mocks, 2)
        self._assert_recovery_call(mocks[support.RUN_AGENT].call_args)
        mocks[support.PUSH_BRANCH].assert_called_once()
        self.assertIn(_LABEL_VALIDATING, scenario.github.label_history)
        self._assert_published_pinned(scenario, pr)

    def _assert_published_pinned(
        self, scenario: IssueScenario, pr: support.FakePR,
    ) -> None:
        pinned = scenario.github.pinned_data(support.ISSUE)
        self.assertFalse(pinned.get(support.AWAITING_HUMAN))
        self.assertIsNone(pinned.get(support.PARK_REASON))
        self.assertEqual(pinned.get("pr_number"), pr.number)
        self.assertIsNone(pinned.get(support.PENDING_FIX_AT))
        self.assertIsNone(pinned.get(support.PENDING_FIX_ISSUE_MAX_ID))
        self.assertIsNone(pinned.get(support.PENDING_FIX_REVIEWER_COMMENT_ID))
        self.assertEqual(pinned.get(support.REVIEW_ROUND), 0)

    def _assert_failure_park(
        self,
        scenario: IssueScenario,
        pr: support.FakePR,
        dirty_file: Path,
        mocks: dict,
    ) -> None:
        self._assert_spawn_count(mocks, 2)
        mocks[support.PUSH_BRANCH].assert_not_called()
        self.assertNotIn(_LABEL_VALIDATING, scenario.github.label_history)
        self._assert_failure_pinned(scenario, pr)
        self._assert_dirty_preserved(dirty_file, mocks)
        self._assert_failure_notice(scenario)


class FixingAGYRecoveryTest(
    unittest.TestCase, _RecoveryFixtureMixin, _RecoveryAssertionsMixin,
):
    """End-to-end reproduction and recovery of #1902 during fixing resumes."""

    def test_premature_exit_recovers_and_publishes(self) -> None:
        wt_path, _ = _make_dirty_worktree(self, "fixing-rec-wt-")
        scenario, pr = self._seed_regression_scenario()
        mocks = self._run_fixing_in_wt(
            scenario,
            wt_path,
            run_agent=[
                _incomplete_agy_run(),
                support._agent(
                    session_id=_agy_stream.SESSION_ID,
                    last_message=_reported("re-ran tests and fixed bug"),
                ),
            ],
            head_shas=(support.SHA_BEFORE, support.SHA_AFTER),
            push_branch=True,
        )
        self._assert_successful_publish(scenario, pr, mocks)

    def test_repeated_premature_exits_park_failure(self) -> None:
        wt_path, dirty_file = _make_dirty_worktree(self, "fixing-fail-wt-")
        scenario, pr = self._seed_regression_scenario()
        mocks = self._run_fixing_in_wt(
            scenario,
            wt_path,
            run_agent=[_incomplete_agy_run(), _incomplete_agy_run()],
            head_shas=(support.SHA_BEFORE, support.SHA_BEFORE),
            dirty_files=[_DIRTY_FILE_NAME],
        )
        self._assert_failure_park(scenario, pr, dirty_file, mocks)

    def test_unfinished_recovery_parks_failure(self) -> None:
        wt_path, _ = _make_dirty_worktree(self, "fixing-cmt-wt-")
        scenario, _ = self._seed_regression_scenario()
        mocks = self._run_fixing_in_wt(
            scenario,
            wt_path,
            run_agent=[_incomplete_agy_run(), _incomplete_agy_run()],
            head_shas=(support.SHA_BEFORE, support.SHA_AFTER),
            dirty_files=[_DIRTY_FILE_NAME],
        )

        self._assert_spawn_count(mocks, 2)
        mocks[support.PUSH_BRANCH].assert_not_called()
        self.assertNotIn(_LABEL_VALIDATING, scenario.github.label_history)
        self._assert_execution_failed_park(scenario)

    def test_genuine_question_parks_without_recovery(self) -> None:
        scenario, _ = self._seed_regression_scenario()
        question_result = support._agent(
            session_id=_agy_stream.SESSION_ID,
            last_message="Which behavior is preferred?",
            exit_code=0,
            unfinished_steps=(),
        )
        with patch.object(support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=question_result,
                head_shas=(support.SHA_BEFORE, support.SHA_BEFORE),
            )

        self._assert_spawn_count(mocks, 1)
        pinned = scenario.github.pinned_data(support.ISSUE)
        self.assertTrue(pinned.get(support.AWAITING_HUMAN))
        self.assertIsNone(pinned.get(support.PARK_REASON))

    def test_validating_anchor_preserved_on_failure(self) -> None:
        wt_path, _ = _make_dirty_worktree(self, "val-anc-wt-")
        scenario, _ = self._seed_fixing_scenario(
            pr_comments=[
                FakeComment(
                    id=support.REVIEWER_FEEDBACK_ID,
                    body=":eyes: reviewer feedback <!--orchestrator-comment-->",
                    user=FakeUser(support.ORCHESTRATOR),
                    created_at=support.now_utc() - support.timedelta(hours=2),
                ),
            ],
            issue_comments=[
                FakeComment(
                    id=support.COMMAND_COMMENT_ID,
                    body=support.CONTINUE_COMMAND,
                    user=_ALICE_USER,
                    created_at=support.now_utc() - support.timedelta(minutes=10),
                ),
            ],
            extra_state={
                support.PENDING_FIX_AT: None,
                support.PENDING_FIX_ISSUE_MAX_ID: None,
                support.PENDING_FIX_REVIEWER_COMMENT_ID: support.REVIEWER_FEEDBACK_ID,
                support.AWAITING_HUMAN: True,
                support.PARK_REASON: support.PARK_AGENT_SILENT,
                support.PR_LAST_COMMENT_ID: support.INITIAL_PR_COMMENT_WATERMARK,
            },
        )
        mocks = self._run_fixing_in_wt(
            scenario,
            wt_path,
            run_agent=[_incomplete_agy_run(), _incomplete_agy_run()],
            head_shas=(support.SHA_BEFORE, support.SHA_BEFORE),
            dirty_files=[_DIRTY_FILE_NAME],
        )

        self._assert_spawn_count(mocks, 2)
        pinned = scenario.github.pinned_data(support.ISSUE)
        self.assertTrue(pinned.get(support.AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(support.PARK_REASON),
            support.PARK_AGENT_EXECUTION_FAILED,
        )
        self.assertEqual(
            pinned.get(support.PENDING_FIX_REVIEWER_COMMENT_ID),
            support.REVIEWER_FEEDBACK_ID,
        )
        self.assertIsNone(pinned.get(support.PENDING_FIX_AT))


class FixingAGYRefusalTest(
    unittest.TestCase, _RecoveryFixtureMixin, _RecoveryAssertionsMixin,
):
    """Pause, timeout, shutdown, and session rotation refusals during fixing."""

    def test_initial_pause_stops_recovery(self) -> None:
        scenario = self._seed_fix_needed_scenario()
        recovered = support._agent(
            session_id=_agy_stream.SESSION_ID,
            last_message=_reported(),
        )
        with (
            patch.object(support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS),
            patch.object(_guards, "_paused_during_agent_run", return_value=True),
        ):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=[_incomplete_agy_run(), recovered],
                head_shas=(support.SHA_BEFORE, support.SHA_AFTER),
                push_branch=True,
            )

        self._assert_spawn_count(mocks, 1)
        self.assertEqual(scenario.github.label_history, [])

    def test_recovery_pause_stops_disposition(self) -> None:
        scenario = self._seed_fix_needed_scenario()
        recovered = support._agent(
            session_id=_agy_stream.SESSION_ID,
            last_message=_reported(),
        )
        with (
            patch.object(support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS),
            patch.object(
                _guards, "_paused_during_agent_run", side_effect=[False, True],
            ),
        ):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=[_incomplete_agy_run(), recovered],
                head_shas=(support.SHA_BEFORE, support.SHA_AFTER),
                push_branch=True,
            )

        self._assert_spawn_count(mocks, 2)
        self.assertEqual(scenario.github.label_history, [])

    def test_timeout_stops_recovery(self) -> None:
        scenario = self._seed_fix_needed_scenario()
        timed_out = _agy.agy_result(
            _agent_models.AgentRunOptions(),
            _agent_models.SubprocessResult(
                _agy_stream.ToolStream.canceled_active_command(),
                "",
                -1,
                True,
                False,
            ),
        )
        with patch.object(support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=[timed_out, _incomplete_agy_run()],
                head_shas=(support.SHA_BEFORE, support.SHA_BEFORE),
            )

        self._assert_spawn_count(mocks, 1)
        pinned = scenario.github.pinned_data(support.ISSUE)
        self.assertTrue(pinned.get(support.AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(support.PARK_REASON),
            support.PARK_AGENT_TIMEOUT,
        )

    def test_shutdown_sweep_stops_recovery(self) -> None:
        scenario = self._seed_fix_needed_scenario()
        interrupted = support._agent(
            session_id=_agy_stream.SESSION_ID,
            interrupted=True,
            exit_code=_SIGTERM_EXIT,
            unfinished_steps=(_STEP_ONE,),
        )
        with patch.object(support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=[interrupted, _incomplete_agy_run()],
                head_shas=(support.SHA_BEFORE, support.SHA_BEFORE),
            )

        self._assert_spawn_count(mocks, 1)
        self.assertEqual(scenario.github.label_history, [])

    def test_session_rotation_recovers_premature_exit(self) -> None:
        scenario = self._seed_fix_needed_scenario(
            extra_state={"dev_resume_count": 10},
        )
        recovered = support._agent(
            session_id="new-rotated-sess",
            last_message=_reported("addressed in rotated session"),
        )
        with (
            patch.object(support.config, "DEV_SESSION_MAX_RESUMES", 10),
            patch.object(support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS),
        ):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=[_incomplete_agy_run(), recovered],
                head_shas=(support.SHA_BEFORE, support.SHA_AFTER),
                push_branch=True,
            )

        self._assert_spawn_count(mocks, 2)
        mocks[support.PUSH_BRANCH].assert_called_once()
        self.assertIn(_LABEL_VALIDATING, scenario.github.label_history)
        pinned = scenario.github.pinned_data(support.ISSUE)
        self.assertEqual(pinned.get("dev_resume_count"), 0)
        self.assertEqual(pinned.get(support.DEV_SESSION_ID), "new-rotated-sess")


if __name__ == "__main__":
    unittest.main()
