# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The shared developer coordinator capturing each actual attempt on the road its caller froze.

Every attempt is accounted as it returns, and only one that finished on its
road's report is captured: an Antigravity exit with unfinished steps and a
poisoned conversation's failure earn their accounting alone, while the
continuation or the fresh retry behind them is captured on the same road,
with its own charge, the prompt it was handed, and the command that ran it.
A capture holds every later developer launch until something decides it,
and one sent and never confirmed holds the tick as a live pause does.
"""
from __future__ import annotations

import contextlib
import hashlib
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.agents.models import ToolLifecycle
from orchestrator.observability.usage import protocol as _protocol
from orchestrator.workflow.engine import completion_routes as _routes, guards as _guards, prompt_notes as _prompt_notes
from orchestrator.workflow.stages.implementing import (
    execution as _execution,
    resume as _resume,
    resume_request as _resume_request,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _FAKE_WT, _TEST_SPEC, _agent, _reported, accounted
from tests.workflow.stages.implementing import held_capture_test_support as _held

_ISSUE = 742
_PROMPT = "Implement the issue."
_SPEC = "claude --model claude-opus-5-5"
_AGY_SPEC = "agy:gemini-3.8-flash"
_POISONED = "poisoned-sess"
_FRESH = "fresh-sess"
_CONVERSATION = "agy-convo"
# The seams the runs here stand on, patched on their defining owners.
_RUNNER = "orchestrator.agents.runner.run_agent"
_HEAD = "orchestrator.git.verification.probes._head_sha"
_ENSURE_WORKTREE = "orchestrator.git.worktrees.creation._ensure_worktree"

# What a run that finished on its report, and an Antigravity exit that left
# a command running, come back as.
_FINISHED = _reported()
_UNFINISHED = (ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE"),)

# The digest of the prompt an Antigravity continuation is handed.
_RECOVERY_PROMPT = hashlib.sha256(_prompt_notes._DEVELOPER_AGY_RECOVERY_PROMPT.encode()).hexdigest()


class CapturedAttemptTest(unittest.TestCase):
    """One issue's coordinated developer runs, each attempt's capture read back off its pinned comment."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_ISSUE, label="workflow:implementing")
        self.github.add_issue(self.issue)
        self.github.seed_state(_ISSUE, dev_agent=_SPEC, dev_session_id=_POISONED)
        self.state = self.github.read_pinned_state(self.issue)

    def test_an_eligible_continuation_is_captured(self) -> None:
        # The first exit left a command running: accounted, never captured.
        # Its continuation finishes on the report, and is captured on the
        # first implementation's road under its own charge, with the recovery
        # prompt it was handed and the command that ran it -- a continuation
        # of the fresh conversation the spawn opened, resuming none before it.
        continued, paused = self._coordinated(
            [
                _agent(session_id=_CONVERSATION, last_message="", exit_code=1, unfinished_steps=_UNFINISHED),
                _agent(session_id=_CONVERSATION, last_message=_FINISHED),
            ],
            backend=_protocol.AGY,
            agent_spec=_AGY_SPEC,
            completion=_held.road(_ISSUE, _routes.CompletionRoute.IMPLEMENTATION),
        )
        captured = _held.capture_of(self.github.pinned_data(_ISSUE))
        self.assertEqual(
            (
                paused,
                captured.invocation,
                captured.run.command,
                captured.run.prompt_revision,
                captured.run.resumed,
            ),
            (False, continued.invocation, _AGY_SPEC, _RECOVERY_PROMPT, None),
        )
        self.assertEqual(accounted(self.github.pinned_data(_ISSUE)), (2, 2))

    def test_only_the_fresh_retry_is_captured(self) -> None:
        # Resuming the pinned conversation fails as one the backend lost:
        # accounted, never captured. The fresh retry it buys reports, and is
        # captured on the resume's road as the fresh conversation it opened.
        attempts = MagicMock(side_effect=[
            _agent(session_id="", last_message="", stderr=f"No conversation found with session ID: {_POISONED}"),
            _agent(session_id=_FRESH, last_message=_FINISHED),
        ])
        with self._seams(attempts), patch(_ENSURE_WORKTREE, return_value=_FAKE_WT):
            _resume._resume_dev_with_text(_resume_request._DevResumeRequest(
                self.github, _TEST_SPEC, self.issue, self.state, "go on", completion=_held.road(_ISSUE),
            ))
        captured = _held.capture_of(self.github.pinned_data(_ISSUE))
        self.assertEqual(
            (attempts.call_count, captured.invocation.ordinal, captured.session_id, captured.run.resumed),
            (2, 2, _FRESH, None),
        )
        self.assertEqual(accounted(self.github.pinned_data(_ISSUE)), (2, 2))

    def test_a_held_capture_holds_every_later_launch(self) -> None:
        # The report is captured though a live pause holds its return, and
        # the pause read as the run returned is the one answered. Nothing
        # decided that capture yet, so the next launch -- on any road -- is
        # refused uncharged rather than run beside it.
        with patch.object(_guards, "_paused_during_agent_run", return_value=True):
            _held_return, paused = self._coordinated(
                [_agent(session_id=_FRESH, last_message=_FINISHED)], pause_guard=True, completion=_held.road(_ISSUE),
            )
        refused, _refusal = self._coordinated([_agent(session_id=_FRESH, last_message=_FINISHED)])
        pinned = self.github.pinned_data(_ISSUE)
        self.assertEqual(
            (paused, pinned[_held.CAPTURED]["stage"], refused.invoked, accounted(pinned)),
            (True, _held.PENDING, False, (1, 1)),
        )

    def test_an_unconfirmed_capture_holds_the_tick(self) -> None:
        # The capture landed and its answer was lost: nothing can say it did
        # until a reading, so the attempt answers held and the caller's state
        # is withheld from every whole-state write, though nothing paused it.
        losing = patch.object(self.github, "edit_pinned_state", _LosesTheCapture(self.github))
        with losing:
            _finished, paused = self._coordinated(
                [_agent(session_id=_FRESH, last_message=_FINISHED)], completion=_held.road(_ISSUE),
            )
        self.github.pinned_failures.lost.discard(_ISSUE)
        captured = _held.capture_of(self.github.pinned_data(_ISSUE))
        held = (paused, self.state.withheld, captured.stage)
        self.assertEqual(held, (True, True, _held.PENDING))

    def _coordinated(self, attempts: list, **options):
        """Coordinate one developer run whose processes come back as `attempts`, the checkout on HEAD_AFTER_RUN."""
        launch = {
            "issue": self.issue, "state": self.state, "worktree": _FAKE_WT,
            "backend": "claude", "stage": "implementing", "prompt": _PROMPT, "agent_spec": _SPEC,
        }
        with self._seams(MagicMock(side_effect=attempts)):
            return _execution._coordinate_developer_run(self.github, **{**launch, **options})

    def _seams(self, attempts: MagicMock) -> contextlib.ExitStack:
        """The runner answering as `attempts`, and the checkout's head the commit the run left."""
        seams = contextlib.ExitStack()
        seams.enter_context(patch(_RUNNER, attempts))
        seams.enter_context(patch(_HEAD, return_value=_held.SOURCE))
        return seams


class _LosesTheCapture:
    """The strict edit, its answer lost for the one that lands the capture."""

    def __init__(self, github) -> None:
        self._github = github

    def __call__(self, issue, state, *, over: dict):
        """Send the edit, its answer lost where it is the capture's."""
        if state.get(_held.CAPTURED) != over.get(_held.CAPTURED):
            self._github.pinned_failures.lost.add(issue.number)
        return type(self._github).edit_pinned_state(self._github, issue, state, over=over)


if __name__ == "__main__":
    unittest.main()
