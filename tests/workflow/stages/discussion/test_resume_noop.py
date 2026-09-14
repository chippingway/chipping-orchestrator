# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ticks on a parked discussion that have to leave everything as it was.

Four things can reach a parked issue without being an answer to it: nobody
having replied, a reply from an author the allowlist does not cover, a round
the shutdown sweep killed before it could answer, and a reply arriving into a
checkout an operator was parked to repair. Each has to end with the durable
record untouched -- because that record is what the next tick reads to find
the answer still waiting.

Every case is asserted against the pinned state rather than only against the
absent spawn. A tick that consumed a reply it never acted on is indisting-
uishable from a correct one until the next tick, by which time the human's
answer is simply gone and only another comment from them will restart it.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from tests.workflow.fixtures import (
    AGENT_RUN_CHARGE_WRITES,
    KEY_AWAITING_HUMAN,
    KEY_LAST_ACTION_COMMENT_ID,
    KEY_PARK_REASON,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    OUTSIDER_AUTHOR,
    OUTSIDER_REPLY,
    PARKED_WATERMARK,
    TRUSTED_AUTHOR,
    UNASKED_ROUND,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_QUIET_ISSUE_NUMBER = 1110
_OUTSIDER_ONLY_ISSUE_NUMBER = 1111
_INTERRUPTED_ISSUE_NUMBER = 1112
_MOVED_ANCHOR_ISSUE_NUMBER = 1113
_DIRTY_TREE_ISSUE_NUMBER = 1114


class DiscussionResumeNoopTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """A parked discussion nobody has answered, in each of its four shapes."""

    def test_no_reply_leaves_the_park_untouched(self) -> None:
        gh, issue = _seed_parked_discussion(_QUIET_ISSUE_NUMBER)
        writes_before = gh.write_state_calls

        mocks = self._run_discussion(
            gh, issue, run_agent=_agent(last_message=UNASKED_ROUND),
        )

        self._assert_reply_still_waiting(gh, issue, mocks, writes_before)

    def test_an_untrusted_batch_reads_as_no_reply(self) -> None:
        gh, issue = _seed_parked_discussion(
            _OUTSIDER_ONLY_ISSUE_NUMBER,
            replies=(_reply(OUTSIDER_REPLY, author=OUTSIDER_AUTHOR),),
        )
        writes_before = gh.write_state_calls

        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (TRUSTED_AUTHOR,)):
            mocks = self._run_discussion(
                gh, issue, run_agent=_agent(last_message=UNASKED_ROUND),
            )

        self._assert_reply_still_waiting(gh, issue, mocks, writes_before)

    def test_an_interrupted_resume_is_replayed(self) -> None:
        # The sweep kills the round before it can answer, so nothing the reply
        # touched is made durable: it is still new to the next process, which
        # runs it again rather than dropping the human's answer.
        gh, issue = _seed_parked_discussion(
            _INTERRUPTED_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )
        writes_before = gh.write_state_calls

        mocks = self._run_discussion(
            gh, issue, run_agent=_agent(last_message="", interrupted=True),
        )

        mocks[_support.RUN_AGENT].assert_called_once()
        self.assertEqual(gh.posted_comments, [])
        self._assert_reply_unconsumed(gh, issue)
        # The round's provenance write and the charge its spawn took are all
        # that landed, and neither records anything about the reply.
        self.assertEqual(
            gh.write_state_calls, writes_before + 1 + AGENT_RUN_CHARGE_WRITES,
        )

    def test_a_moved_anchor_holds_the_resume(self) -> None:
        # The park being replied to already named this commit and quoted the
        # tip to reset back to. A round opened here would rewrite that tip
        # with the moved one, spending the only record of what the branch
        # arrived carrying -- so the tick holds and the answer waits.
        gh, issue = _seed_parked_discussion(
            _MOVED_ANCHOR_ISSUE_NUMBER,
            replies=(_reply(DISCUSSION_REPLY),),
            park_reason=_support.PARK_DISCUSSION_COMMITS,
        )
        writes_before = gh.write_state_calls

        with tempfile.TemporaryDirectory() as tree:
            mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message=UNASKED_ROUND),
                head_shas=(_support.HEAD_AFTER_COMMIT,) * 2,
            )

        self._assert_reply_still_waiting(
            gh,
            issue,
            mocks,
            writes_before,
            park_reason=_support.PARK_DISCUSSION_COMMITS,
        )

    def test_a_dirty_tree_holds_the_resume(self) -> None:
        # The same hold for the other repair an operator can be parked on:
        # preparing a checkout force-removes a dirty tree carrying no commits,
        # so a resumed round must not be what destroys one.
        gh, issue = _seed_parked_discussion(
            _DIRTY_TREE_ISSUE_NUMBER,
            replies=(_reply(DISCUSSION_REPLY),),
            park_reason=_support.PARK_DISCUSSION_DIRTY,
        )
        writes_before = gh.write_state_calls

        with tempfile.TemporaryDirectory() as tree:
            mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message=UNASKED_ROUND),
                dirty_files=_support._dirty_files(),
                head_shas=_support.UNMOVED_HEAD_RESUMED,
            )

        self._assert_reply_still_waiting(
            gh, issue, mocks, writes_before, park_reason=_support.PARK_DISCUSSION_DIRTY,
        )
        mocks[_support.ENSURE_WORKTREE].assert_not_called()

    def _assert_reply_unconsumed(self, gh, issue, park_reason=None) -> None:
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_LAST_ACTION_COMMENT_ID], PARKED_WATERMARK,
        )
        self.assertEqual(
            pinned_data[KEY_PARK_REASON],
            park_reason or _support.PARK_DISCUSSION_RESPONSE,
        )
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])

    def _assert_reply_still_waiting(
        self,
        gh,
        issue,
        mocks,
        writes_before: int,
        *,
        park_reason: str = _support.PARK_DISCUSSION_RESPONSE,
    ) -> None:
        """No round, no comment, no event, and not one durable write."""
        mocks[_support.RUN_AGENT].assert_not_called()
        self.assertEqual(gh.posted_comments, [])
        self.assertEqual(gh.recorded_events, [])
        self.assertEqual(gh.write_state_calls, writes_before)
        self._assert_reply_unconsumed(gh, issue, park_reason)


if __name__ == "__main__":
    unittest.main()
