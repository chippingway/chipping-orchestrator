# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A developer reply its CLI echoes onto stderr, or one opening on a provider's error line, as both readers read it.

An attachment line on stderr is the developer's own text, never the CLI's
evidence: a successful Claude return whose echoed description quotes a
Claude diagnostic is recorded, and its report published, as any other; so
is a Codex return whose reply opens on a provider's error line, since the
turn it closed on completed; and a resume that returns so is no poisoned
session -- nothing retries it, with the analytics sink on or off. And the warning a silent park logs shows its
stderr as the park comment quotes it, the line taken out, with the analytics
sink off as well as on.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.observability.analytics.observations import attachments as _attachments
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent
from tests.workflow.report_values import _FINISHED_REPORT
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

# A description quoting the diagnostic Claude overflows a resumed transcript with.
_QUOTING = "Handle the Claude diagnostic 'Prompt is too long' during a resume."
_QUOTED_SNAPSHOT = f"ANALYTICS: task-snapshot v1 {json.dumps({'description': _QUOTING})}"
_QUOTED_REPLY = f"{_QUOTED_SNAPSHOT}\n{_FINISHED_REPORT}"


def _succeeded(reply: str) -> str:
    """The stream a Claude turn that succeeded on `reply` closes on."""
    return json.dumps({"type": "result", "is_error": False, "result": reply})


# Codex's stream of a turn that completed, whatever its reply says.
_CODEX_COMPLETED = '{"type": "turn.started"}\n{"type": "turn.completed"}'

# A reply opening on the prefix Claude's CLI prints a provider's refusal under, above the snapshot and the report.
_OPENS_ON_AN_ERROR = f"API Error: 503 is the page this change documents.\n\n{_support.ATTACHED}"

# What the CLI writes before echoing a reply onto stderr.
_ECHO = "CLI echoed its reply:"

# The developer's question, its conversation left to resume, and a trusted human's answer.
_ASKED = MappingProxyType({
    "awaiting_human": True, "last_action_comment_id": 900, "dev_session_id": "asked-session", "dev_agent": "claude",
})
_REPLY = FakeComment(id=1000, body="Use the green variant.", user=FakeUser("alice"))

# The resumed conversation's next question, the quoting snapshot above it, its CLI echoing it.
_ASKS = "Which label?"
_QUESTION = f"{_QUOTED_SNAPSHOT}\n{_ASKS}"
_RESUMED = _agent(
    session_id="asked-session", last_message=_QUESTION, stderr=f"{_ECHO}\n{_QUOTED_SNAPSHOT}",
    stdout=_succeeded(_QUESTION),
)


class EchoedReplyTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """Implementing runs whose CLI echoes the developer's reply onto stderr."""

    def test_a_quoted_diagnostic_is_no_refusal(self) -> None:
        # Claude's own result says the turn succeeded.
        github, issue = self.seeded()
        stderr = f"{_ECHO}\n{_QUOTED_SNAPSHOT}"
        returned = _agent(last_message=_QUOTED_REPLY, stdout=_succeeded(_QUOTED_REPLY), stderr=stderr)
        with patch.object(config, "DEV_AGENT", "claude"):
            self.dispatch(github, issue, returned, **self.committing)
        self.published(github)
        self.assertEqual(self.only(_support.SNAPSHOT_EVENT)["description"]["text"], _QUOTING)

    def test_a_completed_codex_turn_is_the_agents(self) -> None:
        # Its reply opens on the prefix Claude's CLI prints a provider's
        # refusal under; Codex's own closing event says the turn completed.
        github, issue = self.seeded(dev_agent="codex")
        returned = _agent(last_message=_OPENS_ON_AN_ERROR, stdout=_CODEX_COMPLETED)
        self.dispatch(github, issue, returned, **self.committing)
        self.published(github)
        snapshot = self.only(_support.SNAPSHOT_EVENT)
        self.assertEqual(snapshot["description"]["text"], _support.DESCRIPTION)
        self.assertEqual(self.diagnosed(), [])

    def test_a_resume_is_not_retried(self) -> None:
        # One launch, resuming the conversation, and the question handed on;
        # its snapshot recorded only where the sink is on.
        for sink, recorded in ((self.sink, 1), (None, 0)):
            self.sink.unlink(missing_ok=True)
            github, issue = self.seeded(**_ASKED)
            issue.comments.append(_REPLY)
            runner = MagicMock(side_effect=[replace(_RESUMED), _agent(session_id="replacement-session")])
            self.dispatch(github, issue, runner, analytics_log_path=sink, has_new_commits=False)
            with self.subTest(sink=sink):
                self.assertEqual(runner.call_args.kwargs["options"].resume_session_id, "asked-session")
                runner.assert_called_once()
                self.assertIn(_ASKS, github.posted_comments[-1][1])
                self.assertEqual(len(self.events(_support.SNAPSHOT_EVENT)), recorded)

    def test_no_warning_carries_the_line(self) -> None:
        # The sink is off, so nothing is collected; the park's warning still
        # quotes the stderr, the echoed line taken out of it.
        github, issue = self.seeded()
        returned = _agent(last_message=_support.SNAPSHOT, stderr=f"{_ECHO}\n{_support.SNAPSHOT}")
        with self.assertLogs("orchestrator.workflow", level="WARNING") as logged:
            self.dispatch(github, issue, returned, analytics_log_path=None, has_new_commits=False)
            parked = [line for line in logged.output if _ECHO in line]
        self.assertEqual(github.pinned_data(_held.ISSUE)["park_reason"], "agent_silent")
        self.assertEqual(self.observations(), [])
        self.assertEqual(len(parked), 1, parked)
        self.assertNotIn(_support.DESCRIPTION, parked[0])
        self.assertIn(_attachments.TAKEN_OUT, parked[0])


if __name__ == "__main__":
    unittest.main()
