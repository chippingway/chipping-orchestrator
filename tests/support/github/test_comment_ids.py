# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The id space every comment this double hands out is numbered in.

One ascending space per client, shared by every thread, by the pinned records
beside them, and by the pull requests those threads belong to, because that is
the space GitHub numbers issue comments in. A double that numbers a thread
from its own comments instead gives two threads the same id and puts a seeded
reply below a record minted after it -- and the orchestrator reads a thread by
comparing ids, so a case written against that double asserts on an ordering
production never has.
"""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import LABEL_IMPLEMENTING

_FIRST_ISSUE = 701
_SECOND_ISSUE = 702
_BODY = "a reply"

# An id a case picked by hand, above anything this client has minted.
_PRELOADED_ID = 5000

_PR_NUMBER = 31
_BRANCH = "orchestrator/issue-701"
_BASE = "main"

# An issue a case builds and never registers, and the first id a fresh client
# hands out -- which is what its hand-numbered comment is given, so an
# allocation blind to that thread repeats it.
_UNREGISTERED_ISSUE = 703
_FIRST_MINTED_ID = 1001


class _IdSpaceCase:
    """Two threads on one client, and every way an id is drawn for them."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issues = [
            make_issue(number, label=LABEL_IMPLEMENTING)
            for number in (_FIRST_ISSUE, _SECOND_ISSUE)
        ]
        for issue in self.issues:
            self.github.add_issue(issue)
            self.github.seed_state(issue.number)

    def _preload(self) -> None:
        """Hand-number one comment above anything the allocator has minted."""
        self.issues[0].comments.append(
            FakeComment(_PRELOADED_ID, _BODY, user=FakeUser("alice")),
        )

    def _seed_reply(self, issue) -> int:
        """Append one reply the way a case seeds a human's, and say which."""
        identified = self.github.next_reply_id(issue)
        issue.comments.append(
            FakeComment(identified, _BODY, user=FakeUser("alice")),
        )
        return identified

    def _minted_comment(self) -> int:
        return self.github.comment(self.issues[1], _BODY).id

    def _minted_seeded_record(self) -> int:
        self.github.seed_state(_SECOND_ISSUE)
        return self.github.read_pinned_state(self.issues[1]).comment_id

    def _minted_fresh_record(self) -> int:
        """The record `write_pinned_state` mints for an issue carrying none."""
        fresh = PinnedState(state_data={})
        self.github.write_pinned_state(self.issues[1], fresh)
        return fresh.comment_id

    def _minted_pr_comment(self) -> int:
        return self.github.pr_comment(_PR_NUMBER, _BODY).id


class CommentIdSpaceTest(_IdSpaceCase, unittest.TestCase):
    """What the double promises about every id it mints."""

    def test_no_two_threads_share_an_id(self) -> None:
        # Interleaved deliberately: a client-wide counter is the only thing
        # that keeps a reply seeded on one thread off an id the other has
        # been given, and a per-thread one collides on the very first pair.
        minted = []
        for _ in range(3):
            for issue in self.issues:
                minted.append(self._seed_reply(issue))
                minted.append(self.github.comment(issue, _BODY).id)

        self.assertEqual(len(set(minted)), len(minted))

    def test_every_id_ascends(self) -> None:
        # Which is what a watermark means: a comment past one is a comment
        # nobody has read, whichever thread or author it came from.
        minted = [
            self._seed_reply(issue)
            for issue in self.issues
            for _ in range(2)
        ]

        self.assertEqual(minted, sorted(minted))

    def test_a_reply_lands_above_its_own_thread(self) -> None:
        # A seeded reply is answering what is already there, so it may never
        # be numbered at or below it -- a reply sharing the watermark's id is
        # one no reader ever sees.
        issue = self.issues[0]
        self.github.comment(issue, _BODY)

        seeded = self._seed_reply(issue)

        self.assertGreater(
            seeded, max(posted.id for posted in issue.comments[:-1]),
        )

    def test_a_record_lands_above_a_seeded_reply(self) -> None:
        # The other direction, and the one a per-thread number breaks: the
        # record is minted from the client's counter, so a reply that never
        # advanced it is handed an id the next record repeats.
        seeded = self._seed_reply(self.issues[0])

        self.assertGreater(self._minted_seeded_record(), seeded)


class CommentIdSourceTest(_IdSpaceCase, unittest.TestCase):
    """Every place this double mints an id, and the one space they share.

    A different claim from the ordering above: not what the space promises,
    but that no source stands outside it. A source drawing from the bare
    counter is monotonic against its own past and against nothing else, so it
    repeats an id a hand-numbered thread already carries.
    """

    def test_every_source_mints_above_the_mark(self) -> None:
        # A case that hand-numbers a thread never went through the allocator,
        # so the mark has to be taken over every thread the client knows -- and
        # a pinned record sharing an id with a comment is a record every
        # reading of that thread hides.
        self._preload()

        for described, minted in (
            ("a posted comment", self._minted_comment()),
            ("a seeded reply", self.github.next_reply_id(self.issues[1])),
            ("a seeded record", self._minted_seeded_record()),
            ("a fresh record", self._minted_fresh_record()),
            ("a pull request comment", self._minted_pr_comment()),
        ):
            with self.subTest(source=described):
                self.assertGreater(minted, _PRELOADED_ID)

    def test_no_source_repeats_another_source_id(self) -> None:
        # The other half of one space: every source draws from it, so no two
        # of them can be handed the same number however they interleave.
        self._preload()

        minted = [
            self._minted_comment(),
            self._minted_seeded_record(),
            self._minted_pr_comment(),
            self._seed_reply(self.issues[0]),
            self._minted_fresh_record(),
        ]

        self.assertEqual(len(set(minted)), len(minted))

    def test_a_record_clears_an_unregistered_thread(self) -> None:
        # A case may seed a record onto an issue it never registered here.
        # Numbered without that thread in view, the record is handed an id the
        # thread already carries -- and `comments_after` hides the pinned
        # comment by id, so the reply the case seeded is one no reading
        # returns.
        github = FakeGitHubClient()
        stranger = make_issue(_UNREGISTERED_ISSUE, label=LABEL_IMPLEMENTING)
        reply = FakeComment(
            _FIRST_MINTED_ID, _BODY, user=FakeUser("alice"),
        )
        stranger.comments.append(reply)

        github.seed_state(stranger)

        recorded = github.read_pinned_state(stranger).comment_id
        self.assertNotEqual(recorded, reply.id)
        self.assertEqual(
            github.comments_after(stranger, None, state_comment_id=recorded),
            [reply],
        )

    def test_a_number_resolves_to_its_thread(self) -> None:
        # The number resolves through the register, which is what every issue
        # this client was given is in, so the older spelling is answered by
        # the same scan.
        self._preload()

        self.github.seed_state(_FIRST_ISSUE)

        self.assertGreater(
            self.github.read_pinned_state(self.issues[0]).comment_id,
            _PRELOADED_ID,
        )

    def test_a_pull_request_comment_moves_the_mark(self) -> None:
        # A pull request's issue comments are numbered in the same space, so
        # one posted there has to push the next id an ISSUE is given past it.
        self.github.open_pr(branch=_BRANCH, base=_BASE, title="t", body="b")
        posted = self._minted_pr_comment()

        self.assertGreater(self._minted_comment(), posted)


if __name__ == "__main__":
    unittest.main()
