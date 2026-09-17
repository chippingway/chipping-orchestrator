# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a process that died inside the publication seam leaves on the record.

The seam records an authorization, takes the park off and consumes the command
DURABLY before this stage gets an answer back, so a rollback that lives only in
the frame that made the call is gone with the process. What the poll after the
crash has to find is the park, its reason and its watermark exactly as the
crash-free run leaves them -- and nothing at all where the seam published, the
one outcome the park is never put back from.

That outcome has a window of its own, and it is why the reading behind the
command is written down rather than applied on the way out: the handoff moves
the label, and everything this stage still holds past that line is on an issue
it never sees again.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    late_rollback as _rollback,
    state as _state,
)
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
    late_consent_crashes as _consent_crashes,
    late_consent_payloads as _consent_payloads,
)

# The client call the seam's own first sentence goes out through, which is the
# earliest moment anything it does is visible from outside the call.
_POST_COMMENT = "comment"

# A tree that is clean when the guard above the seam proves it and carrying
# work no push would publish by the time the seam proves it again: the road
# that makes the seam refuse, and say so, on its own.
_CLEAN_TREE = _WorktreeStatus(readable=True)
_DIRTY_TREE = _WorktreeStatus(readable=True, paths=("src/left_behind.py",))

# A watermark past the command, which is what the seam leaves behind when it
# consumes the reply it was handed and then fails to publish.
_CONSUMED_PAST_THE_COMMAND = 4000

# A reading the ceiling lets through, which is the one road that takes this
# park off without anybody authorizing anything.
_UNDER_THE_CEILING = 12


class _ReadsTheRecordAtEachPost:
    """What the pinned comment held the moment the seam first said anything.

    The ordering both in-flight records rest on, read from inside the one
    window it is about: what this park WAS, and the receipt its first sentence
    goes out under, both have to be durable by the time the seam can say a
    word -- and nothing later can tell.

    The DURABLE record rather than the tick's in-memory copy, because what the
    ordering buys is what a later poll can find: a rollback that lives only in
    the frame that made the call is gone with the process.
    """

    def __init__(self, case) -> None:
        self._case = case
        self._wrapped = case.github.comment
        self.park: list = []
        self.owed: list = []

    def __call__(self, *called, **options):
        saying = self._case._pinned()
        self.park.append(saying.get(_state._HELD_PARK))
        self.owed.append(saying.get(_state._HELD_PUBLICATION))
        return self._wrapped(*called, **options)


class SeamCrashRollbackTest(_consent_case._ParkedCase, unittest.TestCase):
    """A process that dies between the seam's own writes and the rollback.

    The seam records an authorization, takes the park off and consumes the
    command DURABLY before this owner gets an answer back, so a rollback that
    lives only in the frame that made it is gone with the process. What the
    poll after the crash has to find is the park, its reason and its watermark
    exactly as the crash-free run leaves them.
    """

    def test_both_records_go_down_before_the_seam(self) -> None:
        # The window is closed by the ORDER. What the park WAS is on the
        # record before the seam can say a word, which is the only reason a
        # later poll can put it back at all -- and so is the receipt its first
        # sentence goes out under, since the seam can POST the moment it is
        # called and one minted no earlier would leave that sentence with
        # nothing saying it may be owed. Read on the road that makes the seam
        # speak for itself: the tree passes the reading above and is carrying
        # something by the time the seam takes its own.
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE)
        saying = _ReadsTheRecordAtEachPost(self)

        with patch.object(self.github, _POST_COMMENT, saying):
            self._run_tick(tree_states=(_CLEAN_TREE, _DIRTY_TREE))

        self.assertEqual(saying.park, [{
            _state._AWAITING_HUMAN: True,
            _state._PARK_REASON: _command.PARK_UNAUTHORIZED_EXEMPTION,
            _state._LAST_ACTION_COMMENT_ID: _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        }])
        self.assertEqual(len(saying.owed), 1)
        self.assertEqual(len(saying.owed[0]), 1)

    def test_a_crash_past_the_seam_puts_the_park_back(self) -> None:
        # A push that fails after the authorization is recorded: the seam has
        # already cleared the park and consumed the command on the record, and
        # the write that would undo it is the one killed. The next poll is
        # what has to repair it -- and putting the watermark back is what the
        # repair is FOR, since the decision the operator already made has to
        # still be the last fresh word.
        self._crashes_past_the_seam()

        self._run_tick()

        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON],
            _command.PARK_UNAUTHORIZED_EXEMPTION,
        )
        self.assertEqual(
            pinned[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )
        self.assertIsNone(pinned[_state._HELD_PARK])
        self.assertIsNotNone(
            _command._read_the_park(self.github, self.issue, self._state()),
        )

    def test_the_crash_leaves_the_seam_record(self) -> None:
        # The premise, asserted rather than assumed: without the repair the
        # poll after the crash finds an issue nobody is waiting on, over a
        # watermark that has swallowed the command.
        self._crashes_past_the_seam()

        pinned = self._pinned()
        self.assertFalse(pinned[_state._AWAITING_HUMAN])
        self.assertGreater(
            pinned[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )

    def test_a_restore_owing_no_sentence_still_lands(self) -> None:
        # The repair has no write of its own, so the poll that restores a park
        # and finds no sentence to attribute has to persist it anyway. The
        # record a crash leaves is seeded directly here, because what is under
        # test is the poll AFTER one rather than the tick that died.
        self._seed(parked=False, **{
            _state._HELD_PARK: {
                _state._AWAITING_HUMAN: True,
                _state._PARK_REASON:
                    _command.PARK_UNAUTHORIZED_EXEMPTION,
                _state._LAST_ACTION_COMMENT_ID:
                    _consent_payloads.PRIOR_ACTION_COMMENT_ID,
            },
            _state._LAST_ACTION_COMMENT_ID: _CONSUMED_PAST_THE_COMMAND,
            **_consent_payloads.measured_pair(),
        })

        self._run_tick()

        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )
        self.assertIsNone(pinned[_state._HELD_PARK])

    def _crashes_past_the_seam(self) -> None:
        """Record the authorization, fail the push, and lose the rollback."""
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE)
        with (
            patch.object(
                self.github, _consent_payloads.WRITE_PINNED_STATE,
                side_effect=_consent_crashes.DiesRestoringTheHeldPark(self.github),
            ),
            self.assertRaises(_consent_crashes.CrashedTick),
        ):
            self._run_tick(push_branch=False)


class PublishedHandoffCrashTest(_consent_case._ParkedCase, unittest.TestCase):
    """What a crash past the relabel leaves of a handoff that published.

    The one outcome this park is never put back from, and the one window
    nothing later can close: the handoff writes durably and hands the issue to
    `validating`, and everything this stage still held past that line sits on
    an issue it never sees again. So what has to be true of every one of these
    is that the write BEFORE the label already settled it.
    """

    def test_a_published_handoff_is_spent_early(self) -> None:
        # The one way the seam comes back that this park is never put back
        # from: the branch is published and the issue is handed to
        # `validating`. Nothing under that label spends what this stage left
        # in flight and implementing never sees the issue again on this road,
        # so all three fields are settled in the handoff's own durable write
        # ahead of the relabel -- and a process dying past the relabel finds
        # them already spent, with no park for a later re-entry to restore.
        self._crashes_past_the_relabel()

        pinned = self._pinned()
        self.assertIsNone(pinned[_state._HELD_PARK])
        self.assertIsNone(pinned[_state._HELD_PUBLICATION])
        self.assertIsNone(pinned[_state._HELD_COMMAND])
        restored = self._state()
        self.assertFalse(
            _rollback._restores_the_held_park(
                self.github, self.issue, restored,
            ),
        )
        self.assertFalse(restored.get(_state._AWAITING_HUMAN))

    def test_a_small_candidate_spends_its_command(self) -> None:
        # A candidate the ceiling now lets through publishes on its own count
        # and never reads the thread, so the reply that ended the park is
        # still above the watermark when the label moves. Spent on the way out
        # instead of before it, this crash would strand that command on a
        # `validating` issue -- read there as fresh feedback, and paid for
        # with the developer run this whole road exists to avoid.
        commanded = self._crashes_past_the_relabel(
            added_lines=_consent_payloads.SMALL_ADDITIONS,
        )

        # To the command itself, which was the last word on the thread when
        # the reading behind the handoff was taken: consumed short of it the
        # reply strands on a `validating` issue, and past it the boundary
        # swallows replies nothing has read.
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], commanded,
        )

    def test_a_decided_candidate_spends_its_command(self) -> None:
        # The other road past that door. A push that failed after the
        # authorization was recorded leaves the terms standing, so the retry
        # recognizes the commit as decided and pushes it without a reading of
        # its own -- and the command it publishes on is consumed by the same
        # write that moves the label rather than by the one after it.
        self._seed(**_consent_payloads.measured_pair())
        commanded = self._reply(_consent_payloads.AUTHORIZE)
        self._run_tick(push_branch=False)
        # What the failed push said sits above the command, and it is the tip
        # the reading behind this handoff reached -- so that is the boundary
        # the relabel's own write spends, exactly.
        read_to = self._thread_tip()

        self._dies_past_the_relabel()

        self.assertGreater(read_to, commanded)
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], read_to,
        )

    def _crashes_past_the_relabel(self, **run_options) -> int:
        """Publish a parked candidate, and lose every write past the relabel."""
        self._seed(**_consent_payloads.measured_pair())
        commanded = self._reply(_consent_payloads.AUTHORIZE)
        self._dies_past_the_relabel(**run_options)
        return commanded

    def _dies_past_the_relabel(self, **run_options) -> None:
        """Run one tick whose first write past the label move never lands."""
        with (
            patch.object(
                self.github, _consent_payloads.WRITE_PINNED_STATE,
                side_effect=_consent_crashes.DiesPastTheRelabel(self.github),
            ),
            self.assertRaises(_consent_crashes.CrashedTick),
        ):
            self._run_tick(**run_options)


class HeldSeamOutcomeTest(_consent_case._ParkedCase, unittest.TestCase):
    """What a call that published nothing leaves, however it left the record.

    The one fact the rollback reads is whether the write that moves the label
    out of this stage ran, because that write is what spends everything the
    handoff staged. Read off the park flags instead, a seam that cleared them
    without publishing is taken for a publication: the operator's question is
    dropped and their command consumed, and the exemption nobody stands
    behind publishes on the next poll under nobody's authority at all.
    """

    def test_a_cleared_latch_is_not_a_publication(self) -> None:
        # Driven down a road that really leaves that shape: a candidate the
        # ceiling now lets through needs nobody's authorization, so the seam
        # retires this park on its own count and records the commit as owed a
        # push -- and then the push fails, and the label never moves. The
        # flags say an issue nobody is waiting on; the held park says the
        # write that spends it never ran.
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE)

        mocks = self._run_tick(
            added_lines=_UNDER_THE_CEILING, push_branch=False,
        )

        mocks[_consent_payloads.PUSH_BRANCH].assert_called_once()
        self.assertEqual(self.github.label_history, [])
        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON],
            _command.PARK_UNAUTHORIZED_EXEMPTION,
        )
        self.assertEqual(
            pinned[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )
        self.assertIsNone(pinned[_state._HELD_COMMAND])
        self.assertIsNotNone(
            _command._read_the_park(self.github, self.issue, self._state()),
        )

    def test_a_released_park_still_publishes(self) -> None:
        # The road that leaves this park with nothing to trigger it, taken
        # through the real seam and across the restart in the middle. A park
        # still owing its notice re-enters the seam on every poll because the
        # receipt says a sentence is outstanding. A candidate the ceiling now
        # lets through needs nobody's authorization, so the seam takes the
        # park off and the receipt with it -- and then the push fails, and
        # what is put back is a park no receipt, no command and no reading
        # brings the next poll into the seam for.
        #
        # What answers that poll is the APPROVAL. A commit this stage decided
        # to push and has not pushed is a publication owed, dropped by the
        # handoff that spends it, and it says so whatever either road left the
        # flags saying. Read off the park alone, the decided commit sits
        # unpublished for as long as the issue lives, with nobody asked for
        # anything and nothing left to ask.
        self._seed(**{
            _state._HELD_RECEIPT: _consent_payloads.PARK_RECEIPT,
            **_consent_payloads.measured_pair(),
        })
        self._run_tick(added_lines=_UNDER_THE_CEILING, push_branch=False)

        mocks = self._run_tick(added_lines=_UNDER_THE_CEILING)

        self._assert_published(mocks)
        pinned = self._pinned()
        self.assertFalse(pinned[_state._AWAITING_HUMAN])
        self.assertIsNone(pinned[_state._PARK_REASON])
        # Nobody was ever asked anything on this road, so the watermark is
        # still where the poll before it left the thread read to.
        self.assertEqual(
            pinned[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )


if __name__ == "__main__":
    unittest.main()
