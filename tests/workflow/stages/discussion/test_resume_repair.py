# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reply into a checkout that went wrong after the round that asked for it.

The parks that report a read-only violation also say how to undo it, so a
reply arriving while one of those is standing needs nothing more said. A park
that ended cleanly says none of that -- and the tree can still be dirtied or
committed to afterwards, by an operator mid-inspection or by whatever else
shares the host. Answering the frontier then gets silence: no round may open on
that tree, and nothing on the thread explains why.

So the first reply into it is reported, once, with the paths and the command.
The reason that park lands under is itself one the guard recognizes, which is
what makes the report idempotent -- the next reply into the same tree is held
quietly. And no path here consumes the reply, so repairing the tree is the
whole of what an operator has to do: the answer they already wrote is picked up
on the tick after.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.workflow.fixtures import (
    KEY_LAST_ACTION_COMMENT_ID,
    KEY_PARK_REASON,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    PARKED_WATERMARK,
    REPLY_ID,
    UNASKED_ROUND,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_DIRTIED_ISSUE_NUMBER = 1130
_COMMITTED_ISSUE_NUMBER = 1131
_REPAIRED_ISSUE_NUMBER = 1132
_UNREADABLE_ISSUE_NUMBER = 1133
_RESET_COMMAND = "reset --hard"


class DiscussionBlockedResumeTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """What a reply earns when the tree can no longer be opened on."""

    def test_a_dirtied_tree_is_reported_once(self) -> None:
        gh, issue = _seed_parked_discussion(
            _DIRTIED_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        with tempfile.TemporaryDirectory() as tree:
            mocks = self._blocked_tick(gh, issue, Path(tree))
            repeat_mocks = self._blocked_tick(gh, issue, Path(tree))

        mocks[_support.RUN_AGENT].assert_not_called()
        repeat_mocks[_support.RUN_AGENT].assert_not_called()
        # Said once. The reason it left is itself a repair request, so the
        # reply after it changes nothing on the thread.
        self.assertEqual(len(gh.posted_comments), 1)
        self._assert_report_names(
            gh,
            "uncommitted change(s)",
            f"... ({_support.DIRTY_OVERFLOW_COUNT} more)",
            f"{_RESET_COMMAND} {_support.HEAD_BEFORE_ROUND}",
        )
        self._assert_reply_kept(gh, issue, _support.PARK_DISCUSSION_DIRTY)

    def test_an_unreadable_tree_is_reported_once(self) -> None:
        # The resume side of the same probe. `git status` failed, so its list
        # form answers with no paths -- the reading a clean tree gives -- and a
        # round would open on a tree nothing has established anything about.
        # The report names no reset target, because the read that would have
        # found one is the thing that failed.
        gh, issue = _seed_parked_discussion(
            _UNREADABLE_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        with tempfile.TemporaryDirectory() as tree:
            checkout = Path(tree)
            mocks = self._blocked_tick(gh, issue, checkout, unreadable=True)
            self._blocked_tick(gh, issue, checkout, unreadable=True)

        mocks[_support.RUN_AGENT].assert_not_called()
        # One comment across both ticks: the reason this park leaves is itself
        # a repair request, so the second reply into the same tree is held
        # silently -- and a round that had opened would have parked over it.
        self.assertEqual(len(gh.posted_comments), 1)
        self._assert_report_names(
            gh, "could not be read (`git status` or `HEAD` failed)",
        )
        self.assertNotIn(_RESET_COMMAND, gh.posted_comments[0][1])
        self._assert_reply_kept(gh, issue, _support.PARK_DISCUSSION_UNREADABLE)

    def test_a_new_commit_is_reported_once(self) -> None:
        gh, issue = _seed_parked_discussion(
            _COMMITTED_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        with tempfile.TemporaryDirectory() as tree:
            mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message=UNASKED_ROUND),
                head_shas=(_support.HEAD_AFTER_COMMIT,) * 2,
            )
            repeat_mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message=UNASKED_ROUND),
                head_shas=(_support.HEAD_AFTER_COMMIT,) * 2,
            )

        mocks[_support.RUN_AGENT].assert_not_called()
        repeat_mocks[_support.RUN_AGENT].assert_not_called()
        self.assertEqual(len(gh.posted_comments), 1)
        # The reason has to say which violation it was: the operator's next
        # move differs between commits to drop and edits to clean.
        self._assert_report_names(gh, "commits made since")
        self._assert_reply_kept(gh, issue, _support.PARK_DISCUSSION_COMMITS)

    def test_the_reply_survives_the_repair(self) -> None:
        # The whole point of not consuming it: the operator resets the tree
        # and the discussion continues from the answer they already wrote,
        # with no second comment needed from them.
        gh, issue = _seed_parked_discussion(
            _REPAIRED_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        with tempfile.TemporaryDirectory() as tree:
            self._blocked_tick(gh, issue, Path(tree))
            resumed_mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
                head_shas=_support.UNMOVED_HEAD_RESUMED,
            )

        resumed_mocks[_support.RUN_AGENT].assert_called_once()
        self.assertIn(
            DISCUSSION_REPLY, resumed_mocks[_support.RUN_AGENT].call_args.args[1],
        )
        self.assertGreaterEqual(
            gh.pinned_data(issue.number)[KEY_LAST_ACTION_COMMENT_ID], REPLY_ID,
        )

    def _blocked_tick(self, gh, issue, worktree: Path, *, unreadable: bool = False):
        """One tick whose checkout may not be opened on.

        `unreadable` is the other way that happens: the tree holds nothing git
        could name because git could not be asked, which is the reading the
        path list cannot tell apart from a clean tree.
        """
        return self._run_discussion_on_worktree(
            gh,
            issue,
            worktree,
            run_agent=_agent(last_message=UNASKED_ROUND),
            dirty_files=() if unreadable else _support._dirty_files(),
            tree_readable=not unreadable,
            head_shas=_support.UNMOVED_HEAD_RESUMED,
        )

    def _assert_report_names(self, gh, *expected: str) -> None:
        """Everything the operator needs is in the one comment they get."""
        report = gh.posted_comments[0][1]
        for clause in expected:
            with self.subTest(clause=clause):
                self.assertIn(clause, report)

    def _assert_reply_kept(self, gh, issue, park_reason: str) -> None:
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[KEY_PARK_REASON], park_reason)
        self.assertEqual(
            pinned_data[KEY_LAST_ACTION_COMMENT_ID], PARKED_WATERMARK,
        )


if __name__ == "__main__":
    unittest.main()
