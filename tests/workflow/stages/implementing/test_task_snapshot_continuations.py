# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The continuations of a conversation a retry re-grounded, each bound to what it was handed.

A fresh retry beside a body edit grounds its replacement conversation on
that edit, and this host keeps the grounding beside the issue's writer claim
-- never on the pinned comment, so no settlement measures it. A human reply
resuming that conversation hands it the requirements its batch delivers,
which the reply settles as the issue's baseline, so its snapshot is bound to
those. A retry that times out without naming its conversation leaves the
grounding of the one still pinned, so the next retry resuming it is bound to
the edit still. With the analytics sink off, the host keeps nothing.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator.scheduler import writer_claims
from orchestrator.workflow.engine import task_snapshot_grounding as _grounding
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent
from tests.workflow.stages.implementing import (
    held_capture_test_support as _held,
    task_snapshot_test_support as _support,
)

_SESSION = "replacement-session"

_EDIT = "Revised requirement for a fresh conversation."

_GUIDANCE = "Use the green variant for this task."

_CONTINUE = "/orchestrator continue"

# A session failure an operator retries.
_SILENT = MappingProxyType({
    "awaiting_human": True, "park_reason": "agent_silent", "last_action_comment_id": 900, "dev_agent": "claude",
})

# The seams of a tick whose branch the run left where it was.
_UNMOVED = MappingProxyType({"has_new_commits": False, "head_shas": _held.UNMOVED})

# The ids of the comments each tick answers, in order.
_FIRST, _SECOND, _THIRD = 1100, 2000, 3000


def _replying(message: str, session: str | None = _SESSION, **failure):
    """The replacement conversation's run, finishing on `message` -- or failing as `failure` says."""
    return _agent(session_id=session, last_message=message, **failure)


def _said(body: str, comment_id: int) -> FakeComment:
    """The trusted human's comment `body`."""
    return FakeComment(id=comment_id, body=body, user=FakeUser("alice"))


def _resumed(called) -> str | None:
    """The conversation one run of the developer resumed."""
    return called.kwargs["options"].resume_session_id


class ContinuationTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """A replacement conversation's continuations, dispatched as a poll does."""

    def setUp(self) -> None:
        # The session failure parked, its body edited for the fresh
        # conversation a retry will open.
        super().setUp()
        github, issue = self.seeded(**_SILENT)
        issue.body = f"{issue.body}\n{_EDIT}"
        self.github = github
        self.issue = issue

    def test_guidance_binds_its_own_revision(self) -> None:
        self._ticked(_replying(f"Which variant?\n{_support.SNAPSHOT}"), _said(_CONTINUE, _FIRST))
        self.issue.body = self.issue.body.removesuffix(f"\n{_EDIT}")
        ran = self._ticked(_replying(f"Which label?\n{_support.SNAPSHOT}"), _said(_GUIDANCE, _SECOND))
        self.assertEqual(_resumed(ran[_held.RUN_AGENT].call_args), _SESSION)
        self.assertIn(_GUIDANCE, _support.prompt_of(ran))
        retried, guided = self._revisions()
        settled = self.github.pinned_data(_held.ISSUE)["user_content_hash"]
        self.assertEqual((retried == settled, guided), (False, settled))

    def test_a_nameless_timeout_keeps_it(self) -> None:
        # A retry that times out naming no conversation leaves the grounding
        # of the one still pinned. The record is the host's, beside the
        # claim; the pinned comment never carries it.
        runner = MagicMock(side_effect=[
            _replying(_support.SNAPSHOT),
            _replying("", None, timed_out=True),
            _replying(_support.SNAPSHOT),
        ])
        for comment_id in (_FIRST, _SECOND, _THIRD):
            self._ticked(runner, _said(_CONTINUE, comment_id))
        resumed = [_resumed(called) for called in runner.call_args_list]
        self.assertEqual(resumed, [None, _SESSION, _SESSION])
        first, third = self._revisions()
        self.assertEqual(third, first)
        self.assertTrue(self._kept().exists())
        self.assertNotIn("task_snapshot_grounding", self.github.pinned_data(_held.ISSUE))

    def test_a_sink_that_is_off_keeps_nothing(self) -> None:
        self._ticked(_replying(_support.SNAPSHOT), _said(_CONTINUE, _FIRST), analytics_log_path=None)
        self.assertFalse(self._kept().exists())

    def _ticked(self, runner, said: FakeComment, **seams) -> dict:
        """One tick answering `said`, the branch unmoved and the sink this test's; its seams."""
        self.issue.comments.append(said)
        ticked = {**self.sunk, **_UNMOVED, **seams}
        return self.dispatch(self.github, self.issue, runner, **ticked)

    def _revisions(self) -> list[str]:
        """The requirements revision of every snapshot on the sink, in order."""
        return [snapshot[_support.REVISION] for snapshot in self.events(_support.SNAPSHOT_EVENT)]

    def _kept(self):
        """Where this host keeps the issue's grounding."""
        claim = writer_claims.claim_path(self.github.repo_id, _held.ISSUE)
        return claim.with_suffix(_grounding.GROUNDING_SUFFIX)


if __name__ == "__main__":
    unittest.main()
