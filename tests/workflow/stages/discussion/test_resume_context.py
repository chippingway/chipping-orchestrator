# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The conversation a round with nothing cached is rebuilt from.

Two things have to be true of that rebuild, and neither is visible from the
prompt alone.

It has to come from ONE read of the thread. A round that read the thread twice
-- once to decide what it may record as read, once to assemble the text --
would show the agent whatever landed between the two and leave it above the
watermark, and this stage reads no comment twice, so the next tick would send
it again. The case below makes the interval real by having every read of the
thread find a comment that was not there before, and then asserts the one
invariant that says the two agree: nothing the agent was shown sits above the
mark the round left.

And it has to contain the orchestrator's half of the conversation. A
deployment that allowlists its humans and not its own bot account is the
ordinary shape, and the generic prompt filter drops an untrusted author whole
-- which for a rebuild means handing a fresh agent the human's answers by
number with the numbered questions they answer missing.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from tests.workflow.fixtures import (
    KEY_LAST_ACTION_COMMENT_ID,
    _agent,
)
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    OPENING_NOTE,
    REPLY_ID,
    TRUSTED_AUTHOR,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import (
    DISCUSSION_RESPONSE,
    DISCUSSION_SESSION,
    RUN_AGENT,
    _DiscussionWorkflowMixin,
    _seed_discussion,
)

_OPENING_ISSUE_NUMBER = 1140
_RECOVERY_INTERVAL_ISSUE_NUMBER = 1141
_RETAINED_ANALYSIS_ISSUE_NUMBER = 1142

# Above every seeded id, so a comment that arrives mid-tick is always the
# newest one and any disagreement between the two reads is a real ordering.
_ARRIVING_ID = 60000
_ARRIVING_BODY = "one more thing before you answer"

_ROUND_ONE_FRONTIER = "1. own the schema? (recommend: yes) 2. keep the shim?"
_NUMBERED_ANSWER = "1: yes. 2: no, drop it."
_NO_SESSION_ID = ""
# Above the framing note the opening round consumed, so the answer is what
# makes the recovery round this stage's turn again.
_ANSWER_ID = REPLY_ID + 10


class _ThreadGainingComments:
    """A thread that gains a comment on every read of it.

    Both readers are wrapped, because the interval is between reads and not
    between particular readers: whichever pair a round used, the second would
    see a comment the first did not. With one snapshot there is no second.
    """

    def __init__(self, gh, issue) -> None:
        self._issue = issue
        self._read_after = gh.comments_after
        self._read_all = issue.get_comments
        self._next_id = _ARRIVING_ID

    def comments_after(self, issue, after_id):
        self._arrives()
        return self._read_after(issue, after_id)

    def get_comments(self):
        self._arrives()
        return self._read_all()

    def _arrives(self) -> None:
        self._issue.comments.append(
            _reply(
                f"{_ARRIVING_BODY} #{self._next_id}", comment_id=self._next_id,
            ),
        )
        self._next_id += 1


class DiscussionRebuiltContextTest(unittest.TestCase, _DiscussionWorkflowMixin):
    """What a full-context round reads, and what it therefore records."""

    def test_an_opening_round_reads_the_thread_once(self) -> None:
        gh, issue = _seed_discussion(_OPENING_ISSUE_NUMBER)
        issue.comments.append(_reply(OPENING_NOTE))

        mocks = self._run_under_arrivals(gh, issue)

        self._assert_prompt_matches_watermark(gh, issue, mocks)

    def test_a_recovery_round_reads_the_thread_once(self) -> None:
        # The resume shape with the same exposure: no session id to resume, so
        # the batch the turn-taking gate read is NOT what the prompt is built
        # from, and the ceiling has to follow the prompt rather than the gate.
        gh, issue = _seed_parked_discussion(
            _RECOVERY_INTERVAL_ISSUE_NUMBER,
            replies=(_reply(OPENING_NOTE),),
            session_id=None,
        )

        mocks = self._run_under_arrivals(gh, issue)

        self._assert_prompt_matches_watermark(gh, issue, mocks)

    def test_recovery_keeps_the_prior_analysis(self) -> None:
        # Driven through a real first round, because the analysis this has to
        # retain is one the orchestrator posted itself: seeding it would seed
        # the recorded id that makes it retainable along with it.
        gh, issue = _seed_discussion(_RETAINED_ANALYSIS_ISSUE_NUMBER)
        issue.comments.append(_reply(OPENING_NOTE))

        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (TRUSTED_AUTHOR,)):
            self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=_NO_SESSION_ID,
                    last_message=_ROUND_ONE_FRONTIER,
                ),
            )
            issue.comments.append(
                _reply(_NUMBERED_ANSWER, comment_id=_ANSWER_ID),
            )
            recovery_mocks = self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=DISCUSSION_SESSION,
                    last_message=DISCUSSION_RESPONSE,
                ),
            )

        prompt = recovery_mocks[RUN_AGENT].call_args.args[1]
        # The answer, and the questions it answers by number.
        self.assertIn(_NUMBERED_ANSWER, prompt)
        self.assertIn(_ROUND_ONE_FRONTIER, prompt)

    def _run_under_arrivals(self, gh, issue):
        """One tick during which every read of the thread finds it longer."""
        arrivals = _ThreadGainingComments(gh, issue)
        with (
            patch.object(gh, "comments_after", arrivals.comments_after),
            patch.object(issue, "get_comments", arrivals.get_comments),
        ):
            return self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=DISCUSSION_SESSION,
                    last_message=DISCUSSION_RESPONSE,
                ),
            )

    def _assert_prompt_matches_watermark(self, gh, issue, mocks) -> None:
        """The newest comment the agent was shown IS the mark the round left.

        Only equality pins both directions, and both are live: a comment shown
        and not consumed is one the next tick sends again, and a comment
        consumed and not shown is one the agent never gets to read at all.
        Which of the two a second read produces depends on nothing better than
        the order the reads happen to run in.
        """
        watermark = gh.pinned_data(issue.number)[KEY_LAST_ACTION_COMMENT_ID]
        # A comment did arrive mid-tick, or this proves nothing.
        self.assertGreaterEqual(watermark, _ARRIVING_ID)
        prompt = mocks[RUN_AGENT].call_args.args[1]
        shown = [
            comment.id for comment in issue.comments if comment.body in prompt
        ]
        self.assertEqual(max(shown), watermark)


if __name__ == "__main__":
    unittest.main()
