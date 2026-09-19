# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How far a park records the thread as read, and why it is that far.

A park posts its notice and then writes the watermark, and those are two
operations. What goes down is the id of the comment this call POSTED rather
than whatever the thread ends on afterwards -- on a park whose whole point is
waiting for a reply, reading the tip would throw away the answer with the
question.

A park asked with `bounded=True` answers differently: minutes passed inside
the run it follows, so its notice lands above whatever a human wrote in them.
It walks only through our own identified comments, and where it cannot walk --
no floor, a post nothing identified, a thread it cannot re-read -- it leaves
the mark where it was rather than reading the tip.
"""

from __future__ import annotations

import contextlib
import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PINNED_STATE_MARKER
from orchestrator.workflow.engine import comments as _comments, guards as _guards, park_watermarks as _park_watermarks
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import LABEL_IMPLEMENTING
from tests.workflow.interleaving import _RacesPastTheStep

_ISSUE_NUMBER = 613
_NOTICE = "this issue is waiting on a human"
_REPLY = "here is what to do instead"
_TRUSTED_AUTHOR = "alice"
_POST_ISSUE_COMMENT = "_post_issue_comment"
_WATERMARK = "last_action_comment_id"
_AWAITING_HUMAN = "awaiting_human"

# A reply quoting the pinned record's marker, which only the pinned comment
# itself is -- and the bounded walk names that comment by id.
_QUOTES_THE_RECORD = f"the record says {PINNED_STATE_MARKER} ... -- why?"

# An earlier notice of ours, above the floor and above any reply.
_EARLIER_NOTICE = "an earlier notice"

_BOUNDED = "bounded"
_COMMENTS_AFTER = "comments_after"
_BAD_GATEWAY = "502 Bad Gateway"

# A ledger entry nothing can read as an id -- a hand edit, or an older writer.
# The ordinary park appends past it and never reaches the bounded walk's stamp,
# which is the one reader here that parses the ledger.
_LEDGER = "orchestrator_comment_ids"
_UNREADABLE_ID = "not-an-id"
_STAMP_READ_THIS_FAR = "_stamp_read_this_far"


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
        # other reading of the thread is bounded by. Never the bounded walk,
        # and nothing read of the ledger ahead of the post -- so an entry no
        # walk could parse parks the issue all the same.
        for ledger in ([], [_UNREADABLE_ID]):
            with self.subTest(ledger=ledger):
                self.setUp()
                self.state.set(_LEDGER, ledger)

                with patch.object(_park_watermarks, _STAMP_READ_THIS_FAR) as walked:
                    self._park()
                    walked.assert_not_called()

                self.assertTrue(self.state.get(_AWAITING_HUMAN))
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


class BoundedParkWatermarkTest(unittest.TestCase):
    """What `bounded=True` records instead of the notice it posted."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.github.seed_state(_ISSUE_NUMBER)
        self.state = self.github.read_pinned_state(self.issue)
        self.floor = self._reply()
        self.state.set(_WATERMARK, self.floor)

    def test_it_reads_past_our_identified_comments(self) -> None:
        # Our own sentences, recorded before or posted by this park, are read
        # past -- or the next poll answers them as somebody's guidance -- and
        # the walk ends at the first comment the ledger does not name.
        _comments._post_issue_comment(self.github, self.issue, self.state, _EARLIER_NOTICE)
        self._park()
        self.assertEqual(
            self.state.get(_WATERMARK), self.github.latest_comment_id(self.issue),
        )

        self.setUp()
        earlier = _comments._post_issue_comment(
            self.github, self.issue, self.state, _EARLIER_NOTICE,
        ).id
        self._reply()
        self._park()
        self.assertEqual(self.state.get(_WATERMARK), earlier)

    def test_it_stops_at_the_first_comment_not_ours(self) -> None:
        # A reply from the run; one quoting the pinned record's marker, which
        # the walk sees because it names that record by id; and a sentence of
        # ours whose id-recording write never landed, which nothing identified.
        cases = (
            ("a reply from the run", lambda: self._reply()),
            ("a reply quoting the record", lambda: self._reply(_QUOTES_THE_RECORD)),
            ("our unrecorded sentence", lambda: self.github.comment(
                self.issue, _comments._with_orch_marker(_EARLIER_NOTICE),
            )),
        )
        for described, lands in cases:
            with self.subTest(thread=described):
                self.setUp()
                lands()

                self._park()

                self.assertEqual(self.state.get(_WATERMARK), self.floor)
                self.assertTrue(self.state.get(_AWAITING_HUMAN))

    def test_it_leaves_the_mark_where_it_cannot_walk(self) -> None:
        # No floor to walk from, a post nothing identified, and a thread the
        # walk cannot re-read: none may fall back to the tip, where the reply
        # below the notice would be crossed. The park itself is still recorded.
        cases = (
            ("no floor", False, contextlib.nullcontext),
            ("an unidentified post", True, lambda: patch.object(
                _comments, _POST_ISSUE_COMMENT, return_value=None,
            )),
            ("an unreadable thread", True, lambda: patch.object(
                self.github, _COMMENTS_AFTER, side_effect=RuntimeError(_BAD_GATEWAY),
            )),
        )
        for described, floored, failing in cases:
            with self.subTest(thread=described):
                self.setUp()
                self._reply()
                if not floored:
                    self.state.set(_WATERMARK, None)

                with failing():
                    self._park()

                self.assertEqual(
                    self.state.get(_WATERMARK), self.floor if floored else None,
                )
                self.assertTrue(self.state.get(_AWAITING_HUMAN))

    def test_the_flag_is_no_correlation_field(self) -> None:
        # It decides a WRITE, so it is no part of what either sink is told.
        self._park()

        self.assertNotIn(_BOUNDED, self.github.recorded_events[0])

    def _reply(self, said: str = _REPLY) -> int:
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, said, user=FakeUser(_TRUSTED_AUTHOR)),
        )
        return identified

    def _park(self) -> None:
        _guards._park_awaiting_human(
            self.github, self.issue, self.state, _NOTICE, bounded=True,
        )


if __name__ == "__main__":
    unittest.main()
