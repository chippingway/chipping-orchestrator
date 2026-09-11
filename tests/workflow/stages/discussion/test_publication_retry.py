# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The retries a publication waits for, and what a crash inside one costs.

A push that failed is the one unfinished publication this stage does not resume
on its own: the park is a request to an operator, and pushing at a remote that
is refusing us on every poll would comment each time it did. The reply to that
park is the retry, and it is also the operator saying why it would work now.

Which makes the retry's own first write the delicate one. It spends that reply --
a retry must not be asked for twice by the same comment -- so whatever it leaves
behind has to be a publication something will pick up again. Leaving the failure
reason standing through it satisfies neither reader: the recovery path refuses to
resume that reason, and the parked path finds nothing unread to resume it with.

The other retry is the one nobody has to ask for. A lookup GitHub declines is
not a request to a human -- one read has to be taken again, and the next poll
takes it -- so the publication holds silently. That hold still has to WRITE,
and it is the only reason it writes anything at all: the marker is what
persists what a fresh round staged, and the session id is in there.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.workflow.fixtures import KEY_PARK_REASON, _agent
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    UNASKED_ROUND,
    _mark_in_flight,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_RETRY_ISSUE_NUMBER = 1243
_UNREPLIED_PUSH_ISSUE_NUMBER = 1246
_FAILED_RETRY_ISSUE_NUMBER = 1252
_CRASHED_RETRY_ISSUE_NUMBER = 1259
_HELD_LOOKUP_ISSUE_NUMBER = 1265

_CRASH = "the process died opening the pull request"
_CONFIRMED_DESIGN = "confirmed -- writing it up"
# The conversation a fresh round opens, which nothing but its own next durable
# write has ever recorded.
_HELD_SESSION = "d-sess-held"
# A tick that publishes without opening a round reads the tip twice: once
# against the anchor, and once as the tip a publication would push.
_RECOVERED_HEAD = (_support.HEAD_AFTER_COMMIT,) * 2


class DiscussionRetryTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """What the reply to a failed push starts, and what it leaves behind."""

    def test_a_reply_retries_a_failed_publication(self) -> None:
        # The operator fixed whatever broke the push and said so on the
        # thread. The branch still carries the same publishable plan, so the
        # reply republishes it rather than earning a round -- or a request to
        # reset away the design the humans already agreed to.
        gh, issue = self._seed_failed_push(
            _RETRY_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        self._retry_tick(gh, issue)

        self.assertEqual(len(gh.opened_prs), 1)
        self.assertEqual(
            gh.pinned_data(issue.number)[KEY_PARK_REASON],
            _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )

    def test_an_unreplied_failure_waits_for_one(self) -> None:
        # The marked park that is not resumed on its own: pushing every tick at
        # a remote that is refusing us would comment each time it failed, and
        # the reply that retries it is also the operator saying why it would
        # work this time.
        gh, issue = self._seed_failed_push(_UNREPLIED_PUSH_ISSUE_NUMBER)

        mocks = self._retry_tick(gh, issue)

        self.assert_nothing_published(gh, mocks)
        self.assertEqual(gh.posted_comments, [])

    def test_a_crash_mid_retry_resumes_itself(self) -> None:
        # The write that begins the retry has already spent the reply, so the
        # failure reason has to go with it. Left standing, this is where the
        # plan would stop: the recovery path refuses to resume a
        # `discussion_push_failed` publication, the reply that would have
        # carried one is consumed, and the issue waits for a human to say the
        # same thing again.
        gh, issue = self._seed_failed_push(
            _CRASHED_RETRY_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        # The tick dies where a publication has already changed the world: the
        # branch is pushed, the marker is durable, and nothing has recorded the
        # PR it was opening.
        with patch.object(gh, "open_pr", side_effect=RuntimeError(_CRASH)), self.assertRaises(RuntimeError):
            self._retry_tick(gh, issue)

        self._retry_tick(gh, issue)

        # No new reply, and none needed.
        self.assertEqual(len(gh.opened_prs), 1)
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )
        self.assertIsNone(pinned_data[_support.KEY_PUBLISHING_SHA])

    def _seed_failed_push(self, issue_number: int, **park_options):
        """An issue whose publication was pushing when the push failed."""
        gh, issue = _seed_parked_discussion(
            issue_number,
            park_reason=_support.PARK_DISCUSSION_PUSH_FAILED,
            **park_options,
        )
        _mark_in_flight(
            gh, issue.number, **{_support.KEY_PUBLISHING_SHA: _support.HEAD_AFTER_COMMIT},
        )
        return gh, issue

    def _retry_tick(self, gh, issue):
        """One tick over that park, whichever way it decides to answer."""
        mocks = self._run_discussion_in_temp_checkout(
            gh,
            issue,
            run_agent=_agent(last_message=UNASKED_ROUND),
            head_shas=_RECOVERED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            remote_branch_tip=_support.HEAD_AFTER_COMMIT,
        )
        mocks[_support.RUN_AGENT].assert_not_called()
        return mocks


class DiscussionFailedRetryTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """A retry that fails again is not asked for by the same reply twice."""

    def test_a_failed_retry_is_not_repeated(self) -> None:
        # The reply asked for the retry, so the retry spends it. Left unread,
        # the same comment would ask for another push -- and earn another
        # failure comment -- on every poll from here on.
        gh, issue = _seed_parked_discussion(
            _FAILED_RETRY_ISSUE_NUMBER,
            replies=(_reply(DISCUSSION_REPLY),),
            park_reason=_support.PARK_DISCUSSION_PUSH_FAILED,
        )
        _mark_in_flight(
            gh, issue.number, **{_support.KEY_PUBLISHING_SHA: _support.HEAD_AFTER_COMMIT},
        )

        with tempfile.TemporaryDirectory() as tree:
            retry_mocks = self._failing_retry(gh, issue, Path(tree))
            repeat_mocks = self._failing_retry(gh, issue, Path(tree))

        retry_mocks[_support.PUSH_BRANCH].assert_called_once()
        self.assertEqual(
            gh.pinned_data(issue.number)[KEY_PARK_REASON],
            _support.PARK_DISCUSSION_PUSH_FAILED,
        )
        # The second tick finds nothing unread, so it pushes nothing and says
        # nothing: the operator's next reply is what asks again.
        repeat_mocks[_support.PUSH_BRANCH].assert_not_called()
        self.assertEqual(len(gh.posted_comments), 1)

    def _failing_retry(self, gh, issue, tree: Path):
        """One reply-driven retry whose push fails again."""
        return self._run_discussion_on_worktree(
            gh,
            issue,
            tree,
            run_agent=_agent(last_message=UNASKED_ROUND),
            head_shas=_RECOVERED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            push_branch=False,
        )


class DiscussionHeldLookupTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """A publication held because GitHub could not be asked, and its retry."""

    def test_a_held_lookup_keeps_the_round_session(self) -> None:
        # The lookup that asks whether this commit is already on a pull request
        # runs BEFORE the marker, and the marker is the only thing that
        # persists what a fresh round staged. So a failure there is not simply
        # a publication deferred: read as "no pull request" it pushes, and
        # answered by returning without writing it takes the session id the
        # round opened under -- leaving the retry a valid plan it cannot
        # attribute, which it refuses as unpublishable.
        gh, issue = _support._seed_discussion(_HELD_LOOKUP_ISSUE_NUMBER)
        gh.unreadable_pr_lookups.add(_support._issue_branch(issue.number))

        with tempfile.TemporaryDirectory() as tree:
            held = self._round_that_commits(gh, issue, Path(tree))

            # Nothing published, nothing said to the humans, and the two
            # records the retry needs: the tip to resume on, and who wrote it.
            self.assert_nothing_published(gh, held)
            self.assertEqual(
                (
                    gh.posted_comments,
                    gh.pinned_data(issue.number)[_support.KEY_PUBLISHING_SHA],
                    gh.pinned_data(issue.number)[_support.KEY_DISCUSSION_SESSION_ID],
                ),
                ([], _support.HEAD_AFTER_COMMIT, _HELD_SESSION),
            )

            gh.unreadable_pr_lookups.clear()
            self._retry_over(gh, issue, Path(tree))

        # The next poll publishes it, under the session that wrote it.
        self.assertEqual(len(gh.opened_prs), 1)
        self.assertIn(_HELD_SESSION, gh.opened_prs[0].body)
        self.assertEqual(
            gh.pinned_data(issue.number)[KEY_PARK_REASON],
            _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )

    def _round_that_commits(self, gh, issue, tree: Path):
        """One fresh round that writes the plan and hands back a session."""
        return self._run_discussion_on_worktree(
            gh,
            issue,
            tree,
            run_agent=_agent(
                session_id=_HELD_SESSION, last_message=_CONFIRMED_DESIGN,
            ),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
        )

    def _retry_over(self, gh, issue, tree: Path):
        """The poll after it, which opens no round and finishes the hold."""
        return self._run_discussion_on_worktree(
            gh,
            issue,
            tree,
            run_agent=_agent(last_message=UNASKED_ROUND),
            head_shas=_RECOVERED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
        )


if __name__ == "__main__":
    unittest.main()
