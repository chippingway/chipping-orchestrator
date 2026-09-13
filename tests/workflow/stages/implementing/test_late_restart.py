# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a poll finds when the write past a sentence of ours never landed.

Every road on the authorization park posts before it persists the id saying
the post was ours, so a process dying between the two leaves a comment on the
thread that no later reader can attribute. These pin down both halves of that
window: a sentence that never reached the thread is still owed and is said,
and one that reached it is claimed rather than said again -- without moving
the watermark over whatever a human wrote in between.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    state as _state,
)
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA
from tests.workflow.stages.implementing import (
    late_consent_test_support as support,
)


class _Silence(RuntimeError):
    """The process dying before its notice ever reaches the thread."""


class RestartedParkTest(support._ConsentCase, unittest.TestCase):
    """A park whose notice went out and whose write never landed.

    The two are separate operations and always will be. What the order buys is
    which way the damage falls: the park goes down FIRST, so the poll after a
    crash finds somebody already waiting behind this candidate rather than an
    unparked issue to announce all over again -- over a watermark that would
    move past whatever the human wrote in between.
    """

    def test_a_restart_says_nothing_twice(self) -> None:
        # The whole sequence: the notice lands, the write recording it does
        # not, and the operator answers before anything runs again. Read back
        # as unparked, the restarted tick mentions the same people a second
        # time and watermarks past the command -- so the decision they already
        # made is one nothing can ever read.
        self._seed(parked=False)
        self._crashes_past_the_notice()
        commanded = self._reply(support.AUTHORIZE)

        self.assertTrue(self._authorizes())

        self.assertEqual(self._said(), 1)
        self.assertEqual(
            self._pinned()[support.KEY_OVERRIDE_COMMENT_ID], commanded,
        )

    def test_the_park_outlives_the_lost_write(self) -> None:
        # What makes the restart quiet, asserted where it is written rather
        # than only through what it prevents.
        self._seed(parked=False)

        self._crashes_past_the_notice()

        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON], _command.PARK_UNAUTHORIZED_EXEMPTION,
        )

    def test_a_notice_that_never_landed_is_still_owed(self) -> None:
        # The other way round, and why the receipt rides the park rather than
        # the park alone answering "already said": a tick that died BEFORE its
        # notice leaves somebody waiting behind a question nobody asked, and a
        # park read as announced because it is standing would never ask it.
        self._seed(parked=False)
        with (
            patch.object(_guards, support.PARK_AWAITING_HUMAN, side_effect=_Silence),
            self.assertRaises(_Silence),
        ):
            self._authorizes()

        self._authorizes()

        self.assertEqual(self._said(), 1)

    def test_a_park_still_owing_its_notice_says_it(self) -> None:
        # The receipt is why the park alone cannot answer "already said": a
        # tick that died before its notice leaves somebody waiting behind a
        # question nobody asked, and a standing park read as announced would
        # never ask it. Dropped by the write past the post, so the poll after
        # this one is quiet again.
        self._seed(**{
            _state._HELD_RECEIPT: support.PARK_RECEIPT,
            **support.measured_pair(),
        })

        self.assertFalse(self._authorizes())

        self.assertEqual(self._said(), 1)
        self.assertIn(support.AUTHORIZE, self.github.posted_comments[0][1])
        self.assertIsNone(self._pinned()[_state._HELD_RECEIPT])

    def _crashes_past_the_notice(self) -> None:
        """Take the park, say it, and lose the write that recorded saying it."""
        with (
            patch.object(
                self.github, support.WRITE_PINNED_STATE,
                side_effect=support.DiesPastTheNotice(self.github),
            ),
            self.assertRaises(support.CrashedTick),
        ):
            self._authorizes()


class StrandedSentenceTest(support._ConsentCase, unittest.TestCase):
    """A sentence of ours on the thread that no write recorded posting.

    Every road here posts before it persists the id saying the post was ours,
    so a process dying between the two leaves a comment nothing can attribute.
    Whole gate calls, because what answers the window is the receipt read
    against the thread and a case entering past it would answer a different
    question.
    """

    def test_a_stranded_notice_is_said_once(self) -> None:
        # The receipt says a tick died mid-sentence; the thread says which
        # side of the post it died on. Answered off the record alone, the next
        # poll mentions the same people a second time about a decision they
        # have already been asked for.
        self._crashes_past_our_sentence(parked=False)

        self.assertTrue(self._holds())

        self.assertEqual(self._said(), 1)
        self.assertIsNone(self._pinned()[_state._HELD_RECEIPT])

    def test_guidance_under_it_survives(self) -> None:
        # The whole cost of getting this wrong. A second notice moves the
        # watermark past everything under it, so the reply an operator wrote
        # between the two ticks would be consumed unread.
        self._crashes_past_our_sentence(parked=False)
        spoke = self._reply(support.GUIDANCE)

        self.assertTrue(self._holds())

        self.assertEqual(self._said(), 1)
        self.assertLess(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], spoke,
        )

    def test_a_stranded_refusal_is_said_once(self) -> None:
        # The same window on the other sentence this owner words. Its receipt
        # is scoped to the reply it answers, so the poll after re-reads a
        # command already answered and must not answer it twice.
        self._reply(support.AUTHORIZE_ANOTHER)
        self._crashes_past_our_sentence()

        self.assertTrue(self._holds())

        self.assertEqual(self._said(), 1)
        self.assertNotIn(support.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned())

    def test_the_park_outlives_a_stranded_refusal(self) -> None:
        # A command this park may not act on leaves it exactly where it was,
        # crash or no crash.
        self._reply(support.AUTHORIZE_ANOTHER)
        self._crashes_past_our_sentence()

        self._holds()

        self._assert_still_parked()

    def test_a_command_behind_it_still_works(self) -> None:
        # What the unclaimed sentence costs, bounded: it stands in the reading
        # as somebody's word, which is no command, so the park holds -- and
        # the operator's next command is the last fresh reply and publishes.
        self._crashes_past_our_sentence(parked=False)
        commanded = self._reply(support.AUTHORIZE)

        self.assertFalse(self._holds())

        self.assertEqual(
            self._pinned()[support.KEY_OVERRIDE_COMMENT_ID], commanded,
        )



class ReceiptEvidenceTest(support._ConsentCase, unittest.TestCase):
    """What an outstanding receipt may and may not be read as proving.

    It is public text, deterministic from the issue and the commit, and the
    author it is asked beside may be the very token an operator posts under.
    So it may SILENCE a sentence of ours, which costs a poll when it is wrong,
    and it may never CLAIM a comment, which costs whatever its author said.
    """

    def test_a_same_login_receipt_claims_nothing(self) -> None:
        # The receipt is public text, deterministic from the issue and the
        # commit, and the login may be the operator's own. Read as proof that
        # a comment is OURS, this retraction is deleted from the reading and
        # the authorization beneath it becomes the last word and publishes on
        # consent that had been withdrawn.
        self._seed(**{
            _state._HELD_RECEIPT: support.PARK_RECEIPT,
            **support.measured_pair(),
        })
        self._reply(support.AUTHORIZE)
        self._reply(
            f"actually, hold off\n\n{support.PARK_RECEIPT}",
            author=self.github._bot_login,
        )

        self.assertTrue(self._holds())

        self.assertNotIn(support.KEY_OVERRIDE_CANDIDATE_SHA, self._pinned())
        self._assert_still_parked()

    def test_an_unsaid_sentence_is_still_owed(self) -> None:
        # A receipt no comment carries is a sentence that never reached the
        # thread, which is the only thing the record can still be holding, so
        # the road that owes it says it.
        self._seed(**{
            _state._HELD_RECEIPT: support.PARK_RECEIPT,
            **support.measured_pair(),
        })

        self.assertTrue(self._holds())

        self.assertEqual(self._said(), 1)
        self.assertIsNone(self._pinned()[_state._HELD_RECEIPT])

    def test_the_record_silences_no_notice(self) -> None:
        # A receipt is a FIELD on the pinned record before it is a sentence on
        # the thread, and a record whose escaped rendering will not fit is
        # written as its own payload -- so the receipt this asks about is in
        # the pinned comment's body verbatim, under our own login. Read there,
        # a notice a dying tick recorded and never said reads as already said,
        # and the human waiting on the park is told nothing at all.
        self._seed(**{
            _state._HELD_RECEIPT: support.PARK_RECEIPT,
            **support.AT_THE_LIMIT,
            **support.measured_pair(),
        })
        pinned = self._pin_the_record()
        self.assertIn(support.PARK_RECEIPT, self._body_of(pinned))

        self.assertTrue(self._holds())

        self.assertEqual(self._said(), 1)
        self.assertIn(support.AUTHORIZE, self.github.posted_comments[0][1])
        self.assertIsNone(self._pinned()[_state._HELD_RECEIPT])

    def test_the_record_silences_no_refusal(self) -> None:
        # The same window on the other sentence this owner words. Silenced,
        # the command is consumed with no answer on the thread at all -- so
        # the operator is left with a park that never says why their command
        # changed nothing.
        answered = self._reply(support.AUTHORIZE_ANOTHER)
        self._seed(**{
            _state._HELD_RECEIPT: support.refusal_receipt(answered),
            **support.AT_THE_LIMIT,
            **support.measured_pair(),
        })
        pinned = self._pin_the_record()
        self.assertIn(support.refusal_receipt(answered), self._body_of(pinned))

        self.assertTrue(self._holds())

        self.assertEqual(self._said(), 1)
        self.assertIn(
            MEASURED_CANDIDATE_SHA, self.github.posted_comments[0][1],
        )
        self._assert_still_parked()

    def test_a_pasted_receipt_silences_no_notice(self) -> None:
        # The author is asked beside the receipt, which is what keeps an
        # outsider from suppressing a sentence a human is owed by pasting a
        # string anybody can read off the thread.
        self._seed(**{
            _state._HELD_RECEIPT: support.PARK_RECEIPT,
            **support.measured_pair(),
        })
        self._reply(
            f"is this it?\n\n{support.PARK_RECEIPT}", author=support.OUTSIDER,
        )

        self.assertTrue(self._holds())

        self.assertEqual(self._said(), 1)

    def _body_of(self, identified: int) -> str:
        """What one comment on this thread actually says."""
        return next(
            seen.body for seen in self.issue.comments if seen.id == identified
        )


if __name__ == "__main__":
    unittest.main()
