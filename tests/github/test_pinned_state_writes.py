# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the adapter leaves on a thread, and where it takes the watermark from.

`read_pinned_state` decides which comment on an issue IS the record; these two
decide what GitHub ends up holding and how far a tick claims to have read. Both
are driven here over the real client and the PyGithub-shaped issue and comment
doubles, so the requests under test are the ones production makes: a record is
posted with `create_comment`, rewritten with the comment's own `edit`, and
found again by walking the thread.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from tests.github.pinned_state_test_support import (
    BOT,
    bot_comment,
    marker,
    state_client,
)
from tests.support.fakes import FakeComment, FakeIssue, FakeUser, make_issue

_ISSUE = 5
_BRANCH_KEY = "branch"
_ROUND_KEY = "review_round"
_BRANCH = "orchestrator/chippingway__orchestrator/issue-5"
_ATTACKER_BRANCH = "orchestrator/evil"

# The id the record already on a thread carries, a human's reply below it, and
# a comment above both. Hand-picked under the floor the doubles mint from, so
# anything the adapter posts is recognizable by sitting above all three.
_RECORDED_ID = 200
_REPLY_ID = 7
_HIGHEST_ID = 341

_REPLY = "a human answering the park notice"

# What one record is written as, spelled out rather than rendered from the
# owner's own template: the marker GitHub hides the comment behind, the payload
# with its keys sorted, and the terminator. Live issues carry exactly this
# text, so it is the compatibility contract rather than a rendering detail.
_RECORD_BODY = (
    '<!--orchestrator-state {"branch": '
    '"orchestrator/chippingway__orchestrator/issue-5"}-->'
)
_REWRITTEN_BODY = (
    '<!--orchestrator-state {"branch": '
    '"orchestrator/chippingway__orchestrator/issue-5", "review_round": 2}-->'
)

_RECORD = MappingProxyType({_BRANCH_KEY: _BRANCH})
_REWRITTEN = MappingProxyType({_BRANCH_KEY: _BRANCH, _ROUND_KEY: 2})


def _issue(*comments: FakeComment) -> FakeIssue:
    """One thread the adapter writes onto as the account it reads back as.

    GitHub attributes what `create_comment` posts to whoever the token belongs
    to, and the pinned read authenticates a record against exactly that login,
    so the writer and the trusted author are one account here for the same
    reason they are one in production.
    """
    issue = make_issue(_ISSUE, comments=list(comments))
    issue.commenter = FakeUser(BOT)
    return issue


def _human_reply(comment_id: int = _REPLY_ID) -> FakeComment:
    """One comment on the thread that is not the record and never becomes it."""
    return FakeComment(id=comment_id, body=_REPLY, user=FakeUser("alice"))


class WritePinnedStateTest(unittest.TestCase):
    """Which of three things the write does, and what the thread decides it by.

    An issue carrying no record gets one; an issue whose record the state names
    gets that comment rewritten; an issue whose named record GitHub no longer
    has gets a replacement. The middle case is the one nearly every tick spends
    and the one a mistake hides in longest -- a write that posted where it
    should have edited would leave a second record per tick, each of them a
    comment some later read is free to pick up instead of the live one.
    """

    def setUp(self) -> None:
        self.client = state_client()

    def test_a_first_record_is_created_and_named(self) -> None:
        # An issue a human labelled by hand: the state carries no comment id,
        # so there is nothing to rewrite and the record is posted. The id
        # GitHub answers with goes back onto the state, which is the only
        # thing that keeps the NEXT tick from posting a second one.
        issue = _issue(_human_reply())
        state = PinnedState(data=dict(_RECORD))

        written = self.client.write_pinned_state(issue, state)

        self.assertIs(written, state)
        self.assertEqual(len(issue.comments), 2)
        posted = issue.comments[-1]
        self.assertEqual(state.comment_id, posted.id)
        self.assertGreater(posted.id, _REPLY_ID)
        self.assertEqual(posted.body, _RECORD_BODY)
        self.assertEqual(posted.user.login, BOT)

    def test_a_named_record_is_rewritten_in_place(self) -> None:
        # The steady case. The comment the state names is edited, so the
        # thread is left with the same comments it had and the record keeps
        # the id every reader and watermark already has.
        record = bot_comment(_RECORDED_ID, _RECORD_BODY)
        reply = _human_reply()
        issue = _issue(reply, record)
        state = PinnedState(comment_id=_RECORDED_ID, data=dict(_REWRITTEN))

        self.client.write_pinned_state(issue, state)

        self.assertEqual(
            [comment.id for comment in issue.comments],
            [_REPLY_ID, _RECORDED_ID],
        )
        self.assertEqual(record.body, _REWRITTEN_BODY)
        self.assertEqual(reply.body, _REPLY)
        self.assertEqual(state.comment_id, _RECORDED_ID)

    def test_a_vanished_record_is_replaced(self) -> None:
        # A maintainer deleted the pinned comment. The id the state carries
        # names nothing on the thread, and a write that edited by id alone
        # would raise against GitHub and strand the issue: the record is
        # posted again and the state re-pointed at what came back.
        issue = _issue(_human_reply())
        state = PinnedState(comment_id=_RECORDED_ID, data=dict(_RECORD))

        self.client.write_pinned_state(issue, state)

        self.assertEqual(len(issue.comments), 2)
        posted = issue.comments[-1]
        self.assertNotEqual(state.comment_id, _RECORDED_ID)
        self.assertEqual(state.comment_id, posted.id)
        self.assertEqual(posted.body, _RECORD_BODY)

    def test_a_written_record_reads_back(self) -> None:
        # The round trip the whole surface exists for, over both writes: what
        # the adapter renders is what its own parser accepts as state, and the
        # payload survives the edit rather than the create alone. Read back off
        # a thread carrying ordinary conversation too, which is the only shape
        # a live issue ever has.
        issue = _issue(_human_reply())
        state = PinnedState(data=dict(_RECORD))

        self.client.write_pinned_state(issue, state)
        created = self.client.read_pinned_state(issue)
        self.client.write_pinned_state(issue, PinnedState(
            comment_id=state.comment_id, data=dict(_REWRITTEN),
        ))
        edited = self.client.read_pinned_state(issue)

        self.assertEqual(created.comment_id, state.comment_id)
        self.assertEqual(created.data, _RECORD)
        self.assertEqual(edited.comment_id, state.comment_id)
        self.assertEqual(edited.data, _REWRITTEN)
        self.assertTrue(edited.parsed)

    def test_a_forged_record_is_not_the_one_written(self) -> None:
        # A third party got the marker onto the thread before the orchestrator
        # ever recorded anything, which is the window a manually labelled issue
        # sits in. The write posts its own record, and the read that follows
        # has to come back with THAT comment: adopting the forgery would hand
        # the next tick somebody else's branch out of its own durable state.
        forged = FakeComment(
            id=1,
            body=marker({_BRANCH_KEY: _ATTACKER_BRANCH}),
            user=FakeUser("mallory"),
        )
        issue = _issue(forged)
        state = PinnedState(data=dict(_RECORD))

        self.client.write_pinned_state(issue, state)
        read = self.client.read_pinned_state(issue)

        self.assertEqual(read.comment_id, state.comment_id)
        self.assertEqual(read.get(_BRANCH_KEY), _BRANCH)


class LatestCommentIdTest(unittest.TestCase):
    """The mark a tick records for "everything up to here has been read".

    The LARGEST id the thread carries, rather than the one the walk happens to
    finish on -- the same answer only while every comment arrives in ascending
    order. Read off the last one instead, a thread served any other way leaves
    the mark below comments already on the issue, and each of them comes back
    as unanswered conversation on the next tick.
    """

    def setUp(self) -> None:
        self.client = state_client()

    def test_an_empty_thread_has_no_mark(self) -> None:
        # Nothing has been said, so there is nothing to have read. Reported as
        # an absence rather than as a zero, which a comparison would spend as
        # an id every comment already sits above.
        self.assertIsNone(self.client.latest_comment_id(_issue()))

    def test_the_largest_id_is_the_mark(self) -> None:
        for described, order in (
            ("oldest first", (_REPLY_ID, _RECORDED_ID, _HIGHEST_ID)),
            ("newest first", (_HIGHEST_ID, _RECORDED_ID, _REPLY_ID)),
            ("unordered", (_RECORDED_ID, _HIGHEST_ID, _REPLY_ID)),
        ):
            with self.subTest(order=described):
                issue = _issue(*(
                    _human_reply(comment_id) for comment_id in order
                ))

                self.assertEqual(
                    self.client.latest_comment_id(issue), _HIGHEST_ID,
                )

    def test_the_record_counts_toward_the_mark(self) -> None:
        # `comments_after` hides the pinned record and this counts it, and the
        # difference is deliberate: the mark has to sit above every id GitHub
        # has handed out on the thread, so a comment minted after it is
        # unambiguously one nobody has read.
        issue = _issue(_human_reply())
        state = PinnedState(data=dict(_RECORD))

        self.client.write_pinned_state(issue, state)

        self.assertEqual(
            self.client.latest_comment_id(issue), state.comment_id,
        )


if __name__ == "__main__":
    unittest.main()
