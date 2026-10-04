# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The strict rewrite a guarded commit lands through, over the real client.

Driven over the PyGithub-shaped issue and comment doubles, so the requests under
test are the ones production makes: the thread is walked for the comment by its
id, and that comment's own `edit` is what rewrites it. Each case reads back what
the thread carries afterwards, since the contract is as much about what is left
alone as about what is written.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedEdit, PinnedState, pinned_state_body
from tests.github.pinned_state_test_support import BOT, bot_comment, marker, state_client
from tests.support.fakes import FakeComment, FakeIssue, FakeUser, make_issue

_ISSUE = 9
_RECORDED_ID = 300
_REPLY_ID = 12
_REPLY = "a human answering the park notice"
_UNANSWERED = "GitHub did not answer"
_ROUND = "review_round"
_LEDGER = "ledger"

_READ = MappingProxyType({
    "pr_number": 4,
    _ROUND: 1,
    _LEDGER: {"ids": [7, 8]},
})
_WRITTEN = MappingProxyType({**_READ, _ROUND: 2})
_READ_BODY = marker(dict(_READ))
_WRITTEN_BODY = pinned_state_body(dict(_WRITTEN))
_CORRUPTED_BODY = "<!--orchestrator-state [] -->"

# What is left under the record's id once it is no longer the record: nothing,
# or a body a maintainer edited into prose.
_GONE = MappingProxyType({"deleted": (), "edited into prose": ("the state was here",)})

# A record another writer left, and the reading a rewrite was derived over:
# every pair Python calls equal and a reader does not, at any depth, and a
# comment that no longer parses at all.
_MOVED = MappingProxyType({
    "null over absent": (marker({_ROUND: None}), {}),
    "true over 1": (marker({_ROUND: True}), {_ROUND: 1}),
    "1.0 over 1": (marker({_ROUND: 1.0}), {_ROUND: 1}),
    "nested true over 1": (marker({_LEDGER: [7, True]}), {_LEDGER: [7, 1]}),
    "unparsed": (_CORRUPTED_BODY, {}),
})

# Whether an unconfirmed edit landed and whether its response was lost, and
# what the record carries afterwards.
_UNCONFIRMED = MappingProxyType({
    "landed, response lost": (MappingProxyType({"lands": True, "raises": True}), _WRITTEN_BODY),
    "refused": (MappingProxyType({"lands": False, "raises": True}), _READ_BODY),
    "answered with the old body": (MappingProxyType({"lands": False, "raises": False}), _READ_BODY),
})

# What follows the reply on a thread, as each comment's id and body.
_Thread = list[tuple[int, str]]


@dataclass
class _UnconfirmedComment(FakeComment):
    """A pinned comment whose edit GitHub does not confirm.

    `lands` is whether the body reached the comment, and `raises` whether the
    response was lost rather than answered with the body it already had.
    """

    lands: bool = False
    raises: bool = True

    @classmethod
    def recorded(cls, *, lands: bool, raises: bool) -> _UnconfirmedComment:
        """The record as the derivation read it, under its id."""
        return cls(
            id=_RECORDED_ID,
            body=_READ_BODY,
            user=FakeUser(BOT),
            lands=lands,
            raises=raises,
        )

    def edit(self, body: str) -> None:
        """Land the body or not, then lose the response or answer with what the comment holds."""
        if self.lands:
            self.body = body
        if self.raises:
            raise RuntimeError(_UNANSWERED)


def _thread(*comments: FakeComment) -> FakeIssue:
    """A thread whose own posts are attributed to the account the read trusts, behind a human's reply."""
    reply = FakeComment(id=_REPLY_ID, body=_REPLY, user=FakeUser("alice"))
    issue = make_issue(_ISSUE, comments=[reply, *comments])
    issue.commenter = FakeUser(BOT)
    return issue


class EditPinnedStateTest(unittest.TestCase):
    """In place, over the reading it was derived from, or not at all."""

    def setUp(self) -> None:
        self.client = state_client()

    def edit(self, issue: FakeIssue, over: dict) -> tuple[PinnedEdit, _Thread]:
        """Rewrite the record as `_WRITTEN` over `over`, and what the thread carries behind the reply afterwards.

        The reply is never touched and nothing lands ahead of it, whatever
        the answer.
        """
        answer = self.client.edit_pinned_state(
            issue, PinnedState(comment_id=_RECORDED_ID, data=dict(_WRITTEN)), over=over,
        )
        reply, *behind = issue.comments
        self.assertEqual((reply.id, reply.body), (_REPLY_ID, _REPLY))
        return answer, [
            (comment.id, comment.body) for comment in behind
        ]

    def test_a_record_read_as_derived_is_edited(self) -> None:
        # The one road that writes: the comment carries what the derivation
        # read, so it is edited where it stands and GitHub's answer carries
        # the body sent. Nothing is posted and the reply is left alone.
        issue = _thread(bot_comment(_RECORDED_ID, _READ_BODY))

        answer, thread = self.edit(issue, dict(_READ))

        self.assertIs(answer, PinnedEdit.EDITED)
        self.assertEqual(thread, [(_RECORDED_ID, _WRITTEN_BODY)])
        self.assertEqual(self.client.read_pinned_state(issue).data, _WRITTEN)

    def test_a_record_gone_is_never_recreated(self) -> None:
        # Not the record any more, and the legacy writer's repost would pin a
        # comment nobody read. The thread is left exactly as it was.
        for case, bodies in _GONE.items():
            with self.subTest(case=case):
                issue = _thread(*(bot_comment(_RECORDED_ID, body) for body in bodies))

                answer, thread = self.edit(issue, dict(_READ))

                self.assertIs(answer, PinnedEdit.MISSING)
                self.assertEqual(thread, [(_RECORDED_ID, body) for body in bodies])

    def test_a_record_moved_since_reading_stands(self) -> None:
        # The derivation was made over one record and the comment carries
        # another, so a rewrite would put the older reading's values back.
        for case, (carried, read) in _MOVED.items():
            with self.subTest(case=case):
                answer, thread = self.edit(_thread(bot_comment(_RECORDED_ID, carried)), read)

                self.assertIs(answer, PinnedEdit.MOVED)
                self.assertEqual(thread, [(_RECORDED_ID, carried)])

    def test_a_thread_that_will_not_read(self) -> None:
        issue = _thread(bot_comment(_RECORDED_ID, _READ_BODY))

        with patch.object(issue, "get_comments", side_effect=RuntimeError(_UNANSWERED)):
            answer, thread = self.edit(issue, dict(_READ))

        self.assertIs(answer, PinnedEdit.UNREAD)
        self.assertEqual(thread, [(_RECORDED_ID, _READ_BODY)])

    def test_an_unconfirmed_edit_however_it_landed(self) -> None:
        # A lost response, a refused request, and an answer carrying another
        # body are one answer to the caller, who cannot tell which it got;
        # what the record carries afterwards is each one's own.
        for case, (failure, carried) in _UNCONFIRMED.items():
            with self.subTest(case=case):
                issue = _thread(_UnconfirmedComment.recorded(**failure))

                edited = self.edit(issue, dict(_READ))

                self.assertEqual(edited, (PinnedEdit.UNCONFIRMED, [(_RECORDED_ID, carried)]))


if __name__ == "__main__":
    unittest.main()
