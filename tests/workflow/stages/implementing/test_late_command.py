# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which reply on a standing authorization park a tick should act on.

A reading and nothing else: no record is written here and nothing is decided,
so what these pin down is which comment the road behind it is handed, how far
the thread was looked at, and every author and shape that is never in the
reading at all.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    state as _state,
)
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA
from tests.workflow.stages.implementing import (
    late_consent_test_support as support,
)


class ReadTheParkTest(support._ParkedCase, unittest.TestCase):
    """The command a human has written on this park, or nothing."""

    def test_the_command_carries_what_it_names(self) -> None:
        identified = self._reply(support.AUTHORIZE)

        answer = self._read()

        self.assertEqual(answer.named, MEASURED_CANDIDATE_SHA)
        self.assertEqual(answer.comment_id, identified)

    def test_a_thread_with_nothing_new_reads_nothing(self) -> None:
        # A human who has not replied yet, which is every poll of a standing
        # park until one does.
        self.assertIsNone(self._read())

    def test_an_abbreviation_carries_nothing(self) -> None:
        # A command nobody could act on is still a gesture this park owes an
        # answer to. The empty id can never equal a candidate, so it takes the
        # refusal road by itself rather than earning a silent park.
        identified = self._reply(support.AUTHORIZE_ABBREVIATED)

        answer = self._read()

        self.assertEqual(answer.named, "")
        self.assertEqual(answer.comment_id, identified)

    def test_the_last_fresh_reply_decides(self) -> None:
        # Guidance written after a command outranks it, and a command written
        # after guidance is the decision that replaced it. Read as a set, one
        # stale reply would refuse every command posted behind it for as long
        # as the park stood.
        self._reply(support.AUTHORIZE_ANOTHER)
        self._reply(support.GUIDANCE)
        decided = self._reply(support.AUTHORIZE)

        answer = self._read()

        self.assertEqual(answer.comment_id, decided)

    def test_a_quoted_record_hides_no_reply(self) -> None:
        # The pinned comment is named by its ID, so a reply that merely quotes
        # its marker stays in the reading. Found by the marker instead, that
        # reply would read as the record itself and vanish -- and the stale
        # authorization beneath it would become the last word and publish on
        # consent that had been withdrawn.
        self._reply(support.AUTHORIZE)
        self._reply(support.QUOTES_THE_RECORD)

        self.assertIsNone(self._read())

    def test_the_watermark_is_what_was_looked_at(self) -> None:
        # Every comment the fetch returned counts, filtered-out ones included:
        # what a watermark records is what has been LOOKED at, and an
        # outsider's reply that never reaches the next poll as unread is the
        # whole point of recording one.
        acted = self._reply(support.AUTHORIZE)
        seen = self._reply(support.GUIDANCE, author=support.OUTSIDER)

        with patch.object(
            config, support.ALLOWLIST_CONFIG, (support.TRUSTED_AUTHOR,),
        ):
            answer = self._read()

        self.assertEqual(answer.comment_id, acted)
        self.assertEqual(answer.watermark, seen)

    def _read(self):
        return _command._read_the_park(self.github, self.issue, self._state())


class UnreadReplyTest(support._ParkedCase, unittest.TestCase):
    """Every reply this reading is never handed, and why each is left."""

    def test_another_park_is_not_this_ones_to_end(self) -> None:
        # Both halves of the park say who is waiting behind which question,
        # and a command written under either of the others is not an answer
        # to this one.
        for described, seeded in (
            ("another reason", {_state._PARK_REASON: "late_measurement_failed"}),
            ("nobody waiting", {_state._AWAITING_HUMAN: False}),
        ):
            with self.subTest(park=described):
                self.setUp()
                self._seed(**seeded)
                self._reply(support.AUTHORIZE)

                self.assertIsNone(self._read())

    def test_guidance_is_not_this_parks_to_read(self) -> None:
        # A last word that is not the whole command belongs to the ordinary
        # resume that feeds it to the developer rather than to a bypass taken
        # behind their back.
        for described, written in (
            ("prose", support.GUIDANCE),
            ("the command inside a paragraph", f"sure: {support.AUTHORIZE}"),
            ("a bare continue", "/orchestrator continue"),
        ):
            with self.subTest(reply=described):
                self.setUp()
                self._reply(written)

                self.assertIsNone(self._read())

    def test_an_outsider_authorizes_nothing(self) -> None:
        # The allowlist's rule applied where the thread is read: an outsider's
        # comment is not in the reading, so nothing they post can authorize
        # anything or move a watermark past somebody who may.
        self._reply(support.AUTHORIZE, author=support.OUTSIDER)

        with patch.object(
            config, support.ALLOWLIST_CONFIG, (support.TRUSTED_AUTHOR,),
        ):
            self.assertIsNone(self._read())

    def test_guidance_written_last_reads_nothing(self) -> None:
        # The same batch the other way round: the safe reading of somebody who
        # asked to publish and then asked for a change publishes nothing.
        self._reply(support.AUTHORIZE)
        self._reply(support.GUIDANCE)

        self.assertIsNone(self._read())

    def _read(self):
        return _command._read_the_park(self.github, self.issue, self._state())


class OrchestratorAuthorshipTest(support._ParkedCase, unittest.TestCase):
    """What it takes to prove a reply was this process's own, and why.

    Dropping a comment here is the same act as deleting what its author said:
    the reading takes the LAST fresh reply, so one removed lets the reply
    beneath it stand as the last word. Over-filter and a retraction becomes an
    authorization; under-filter and a sentence of ours masks a command. Only
    the first of those publishes something nobody agreed to.
    """

    def test_a_pasted_marker_hides_no_retraction(self) -> None:
        # The marker is plain text on a public thread and anybody may paste
        # it, deliberately or by quoting a comment of ours that carries one.
        # Taken as proof, a trusted operator's retraction would be dropped,
        # the authorization under it would become the last word, and the
        # candidate would publish on consent that had been withdrawn.
        self._reply(support.AUTHORIZE)
        self._reply(
            f"actually, hold off\n\n{_comments._ORCH_COMMENT_MARKER}",
        )

        with patch.object(
            config, support.ALLOWLIST_CONFIG, (support.TRUSTED_AUTHOR,),
        ):
            self.assertIsNone(self._read())

    def test_a_shared_login_hides_no_retraction(self) -> None:
        # The token this orchestrator posts under belongs to a human, and this
        # repository says so where the id ledger is defined. A reviewer who
        # shares that account matches the bot login exactly, so a retraction
        # they wrote under a quoted marker would read as the orchestrator
        # talking to itself -- and the reviewer whose consent this park exists
        # to collect is precisely the one that hazard silences.
        self._reply(support.AUTHORIZE, author=self.github._bot_login)
        self._reply(
            f"actually, hold off\n\n{_comments._ORCH_COMMENT_MARKER}",
            author=self.github._bot_login,
        )

        self.assertIsNone(self._read())

    def test_our_own_comment_does_not_mask_a_command(self) -> None:
        # The other direction, and the reason this filter exists: a sentence
        # of ours standing last would leave the command beneath it unread and
        # the park standing over a decision an operator had already made.
        acted = self._reply(support.AUTHORIZE)
        self._we_reply("this issue is waiting on a human")

        self.assertEqual(self._read().comment_id, acted)

    def test_an_unrecorded_comment_is_not_ours(self) -> None:
        # What failing closed costs, stated so nobody trades it back: a
        # comment of ours the ledger cannot vouch for -- an id evicted past
        # its bound -- stays in the reading, and being no command it leaves
        # the park standing rather than letting the reply beneath it publish.
        self._reply(support.AUTHORIZE)
        self.issue.comments.append(FakeComment(
            self.github.next_reply_id(self.issue),
            f"an older notice\n\n{_comments._ORCH_COMMENT_MARKER}",
            user=FakeUser(self.github._bot_login),
        ))

        self.assertIsNone(self._read())

    def _we_reply(self, body: str) -> int:
        """Post one comment the way this workflow posts every one of them.

        Through the owner that writes them, so the comment is ours by the one
        piece of evidence a commenter cannot forge -- the id ledger -- rather
        than by a body a test spelled to look right.
        """
        state = self._state()
        posted = _comments._post_issue_comment(
            self.github, self.issue, state, body,
        )
        self.github.write_pinned_state(self.issue, state)
        return posted.id

    _read = ReadTheParkTest._read


if __name__ == "__main__":
    unittest.main()
