# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which comments on this park's thread are the orchestrator's own words.

Every road here posts before anything records having posted it, and a sentence
nothing can attribute is read as somebody's word: it becomes the last reply,
the park's reading hands the tick back, and the ordinary resume spawns a
developer against our own prose and consumes whatever a human wrote under it.

Two records answer that. The id goes down the instant each post returns. The
receipt covers the one API call in between, and what it commits to is the
SENTENCE -- the secret and the exact body it went out on -- so a reply quoting
that sentence answers nothing, carrying its author's words beside ours.
"""

from __future__ import annotations

import secrets
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.implementing import (
    late_authorship as _authorship,
    late_command as _command,
    state as _state,
)
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
    late_consent_crashes as _consent_crashes,
    late_consent_payloads as _consent_payloads,
)

_CLEAN_TREE = _WorktreeStatus(readable=True)
_DIRTY_TREE = _WorktreeStatus(readable=True, paths=("src/left_behind.py",))

# A checkout that passes every reading up to the push and is dirty by the time
# the handoff proves it again, which is the road the seam says two things on.
_DIRTIED_AFTER_THE_PUSH = (
    _CLEAN_TREE, _CLEAN_TREE, _CLEAN_TREE, _DIRTY_TREE, _DIRTY_TREE,
)

# The sentence a command naming another commit earns, as the tick that died
# before recording it left it on the thread.
_REFUSAL = "that names another commit"

# A human taking their authorization back, quoting the comment they answer the
# way a thread does -- their words beside ours, from the token we share.
_RETRACTION = "actually, hold off -- re:\n\n> {quoted}"

# What a human turns a comment of theirs into once they have changed their
# mind, which is the moment anything reading it as ours has to stop.
_TAKES_IT_BACK = "hold off -- I take that back"

# What somebody appends to a comment, which is enough to make it no longer
# the sentence the record committed to.
_ONE_MORE_THING = " and one more thing"

# A checkout no reading finds, which holds this park short of publishing
# without saying anything or consuming a reply.
_MISSING_WORKTREE = Path("/tmp/orchestrator-test-late-authorship-gone")


class _SaidCase(_consent_case._ParkedCase):
    """One park, and the sentences a handoff into the seam says on it."""

    def _attributed(self) -> list:
        """Every comment id this issue's record claims the orchestrator wrote."""
        return self._pinned().get(_consent_payloads.ORCHESTRATOR_IDS) or []

    def _strands(self, body: str = _REFUSAL) -> int:
        """Say one thing the way the seam does, and lose the write past it.

        The client's own order -- commit to the finished sentence, then post
        it -- with its third step, the write that records the id, simply not
        taken. What that leaves is what a process dying in that one call
        leaves.
        """
        secret = secrets.token_hex(_authorship._PROOF_BYTES)
        said = "{body}\n\n{receipt}".format(
            body=body,
            receipt=_authorship._PUBLICATION_RECEIPT.format(
                issue=_consent_payloads.ISSUE_NUMBER, proof=secret,
            ),
        )
        committed = self._state()
        committed.set(
            _state._HELD_PUBLICATION, [_authorship._commits_to(secret, said)],
        )
        self.github.write_pinned_state(self.issue, committed)
        return self.github.comment(self.issue, said).id

    def _comment(self, comment_id: int):
        """One comment on this thread, as a reading of it would find it."""
        return next(
            seen for seen in self.issue.comments if seen.id == comment_id
        )

    def _replays(self, said: int, quoting: bool = False) -> int:
        """Say one of our sentences back, from the token this park shares.

        Verbatim by default, which is what a copy is; `quoting` wraps it the
        way a thread does when somebody answers it, so the body carries their
        words as well as ours.
        """
        copied = self._comment(said).body
        return self._reply(
            _RETRACTION.format(quoted=copied) if quoting else copied,
            author=self.github._bot_login,
        )

    def _edits(self, comment_id: int, into: str) -> None:
        """Rewrite one comment the way its author can."""
        edited = next(
            seen for seen in self.issue.comments if seen.id == comment_id
        )
        edited.body = into

    def _assert_published_nothing(self, *ticks) -> None:
        """No push and no handoff, whatever else these ticks decided.

        The whole of what a retraction has to buy: a reply that is not the
        command is guidance and the developer IS resumed against it, so what
        distinguishes consent withdrawn from consent acted on is the branch
        this issue does not have.
        """
        for mocks in ticks:
            mocks[_consent_payloads.PUSH_BRANCH].assert_not_called()
        self.assertEqual(self.github.label_history, [])

    def _deletes(self, comment_id: int) -> None:
        """Take one comment off the thread, the way its author can."""
        self.issue.comments = [
            seen for seen in self.issue.comments if seen.id != comment_id
        ]


class SeamRecordsWhatItSaysTest(_SaidCase, unittest.TestCase):
    """The ordinary road, where nothing is ever stranded to recover.

    The client the handoff hands the seam records each id the moment GitHub
    gives it back, so a sentence of ours is attributable from the instant it
    exists rather than from whenever the seam happens to return.
    """

    def test_one_sentence_is_recorded_once(self) -> None:
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE)

        self._run_tick(tree_states=(_CLEAN_TREE, _DIRTY_TREE))

        self.assertEqual(self._attributed(), self._sentences())

    def test_a_pair_is_recorded_once_each(self) -> None:
        # The seam says a pull request opened and then a refusal over a
        # checkout that went dirty under the push. Each id is recorded by the
        # client and again by the owner that posts every comment in this
        # workflow, and the ledger is a bounded list: a second entry buys
        # nothing and costs a slot, so older notices of ours would fall out of
        # it sooner and reach a developer as somebody's guidance.
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE)

        self._run_tick(tree_states=_DIRTIED_AFTER_THE_PUSH)

        said = self._sentences()
        self.assertEqual(len(said), 2)
        self.assertEqual(self._attributed(), said)

    def test_nothing_is_left_outstanding(self) -> None:
        # The receipt covers one API call and is dropped by the write that
        # ends it, so a run that finished owes the record nothing.
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE)

        self._run_tick(tree_states=(_CLEAN_TREE, _DIRTY_TREE))

        self.assertIsNone(self._pinned()[_state._HELD_PUBLICATION])

    def test_a_recorded_id_is_never_doubled(self) -> None:
        # The ledger is a set kept in a bounded list, and the roads that write
        # it layer: a comment posted through the seam's client and then
        # through the owner that posts every one of them is recorded twice
        # unless recording is idempotent.
        self._seed(**_consent_payloads.measured_pair())
        state = self._state()
        _comments._track_orchestrator_comment(state, _consent_payloads.ISSUE_NUMBER)
        _comments._track_orchestrator_comment(state, _consent_payloads.ISSUE_NUMBER)

        self.assertEqual(
            state.get(_consent_payloads.ORCHESTRATOR_IDS), [_consent_payloads.ISSUE_NUMBER],
        )

    def _sentences(self) -> list:
        """Every comment on this thread that went out as one of ours."""
        return [
            seen.id for seen in self.issue.comments
            if _authorship._PROOF_ON_A_COMMENT.search(seen.body or "")
        ]


class LostWriteLedgerRepairTest(_SaidCase, unittest.TestCase):
    """The one API call between a post and the write recording it.

    A sentence stranded there has nothing on the record naming it, so every
    reader would treat it as somebody's word: it becomes the last reply, the
    park's reading hands the tick back, and the resume spawns a developer
    against our own prose and consumes whatever a human wrote under it. The
    repair runs ahead of all of that and puts the comment in the ledger every
    one of those readers already asks.
    """

    def test_a_stranded_sentence_is_ledgered(self) -> None:
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE_ANOTHER)
        said = self._strands()

        mocks = self._run_tick()

        self.assertEqual(self._attributed(), [said])
        self.assertIsNone(self._pinned()[_state._HELD_PUBLICATION])
        mocks[_consent_payloads.RUN_AGENT].assert_not_called()

    def test_the_repair_moves_no_watermark(self) -> None:
        # A watermark moved to our sentence crosses everything under it, so an
        # operator who read the notice and wrote the corrected command before
        # this poll ran would have it consumed unread and never acted on.
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE_ANOTHER)
        self._reply(_consent_payloads.AUTHORIZE)
        self._strands()

        self._run_tick()

        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )

    def test_the_next_poll_acts_on_the_correction(self) -> None:
        # What repairing the ledger is for, across a restart: our own prose is
        # out of the reading, so the operator's corrected command is the last
        # fresh word again and the poll after the repair publishes on it.
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE_ANOTHER)
        corrected = self._reply(_consent_payloads.AUTHORIZE)
        self._strands()
        self._run_tick()

        mocks = self._run_tick()

        mocks[_consent_payloads.PUSH_BRANCH].assert_called_once()
        mocks[_consent_payloads.RUN_AGENT].assert_not_called()
        self.assertEqual(
            self._pinned()[_consent_payloads.KEY_OVERRIDE_COMMENT_ID], corrected,
        )

    def test_only_the_earliest_answer_is_ledgered(self) -> None:
        # A copy can only follow what it copies, so where the thread carries
        # two comments saying our sentence, ours is the earlier. Claiming the
        # later one as well would be claiming a comment we did not post.
        self._seed(**_consent_payloads.measured_pair())
        said = self._strands()
        copied = self._replays(said)

        self._run_tick()

        self.assertEqual(self._attributed(), [said])
        self.assertNotIn(copied, self._attributed())

    def test_a_receipt_nothing_answers_ledgers_nobody(self) -> None:
        # A tick that died BEFORE its post leaves a receipt over a thread
        # nothing of ours ever reached. Nothing is claimed, and the receipt
        # goes: no road here re-says a sentence the seam worded, so keeping it
        # would buy a thread read a poll forever and say nothing new.
        self._seed(**{
            _state._HELD_PUBLICATION: [
                _authorship._commits_to(
                    secrets.token_hex(_authorship._PROOF_BYTES), _REFUSAL,
                ),
            ],
            **_consent_payloads.measured_pair(),
        })
        spoken = self._reply(_consent_payloads.GUIDANCE)

        self._run_tick()
        self.assertIsNone(self._pinned()[_state._HELD_PUBLICATION])

        mocks = self._run_tick()

        self.assertNotIn(spoken, self._attributed())
        mocks[_consent_payloads.RUN_AGENT].assert_called_once()
        self.assertGreaterEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], spoken,
        )


class RestartedParkNoticeTest(_SaidCase, unittest.TestCase):
    """The park's own notice, said and never recorded, over several polls.

    The window is one API call, but what follows it is a sequence: the poll
    that repairs the ledger, the poll that puts the park back, and the poll
    that answers what the record still says the thread is owed. What has to
    hold across all of them is that the orchestrator's own notice is never the
    reply a developer is resumed against, and that no watermark crosses it.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**{
            _state._HELD_RECEIPT: _consent_payloads.PARK_RECEIPT,
            **_consent_payloads.measured_pair(),
        })
        self._crash_saying_the_notice()

    def test_no_poll_answers_the_notice(self) -> None:
        # Nobody is resumed against it and nothing is published on it, and no
        # watermark crosses it either -- a resume consumes our own prose, and
        # everything a human wrote under it, on the way to paying for a run.
        polls = [self._run_tick() for _ in range(3)]

        for mocks in polls:
            mocks[_consent_payloads.RUN_AGENT].assert_not_called()
            mocks[_consent_payloads.PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )

    def test_the_notice_is_ledgered_once(self) -> None:
        # What every poll of it rests on, asserted where it is decided rather
        # than only through what it prevents. Once, because the ledger is a
        # set kept in a bounded list and a second entry costs a slot.
        said = self.github.latest_comment_id(self.issue)

        for _ in range(3):
            self._run_tick()

            self.assertEqual(self._attributed(), [said])

    def test_the_notice_is_never_said_twice(self) -> None:
        # The other half of recording it: the thread already carries the
        # sentence a human is waiting on, so no poll mentions them again.
        for _ in range(3):
            self._run_tick()

        self.assertEqual(len(self._sentences()), 1)

    def test_repeated_windows_lose_no_notice(self) -> None:
        # The repair is per-poll, so nothing queues up waiting for it and no
        # bound on the record can evict a sentence still standing above the
        # watermark. Every notice this issue ever stranded is in the ledger,
        # and none of them ever reaches a developer.
        for _ in range(8):
            self._owes_the_notice_again()
            self._crash_saying_the_notice()
            mocks = self._run_tick()
            mocks[_consent_payloads.RUN_AGENT].assert_not_called()

        self.assertEqual(self._attributed(), self._sentences())
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID],
            _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )

    def _owes_the_notice_again(self) -> None:
        """Put this park back where it owes its own notice, ledger and all.

        The record is edited rather than re-seeded, because what the case is
        about is a ledger that GROWS across windows: seeding one afresh would
        throw away every sentence the polls before it recorded.
        """
        owing = self._state()
        owing.set(_state._HELD_RECEIPT, _consent_payloads.PARK_RECEIPT)
        owing.set(
            _state._LAST_ACTION_COMMENT_ID, _consent_payloads.PRIOR_ACTION_COMMENT_ID,
        )
        owing.set(_state._AWAITING_HUMAN, True)
        owing.set(
            _state._PARK_REASON, _command.PARK_UNAUTHORIZED_EXEMPTION,
        )
        self.github.write_pinned_state(self.issue, owing)

    def _crash_saying_the_notice(self) -> None:
        """Post the park's own notice and lose the write that records its id.

        Through the seam, which is where every sentence on this park is
        worded, and killed at the write the client makes the instant the post
        returns -- the one API call this whole road is about.
        """
        with (
            patch.object(
                self.github, _consent_payloads.WRITE_PINNED_STATE,
                side_effect=_consent_crashes.DiesPastTheNotice(self.github),
            ),
            self.assertRaises(_consent_crashes.CrashedTick),
        ):
            self._run_tick()

    _sentences = SeamRecordsWhatItSaysTest._sentences


class SentenceBoundReceiptTest(_SaidCase, unittest.TestCase):
    """What may answer a receipt, and everything that looks like it and cannot.

    The receipt commits to the sentence rather than the sender, which is the
    only claim that survives the secret being disclosed. Posting our sentence
    discloses it, so a reply quoting that sentence carries it too -- and the
    login beside both is a token this repository says may be shared with the
    human whose consent this park collects.
    """

    def test_a_quote_of_our_sentence_answers_nothing(self) -> None:
        # Their reply carries our secret and their own words, and the digest
        # is of ours alone. Recognized, it would be passed over by every later
        # reading, the older authorization beneath it would become the last
        # word, and the branch would publish on consent withdrawn. That holds
        # whether or not our own sentence is still there to be the earlier of
        # the two: ordering is not what this rests on.
        for described, gone in (("standing", False), ("deleted", True)):
            with self.subTest(ours=described):
                self.setUp()
                self._seed(**_consent_payloads.measured_pair())
                self._reply(_consent_payloads.AUTHORIZE)
                retracted = self._answered_and_maybe_deleted(gone)

                self._assert_published_nothing(
                    self._run_tick(), self._run_tick(),
                )
                self.assertNotIn(retracted, self._attributed())

    def test_a_replay_after_ours_is_never_the_one(self) -> None:
        # A copy of our sentence answers the receipt as ours does, so what
        # keeps it out of the ledger is order: a copy can only follow what it
        # copies. Their comment stays a human's word, and their edit of it
        # into a retraction is read as one.
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.AUTHORIZE)
        said = self._strands()
        copied = self._replays(said)
        self._run_tick()
        self._edits(copied, into=_TAKES_IT_BACK)

        mocks = self._run_tick()

        self.assertNotIn(copied, self._attributed())
        mocks[_consent_payloads.PUSH_BRANCH].assert_not_called()
        self.assertEqual(self.github.label_history, [])

    def test_an_edited_sentence_answers_nothing(self) -> None:
        # A body changed after we said it is no longer the sentence the record
        # committed to -- ours or anybody's -- so nothing is claimed, which
        # costs a resume against our own words rather than a retraction.
        self._seed(**_consent_payloads.measured_pair())
        said = self._strands()
        self._edits(said, into=self._comment(said).body + _ONE_MORE_THING)

        self._run_tick()

        self.assertNotIn(said, self._attributed())

    def test_the_recorded_digest_answers_nothing(self) -> None:
        # The record is a comment on the issue, so everything it holds is
        # public the moment it is written. A human who reads the digest off
        # the pinned comment and writes it into a retraction -- bare, or
        # wrapped in the receipt syntax this stage stamps -- has written the
        # one string the record names, and every candidate is HASHED before it
        # is compared, so the digest of a digest is not the digest.
        digest = _authorship._commits_to(
            secrets.token_hex(_authorship._PROOF_BYTES), _REFUSAL,
        )
        self._seed(**{
            _state._HELD_PUBLICATION: [digest], **_consent_payloads.measured_pair(),
        })
        self._reply(_consent_payloads.AUTHORIZE)
        for described, written in (
            ("the digest itself", digest),
            ("the digest in our own receipt", _authorship._PUBLICATION_RECEIPT.format(
                issue=_consent_payloads.ISSUE_NUMBER, proof=digest,
            )),
        ):
            with self.subTest(quoted=described):
                retracted = self._reply(
                    _RETRACTION.format(quoted=written),
                    author=self.github._bot_login,
                )

                self._run_tick()

                self.assertNotIn(retracted, self._attributed())

    def test_the_pinned_record_is_never_a_carrier(self) -> None:
        # A receipt is a FIELD on that record before it is a sentence on a
        # thread, and a record whose escaped rendering would not fit is
        # written as its own payload -- so on those issues it sits verbatim in
        # the pinned comment, under our own login and below almost everything
        # else. The record is dropped from the reading rather than answered.
        self._seed(**{
            _state._HELD_RECEIPT: _consent_payloads.PARK_RECEIPT,
            **_consent_payloads.AT_THE_LIMIT,
            **_consent_payloads.measured_pair(),
        })
        recorded = self._pin_the_record()

        self._run_tick()

        self.assertNotIn(recorded, self._attributed())


    def _answered_and_maybe_deleted(self, gone: bool) -> int:
        """Strand a sentence, have it quoted back, and say which reply that is."""
        said = self._strands()
        retracted = self._replays(said, quoting=True)
        if gone:
            self._deletes(said)
        return retracted


if __name__ == "__main__":
    unittest.main()
