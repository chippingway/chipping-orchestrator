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
receipt it was armed with, once every gate has passed again -- the readiness
proof among them, so a head no evidence answers for is never pinged.

A ping over a final docs pass's completion is said once the same way, on
whichever head the pass completed on, and its writes are decided on that
completion too: one a maintainer edits by hand while the gate decides refuses
the arming, and the ping is never posted over it -- nor, on an unmergeable
pull request, is the park written back over the edit, whether it lands while
mergeability is asked or while the park's notice is posted.
"""
from __future__ import annotations

import unittest
from itertools import product
from unittest.mock import patch

from tests.workflow import published_reports as _published_reports, verified_approvals as _verified
from tests.workflow.stages.in_review import completion_test_support as _completion, ready_ping_test_support as support

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


def _reverified(case) -> None:
    """A report of the head the pull request stands on now settled, and approved over passing evidence of it."""
    _published_reports.republishes_the_report(case.github, case.issue)
    _verified.verifies_the_approval(case.github, case.issue)


def _receipts(case) -> list:
    """The receipt each ready ping on the thread carries, oldest first."""
    said = "".join(posted.body for posted in case.pings())
    return support.RECEIPT.findall(said)


def _recorded(case) -> tuple:
    """The head the pinned comment records as pinged, and the ping it records as pending."""
    pinned = case.pinned()
    return pinned[support.READY_PING_SHA], pinned[support.PENDING]


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

    def test_a_new_head_is_pinged_once_verified(self) -> None:
        # The ping over one head is posted and its record refused, and a push
        # moves the pull request on before the next tick: the pending ping
        # names a head that no longer stands, so its comment answers nothing
        # about the new one -- and no evidence answers for the new head, so
        # nothing is posted or written over it, approved on GitHub or not.
        # Once a report of the new head is approved over passing evidence of
        # it, that approval retires the pending record, and the new head is
        # pinged once under a receipt of its own.
        self.seeded()
        with support.failing(self, support.REFUSED, settling=True):
            self.tick()
        self.pull_request.head.sha = PUSHED_HEAD
        writes = self.github.write_state_calls

        self.tick()
        held = (len(self.pings()), self.github.write_state_calls - writes)
        _reverified(self)
        self.tick()

        receipts = _receipts(self)
        distinct = set(receipts)
        self.assertEqual(held, (1, 0))
        self.assertEqual((len(receipts), len(distinct)), (2, 2))
        self.assertEqual(_recorded(self), (PUSHED_HEAD, None))

    def test_a_copied_receipt_is_not_the_ping(self) -> None:
        # A human pastes a ping pending over the head onto the thread, receipt
        # and markers and all, before it was ever posted: a copy is nobody's
        # feedback, and nobody's ping either, since this orchestrator did not
        # write it -- the ping is posted once, under that receipt.
        self.seeded()
        ledger = list(self.pinned()[support.LEDGER])
        with support.failing(self, support.LOST, settling=False):
            self.tick()
        receipt = self.pinned()[support.PENDING][RECEIPT]
        copied = self.replies(support.COPIED.format(receipt=receipt))

        self.tick()

        own = [said.id for said in self.pings() if said.id != copied]
        ledger.extend(own)
        self.assertEqual(len(own), 1)
        self.assertEqual(_recorded(self), (support.HEAD, None))
        self.assertEqual(self.pinned()[support.LEDGER], ledger)
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


class CompletionPingRecoveryTest(_completion._CompletionFixture, unittest.TestCase):
    """A ping over a final docs pass's completion is said once, and decided on that completion."""

    def test_an_unanswered_arming_posts_once(self) -> None:
        # An arming GitHub did not confirm posts nothing; the next tick posts
        # the ping once over the head the pass completed on, under the
        # receipt the lost write armed where it landed.
        for kind, (how, landed) in product(_completion.KINDS, UNANSWERED):
            with self.subTest(kind=kind, how=how):
                self.completed(kind)
                with support.failing(self, how, settling=False):
                    self.tick()
                armed = self.pinned().get(support.PENDING) or {}
                self.assertEqual((self.pings(), bool(armed)), ([], landed))

                self.tick()

                self.assert_settled(armed.get(RECEIPT))
                self.doCleanups()
                self.setUp()

    def test_an_unsettled_ping_is_never_reposted(self) -> None:
        # The ping is posted and the write recording it refused: the next
        # tick finds the comment carrying its receipt and records it.
        for kind in _completion.KINDS:
            with self.subTest(kind):
                self.completed(kind)
                with support.failing(self, support.REFUSED, settling=True):
                    self.tick()
                self.assertEqual(len(self.pings()), 1)

                self.tick()

                self.assert_settled()
                self.doCleanups()
                self.setUp()

    def test_a_hand_edited_completion_is_not_armed(self) -> None:
        # A maintainer cuts the completion's final head short while the gate
        # asks whether the pull request is mergeable. The proof was read over
        # the completion in hand, but the arming is decided on the comment's,
        # so it is refused and nothing is posted -- and the next tick reads
        # the damaged record and pings nobody.
        self.completed(_completion.EXECUTED)
        edited = support._EditedWhileMerging(self, **{_completion.COMPLETION: self.damaged()})
        with patch.object(self.github, support.MERGEABILITY, edited):
            self.tick()
        self.tick()

        pinned = self.pinned()
        self.assertEqual(self.pings(), [])
        self.assertIsNone(pinned.get(support.READY_PING_SHA))
        self.assertIsNone(pinned.get(support.PENDING))

    def test_a_hand_edit_outlasts_the_park(self) -> None:
        # The same edit while the pull request reads unmergeable: the park
        # would write the state in hand whole, putting back the completion the
        # maintainer replaced -- one the next readiness proof would trust -- so
        # it posts and writes nothing, and the edit stands.
        self.completed(_completion.EXECUTED)
        damaged = self.damaged()
        before = (self.github.write_state_calls, len(self.issue.comments))
        edited = support._EditedWhileMerging(self, mergeable=False, **{_completion.COMPLETION: damaged})
        with patch.object(self.github, support.MERGEABILITY, edited):
            self.tick()

        pinned = self.pinned()
        self.assertEqual(pinned[_completion.COMPLETION], damaged)
        self.assertIsNone(pinned.get("park_reason"))
        self.assertEqual((self.github.write_state_calls, len(self.issue.comments)), before)

    def test_an_edit_behind_the_notice_is_kept(self) -> None:
        # The pull request reads unmergeable and the park's notice goes out,
        # and a maintainer cuts the completion short while it is posted: the
        # park lands as a guarded commit decided on the completion, so it is
        # refused rather than written back over the edit, and the notice is
        # all it leaves.
        self.completed(_completion.EXECUTED)
        self.pull_request.mergeable = False
        damaged = self.damaged()
        said = len(self.issue.comments)
        self.damages_behind_the_park_notice()

        self.tick()

        pinned = self.pinned()
        self.assertEqual(pinned[_completion.COMPLETION], damaged)
        self.assertIsNone(pinned.get("park_reason"))
        self.assertEqual(len(self.issue.comments), said + 1)


if __name__ == "__main__":
    unittest.main()
