# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A recovery of a recorded late candidate is held to a captured report's source as well as to the record.

A guidance resume on a late measurement park reports over a commit of its own,
and that report is captured and handed off. Should the checkout be found on
the candidate the late record names instead, the gate parks it rather than
measure it -- and the bare `/orchestrator continue` that re-measures the
recorded pair is held the same way: the record names one commit and the owed
report another, no head is both, and publishing the recorded one would open a
pull request the report's binding then refuses.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from orchestrator.git.measurement.models import FrozenCommit
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _agent, _reported
from tests.workflow.stages.implementing import held_capture_test_support as _held
from tests.workflow.stages.implementing.late_gate_test_support import recorded_generation

# The candidate the late record names, which the checkout stands on.
_RECORDED = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
_SESSION = "dev-session"
_PARKED_AT = 900
_GUIDANCE_ID = 1100


def _reply(comment_id: int, body: str) -> FakeComment:
    """A trusted human's comment on the issue."""
    return FakeComment(id=comment_id, body=body, user=FakeUser("alice"))


def _after_everything(github, issue) -> int:
    """An id above every comment on the issue and the park's reply boundary."""
    boundary = github.pinned_data(_held.ISSUE)["last_action_comment_id"]
    return max(boundary, *(seen.id for seen in issue.comments)) + 1


class RecordedCandidateTest(unittest.TestCase, _held.HeldCaptureTicks):
    """Two commits named -- the record's and the captured report's -- and no head both: nothing is published."""

    def setUp(self) -> None:
        self._checkout = Path(self.enterContext(TemporaryDirectory())) / "checkout"
        self._checkout.mkdir()

    def test_a_measurement_retry_holds_the_source(self) -> None:
        github, issue = self.seeded(
            **recorded_generation(current_issue=_held.ISSUE, root_issue=_held.ISSUE, candidate_sha=_RECORDED),
            awaiting_human=True,
            park_reason="late_measurement_failed",
            last_action_comment_id=_PARKED_AT,
            dev_agent="claude",
            dev_session_id=_SESSION,
        )
        issue.comments.append(_reply(_GUIDANCE_ID, "Please fix the implementation"))
        resumed = self._dispatched(
            github, issue, _agent(session_id=_SESSION, last_message=_reported()), (_RECORDED, _held.SOURCE),
        )
        self.assert_held(github, resumed)
        issue.comments.append(_reply(_after_everything(github, issue), "/orchestrator continue"))
        retried = self._dispatched(github, issue, MagicMock(), (_RECORDED,))
        retried[_held.RUN_AGENT].assert_not_called()
        self.assert_held(github, retried)

    def assert_held(self, github, ran) -> None:
        """The developer ran once and the dispatch pushed and opened nothing; the report still about the source."""
        pinned = github.pinned_data(_held.ISSUE)
        handoff = pinned[_held.CAPTURED]
        pushed = ran["_push_branch"].call_count
        self.assertEqual((pinned["issue_agent_runs"], pushed), (1, 0))
        self.assertEqual(
            (github.opened_prs, pinned["awaiting_human"], handoff["stage"], handoff["source"]),
            ([], True, _held.HANDED_OFF, _held.SOURCE),
        )

    def _dispatched(self, github, issue, run_agent, head_shas: tuple):
        """One dispatch over the checkout here, its head proving to the recorded candidate."""
        return self.dispatch(
            github,
            issue,
            run_agent,
            head_shas=head_shas,
            has_new_commits=True,
            issue_checkout=self._checkout,
            issue_worktree=self._checkout,
            candidate_commit=FrozenCommit(sha=_RECORDED),
        )


if __name__ == "__main__":
    unittest.main()
