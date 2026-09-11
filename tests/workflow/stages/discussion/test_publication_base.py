# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commit a publication measures the branch against.

A round is judged by what its branch changes against the base branch, so the
base is half of that judgement and the half the agent is closest to: the
per-issue checkout is a linked worktree sharing the clone's refs, so
`refs/remotes/<remote>/<base>` is a name the round itself can repoint. An agent
that commits code, moves that ref onto the code commit, and then commits the
plan leaves a ref-relative diff naming one path and a branch carrying two
commits -- and the push publishes both.

What closes it is an object id read from the remote before the agent is
spawned, recorded on the issue, and named to the diff. Recorded rather than
re-read, because the tick that publishes need not be the tick that ran: a
recovery has to measure against the base its round was given, and a fresh read
would put the local ref back in the answer.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.workflow.fixtures import (
    _TEST_SPEC,
    BASE_TIP_SHA,
    KEY_PARK_REASON,
    TEST_BASE_BRANCH,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_PINNED_ISSUE_NUMBER = 1270
_RECOVERED_ISSUE_NUMBER = 1271
_NO_BASE_ISSUE_NUMBER = 1272

_CONFIRMED = "confirmed -- writing it up"
_INHERITING_ROUND = "a round that would inherit it"
# The base the round that already ran was given, spelled differently from what
# a read taken now hands back: a publication that re-read the base would be
# measuring against the second one.
_RECORDED_BASE = "the-base-that-rounds-work-was-given"
# A publication that opens no round of its own reads the tip twice: once
# against the anchor, and once as the tip it would push.
_RECOVERED_HEAD = (_support.HEAD_AFTER_COMMIT,) * 2
_NO_READING = "could not be established"


class DiscussionPlanBaseTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """Where the base-relative diff takes its base from, and when it has none."""

    def test_the_round_pins_what_the_remote_says(self) -> None:
        # Read through the token before the agent can touch the checkout, and
        # recorded on the issue -- so what the branch is finally measured
        # against is a commit established off-host and out of the round's
        # reach, not a local ref sitting in the object store it writes into.
        gh, issue = _support._seed_discussion(_PINNED_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION, last_message=_CONFIRMED,
            ),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
        )

        base_read = mocks[_support.REMOTE_BASE_TIP].call_args_list[0]
        self.assertEqual(
            (base_read.args[0], base_read.args[2]),
            (_TEST_SPEC, TEST_BASE_BRANCH),
        )
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[_support.KEY_BASE_SHA], BASE_TIP_SHA)
        self.assertEqual(
            mocks[_support.COMMITTED_PATHS].call_args.args[1], BASE_TIP_SHA,
        )
        self.assertEqual(len(gh.opened_prs), 1)

    def test_a_recovery_uses_the_recorded_base(self) -> None:
        # The round committed the plan and was cut short before it could say
        # so, so this tick publishes for it -- against the base that round was
        # given. Reading the base again here would measure the commit against
        # whatever the base branch has moved to since, and against a local ref
        # the round itself had every chance to repoint.
        gh, issue = _support._seed_discussion(_RECOVERED_ISSUE_NUMBER)
        gh.seed_state(
            issue.number,
            **{
                _support.KEY_ROUND_BRANCH: _support._issue_branch(issue.number),
                _support.KEY_ROUND_SHA: _support.HEAD_BEFORE_ROUND,
                _support.KEY_ROUND_OPEN: True,
                _support.KEY_BASE_SHA: _RECORDED_BASE,
                _support.KEY_DISCUSSION_SESSION_ID: _support.DISCUSSION_SESSION,
            },
        )

        with tempfile.TemporaryDirectory() as tree:
            mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message=_INHERITING_ROUND),
                head_shas=_RECOVERED_HEAD,
                committed_paths=(self.plan_path(issue.number),),
            )

        self.assertEqual(
            mocks[_support.COMMITTED_PATHS].call_args.args[1], _RECORDED_BASE,
        )
        # The base is the record's, not a fresh read's. The publication does
        # ask the remote about the plan's own branch before it moves it.
        self.assertNotIn(TEST_BASE_BRANCH, self.remote_reads(mocks))
        self.assertEqual(len(gh.opened_prs), 1)

    def test_a_round_with_no_base_publishes_nothing(self) -> None:
        # The remote could not be asked -- a token that would not resolve, a
        # network that was down -- so this round has no base at all. The paths
        # a diff reported against nothing are not a reading of the branch, and
        # a publication resting on them would push whatever the agent had put
        # beneath the plan.
        gh, issue = _support._seed_discussion(_NO_BASE_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION, last_message=_CONFIRMED,
            ),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            remote_base_tip=None,
        )

        self.assert_nothing_published(gh, mocks)
        self.assert_worktree_preserved(mocks)
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_INVALID,
        )
        self.assertNotIn(_support.KEY_PLAN_PATH, pinned_data)
        # Reported as a reading that never happened rather than as an empty
        # diff, which an operator would answer by resetting the branch.
        _, body = gh.posted_comments[0]
        self.assertIn(_NO_READING, body)


if __name__ == "__main__":
    unittest.main()
