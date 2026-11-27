# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Each attempt the shared developer coordinator makes, asked for a task snapshot and observed on its own.

A poisoned session's fresh retry and an Antigravity command recovery are
continuations of the request they retry, so each is asked as the attempt
before it was, and each genuine return is recorded under its own charge --
the stale conversation the retry replaces, which its CLI could not open,
under none. A run frozen on no road, or on a road other than the
implementing two, is neither asked nor observed, and an attempt that
returned no finished reply -- timed out, left a command running, or answered
on a clean exit by its provider's refusal or its CLI's own, an exhausted
quota, an overflowed transcript, or a Codex turn ending on `turn.failed`
whatever its code -- records nothing.
"""
from __future__ import annotations

import contextlib
import json
from unittest.mock import MagicMock, patch

from orchestrator.agents.models import ToolLifecycle
from orchestrator.observability.usage import protocol as _protocol
from orchestrator.workflow.engine import (
    completion_routes as _routes,
    prompt_notes as _notes,
    task_snapshot_grounding as _grounding,
)
from orchestrator.workflow.stages.implementing import (
    execution as _execution,
    resume as _resume,
    resume_request as _resume_request,
)
from tests.agents.codex_stream_cases import codex_jsonl, turn_failed, turn_started
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _FAKE_WT, _TEST_SPEC, _agent
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

_PROMPT = "Implement the issue."
_ASKED = f"{_PROMPT}\n\n{_notes._TASK_SNAPSHOT_NOTE}"
_RUNNER = "orchestrator.agents.runner.run_agent"
_HEAD = "orchestrator.git.verification.probes._head_sha"
_ENSURE_WORKTREE = "orchestrator.git.worktrees.creation._ensure_worktree"
_SPEC = "claude --model claude-opus-5-5"
_POISONED = "poisoned-sess"
_CONVERSATION = "agy-convo"
_UNFINISHED = (ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE"),)
_COMPLETION = "completion"

# Claude's own verdict on a turn its provider refused, beside a clean exit.
_REFUSED = json.dumps({"type": "result", "is_error": True, "result": "API Error: 529 Overloaded."})

# Codex turns ending on `turn.failed` beside a clean exit and no final message: the account's usage limit, and an
# overloaded server.
_CODEX_STOPPED = codex_jsonl(turn_started(), turn_failed("Quota exhausted.", codex_error_info="usage_limit_exceeded"))
_CODEX_FAILED = codex_jsonl(turn_started(), turn_failed("Server overloaded.", codex_error_info="server_overloaded"))

# What a poisoned resume and the fresh retry behind it record: nothing for the
# conversation the CLI could not open, the snapshot under the second charge.
_RETRIED = ((_support.SNAPSHOT_EVENT, (2, "resume")),)

# The result field a run's final message is returned in.
_SAID = "last_message"

_IMPLEMENTATION = _routes.CompletionRoute.IMPLEMENTATION
_RESUME = _routes.CompletionRoute.RESUME

# Runs nothing records: what each returned, the road it was frozen on, the
# prompt it was handed, and whether it reached the agent, so that the road's
# grounding of its conversation is kept -- none where the provider or the CLI
# refused the turn.
_UNRECORDED = (
    ("no road", {}, None, _PROMPT, False),
    ("a fix round", {}, _routes.CompletionRoute.REQUESTED_CHANGES, _PROMPT, False),
    ("a timed-out attempt", {"timed_out": True}, _IMPLEMENTATION, _ASKED, True),
    ("a refused turn", {"stdout": f"{_REFUSED}\n"}, _IMPLEMENTATION, _ASKED, False),
    ("an exhausted quota", {_SAID: "You've hit your 5-hour limit"}, _RESUME, _ASKED, False),
    ("an overflowed transcript", {_SAID: "Prompt is too long"}, _RESUME, _ASKED, False),
    ("a Codex usage limit", {_SAID: "", "stdout": _CODEX_STOPPED}, _RESUME, _ASKED, False),
    ("a failed Codex turn", {_SAID: "", "stdout": _CODEX_FAILED}, _IMPLEMENTATION, _ASKED, False),
)


def _grounding_of(case: CoordinatedAttemptTest):
    """Where this host keeps the grounding of `case`'s issue."""
    return _grounding.Grounding.of(case.github.repo_id, _held.ISSUE, case.state).path


def _recorded_as(record: dict) -> tuple:
    """What one observation is: its kind, and the charge and road it names."""
    return (record["event"], _support.charged(record))


class CoordinatedAttemptTest(_support.SinkOfItsOwn):
    """One issue's coordinated developer attempts, and the observations they leave."""

    def setUp(self) -> None:
        super().setUp()
        self.github = FakeGitHubClient()
        self.issue = make_issue(_held.ISSUE, label="workflow:implementing")
        self.github.add_issue(self.issue)
        self.github.seed_state(_held.ISSUE, dev_agent=_SPEC, dev_session_id=_POISONED)
        self.state = self.github.read_pinned_state(self.issue)

    def test_a_fresh_retry_is_asked_and_observed(self) -> None:
        # The poisoned attempt exited 0 on a conversation its CLI could not
        # open, so it reached no agent and is recorded nowhere; the fresh
        # retry it buys is asked again and recorded under the second charge.
        attempts = MagicMock(side_effect=[
            _agent(session_id="", last_message="", stderr=f"No conversation found with session ID: {_POISONED}"),
            _agent(session_id="fresh-sess", last_message=_support.ATTACHED),
        ])
        request = _resume_request._DevResumeRequest(
            self.github, _TEST_SPEC, self.issue, self.state, "go on", completion=_held.road(_held.ISSUE),
        )
        with self._seams(attempts), patch(_ENSURE_WORKTREE, return_value=_FAKE_WT):
            _resume._resume_dev_with_text(request)
        prompts = [attempt.args[1] for attempt in attempts.call_args_list]
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:
            self.assertTrue(prompt.endswith(_notes._TASK_SNAPSHOT_NOTE))
        self.assertEqual(tuple(map(_recorded_as, self.observations())), _RETRIED)

    def test_an_antigravity_recovery_is_observed(self) -> None:
        # The first exit left a command running and records nothing; the
        # recovery behind it is recorded under its own charge.
        self._coordinated(
            [
                _agent(session_id=_CONVERSATION, last_message="", exit_code=1, unfinished_steps=_UNFINISHED),
                _agent(session_id=_CONVERSATION, last_message=_support.ATTACHED),
            ],
            backend=_protocol.AGY,
            agent_spec="agy:gemini-3.8-flash",
            route=_routes.CompletionRoute.IMPLEMENTATION,
        )
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertEqual(_support.charged(snapshot), (2, "implementation"))

    def test_no_other_run_is_recorded(self) -> None:
        for name, failure, route, prompt, grounds in _UNRECORDED:
            with self.subTest(case=name):
                self._records_nothing(failure, route, prompt)
                self.assertEqual(_grounding_of(self).exists(), grounds)

    def _coordinated(self, attempts: list, route: _routes.CompletionRoute | None = None, **options) -> MagicMock:
        """Coordinate one developer run on `route`'s road, its processes coming back as `attempts`; the runner."""
        if route is not None:
            options[_COMPLETION] = _held.road(_held.ISSUE, route)
        launch = {
            "issue": self.issue, "state": self.state, "worktree": _FAKE_WT,
            "backend": "claude", "stage": "implementing", "prompt": _PROMPT, "agent_spec": _SPEC,
        }
        runner = MagicMock(side_effect=attempts)
        with self._seams(runner):
            _execution._coordinate_developer_run(self.github, **{**launch, **options})
        return runner

    def _records_nothing(self, failure: dict, route: _routes.CompletionRoute | None, prompt: str) -> None:
        """One run that returns `failure` on `route`'s road: handed `prompt`, and observed nowhere."""
        _grounding_of(self).unlink(missing_ok=True)
        self.state = self.github.read_pinned_state(self.issue)
        returned = _agent(**{_SAID: _support.ATTACHED, **failure})
        runner = self._coordinated([returned], route=route)
        self.assertEqual(runner.call_args.args[1], prompt)
        self.assertEqual(self.observations(), [])

    def _seams(self, runner: MagicMock) -> contextlib.ExitStack:
        """The runner answering as `runner`, and the checkout's head the commit a run left."""
        seams = contextlib.ExitStack()
        seams.enter_context(patch(_RUNNER, runner))
        seams.enter_context(patch(_HEAD, return_value=_held.SOURCE))
        return seams
