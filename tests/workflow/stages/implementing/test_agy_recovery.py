# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Direct coordinator tests for bounded tracked AGY command recovery."""

from __future__ import annotations

import signal
from pathlib import Path
from unittest import TestCase, main, mock

from orchestrator.agents.models import AgentResult, ToolLifecycle
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage import protocol as _protocol
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    guards as _guards,
    prompt_notes as _prompt_notes,
    run_charge_state as _run_charge_state,
    run_circuit as _run_circuit,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import execution as _execution
from tests.support import fakes

_ISSUE_NUMBER = 42
_STAGE = "implementing"
_PROMPT = "Implement feature XYZ"
_AGENT_SPEC = "agy:gemini-3.8-flash"
_SESSION_ID = "agy-convo-42"
_CLAUDE_BACKEND = "claude"
_TIMEOUT = 1200
_EXTRA_ARGS = ("--wait",)
_STEP_ONE = 1
_STEP_TWO = 2
_INCOMPLETE_IN_TOKENS = 150
_INCOMPLETE_OUT_TOKENS = 75
_COMPLETED_IN_TOKENS = 200
_COMPLETED_OUT_TOKENS = 100
_CIRCUIT_IN_ONE = 100
_CIRCUIT_OUT_ONE = 50
_CIRCUIT_IN_TWO = 120
_CIRCUIT_OUT_TWO = 60
_EXPECTED_RUNS = 2
_EXPECTED_BUDGET_EVENTS = 4
_TOTAL_TOKENS = (
    _INCOMPLETE_IN_TOKENS + _INCOMPLETE_OUT_TOKENS
    + _COMPLETED_IN_TOKENS + _COMPLETED_OUT_TOKENS
)

_RUN_AGENT_TRACKED = "_run_agent_tracked"
_AGENT_SPAWN = "agent_spawn"
_AGENT_RUN_BUDGET = "agent_run_budget"
_STARTED_PHASE = "started"
_RUNS_USED = "agent_runs_used"
_BACKEND_KEY = "backend"
_PROMPT_KEY = "prompt"
_RESUME_SESSION_KEY = "resume_session_id"
_TIMEOUT_KEY = "timeout"
_EVENT_KEY = "event"
_PHASE_KEY = "phase"
_SESSION_ID_KEY = "session_id"
_CWD_KEY = "cwd"
_STAGE_KEY = "stage"
_AGENT_SPEC_KEY = "agent_spec"
_EXTRA_ARGS_KEY = "extra_args"

_UNFINISHED_STEP = ToolLifecycle(
    step_index=_STEP_ONE, tool_name="run_command", state="ACTIVE",
)
_SECOND_UNFINISHED_STEP = ToolLifecycle(
    step_index=_STEP_TWO, tool_name="run_command", state="ACTIVE",
)


def _incomplete_result(
    session_id: str | None = _SESSION_ID,
    unfinished_steps: tuple[ToolLifecycle, ...] = (_UNFINISHED_STEP,),
    **kwargs: object,
) -> AgentResult:
    defaults: dict[str, object] = {
        _SESSION_ID_KEY: session_id,
        "last_message": "",
        "exit_code": 1,
        "timed_out": False,
        "stdout": "active step",
        "stderr": "Antigravity ended with unfinished tool steps",
        "interrupted": False,
        "invoked": True,
        "unfinished_steps": unfinished_steps,
        "usage": UsageMetrics(
            backend=_protocol.AGY,
            input_tokens=_INCOMPLETE_IN_TOKENS,
            output_tokens=_INCOMPLETE_OUT_TOKENS,
        ),
    }
    defaults.update(kwargs)
    return AgentResult(**defaults)


def _completed_result(
    session_id: str | None = _SESSION_ID,
    **kwargs: object,
) -> AgentResult:
    defaults: dict[str, object] = {
        _SESSION_ID_KEY: session_id,
        "last_message": "All work committed.",
        "exit_code": 0,
        "timed_out": False,
        "stdout": "success",
        "stderr": "",
        "interrupted": False,
        "invoked": True,
        "unfinished_steps": (),
        "usage": UsageMetrics(
            backend=_protocol.AGY,
            input_tokens=_COMPLETED_IN_TOKENS,
            output_tokens=_COMPLETED_OUT_TOKENS,
        ),
    }
    defaults.update(kwargs)
    return AgentResult(**defaults)


class _AGYRecoveryBase(TestCase):
    def setUp(self) -> None:
        self.gh = fakes.FakeGitHubClient()
        self.issue = fakes.make_issue(_ISSUE_NUMBER, label=_STAGE)
        self.gh.add_issue(self.issue)
        self.state = PinnedState()
        self.worktree = Path("/fake/worktree")
        self.budget = _run_charge_state.AgentRunBudget(
            issue=self.issue, state=self.state,
        )

    def _assert_call_invariants(self, tracked_call: mock.MagicMock) -> None:
        self.assertEqual(tracked_call.args, (self.gh, self.budget))
        self.assertEqual(tracked_call.kwargs[_BACKEND_KEY], _protocol.AGY)
        self.assertEqual(tracked_call.kwargs[_CWD_KEY], self.worktree)
        self.assertEqual(tracked_call.kwargs[_STAGE_KEY], _STAGE)
        self.assertEqual(tracked_call.kwargs[_AGENT_SPEC_KEY], _AGENT_SPEC)
        self.assertEqual(tracked_call.kwargs[_EXTRA_ARGS_KEY], _EXTRA_ARGS)
        self.assertEqual(tracked_call.kwargs[_TIMEOUT_KEY], _TIMEOUT)

    def _assert_continuation_calls(
        self, tracked_mock: mock.MagicMock,
    ) -> None:
        first_call = tracked_mock.call_args_list[0]
        second_call = tracked_mock.call_args_list[1]
        self._assert_call_invariants(first_call)
        self._assert_call_invariants(second_call)
        self.assertEqual(first_call.kwargs[_PROMPT_KEY], _PROMPT)
        self.assertIsNone(first_call.kwargs[_RESUME_SESSION_KEY])
        self.assertEqual(
            second_call.kwargs[_PROMPT_KEY],
            _prompt_notes._DEVELOPER_AGY_RECOVERY_PROMPT,
        )
        self.assertEqual(second_call.kwargs[_RESUME_SESSION_KEY], _SESSION_ID)

    def _assert_circuit_and_events(self) -> None:
        spawn_events = [
            event for event in self.gh.recorded_events
            if event.get(_EVENT_KEY) == _AGENT_SPAWN
        ]
        self.assertEqual(len(spawn_events), _EXPECTED_RUNS)
        self.assertIsNone(spawn_events[0].get(_SESSION_ID_KEY))
        self.assertEqual(spawn_events[1].get(_SESSION_ID_KEY), _SESSION_ID)

        self.assertEqual(self.state.get(_RUNS_USED), _EXPECTED_RUNS)
        durable = self.gh.read_pinned_state(self.issue)
        self.assertEqual(durable.get(_RUNS_USED), _EXPECTED_RUNS)

        budget_events = [
            event for event in self.gh.recorded_events
            if event.get(_EVENT_KEY) == _AGENT_RUN_BUDGET
        ]
        self.assertEqual(len(budget_events), _EXPECTED_BUDGET_EVENTS)
        started_events = [
            event for event in budget_events
            if event.get(_PHASE_KEY) == _STARTED_PHASE
        ]
        self.assertEqual(len(started_events), _EXPECTED_RUNS)


class AGYRecoveryUntouchedTest(_AGYRecoveryBase):
    """Direct tests proving non-AGY and normally completed results are untouched."""

    def test_non_agy_result_is_untouched(self) -> None:
        claude_result = AgentResult(
            session_id="claude-sess-1",
            last_message="Implemented",
            exit_code=0,
            timed_out=False,
            stdout="done",
            stderr="",
            unfinished_steps=(_UNFINISHED_STEP,),
        )
        with mock.patch.object(_usage, _RUN_AGENT_TRACKED, return_value=claude_result) as tracked_mock:
            untouched, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_CLAUDE_BACKEND,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertIs(untouched, claude_result)
            self.assertFalse(paused)
            tracked_mock.assert_called_once()
            self.assertEqual(tracked_mock.call_args.kwargs[_BACKEND_KEY], _CLAUDE_BACKEND)

    def test_normally_completed_result_untouched(self) -> None:
        completed = _completed_result()
        with mock.patch.object(_usage, _RUN_AGENT_TRACKED, return_value=completed) as tracked_mock:
            untouched, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertIs(untouched, completed)
            self.assertFalse(paused)
            tracked_mock.assert_called_once()
            self.assertEqual(tracked_mock.call_args.kwargs[_BACKEND_KEY], _protocol.AGY)

    def test_missing_conversation_stops_recovery(self) -> None:
        incomplete = _incomplete_result(session_id=None)
        with mock.patch.object(_usage, _RUN_AGENT_TRACKED, return_value=incomplete) as tracked_mock:
            untouched, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertIs(untouched, incomplete)
            self.assertFalse(paused)
            tracked_mock.assert_called_once()

    def test_empty_conversation_id_stops_recovery(self) -> None:
        incomplete = _incomplete_result(session_id="")
        with mock.patch.object(_usage, _RUN_AGENT_TRACKED, return_value=incomplete) as tracked_mock:
            untouched, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertIs(untouched, incomplete)
            self.assertFalse(paused)
            tracked_mock.assert_called_once()


class AGYRecoveryContinuationTest(_AGYRecoveryBase):
    """Direct tests proving bounded single continuation and loop avoidance."""

    def test_incomplete_result_resumes_once(self) -> None:
        recovered = _completed_result(last_message="Recovered and finished")
        with mock.patch.object(
            _usage, _RUN_AGENT_TRACKED, side_effect=[_incomplete_result(), recovered],
        ) as tracked_mock:
            continued, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
                agent_spec=_AGENT_SPEC,
                timeout=_TIMEOUT,
                extra_args=_EXTRA_ARGS,
            )
            self.assertIs(continued, recovered)
            self.assertFalse(paused)
            self.assertEqual(tracked_mock.call_count, _EXPECTED_RUNS)
            self._assert_continuation_calls(tracked_mock)
            self.assertEqual(self.state.get("issue_agent_runs"), _EXPECTED_RUNS)
            self.assertEqual(self.state.get("issue_total_tokens"), _TOTAL_TOKENS)

    def test_second_premature_exit_returns_failure(self) -> None:
        second_exit = _incomplete_result(
            session_id=_SESSION_ID,
            unfinished_steps=(_SECOND_UNFINISHED_STEP,),
        )
        with mock.patch.object(
            _usage, _RUN_AGENT_TRACKED, side_effect=[_incomplete_result(), second_exit],
        ) as tracked_mock:
            continued, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertEqual(tracked_mock.call_count, _EXPECTED_RUNS)
            self.assertIs(continued, second_exit)
            self.assertFalse(paused)
            self.assertEqual(len(continued.unfinished_steps), 1)
            self.assertEqual(
                continued.unfinished_steps[0].step_index, _STEP_TWO,
            )

    def test_initial_result_can_be_provided_directly(self) -> None:
        recovered = _completed_result()
        with mock.patch.object(
            _usage, _RUN_AGENT_TRACKED, return_value=recovered,
        ) as tracked_mock:
            continued, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                initial_result=_incomplete_result(),
                initial_paused=False,
            )
            self.assertIs(continued, recovered)
            self.assertFalse(paused)
            tracked_mock.assert_called_once()
            self.assertEqual(
                tracked_mock.call_args.kwargs[_PROMPT_KEY],
                _prompt_notes._DEVELOPER_AGY_RECOVERY_PROMPT,
            )
            self.assertEqual(
                tracked_mock.call_args.kwargs[_RESUME_SESSION_KEY],
                _SESSION_ID,
            )

    def test_backend_cancellation_resumes(self) -> None:
        canceled = _incomplete_result(interrupted=True, exit_code=1)
        recovered = _completed_result()
        with mock.patch.object(
            _usage, _RUN_AGENT_TRACKED, side_effect=[canceled, recovered],
        ) as tracked_mock:
            continued, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
                agent_spec=_AGENT_SPEC,
                timeout=_TIMEOUT,
                extra_args=_EXTRA_ARGS,
            )
            self.assertIs(continued, recovered)
            self.assertFalse(paused)
            self.assertEqual(tracked_mock.call_count, _EXPECTED_RUNS)
            self._assert_continuation_calls(tracked_mock)


class AGYRecoveryGuardsAndCircuitTest(_AGYRecoveryBase):
    """Direct tests proving stop guards and circuit tracking during recovery."""

    def test_timeout_stops_recovery(self) -> None:
        timed_out = _incomplete_result(timed_out=True)
        with mock.patch.object(_usage, _RUN_AGENT_TRACKED, return_value=timed_out) as tracked_mock:
            guarded, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertIs(guarded, timed_out)
            self.assertFalse(paused)
            tracked_mock.assert_called_once()

    def test_shutdown_interruption_stops_recovery(self) -> None:
        interrupted = _incomplete_result(
            interrupted=True, exit_code=-signal.SIGTERM,
        )
        with mock.patch.object(_usage, _RUN_AGENT_TRACKED, return_value=interrupted) as tracked_mock:
            guarded, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertIs(guarded, interrupted)
            self.assertFalse(paused)
            tracked_mock.assert_called_once()

    def test_never_invoked_refusal_stops_recovery(self) -> None:
        refused = _run_circuit._refused_run()
        refused.unfinished_steps = (_UNFINISHED_STEP,)
        with mock.patch.object(_usage, _RUN_AGENT_TRACKED, return_value=refused) as tracked_mock:
            guarded, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertIs(guarded, refused)
            self.assertFalse(paused)
            tracked_mock.assert_called_once()

    def test_freshly_observed_pause_stops_recovery(self) -> None:
        incomplete = _incomplete_result()
        with mock.patch.object(
            _usage, _RUN_AGENT_TRACKED, return_value=incomplete,
        ) as tracked_mock, mock.patch.object(
            _guards, "_paused_during_agent_run", return_value=True,
        ):
            guarded, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
                pause_guard=True,
            )
            self.assertIs(guarded, incomplete)
            self.assertTrue(paused)
            tracked_mock.assert_called_once()

    def test_pause_during_recovery_run_returns_paused(self) -> None:
        recovered = _completed_result()
        with mock.patch.object(
            _usage, _RUN_AGENT_TRACKED, side_effect=[_incomplete_result(), recovered],
        ) as tracked_mock, mock.patch.object(
            _guards, "_paused_during_agent_run", side_effect=[False, True],
        ):
            guarded, paused = _execution._coordinate_developer_run(
                self.gh,
                self.budget,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
                pause_guard=True,
            )
            self.assertIs(guarded, recovered)
            self.assertTrue(paused)
            self.assertEqual(tracked_mock.call_count, _EXPECTED_RUNS)

    def test_coordinate_agy_recovery_alias(self) -> None:
        self.assertIs(
            _execution._coordinate_agy_recovery,
            _execution._coordinate_developer_run,
        )

    def test_recovery_visible_to_circuit_and_events(self) -> None:
        incomplete = AgentResult(
            session_id=_SESSION_ID,
            last_message="",
            exit_code=1,
            timed_out=False,
            stdout="step 1 active",
            stderr="unfinished tool steps",
            unfinished_steps=(_UNFINISHED_STEP,),
            usage=UsageMetrics(
                backend=_protocol.AGY,
                input_tokens=_CIRCUIT_IN_ONE,
                output_tokens=_CIRCUIT_OUT_ONE,
            ),
        )
        recovered = AgentResult(
            session_id=_SESSION_ID,
            last_message="Recovered successfully",
            exit_code=0,
            timed_out=False,
            stdout="step 1 completed",
            stderr="",
            unfinished_steps=(),
            usage=UsageMetrics(
                backend=_protocol.AGY,
                input_tokens=_CIRCUIT_IN_TWO,
                output_tokens=_CIRCUIT_OUT_TWO,
            ),
        )

        with mock.patch(
            "orchestrator.agents.runner.run_agent",
            side_effect=[incomplete, recovered],
        ):
            guarded, paused = _execution._coordinate_developer_run(
                self.gh,
                issue=self.issue,
                state=self.state,
                worktree=self.worktree,
                backend=_protocol.AGY,
                stage=_STAGE,
                prompt=_PROMPT,
            )
            self.assertIs(guarded, recovered)
            self.assertFalse(paused)
            self._assert_circuit_and_events()


if __name__ == "__main__":
    main()
