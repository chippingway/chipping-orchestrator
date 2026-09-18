# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How far a park records the thread as read, and why it is that far.

A park posts its notice and then writes the watermark, and those are two
operations. What goes down is the id of the comment this call POSTED rather
than whatever the thread ends on afterwards -- on a park whose whole point is
waiting for a reply, reading the tip would throw away the answer with the
question.

A park that FOLLOWS an agent run answers it differently, and asks for that
with `bounded=True`: minutes passed inside such a run, so the park's own
notice lands above whatever a human wrote in them and the notice-id floor
below would cross exactly the reply the park is waiting for.

Neither answer ever reads the thread's tip. What a park may record itself as
having read past is a comment actually posted and identified, so a post no id
came back from moves the mark nowhere rather than to whatever the thread
happens to end on.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

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

# How a park that follows a run asks for the bound, which is no part of what
# the park reports about that run.
_BOUNDED = "bounded"


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

    def test_an_unreadable_post_moves_nothing(self) -> None:
        # What a park may record itself as having read past is a comment
        # actually posted and identified, and an id nothing read identifies
        # none. Taking the tip for it would cross whatever else is standing on
        # the thread; leaving the mark costs a poll at worst, since our own
        # unrecorded sentence carries our marker with no ledger entry behind
        # it and is refused as forged by every reading that builds a prompt.
        self._reply()

        with patch.object(_comments, _POST_ISSUE_COMMENT, return_value=None):
            self._park()

        self.assertIsNone(self.state.get(_WATERMARK))
        self.assertTrue(self.state.get("awaiting_human"))

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


class BoundedParkWatermarkTest(unittest.TestCase):
    """What `bounded=True` records instead of that floor.

    Every park that follows an agent run asks for it, so what it has to be is
    the ledger walk: past our own identified comments and no further.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.github.seed_state(_ISSUE_NUMBER)
        self.state = self.github.read_pinned_state(self.issue)

    def test_it_stops_at_a_reply_from_the_run(self) -> None:
        # The comment a human wrote while the agent was out. The notice this
        # park posts lands above it, so the unbounded floor would cross it.
        self.state.set(_WATERMARK, self._reply())
        landed = self._reply()

        self._park()

        self.assertLess(self.state.get(_WATERMARK), landed)
        self.assertTrue(self.state.get("awaiting_human"))

    def test_it_still_clears_its_own_notice(self) -> None:
        # What the bound may not cost: our own sentence still has to be read
        # past, or every poll after this answers it as somebody's guidance.
        self.state.set(_WATERMARK, self._reply())

        self._park()

        self.assertEqual(
            self.state.get(_WATERMARK),
            self.github.latest_comment_id(self.issue),
        )

    def test_the_flag_is_no_correlation_field(self) -> None:
        # Popped like `reason` rather than admitted to the bounded payload
        # this park reports the run under: it decides a WRITE, so it is no
        # part of what either sink is told about the run.
        self._park()

        self.assertNotIn(_BOUNDED, self.github.recorded_events[0])

    def _reply(self) -> int:
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, _REPLY, user=FakeUser(_TRUSTED_AUTHOR)),
        )
        return identified

    def _park(self) -> None:
        _guards._park_awaiting_human(
            self.github, self.issue, self.state, _NOTICE, bounded=True,
        )


if __name__ == "__main__":
    unittest.main()
