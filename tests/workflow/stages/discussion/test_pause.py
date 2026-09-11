# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The rounds that finish and are then declined, and what the next tick makes
of what they left.

An operator who applies `paused` (or `backlog`) while the round is in flight,
and a shutdown sweep that kills it, reach the same requirement from different
directions: whatever the round produced must not be posted, parked, or written,
and the durable state has to stay exactly as the previous tick left it so the
next active tick opens the same first round again. Both are read after the
spawn returns -- the pause off a freshly fetched issue, since the handler's own
snapshot predates the label.

What a declined round does leave is the anchor its spawn wrote: the SHA the
checkout was on when it opened. That is not a disposition, it is the record
that makes one possible later -- without it the next tick would reuse the same
checkout and read a commit the declined round made as work the branch arrived
carrying.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.labels import BACKLOG_LABEL, PAUSED_LABEL
from tests.workflow.fixtures import (
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_PAUSED_ISSUE_NUMBER = 930
_BACKLOG_ISSUE_NUMBER = 931
_INTERRUPTED_ISSUE_NUMBER = 932
_PAUSED_COMMIT_ISSUE_NUMBER = 933
_PAUSED_CLEAN_ISSUE_NUMBER = 934
# The recovery tick reads the tip twice: once to see it has moved off the
# anchor, and once as the tip the publication check would publish.
_MOVED = (_support.HEAD_AFTER_COMMIT, _support.HEAD_AFTER_COMMIT)
_UNMOVED = (_support.HEAD_BEFORE_ROUND,)


class DiscussionLivePauseTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """A control label applied mid-round freezes the issue before publication."""

    def test_each_control_label_withholds_the_round(self) -> None:
        for issue_number, control_label in (
            (_PAUSED_ISSUE_NUMBER, PAUSED_LABEL),
            (_BACKLOG_ISSUE_NUMBER, BACKLOG_LABEL),
        ):
            with self.subTest(control_label=control_label):
                self._assert_round_withheld(issue_number, control_label)

    def test_a_paused_commit_is_recovered_next_tick(self) -> None:
        # The pause withholds every disposition, so the round that committed
        # says nothing this tick. The next one has to say it instead -- and it
        # can only tell that commit apart from work the branch arrived with by
        # the anchor the withheld round's spawn left behind.
        gh, issue = _support._seed_discussion(_PAUSED_COMMIT_ISSUE_NUMBER)

        with tempfile.TemporaryDirectory() as tree:
            self._run_paused_round(gh, issue, Path(tree), _UNMOVED)

            # Nothing published, and the anchor is the only thing left.
            self.assertEqual(gh.posted_comments, [])
            self.assertEqual(
                gh.pinned_data(issue.number)[_support.KEY_ROUND_SHA],
                _support.HEAD_BEFORE_ROUND,
            )
            self.assertNotIn(KEY_PARK_REASON, gh.pinned_data(issue.number))

            # Unpaused: HEAD has moved away from the anchor, so the commit is
            # named rather than adopted as the next round's baseline.
            recovery_mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message="a round that would adopt it"),
                head_shas=_MOVED,
            )

        recovery_mocks[_support.RUN_AGENT].assert_not_called()
        recovery_mocks[_support.ENSURE_WORKTREE].assert_not_called()
        self.assert_worktree_preserved(recovery_mocks)
        self._assert_commit_named(gh, issue.number)

    def test_a_paused_clean_round_replays(self) -> None:
        # The other half of the anchor's contract: a withheld round that left
        # nothing must not wedge the issue. HEAD still matches, so the next
        # active tick opens the same first round the pause promised.
        gh, issue = _support._seed_discussion(_PAUSED_CLEAN_ISSUE_NUMBER)

        with tempfile.TemporaryDirectory() as tree:
            self._run_paused_round(gh, issue, Path(tree), _UNMOVED)

            replay_mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
                # Read by the recovery probe, the replayed round's own
                # baseline, and its assessment.
                head_shas=(_support.HEAD_BEFORE_ROUND,) * 3,
            )

        replay_mocks[_support.RUN_AGENT].assert_called_once()
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[KEY_PARK_REASON], "discussion_response")
        # The replayed round finished without moving the branch, so its anchor
        # stands as the certificate a later relabel is judged against.
        self.assertEqual(pinned_data[_support.KEY_ROUND_SHA], _support.HEAD_BEFORE_ROUND)

    def _run_paused_round(self, gh, issue, tree: Path, head_shas: tuple):
        with patch.object(
            gh,
            "get_issue",
            return_value=_support._paused_view(issue.number, PAUSED_LABEL),
        ):
            return self._run_discussion_on_worktree(
                gh,
                issue,
                tree,
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
                head_shas=head_shas,
            )

    def _assert_commit_named(self, gh, issue_number: int) -> None:
        pinned_data = gh.pinned_data(issue_number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_INVALID,
        )
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])
        # The anchor outlives the park that reported the commit: it is the
        # only recorded point separating what the agent wrote from what the
        # branch already carried, so it is both the reset target the park
        # quotes and what the relabel guard measures against afterwards.
        self.assertEqual(pinned_data[_support.KEY_ROUND_SHA], _support.HEAD_BEFORE_ROUND)
        self.assertEqual(len(gh.posted_comments), 1)
        _, body = gh.posted_comments[0]
        self.assertIn(config.HITL_MENTIONS, body)
        self.assertIn(_support.HEAD_BEFORE_ROUND, body)
        self.assertNotIn(_support.DISCUSSION_RESPONSE, body)

    def _assert_round_withheld(
        self, issue_number: int, control_label: str,
    ) -> None:
        gh, issue = _support._seed_discussion(issue_number)

        with patch.object(
            gh,
            "get_issue",
            return_value=_support._paused_view(issue_number, control_label),
        ):
            mocks = self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
            )

        mocks[_support.RUN_AGENT].assert_called_once()
        # No disposition: no comment, no park, and no session pointer to a
        # conversation the humans never saw. Only the pre-spawn record stands.
        self.assertEqual(gh.posted_comments, [])
        pinned_data = gh.pinned_data(issue_number)
        self.assertNotIn(KEY_PARK_REASON, pinned_data)
        self.assertNotIn(_support.KEY_DISCUSSION_SESSION_ID, pinned_data)
        self.assertFalse(pinned_data.get(KEY_AWAITING_HUMAN))
        self.assertEqual(
            pinned_data[_support.KEY_DISCUSSION_AGENT], config.DECOMPOSE_AGENT_SPEC,
        )
        self.assertEqual(pinned_data[_support.KEY_ROUND_SHA], _support.HEAD_BEFORE_ROUND)
        self.assert_worktree_preserved(mocks)


class DiscussionInterruptedRoundTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """A shutdown-killed round on a clean tree leaves no trace to reply to."""

    def test_interrupted_round_publishes_nothing(self) -> None:
        gh, issue = _support._seed_discussion(_INTERRUPTED_ISSUE_NUMBER)

        self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message="",
                exit_code=1,
                interrupted=True,
            ),
        )

        # An interrupted run is not a silent one: it must not park, comment,
        # or persist the session it opened.
        self.assertEqual(gh.posted_comments, [])
        pinned_data = gh.pinned_data(issue.number)
        self.assertNotIn(_support.KEY_DISCUSSION_SESSION_ID, pinned_data)
        self.assertFalse(pinned_data.get(KEY_AWAITING_HUMAN))
        self.assertIsNone(pinned_data.get(KEY_PARK_REASON))
        # The anchor stays, so the next tick can classify anything it left.
        self.assertEqual(pinned_data[_support.KEY_ROUND_SHA], _support.HEAD_BEFORE_ROUND)


if __name__ == "__main__":
    unittest.main()
