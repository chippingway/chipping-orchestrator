# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An Antigravity command recovery's task snapshot, grounded in the conversation it resumes.

A fresh retry beside a body edit grounds its replacement conversation on the
edit. A later retry resuming that conversation can leave a command running
and return under another conversation id, which the coordinator's command
recovery then resumes: the recovery's snapshot is bound to what that very
conversation was handed -- the edit, carried over to the id its attempt
returned -- never to the baseline the launch options' conversation would
fall back to.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents.models import ToolLifecycle
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

_EDIT = "Require the green variant."

_FRESH = "fresh-session"

_RECOVERED = "recovery-session"

# An Antigravity session failure an operator retries.
_SILENT = MappingProxyType({
    "awaiting_human": True, "park_reason": "agent_silent", "last_action_comment_id": 900, "dev_agent": "agy",
})

_UNFINISHED = (ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE"),)

# The two trusted retries, and the seams of a tick whose branch the run left where it was.
_RETRIES = tuple(
    FakeComment(id=comment_id, body="/orchestrator continue", user=FakeUser("alice")) for comment_id in (1100, 2000)
)
_UNMOVED = MappingProxyType({"has_new_commits": False, "head_shas": _held.UNMOVED})


def _runs() -> list:
    """The fresh retry's run; the next retry's, a command left running under another id; the recovery resuming that."""
    return [
        _agent(session_id=_FRESH, last_message=_support.SNAPSHOT),
        _agent(session_id=_RECOVERED, last_message="", exit_code=1, unfinished_steps=_UNFINISHED),
        _agent(session_id=_RECOVERED, last_message=_support.SNAPSHOT),
    ]


def _retried_twice(case: CommandRecoveryTest, github, issue) -> MagicMock:
    """Dispatch both retries over `issue`, the sink `case`'s; the runner they launched."""
    runner = MagicMock(side_effect=_runs())
    seams = {**case.sunk, **_UNMOVED}
    for retry in _RETRIES:
        issue.comments.append(retry)
        case.dispatch(github, issue, runner, **seams)
    return runner


def _resumed(runner: MagicMock) -> list:
    """The conversation each launch resumed, in order."""
    return [called.kwargs["options"].resume_session_id for called in runner.call_args_list]


def _revisions(case: CommandRecoveryTest) -> list:
    """The requirements revision of every snapshot on `case`'s sink, in order."""
    return [snapshot[_support.REVISION] for snapshot in case.events(_support.SNAPSHOT_EVENT)]


class CommandRecoveryTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """Two retries of a replacement conversation, the second recovered from a command left running."""

    def test_a_recovery_keeps_its_grounding(self) -> None:
        github, issue = self.seeded(**_SILENT)
        issue.body = f"{issue.body}\n{_EDIT}"
        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", ("alice",)):
            runner = _retried_twice(self, github, issue)
        self.assertEqual(_resumed(runner), [None, _FRESH, _RECOVERED])
        fresh, recovered = _revisions(self)
        self.assertNotEqual(fresh, github.pinned_data(_held.ISSUE)["user_content_hash"])
        self.assertEqual(recovered, fresh)


if __name__ == "__main__":
    unittest.main()
