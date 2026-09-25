# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for bounded tracked AGY recovery during fresh implementation."""

from __future__ import annotations

import signal
import unittest
from unittest.mock import patch

from orchestrator.agents import models as _agent_models
from orchestrator.agents.backends import agy as _agy
from orchestrator.workflow.engine import (
    guards as _guards,
    prompt_notes as _prompt_notes,
)
from tests.support import agy_stream as _agy_stream
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import (
    LABEL_IMPLEMENTING,
    LABEL_VALIDATING,
    _agent,
    _PatchedWorkflowMixin,
    _reported,
)
from tests.workflow.stages.implementing import fresh_test_support
from tests.workflow.stages.implementing_fixing_test_cases import IssueScenario

_AGY = "agy"
_RUN_COMMAND = "run_command"
_ACTIVE = "ACTIVE"
_RUN_AGENT = "run_agent"
_AWAITING_HUMAN = "awaiting_human"
_PARK_REASON = "park_reason"
_PARK_AGENT_TIMEOUT = "agent_timeout"
_EXECUTION_FAILED = "agent_execution_failed"
_AGENT_QUESTION = "agent_question"
_AGENT_RUNS_USED = "agent_runs_used"
_WORKFLOW_CHANNEL = "orchestrator.workflow"
_STEP_ONE = _agent_models.ToolLifecycle(step_index=1, tool_name=_RUN_COMMAND, state=_ACTIVE)


def _seed_fresh_issue(dev_agent: str = _AGY, **state: object) -> IssueScenario:
    gh = FakeGitHubClient()
    issue = make_issue(1, label=LABEL_IMPLEMENTING)
    gh.add_issue(issue)
    if dev_agent != "codex":
        state["dev_agent"] = dev_agent
    if state:
        gh.seed_state(1, **state)
    return IssueScenario(gh, issue)


def _incomplete_agy_run(
    cmd: str = "pytest", timed_out: bool = False,
) -> _agent_models.AgentResult:
    return _agy.agy_result(
        _agent_models.AgentRunOptions(),
        _agent_models.SubprocessResult(
            _agy_stream.ToolStream.canceled_active_command(cmd=cmd),
            "",
            1,
            timed_out,
            False,
        ),
    )


class _RecoveryBase(unittest.TestCase, _PatchedWorkflowMixin):
    def _assert_spawn_count(self, mocks: dict, count: int) -> None:
        self.assertEqual(mocks[_RUN_AGENT].call_count, count)

    def _assert_recovery_call(self, agent_call: unittest.mock._Call) -> None:
        self.assertEqual(
            agent_call.args[1],
            _prompt_notes._DEVELOPER_AGY_RECOVERY_PROMPT,
        )
        self.assertEqual(
            agent_call.kwargs.get("resume_session_id"),
            _agy_stream.SESSION_ID,
        )

    def _pinned_data(self, scenario: IssueScenario) -> dict[str, object]:
        return scenario.github.pinned_data(1)

    def _assert_failure_pinned(self, scenario: IssueScenario) -> None:
        pinned = self._pinned_data(scenario)
        self.assertTrue(pinned.get(_AWAITING_HUMAN))
        self.assertEqual(pinned.get(_PARK_REASON), _EXECUTION_FAILED)
        self.assertNotEqual(pinned.get(_PARK_REASON), _AGENT_QUESTION)
        self.assertEqual(pinned.get("retry_count"), 1)
        self.assertEqual(pinned.get(_AGENT_RUNS_USED), 2)

    def _assert_pr_state(self, scenario: IssueScenario) -> None:
        pinned = self._pinned_data(scenario)
        opened_pr = scenario.github.opened_prs[0]
        self.assertEqual(pinned["pr_number"], opened_pr.number)
        self.assertEqual(pinned["dev_agent"], _AGY)
        self.assertEqual(pinned["dev_session_id"], _agy_stream.SESSION_ID)
        self.assertEqual(pinned["review_round"], 0)
        self.assertEqual(pinned.get(_AGENT_RUNS_USED), 2)

    def _assert_committed_park(self, scenario: IssueScenario) -> None:
        pinned = self._pinned_data(scenario)
        self.assertTrue(pinned.get(_AWAITING_HUMAN))
        self.assertEqual(pinned.get(_PARK_REASON), _EXECUTION_FAILED)
        self.assertEqual(pinned.get("pre_implement_sha"), "sha-before")
        self.assertEqual(scenario.github.opened_prs, [])

    def _assert_published_continue(self, scenario: IssueScenario) -> None:
        self.assertEqual(len(scenario.github.opened_prs), 1)
        self.assertIn((1, LABEL_VALIDATING), scenario.github.label_history)
        pinned = self._pinned_data(scenario)
        self.assertIsNone(pinned.get("pre_implement_sha"))
        self.assertIsNone(pinned.get(_PARK_REASON))
        self.assertFalse(pinned.get(_AWAITING_HUMAN))


class HandleImplementingAGYRecoveryTest(_RecoveryBase):
    """Cover the #1912 shape: premature exit recovery and retry exhaustion."""

    def test_premature_exit_recovers_and_opens_pr(self) -> None:
        scenario = _seed_fresh_issue()
        recovered = _agent(
            session_id=_agy_stream.SESSION_ID,
            last_message=_reported(),
        )
        mocks = self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=[_incomplete_agy_run(), recovered],
            has_new_commits=[False, True],
            push_branch=True,
        )
        self._assert_spawn_count(mocks, 2)
        self._assert_recovery_call(mocks[_RUN_AGENT].call_args)
        fresh_test_support.assert_pr_routing(self, scenario)
        self._assert_pr_state(scenario)

    def test_repeated_premature_exits_park_failure(self) -> None:
        scenario = _seed_fresh_issue()
        with self.assertLogs(_WORKFLOW_CHANNEL, level="WARNING") as logs:
            mocks = self._run_implementing(
                scenario.github,
                scenario.issue,
                run_agent=[_incomplete_agy_run(), _incomplete_agy_run()],
                has_new_commits=False,
            )
            log_messages = [record.getMessage() for record in logs.records]

        self._assert_spawn_count(mocks, 2)
        self._assert_failure_pinned(scenario)
        fresh_test_support.assert_execution_failure_park(self, scenario, log_messages)

    def test_unfinished_recovery_with_commits_parks(self) -> None:
        scenario = _seed_fresh_issue()
        mocks = self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=[_incomplete_agy_run(), _incomplete_agy_run()],
            has_new_commits=[False, True],
        )
        self._assert_spawn_count(mocks, 2)
        self.assertEqual(scenario.github.opened_prs, [])
        self.assertEqual(scenario.github.label_history, [])
        self._assert_failure_pinned(scenario)

    def test_timed_out_recovery_with_commits_parks(self) -> None:
        scenario = _seed_fresh_issue()
        mocks = self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=[
                _incomplete_agy_run(),
                _incomplete_agy_run(timed_out=True),
            ],
            has_new_commits=[False, True],
        )
        self._assert_spawn_count(mocks, 2)
        self.assertEqual(scenario.github.opened_prs, [])
        self.assertEqual(scenario.github.label_history, [])
        pinned = self._pinned_data(scenario)
        self.assertTrue(pinned.get(_AWAITING_HUMAN))
        self.assertEqual(pinned.get(_PARK_REASON), _PARK_AGENT_TIMEOUT)

    def test_partial_output_never_counts_as_passing(self) -> None:
        scenario = _seed_fresh_issue()
        partial_passing = _agent(
            session_id=_agy_stream.SESSION_ID,
            last_message="pytest passed 5 tests",
            stdout="===== 5 passed in 0.10s =====",
            stderr="Antigravity ended with unfinished tool steps",
            exit_code=1,
            unfinished_steps=(_STEP_ONE,),
        )
        mocks = self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=[partial_passing, _incomplete_agy_run()],
            has_new_commits=False,
        )
        self._assert_spawn_count(mocks, 2)
        self.assertEqual(scenario.github.opened_prs, [])
        pinned = self._pinned_data(scenario)
        self.assertTrue(pinned.get(_AWAITING_HUMAN))
        self.assertEqual(pinned.get(_PARK_REASON), _EXECUTION_FAILED)

    def test_codex_claude_premature_exit_unchanged(self) -> None:
        for backend in ("codex", "claude"):
            with self.subTest(backend=backend):
                scenario = _seed_fresh_issue(dev_agent=backend)
                premature = _agent(
                    session_id="dev-sess",
                    last_message="partial output",
                    exit_code=1,
                    unfinished_steps=(_STEP_ONE,),
                )
                mocks = self._run_implementing(
                    scenario.github,
                    scenario.issue,
                    run_agent=premature,
                    has_new_commits=False,
                )
                self._assert_spawn_count(mocks, 1)
                self.assertEqual(
                    self._pinned_data(scenario).get(_PARK_REASON),
                    _EXECUTION_FAILED,
                )

    def test_premature_exit_published_on_continue(self) -> None:
        # End-to-end recovery sequence:
        # Tick 1: An implementing run commits work (sha-before -> sha-committed)
        # but exits prematurely with unfinished steps (parks agent_execution_failed).
        # Tick 2: Operator posts `/orchestrator continue`.
        # Retry returns REPORT: READY with no further HEAD movement (head == sha-committed).
        # Clean ahead-of-base commit attributable to failed run is published.
        scenario = _seed_fresh_issue()
        premature = _incomplete_agy_run()
        # Tick 1:
        self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=[premature, premature],
            head_shas=["sha-before", "sha-committed"],
            has_new_commits=[False, True],
        )
        self._assert_committed_park(scenario)

        # Human operator posts `/orchestrator continue`
        scenario.issue.comments.append(
            FakeComment(id=100, body="/orchestrator continue", user=FakeUser("dave")),
        )

        # Tick 2: continue retry runs, returns REPORT: READY at sha-committed (no head change)
        self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=_agent(session_id=_agy_stream.SESSION_ID, last_message=_reported("done")),
            head_shas=["sha-committed", "sha-committed"],
            has_new_commits=True,
            dirty_files=(),
            push_branch=True,
        )
        self._assert_published_continue(scenario)



class HandleImplementingAGYRefusalTest(_RecoveryBase):
    """Pause, timeout, shutdown, and run-limit refusals prevent extra recovery."""

    def test_initial_pause_stops_recovery(self) -> None:
        scenario = _seed_fresh_issue()
        recovered = _agent(session_id=_agy_stream.SESSION_ID, last_message=_reported())
        with patch.object(_guards, "_paused_during_agent_run", return_value=True):
            mocks = self._run_implementing(
                scenario.github,
                scenario.issue,
                run_agent=[_incomplete_agy_run(), recovered],
                has_new_commits=[False, True],
                push_branch=True,
            )
        self._assert_spawn_count(mocks, 1)
        self.assertEqual(scenario.github.opened_prs, [])
        self.assertEqual(scenario.github.label_history, [])

    def test_recovery_pause_stops_disposition(self) -> None:
        scenario = _seed_fresh_issue()
        recovered = _agent(session_id=_agy_stream.SESSION_ID, last_message=_reported())
        with patch.object(_guards, "_paused_during_agent_run", side_effect=[False, True]):
            mocks = self._run_implementing(
                scenario.github,
                scenario.issue,
                run_agent=[_incomplete_agy_run(), recovered],
                has_new_commits=[False, True],
                push_branch=True,
            )
        self._assert_spawn_count(mocks, 2)
        self.assertEqual(scenario.github.opened_prs, [])
        self.assertEqual(scenario.github.label_history, [])

    def test_timeout_stops_recovery(self) -> None:
        scenario = _seed_fresh_issue()
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
        mocks = self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=[timed_out, _incomplete_agy_run()],
            has_new_commits=False,
        )
        self._assert_spawn_count(mocks, 1)
        self.assertEqual(
            scenario.github.pinned_data(1).get(_PARK_REASON),
            "agent_timeout",
        )

    def test_shutdown_sweep_stops_recovery(self) -> None:
        scenario = _seed_fresh_issue()
        interrupted = _agent(
            session_id=_agy_stream.SESSION_ID,
            interrupted=True,
            exit_code=-signal.SIGTERM,
            unfinished_steps=(_STEP_ONE,),
        )
        mocks = self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=[interrupted, _incomplete_agy_run()],
            has_new_commits=False,
        )
        self._assert_spawn_count(mocks, 1)
        self.assertEqual(scenario.github.opened_prs, [])

    def test_run_limit_refusal_stops_recovery(self) -> None:
        scenario = _seed_fresh_issue(agent_run_allowance=1)
        mocks = self._run_implementing(
            scenario.github,
            scenario.issue,
            run_agent=_incomplete_agy_run(),
            has_new_commits=False,
        )
        self._assert_spawn_count(mocks, 1)
        self.assertEqual(scenario.github.opened_prs, [])
        self.assertEqual(scenario.github.label_history, [])
