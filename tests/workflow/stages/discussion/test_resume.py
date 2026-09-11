# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a human's answer to a parked round is handed to, and how far it moves.

A park is the humans' turn, so the only thing that ends it is one of them
answering. What that answer then reaches is the round that asked the question
-- the pinned session, fed the reply and told to redraw the tree around it --
because a fresh agent would re-open a design the thread has already narrowed.

The two ways that can go wrong have their own cases here. An untrusted author
may neither steer the agent nor be recorded as read, and the ceiling the
consume stops at is asked of the owner rather than through a tick, since the
park that follows stamps the watermark at the newest comment on the thread
whatever the consume staged. And a round with no session id to resume has
nothing cached at all, so it is given the whole conversation rebuilt rather
than a quote that would arrive with no design attached to it.

The ticks that must leave the park untouched are in `test_resume_noop.py`.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import prompts as _prompts
from tests.workflow.fixtures import (
    KEY_AWAITING_HUMAN,
    KEY_LAST_ACTION_COMMENT_ID,
    KEY_PARK_REASON,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    MALICIOUS_URL,
    REPLY_ID,
    TRUSTED_AUTHOR,
    _mixed_batch,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_RESUME_ISSUE_NUMBER = 1100
_MIXED_BATCH_ISSUE_NUMBER = 1101
_STALE_SESSION_ISSUE_NUMBER = 1102
_NO_SESSION_ISSUE_NUMBER = 1103
_COMMITTED_ISSUE_NUMBER = 1104

_PREVIOUS_SESSION = "d-sess-before-the-relabel"
_FULL_PROMPT_CLAUSE = "Nobody has asked you to implement anything"
_FOLLOWUP_CLAUSE = "The humans replied on the issue thread"


class DiscussionResumeTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """The round a trusted reply reopens, and what it is asked."""

    def test_a_reply_resumes_the_pinned_session(self) -> None:
        human_reply = _reply(DISCUSSION_REPLY)
        gh, issue = _seed_parked_discussion(
            _RESUME_ISSUE_NUMBER, replies=(human_reply,),
        )

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_support.DISCUSSION_RESPONSE,
            ),
        )

        self.assert_nothing_published(gh, mocks)
        self.assert_worktree_preserved(mocks)
        spawn_call = mocks[_support.RUN_AGENT].call_args
        # The round the humans answered is the one continued, and what it is
        # sent is the answer plus the instruction to redraw the tree -- not an
        # opening analysis that would ask the settled questions again.
        self.assertEqual(
            spawn_call.kwargs.get(_support.RESUME_SESSION_ID), _support.DISCUSSION_SESSION,
        )
        self.assertEqual(
            spawn_call.args[1],
            _prompts._build_discussion_followup_prompt(
                [human_reply], self.plan_path(issue.number),
            ),
        )
        self._assert_parked_on_the_next_frontier(gh, issue)

    def test_only_trusted_replies_reach_the_agent(self) -> None:
        gh, issue = _seed_parked_discussion(
            _MIXED_BATCH_ISSUE_NUMBER, replies=_mixed_batch(),
        )

        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (TRUSTED_AUTHOR,)):
            mocks = self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
            )

        prompt = mocks[_support.RUN_AGENT].call_args.args[1]
        self.assertIn(DISCUSSION_REPLY, prompt)
        self.assertNotIn(MALICIOUS_URL, prompt)

    def test_a_fresh_round_clears_a_stale_session(self) -> None:
        # An issue relabeled out of this stage and back arrives unparked but
        # still carrying the session its previous discussion ran on. The round
        # that opens is a NEW conversation, so a backend that hands back no id
        # has to leave none behind: kept, the pin would have the next reply
        # resume an argument about a design the thread has moved past.
        gh, issue = _support._seed_discussion(_STALE_SESSION_ISSUE_NUMBER)
        gh.seed_state(
            issue.number,
            **{
                _support.KEY_DISCUSSION_AGENT: config.DECOMPOSE_AGENT_SPEC,
                _support.KEY_DISCUSSION_SESSION_ID: _PREVIOUS_SESSION,
            },
        )

        self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id="", last_message=_support.DISCUSSION_RESPONSE,
            ),
        )

        self.assertIsNone(
            gh.pinned_data(issue.number)[_support.KEY_DISCUSSION_SESSION_ID],
        )

        issue.comments.append(_reply(DISCUSSION_REPLY))
        reply_mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_support.DISCUSSION_RESPONSE,
            ),
        )

        # So the reply that follows rebuilds the whole context instead of
        # resuming a conversation nothing on this thread belongs to.
        spawn_call = reply_mocks[_support.RUN_AGENT].call_args
        self.assertIsNone(spawn_call.kwargs.get(_support.RESUME_SESSION_ID))
        self.assertIn(_FULL_PROMPT_CLAUSE, spawn_call.args[1])

    def test_a_sessionless_round_rebuilds_context(self) -> None:
        # The prior round's backend handed back no session id, so this resume
        # reaches a fresh agent with nothing cached. A quote of the reply
        # alone would arrive with no issue body, no design, and no frontier to
        # fold the answer into.
        gh, issue = _seed_parked_discussion(
            _NO_SESSION_ISSUE_NUMBER,
            replies=(_reply(DISCUSSION_REPLY),),
            session_id=None,
        )

        mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_support.DISCUSSION_RESPONSE,
            ),
        )

        spawn_call = mocks[_support.RUN_AGENT].call_args
        self.assertIsNone(spawn_call.kwargs.get(_support.RESUME_SESSION_ID))
        prompt = spawn_call.args[1]
        self.assertIn(_FULL_PROMPT_CLAUSE, prompt)
        self.assertNotIn(_FOLLOWUP_CLAUSE, prompt)
        # The issue and the reply both reach it, the reply through the
        # trust-filtered conversation block rather than as a quote of its own.
        self.assertIn(_support.DISCUSSION_TOPIC, prompt)
        self.assertIn(DISCUSSION_REPLY, prompt)
        # And the recovered round's own session is what the next one resumes.
        self.assertEqual(
            gh.pinned_data(issue.number)[_support.KEY_DISCUSSION_SESSION_ID],
            _support.DISCUSSION_SESSION,
        )

    def test_a_resumed_round_that_commits_parks(self) -> None:
        # The no-write contract does not soften once the humans are engaged: a
        # round that answers by editing has taken the confirmation this stage
        # exists to wait for. The anchor it opened on survives the park, since
        # it is the tip an operator has to reset back to -- and this round
        # rewrote it with the same value it already held, which is what makes
        # the reset target of a multi-round discussion still meaningful.
        gh, issue = _seed_parked_discussion(
            _COMMITTED_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        with tempfile.TemporaryDirectory() as tree:
            mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message="done, I went ahead and built it",
                ),
                head_shas=_support.MOVED_HEAD_RESUMED,
            )

        self.assert_nothing_published(gh, mocks)
        self.assert_worktree_preserved(mocks)
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_INVALID,
        )
        self.assertEqual(pinned_data[_support.KEY_ROUND_SHA], _support.HEAD_BEFORE_ROUND)
        self.assertIn(_support.HEAD_BEFORE_ROUND, gh.posted_comments[-1][1])

    def _assert_parked_on_the_next_frontier(self, gh, issue) -> None:
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_RESPONSE)
        self.assertTrue(pinned_data[KEY_AWAITING_HUMAN])
        self.assertGreaterEqual(
            pinned_data[KEY_LAST_ACTION_COMMENT_ID], REPLY_ID,
        )
        self.assertIn(f"> {_support.DISCUSSION_RESPONSE}", gh.posted_comments[-1][1])


if __name__ == "__main__":
    unittest.main()
