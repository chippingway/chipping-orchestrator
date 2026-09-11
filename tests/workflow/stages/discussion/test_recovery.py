# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Classifying an unfinished round's commit when its checkout is gone.

The anchor names a SHA, so the question is always the same one -- has the tip
moved off it -- and the only thing that changes when the worktree directory has
been removed is where the tip is read from. It has to be the branch's tip and
not whether the branch is ahead of base: an issue relabeled here from a PR
stage carries its dev's commits whatever the discussion did, so the
ahead-of-base answer would convict a round that committed nothing, park the
issue, and leave a human to work out that nothing happened.
"""

from __future__ import annotations

import unittest

from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_INHERITED_ISSUE_NUMBER = 1010
_MOVED_TIP_ISSUE_NUMBER = 1011
_NO_BRANCH_ISSUE_NUMBER = 1012
_LEGACY_ANCHOR_ISSUE_NUMBER = 1013


class DiscussionMissingWorktreeRecoveryTest(
    unittest.TestCase, _DiscussionWorkflowMixin,
):

    def test_a_branch_still_on_the_anchor_replays(self) -> None:
        # The branch IS ahead of base -- it arrived that way from a PR stage --
        # but its tip is exactly what the withheld round opened on, so that
        # round committed nothing and the tick replays it. Asking the
        # ahead-of-base question instead would convict it here.
        gh, issue = self._seed_unfinished_round(_INHERITED_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_support.DISCUSSION_RESPONSE,
            ),
            branch_tip_sha=_support.HEAD_BEFORE_ROUND,
            unpushed_branch=_support._issue_branch(issue.number),
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        self.assertEqual(
            gh.pinned_data(issue.number)[KEY_PARK_REASON], "discussion_response",
        )

    def test_a_moved_branch_tip_parks(self) -> None:
        gh, issue = self._seed_unfinished_round(_MOVED_TIP_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(last_message="a round that would inherit it"),
            branch_tip_sha=_support.HEAD_AFTER_COMMIT,
        )

        mocks[_support.RUN_AGENT].assert_not_called()
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_INVALID,
        )
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])

    def test_the_recorded_branch_is_the_one_probed(self) -> None:
        # The round opens on `_resolve_branch_name`, which honours a pinned
        # legacy ref. Deriving the namespaced name here instead would read a
        # branch the round never touched -- unchanged, while the commit it
        # made sits on the branch it did.
        gh, issue = _support._seed_discussion(_LEGACY_ANCHOR_ISSUE_NUMBER)
        anchored_branch = _support._issue_branch(issue.number, legacy=True)
        gh.seed_state(
            issue.number,
            **{
                _support.KEY_ROUND_BRANCH: anchored_branch,
                _support.KEY_ROUND_SHA: _support.HEAD_BEFORE_ROUND,
                _support.KEY_ROUND_OPEN: True,
            },
        )

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(last_message="a round that would inherit it"),
            branch_tip_sha=_support.HEAD_AFTER_COMMIT,
        )

        self.assertEqual(
            mocks[_support.BRANCH_TIP_SHA].call_args.args, (_TEST_SPEC, anchored_branch),
        )
        mocks[_support.RUN_AGENT].assert_not_called()

    def test_a_branch_that_no_longer_exists_replays(self) -> None:
        # Nothing to attribute: no worktree and no branch means the withheld
        # round left nothing behind that a later one could inherit.
        gh, issue = self._seed_unfinished_round(_NO_BRANCH_ISSUE_NUMBER)

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_support.DISCUSSION_RESPONSE,
            ),
            branch_tip_sha="",
        )

        mocks[_support.RUN_AGENT].assert_called_once()

    def _seed_unfinished_round(self, issue_number: int):
        """An issue whose last round ended without reaching a disposition.

        Both halves of the anchor are seeded, as a real round writes them:
        the SHA alone cannot say which ref it belongs to. `_worktree_path` is
        left unpatched, so the checkout it names is not on disk -- the case
        where the tip can only be read off that branch.
        """
        gh, issue = _support._seed_discussion(issue_number)
        gh.seed_state(
            issue.number,
            **{
                _support.KEY_ROUND_BRANCH: _support._issue_branch(issue_number),
                _support.KEY_ROUND_SHA: _support.HEAD_BEFORE_ROUND,
                _support.KEY_ROUND_OPEN: True,
            },
        )
        return gh, issue


if __name__ == "__main__":
    unittest.main()
