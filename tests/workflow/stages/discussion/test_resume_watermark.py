# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a discussion round records as read, and what it deliberately does not.

A round reads the thread once, at the top, and then spends minutes inside an
agent run. Everything that lands in that window -- a human's second thought, a
comment from an author the allowlist does not yet cover -- was never in front
of the agent, and this stage reads no comment twice: recorded as consumed, it
would be answered never. So the ceiling the park leaves is the newest comment
the round's own prompt was built from, not the newest comment on the thread.

That leaves the stage's own analysis sitting above its own watermark, which is
the trade this makes deliberately. It is safe for the reason the in_review and
validating scans rely on: an orchestrator-posted comment is recognized by the
id recorded when it was posted and by the marker in its body, never by author
login -- which on a PAT shared with a human's account would swallow that
human's replies as bot noise.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from tests.workflow.fixtures import (
    KEY_LAST_ACTION_COMMENT_ID,
    _agent,
)
from tests.workflow.stages.discussion import discussion_resume_test_support as _support
from tests.workflow.stages.discussion.discussion_test_support import (
    DISCUSSION_RESPONSE,
    DISCUSSION_SESSION,
    RUN_AGENT,
    _DiscussionWorkflowMixin,
    _seed_discussion,
)

_MID_RUN_ISSUE_NUMBER = 1120
_TRAILING_ISSUE_NUMBER = 1121
_SELF_ANSWER_ISSUE_NUMBER = 1122

_SECOND_THOUGHT = "actually, hold 2 -- the shim has a caller I forgot"
# Below the fake client's own posted-comment counter, so the park comment the
# round posts lands ABOVE the watermark it leaves. Nothing but the
# orchestrator-comment filter can keep the stage off its own analysis there.
_EARLY_NOTE_ID = 12
_ORCHESTRATOR_COMMENT_IDS = "orchestrator_comment_ids"


class _AnsweredMidRun:
    """A spawn a human comments over while it is still running.

    The window is what makes the case: minutes pass inside a real agent run,
    and what lands in them was never in front of the prompt the round was
    built from.
    """

    def __init__(self, issue, agent_result) -> None:
        self._issue = issue
        self._agent_result = agent_result

    def __call__(self, *spawn_args, **spawn_kwargs):
        self._issue.comments.append(
            _support._reply(_SECOND_THOUGHT, comment_id=_support.TRAILING_REPLY_ID),
        )
        return self._agent_result


class DiscussionConsumedWatermarkTest(
    unittest.TestCase, _DiscussionWorkflowMixin,
):
    """The ceiling a round leaves, measured against what it actually read."""

    def test_a_mid_run_reply_earns_the_next_round(self) -> None:
        gh, issue = _support._seed_parked_discussion(
            _MID_RUN_ISSUE_NUMBER, replies=(_support._reply(_support.DISCUSSION_REPLY),),
        )

        self._run_discussion(
            gh,
            issue,
            run_agent=MagicMock(side_effect=_AnsweredMidRun(
                issue,
                _agent(
                    session_id=DISCUSSION_SESSION,
                    last_message=DISCUSSION_RESPONSE,
                ),
            )),
        )

        # The park stamped nothing past the reply the prompt quoted, so the
        # comment that landed mid-run is still unread.
        self.assertEqual(
            gh.pinned_data(issue.number)[KEY_LAST_ACTION_COMMENT_ID], _support.REPLY_ID,
        )

        next_mocks = self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=DISCUSSION_SESSION,
                last_message="and here is what that changes",
            ),
        )

        next_mocks[RUN_AGENT].assert_called_once()
        self.assertIn(_SECOND_THOUGHT, next_mocks[RUN_AGENT].call_args.args[1])

    def test_an_outsider_after_the_reply_survives(self) -> None:
        # The park stamps at the newest comment on the thread, so the round's
        # own trusted ceiling has to be put back over it -- otherwise the
        # outsider's comment is recorded as read by a prompt that never
        # contained it, and allowlisting them later finds it already consumed.
        gh, issue = _support._seed_parked_discussion(
            _TRAILING_ISSUE_NUMBER, replies=_support._mixed_batch(),
        )

        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_support.TRUSTED_AUTHOR,)):
            self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=DISCUSSION_SESSION,
                    last_message=DISCUSSION_RESPONSE,
                ),
            )

        self.assertEqual(
            gh.pinned_data(issue.number)[KEY_LAST_ACTION_COMMENT_ID], _support.REPLY_ID,
        )

    def test_the_stage_never_answers_itself(self) -> None:
        # An opening round consumes the thread its full prompt quoted -- those
        # comments are answered, and left unconsumed they would earn a second
        # round about themselves. What it must NOT consume is its own posted
        # analysis, which sits above that ceiling: the round after this one is
        # quiet because the reply scan knows the stage's own comments, not
        # because the watermark was pushed past them.
        gh, issue = _seed_discussion(_SELF_ANSWER_ISSUE_NUMBER)
        issue.comments.append(_support._reply(_support.OPENING_NOTE, comment_id=_EARLY_NOTE_ID))

        self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=DISCUSSION_SESSION,
                last_message=DISCUSSION_RESPONSE,
            ),
        )

        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_LAST_ACTION_COMMENT_ID], _EARLY_NOTE_ID,
        )
        posted_id = min(pinned_data[_ORCHESTRATOR_COMMENT_IDS])
        self.assertGreater(posted_id, _EARLY_NOTE_ID)

        quiet_mocks = self._run_discussion(
            gh, issue, run_agent=_agent(last_message=_support.UNASKED_ROUND),
        )

        quiet_mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(len(gh.posted_comments), 1)


if __name__ == "__main__":
    unittest.main()
