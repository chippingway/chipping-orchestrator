# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How far a park records the thread as read, and why it is that far.

A park posts its notice and then writes the watermark, and those are two
operations. What goes down is the id of the comment this call POSTED rather
than whatever the thread ends on afterwards -- on a park whose whole point is
waiting for a reply, reading the tip would throw away the answer with the
question.

A park that ended an agent RUN answers it differently, and hands the answer
in: minutes passed inside such a park, so its own notice lands above whatever
a human wrote in them and the notice-id floor below would cross exactly the
reply the park is waiting for.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import comments as _comments, guards as _guards
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import LABEL_IMPLEMENTING
from tests.workflow.interleaving import _RacesPastTheStep

_ISSUE_NUMBER = 613
_NOTICE = "this issue is waiting on a human"
_REPLY = "here is what to do instead"
_TRUSTED_AUTHOR = "alice"
_POST_ISSUE_COMMENT = "_post_issue_comment"
_WATERMARK = "last_action_comment_id"

# How a park that ended a run hands its bound in, which is no part of what the
# park reports about that run.
_HOOK = "watermark"


class ParkWatermarkTest(unittest.TestCase):
    """What the park's own write records the thread as read to."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.github.seed_state(_ISSUE_NUMBER)
        self.state = self.github.read_pinned_state(self.issue)

    def test_it_records_the_notice_it_posted(self) -> None:
        # Which is the tip in the ordinary case, so this is the floor every
        # other reading of the thread is bounded by.
        self._park()

        self.assertTrue(self.state.get("awaiting_human"))
        self.assertEqual(
            self.state.get(_WATERMARK),
            self.github.latest_comment_id(self.issue),
        )

    def test_a_reply_landing_as_it_parks_survives(self) -> None:
        # The window between the post and this write. Read off the thread's
        # tip, the reply becomes the watermark and is skipped for good --
        # which on this park is the answer being thrown away by the question.
        landed = []
        racing = _RacesPastTheStep(
            _comments._post_issue_comment, lambda: landed.append(self._reply()),
        )

        with patch.object(_comments, _POST_ISSUE_COMMENT, racing):
            self._park()

        self.assertEqual(len(landed), 1)
        self.assertLess(self.state.get(_WATERMARK), landed[0])

    def test_an_unreadable_post_falls_back_to_the_tip(self) -> None:
        # The lesser of the two failures left: a watermark that never moved
        # would leave the park's own notice to be read back as somebody's
        # fresh guidance on every dispatch after this one.
        standing = self._reply()

        with patch.object(_comments, _POST_ISSUE_COMMENT, return_value=None):
            self._park()

        self.assertEqual(self.state.get(_WATERMARK), standing)

    def _reply(self) -> int:
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, _REPLY, user=FakeUser(_TRUSTED_AUTHOR)),
        )
        return identified

    def _park(self) -> None:
        _guards._park_awaiting_human(
            self.github, self.issue, self.state, _NOTICE,
        )


class ParkWatermarkHookTest(unittest.TestCase):
    """The bound a park that ended a run hands in, in place of that floor."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.state = MagicMock()
        self.bounded = MagicMock()

    def test_the_hook_decides_the_write(self) -> None:
        # Called with the id ledger as it stood BEFORE this call's own post,
        # which is what tells the notice from the comments that were already
        # there -- and it REPLACES the notice-id write rather than running
        # beside it, since two writes would leave the later one standing.
        self._park_with_the_hook()

        self.bounded.assert_called_once_with(
            self.github, self.issue, self.state, set(),
        )
        self.state.set.assert_any_call("awaiting_human", True)
        for written in self.state.set.call_args_list:
            self.assertNotEqual(written.args[0], _WATERMARK)

    def test_the_hook_is_no_correlation_field(self) -> None:
        # Popped like `reason` rather than admitted to the bounded payload
        # this park reports the run under: it decides a WRITE, and a
        # vocabulary that carried a callable would ship one to the sink.
        self._park_with_the_hook()

        self.assertNotIn(_HOOK, self.github.recorded_events[0])

    def _park_with_the_hook(self) -> None:
        _guards._park_awaiting_human(
            self.github, self.issue, self.state, _NOTICE,
            watermark=self.bounded,
        )


if __name__ == "__main__":
    unittest.main()
