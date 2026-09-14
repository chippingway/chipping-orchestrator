# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Interrupted notice delivery and oversized serialized records for unsplit cases."""
from __future__ import annotations

from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    pinned_state_body,
)
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
)
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.stages.decomposition import late_notice_payloads as _notice_payloads
from tests.workflow.stages.decomposition.late_content_support import (
    RefusedComment,
)
from tests.workflow.stages.decomposition.late_settlement_support import (
    KEY_LAST_ACTION_COMMENT_ID,
    SAID_ONCE,
    GuardedLateCase,
)


class _NoticeCase(GuardedLateCase):
    """One unsplit park whose sentence landed and whose write did not.

    The window both readings below are taken in: the post and the write that
    records it are two operations, so what a crash between them leaves is an
    obligation standing over a thread that already carries the sentence.
    """

    def _say_it_and_lose_the_write(self, run) -> None:
        """Post this verdict's notice, then lose the write that recorded it.

        The post and the write are two operations, so what a crash between
        them leaves is an obligation standing over a thread that already
        carries the sentence -- and the watermark its mention moves back where
        the post found it. Reached by refusing the first attempt, which is
        what leaves the obligation readable before the post discharges it.
        """
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._decide(run)
        owed = self._pinned()
        self._adjudicate()
        self.github.seed_state(self.issue.number, **{
            **self._pinned(),
            _late_notice.PARK_NOTICE: owed[_late_notice.PARK_NOTICE],
            KEY_LAST_ACTION_COMMENT_ID: owed.get(KEY_LAST_ACTION_COMMENT_ID),
        })

    def _assert_said_once(self) -> None:
        """The thread carries the sentence once, and nothing owes it again."""
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)
        self.assertNotIn(_late_notice.PARK_NOTICE, self._pinned())


class _RefusedDeliveryCase(GuardedLateCase):
    """One record whose park is taken with the notice's comment refused.

    The window every case below is a regression inside: the park is durable
    and the sentence it owes is not yet on the thread, so what the pinned
    comment holds afterwards is the only thing that will ever say it.
    """

    def _refuse_the_notice(self) -> None:
        """Take the park, and lose the comment that would have explained it."""
        with RefusedComment(self.github), self.assertRaises(RuntimeError):
            self._adjudicate()


class _TerminatorRecordCase(_RefusedDeliveryCase):
    """A record carrying the wrapper's own terminator, at the old ceiling.

    Live on issues, written by a binary that rendered the payload without
    escaping those terminators -- an agent's explanation and a preserved
    pull-request body are where they come from. The record is unchanged and
    already durable; only what rendering it costs moved. Every case below is
    a regression about not charging the sentence its park owes for that.
    """

    terminators = 0

    def setUp(self) -> None:
        super().setUp()
        self.github.seed_state(
            self.issue.number,
            **_notice_payloads._legacy_record(terminators=self.terminators, room_left=0),
        )

    def test_a_refused_notice_is_still_owed(self) -> None:
        self._refuse_the_notice()

        self.assertEqual(self.github.posted_comments, [])
        self.assertIn(_late_notice.PARK_NOTICE, self._pinned())

    def test_the_next_tick_says_it(self) -> None:
        self._refuse_the_notice()

        outcome, spawn = self._adjudicate()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(len(self.github.posted_comments), SAID_ONCE)
        self.assertNotIn(_late_notice.PARK_NOTICE, self._pinned())

    def test_the_comment_it_writes_still_fits(self) -> None:
        # The bound neither the raised ceiling nor the rendering may cross:
        # a comment GitHub refuses is one the park and its sentence ride out
        # on, and this park is one nothing supersedes.
        self._adjudicate()

        self.assertLessEqual(
            len(pinned_state_body(self._pinned())), MAX_PINNED_BODY,
        )
