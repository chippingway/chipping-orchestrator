# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ready ping said once, whatever GitHub or a restart does to its writes, its post, and its thread.

Every ping is armed in a write of its own before it is posted, its record is
prepared before the post, and that record lands behind it. A write left
unanswered -- a comment nobody could read, an edit refused, one that landed
and lost its answer, a comment with no room -- stops the ping where it stands,
with nothing posted past an arming or preparation that did not land. The tick
that follows reads what landed: a ping pending whose comment the thread
already carries is recorded rather than posted again, a thread nobody could
read holds it, and one that reads without it is posted once, under the
receipt it was armed with, once every gate has passed again.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.workflow.stages.in_review import ready_ping_test_support as support

# Each way an edit is left unanswered, and whether it landed anyway.
UNANSWERED = (
    (support.UNREADABLE, False),
    (support.REFUSED, False),
    (support.LOST, True),
)

# What a human replies on the thread beside a ping.
REPLY = "one more thing before this merges"

# The member of a pending ping its receipt is recorded under.
RECEIPT = "receipt"

# A head a push moves the pull request on to.
PUSHED_HEAD = "beefcafe" * 5


class UnlandedArmingTest(unittest.TestCase, support._ReadyPingFixture):
    """An arming or a preparation that did not land posts nothing."""

    def test_an_unanswered_arming_posts_nothing(self) -> None:
        # Nothing is posted behind an arming GitHub did not confirm. The next
        # tick posts the ping once: under the receipt the lost write armed,
        # where it landed, since that is the ping the comment says is owed.
        for how, landed in UNANSWERED:
            with self.subTest(how=how):
                self.seeded()
                with support.failing(self, how, settling=False):
                    self.tick()
                armed = self.pinned().get(support.PENDING) or {}
                self.assertEqual((self.pings(), bool(armed)), ([], landed))

                self.tick()

                self.assert_settled(armed.get(RECEIPT))

    def test_a_full_comment_arms_nothing(self) -> None:
        # The arming is measured whole before it goes out: a comment with no
        # room left for it is armed nothing, posted nothing, and sent no
        # write, and the ping follows once a human has made room.
        self.seeded()
        self.fills()
        writes = self.github.write_state_calls

        self.tick()

        self.assertEqual((self.pings(), self.github.write_state_calls), ([], writes))
        self.fills(filled=False)
        self.tick()
        self.assert_settled()

    def test_a_ping_recorded_by_hand_is_not_armed(self) -> None:
        # A maintainer records the head as pinged on the pinned comment while
        # the gate asks whether the pull request is mergeable: the arming was
        # decided over the reading without it, so it is refused and nothing is
        # posted -- and the next tick finds the head pinged and says nothing.
        self.seeded()
        edited = support._EditedWhileMerging(self, **{support.READY_PING_SHA: support.HEAD})
        with patch.object(self.github, support.MERGEABILITY, edited):
            self.tick()
        self.tick()

        pinned = self.pinned()
        recorded = (pinned[support.READY_PING_SHA], pinned.get(support.PENDING))
        self.assertEqual(self.pings(), [])
        self.assertEqual(recorded, (support.HEAD, None))

    def test_a_refused_preparation_posts_nothing(self) -> None:
        # The arming lands, and the comment the record is then prepared over
        # will not read, or has been filled to its limit by hand: nothing is
        # posted, the arming stands, and once the comment takes it again the
        # ping is posted once under the receipt that arming recorded.
        for full in (False, True):
            with self.subTest(full=full):
                self.seeded()
                behind = support._BehindArming(self, full=full)
                with patch.object(self.github, support.EDIT_PINNED_STATE, behind):
                    self.tick()
                armed = self.pinned()[support.PENDING]
                self.assertEqual(self.pings(), [])

                self.fills(filled=False)
                self.tick()

                self.assert_settled(armed[RECEIPT])


class UnsettledPingTest(unittest.TestCase, support._ReadyPingFixture):
    """A ping posted whose record never landed, or whose post never answered, is found rather than said twice."""

    def test_an_unsettled_ping_is_never_reposted(self) -> None:
        # The ping is posted and its record left unanswered. Where the record
        # did not land, the arming stands and the next tick finds the comment
        # carrying its receipt -- recorded, not posted again; where it landed
        # with its answer lost, the next tick finds the head pinged.
        for how, landed in UNANSWERED:
            with self.subTest(how=how):
                self.seeded()
                with support.failing(self, how, settling=True):
                    self.tick()
                pinged = self.pinned().get(support.READY_PING_SHA) == support.HEAD
                self.assertEqual((len(self.pings()), pinged), (1, landed))

                self.tick()

                self.assert_settled()

    def test_a_restart_records_the_posted_ping(self) -> None:
        # A poller killed between the post and the write recording it leaves
        # the ping on the thread and its arming on the comment: the restarted
        # tick records the comment it finds, and says nothing again.
        self.seeded()
        dies = support.failing(self, support.DIES, settling=True)
        with dies, self.assertRaises(SystemExit):
            self.tick()
        self.assertEqual(len(self.pings()), 1)

        self.tick()

        self.assert_settled()

    def test_a_lost_post_is_recorded_at_once(self) -> None:
        # GitHub takes the post and loses its answer: the thread read behind
        # it finds the comment carrying the receipt, and the same tick records
        # it as the ping.
        self.seeded()
        lost = support._UnansweredPost(self.github, lands=True)
        with patch.object(self.github, support.COMMENT, lost):
            self.tick()

        self.assert_settled()

    def test_an_unread_post_is_settled_later(self) -> None:
        # A post that raised, with a thread that will not read behind it:
        # whether it landed is unknown, so nothing is recorded and the arming
        # stands. The next tick reads the thread -- recording a ping that
        # landed, and posting once one that did not.
        for lands in (True, False):
            with self.subTest(lands=lands):
                self.seeded()
                unanswered = support._UnansweredPost(self.github, lands=lands)
                posting = patch.object(self.github, support.COMMENT, unanswered)
                with posting, support._UnreadOnce(self.github, support.COMMENT):
                    self.tick()
                posted = len(self.pings())
                pinged = self.pinned().get(support.READY_PING_SHA)
                self.assertEqual((posted, pinged), (int(lands), None))

                self.tick()

                self.assert_settled()


class PendingPingRecoveryTest(unittest.TestCase, support._ReadyPingFixture):
    """A later tick reads the thread before it says anything over a ping still pending."""

    def test_an_unread_thread_holds_the_ping(self) -> None:
        # A ping armed and posted whose record was refused, or armed with its
        # answer lost and never posted, and a thread that will not read on the
        # next tick: that proves neither the post nor its absence, so nothing
        # is posted or written. Once it reads, what is there is recorded, or
        # posted once.
        for settling, how in ((True, support.REFUSED), (False, support.LOST)):
            with self.subTest(posted=settling):
                self.seeded()
                with support.failing(self, how, settling=settling):
                    self.tick()
                held = (len(self.pings()), self.github.write_state_calls)
                with support._UnreadOnce(self.github, support.MERGEABILITY):
                    self.tick()
                answered = (len(self.pings()), self.github.write_state_calls)
                self.assertEqual(answered, held)

                self.tick()

                self.assert_settled()

    def test_a_pending_ping_passes_every_gate_again(self) -> None:
        # A ping armed and never posted is a new post when it is retried, so
        # every gate in front of it is asked again: a human's standing change
        # request on the head, or an approval withdrawn, holds it with nothing
        # written, and once either is answered it is posted once.
        for gate, held in (("changes_requested", True), ("approved", False)):
            with self.subTest(gate=gate):
                self.seeded()
                with support.failing(self, support.LOST, settling=False):
                    self.tick()
                setattr(self.pull_request, gate, held)
                writes = self.github.write_state_calls
                self.tick()
                answered = (self.pings(), self.github.write_state_calls)
                self.assertEqual(answered, ([], writes))

                setattr(self.pull_request, gate, not held)
                self.tick()

                self.assert_settled()

    def test_a_new_head_is_pinged_past_a_pending_one(self) -> None:
        # The ping over one head is posted and its record refused, and a push
        # moves the pull request on before the next tick: the pending ping
        # names a head that no longer stands, so its comment answers nothing
        # about the new one, which is armed and pinged in its own right.
        self.seeded()
        with support.failing(self, support.REFUSED, settling=True):
            self.tick()
        self.pull_request.head.sha = PUSHED_HEAD

        self.tick()

        pinned = self.pinned()
        recorded = (pinned[support.READY_PING_SHA], pinned[support.PENDING])
        self.assertEqual(len(self.pings()), 2)
        self.assertEqual(recorded, (PUSHED_HEAD, None))

    def test_a_copied_receipt_is_not_the_ping(self) -> None:
        # A human pastes a ping pending over the head onto the thread, receipt
        # and markers and all, before it was ever posted: a copy is nobody's
        # feedback, and nobody's ping either, since this orchestrator did not
        # write it -- the ping is posted once, under that receipt.
        self.seeded()
        with support.failing(self, support.LOST, settling=False):
            self.tick()
        receipt = self.pinned()[support.PENDING][RECEIPT]
        copied = self.replies(support.COPIED.format(receipt=receipt))

        self.tick()

        own = [said.id for said in self.pings()]
        own.remove(copied)
        pinned = self.pinned()
        recorded = pinned[support.READY_PING_SHA]
        self.assertEqual((len(own), recorded), (1, support.HEAD))
        self.assertEqual(pinned[support.LEDGER], own)
        self.assertEqual(self.github.label_history, [])

    def test_a_reply_beside_a_lost_ping_is_feedback(self) -> None:
        # The thread carries a ping whose record was refused -- this
        # orchestrator's by its marker, though no ledger entry names it --
        # and a human's reply below it. The reply goes to `fixing` as the
        # whole batch, the ping is nobody's feedback, and no watermark moved
        # past either.
        self.seeded()
        with support.failing(self, support.REFUSED, settling=True):
            self.tick()
        reply_id = self.replies(REPLY)

        self.tick()

        pinned = self.pinned()
        self.assertEqual(self.github.label_history, [(support.ISSUE, "workflow:fixing")])
        batch = (pinned["pending_fix_issue_ids"], pinned[support.PR_LAST_COMMENT_ID])
        self.assertEqual(batch, ([reply_id], 0))


if __name__ == "__main__":
    unittest.main()
