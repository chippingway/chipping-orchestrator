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
the edit still, and a reply whose launch the run budget refuses hands the
conversation nothing and leaves the grounding as it was. With the analytics
sink off, the fresh conversation's fingerprint is never taken and the host
keeps nothing; with it on and that fingerprint failing, the failure stays
inside the observation's boundary: the retry launches all the same, and
nothing is recorded or kept.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
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

# What fingerprints the requirements a retry's fresh conversation is re-grounded with.
_FINGERPRINT = "orchestrator.workflow.stages.implementing.completion_roads._requirements"

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


def _parked(case: ContinuationTest) -> None:
    """Park `case`'s issue on a session failure, its body edited for the fresh conversation a retry will open."""
    github, issue = case.seeded(**_SILENT)
    issue.body = f"{issue.body}\n{_EDIT}"
    case.github = github
    case.issue = issue


def _revisions(case: _support.SinkOfItsOwn) -> list[str]:
    """The requirements revision of every snapshot on `case`'s sink, in order."""
    return [snapshot[_support.REVISION] for snapshot in case.events(_support.SNAPSHOT_EVENT)]


class ContinuationTest(_support.SinkOfItsOwn, _held.HeldCaptureTicks):
    """A replacement conversation's continuations, dispatched as a poll does."""

    def setUp(self) -> None:
        super().setUp()
        _parked(self)

    def test_guidance_binds_its_own_revision(self) -> None:
        self._ticked(_replying(f"Which variant?\n{_support.SNAPSHOT}"), _said(_CONTINUE, _FIRST))
        self.issue.body = self.issue.body.removesuffix(f"\n{_EDIT}")
        ran = self._ticked(_replying(f"Which label?\n{_support.SNAPSHOT}"), _said(_GUIDANCE, _SECOND))
        self.assertEqual(_resumed(ran[_held.RUN_AGENT].call_args), _SESSION)
        self.assertIn(_GUIDANCE, _support.prompt_of(ran))
        retried, guided = _revisions(self)
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
        first, third = _revisions(self)
        self.assertEqual(third, first)
        self.assertTrue(self._kept().exists())
        self.assertNotIn("task_snapshot_grounding", self.github.pinned_data(_held.ISSUE))

    def test_a_refused_launch_keeps_it(self) -> None:
        # The reply that would hand the conversation new requirements is
        # never launched: the run budget refuses it, so nothing is recorded
        # and the grounding the retry kept stands.
        self._ticked(_replying(_support.SNAPSHOT), _said(_CONTINUE, _FIRST))
        kept = self._kept().read_text(encoding="utf-8")
        self.issue.body = self.issue.body.removesuffix(f"\n{_EDIT}")
        refused = MagicMock()
        with patch.object(config, "MAX_AGENT_RUNS_PER_ISSUE", 1):
            self._ticked(refused, _said(_GUIDANCE, _SECOND))
        refused.assert_not_called()
        self.assertEqual(self.github.pinned_data(_held.ISSUE)["park_reason"], "agent_run_limit")
        self.assertEqual(len(self.observations()), 1)
        self.assertEqual(self._kept().read_text(encoding="utf-8"), kept)

    def test_an_unobserved_retry_keeps_nothing(self) -> None:
        for sink in (None, self.sink):
            _parked(self)
            retried = _replying(_support.SNAPSHOT)
            with patch(_FINGERPRINT, side_effect=OSError("fingerprint unavailable")):
                ran = self._ticked(retried, _said(_CONTINUE, _FIRST), analytics_log_path=sink)
            with self.subTest(sink=sink):
                ran[_held.RUN_AGENT].assert_called_once()
                self.assertFalse(self._kept().exists())
        self.assertEqual(self.observations(), [])

    def _ticked(self, runner, said: FakeComment, **seams) -> dict:
        """One tick answering `said`, the branch unmoved and the sink this test's; its seams."""
        self.issue.comments.append(said)
        ticked = {**self.sunk, **_UNMOVED, **seams}
        return self.dispatch(self.github, self.issue, runner, **ticked)

    def _kept(self):
        """Where this host keeps the issue's grounding."""
        claim = writer_claims.claim_path(self.github.repo_id, _held.ISSUE)
        return claim.with_suffix(_grounding.GROUNDING_SUFFIX)


if __name__ == "__main__":
    unittest.main()
