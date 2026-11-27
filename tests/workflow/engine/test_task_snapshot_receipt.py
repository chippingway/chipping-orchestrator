# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which returns a task snapshot is recorded from, read off the stream's own terminal evidence.

A run's stdout can hold a record the usage parser refuses -- an integer past
the conversion limit, which JSON will not decode -- so its usage parse fails.
The snapshot stands on no usage parse: the turn the stream closes on is read
off the records that decode at all, so a turn that completed past such a
record is recorded, the workflow reading its reply without the line, while a
Codex turn that failed past it, or a turn the provider refused, records
nothing and keeps no grounding. Nothing about the observation reaches the
reply's settlement either: readers that fail, and a logger that fails to warn
of them, still leave the workflow its reply with the line kept out.
"""
from __future__ import annotations

import json
import sys
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.agents.models import AgentInvocation, AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.analytics.observations import attachments as _attachments
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


def _received(stdout: str, refused=None) -> AgentResult:
    """A resumed conversation's clean return over `stdout`, received on an implementing resume's road.

    `refused` is the launching stage's reading of a CLI refusal, none by default.
    """
    returned = AgentResult(
        session_id=_SESSION, last_message=_REPLY, exit_code=0, timed_out=False, stdout=stdout, stderr="",
        invocation=AgentInvocation("owner/repo", _ISSUE, 1, 0, 1, "nonce"),
    )
    handoff = _completion_records.CompletionHandoff(_routes.CompletionRoute.RESUME, WorkflowLabel.IMPLEMENTING, "")
    conversation = _task_snapshots.Conversation(_REPO_ID, _ISSUE, _SESSION, None, "owner/repo")
    _task_snapshots.receive(handoff, returned, _STATE, conversation, refused=refused or _unrefused)
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

    def test_a_failing_warning_spares_the_reply(self) -> None:
        # The refusal reading and the attachment scan both failing, and the
        # warning of each failing too: the reply is left as the workflow reads
        # it all the same, and nothing is recorded.
        unwarned = patch.object(_task_snapshots.log, "warning", side_effect=OSError("log unavailable"))
        unscanned = patch.object(_attachments, "attachment_lines", side_effect=ValueError("scan unavailable"))
        with unwarned, unscanned:
            returned = _received(_COMPLETED, MagicMock(side_effect=ValueError("reading unavailable")))
        self.assertEqual((returned.last_message, self.observations()), (_QUESTION, []))


if __name__ == "__main__":
    unittest.main()
