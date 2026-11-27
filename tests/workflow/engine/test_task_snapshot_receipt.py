# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which returns a task snapshot is recorded from, read off the stream's own terminal evidence.

A run's stdout can hold a record the usage parser refuses -- an integer past
the conversion limit, which JSON will not decode -- so its usage parse fails.
The snapshot stands on no usage parse: the turn the stream closes on is read
off the records that decode at all, so a turn that completed past such a
record is recorded, the workflow reading its reply without the line, while a
Codex turn that failed past it, or a turn the provider refused, records
nothing and keeps no grounding.
"""
from __future__ import annotations

import json
import sys
import unittest

from orchestrator.agents.models import AgentInvocation, AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage import metrics as _metrics
from orchestrator.workflow.engine import (
    completion_records as _completion_records,
    completion_routes as _routes,
    task_snapshot_grounding as _grounding,
    task_snapshots as _task_snapshots,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.implementing import task_snapshot_test_support as _support

_REPO_ID = 1
_ISSUE = 42
_SESSION = "resumed-session"
_QUESTION = "Which flag?"
_REPLY = f"{_support.SNAPSHOT}\n{_QUESTION}"

# A record JSON will not decode, and the turns a stream closes on past it.
_DIGITS = "1" * (sys.get_int_max_str_digits() + 1)
_UNDECODABLE = f'{{"unrelated": {_DIGITS}}}'
_STARTED = json.dumps({"type": "turn.started"})
_COMPLETED = f'{_STARTED}\n{_UNDECODABLE}\n{json.dumps({"type": "turn.completed"})}'
_OVERLOADED = json.dumps({"type": "turn.failed", "error": {"message": "Overloaded.", "codex_error_info": "overloaded"}})
_REFUSED = json.dumps({"type": "result", "is_error": True, "result": "API Error: 529 Overloaded."})
_UNREACHED = (
    ("a failed Codex turn", f"{_STARTED}\n{_UNDECODABLE}\n{_OVERLOADED}"),
    ("a refused turn", f"{_UNDECODABLE}\n{_REFUSED}"),
)

_STATE = PinnedState(comment_id=1, state_data={})


def _received(stdout: str) -> AgentResult:
    """A resumed conversation's clean return over `stdout`, received on an implementing resume's road."""
    returned = AgentResult(
        session_id=_SESSION, last_message=_REPLY, exit_code=0, timed_out=False, stdout=stdout, stderr="",
        invocation=AgentInvocation("owner/repo", _ISSUE, 1, 0, 1, "nonce"),
    )
    handoff = _completion_records.CompletionHandoff(_routes.CompletionRoute.RESUME, WorkflowLabel.IMPLEMENTING, "")
    conversation = _task_snapshots.Conversation(_REPO_ID, _ISSUE, _SESSION, None, "owner/repo")
    _task_snapshots.receive(handoff, returned, _STATE, conversation, refused=_unrefused)
    return returned


def _unrefused() -> bool:
    """The launching stage's reading that its CLI refused nothing."""
    return False


class UndecodableStreamTest(_support.SinkOfItsOwn):
    """A stream holding a record JSON will not decode, received with the analytics sink on."""

    def test_a_completed_turn_is_recorded(self) -> None:
        with self.assertRaises(ValueError):
            _metrics.parse_agent_usage("codex", _COMPLETED)
        returned = _received(_COMPLETED)
        self.assertEqual(returned.last_message, _QUESTION)
        self.assertEqual(len(self.events(_support.SNAPSHOT_EVENT)), 1)

    def test_an_unreached_turn_is_not(self) -> None:
        # Told apart and left unobserved, never lost to a stream it could not read.
        grounding = _grounding.Grounding.of(_REPO_ID, _ISSUE, _STATE).path
        for name, stdout in _UNREACHED:
            with self.assertNoLogs("orchestrator.workflow", level="WARNING"):
                returned = _received(stdout)
            with self.subTest(turn=name):
                self.assertEqual(returned.last_message, _QUESTION)
                self.assertEqual(self.observations(), [])
                self.assertFalse(grounding.exists())


if __name__ == "__main__":
    unittest.main()
