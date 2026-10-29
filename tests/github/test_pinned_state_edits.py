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

import json
import unittest
from dataclasses import dataclass
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from orchestrator.github.pinned_state import PINNED_STATE_TEMPLATE, PinnedEdit, PinnedState, pinned_state_body
from tests.github.pinned_state_test_support import (
    BOT,
    ORDINARY_PROSE,
    RAW_ORDINARY_QUOTE,
    REFUSED_PAYLOADS,
    bot_comment,
    cut_short,
    marker,
    state_client,
)
from tests.support.fakes import FakeComment, FakeIssue, FakeUser, make_issue

_ISSUE = 9
_AHEAD_ID = 150
_RECORDED_ID = 300
_REPLY_ID = 12
_REPLY = "a human answering the park notice"
_UNANSWERED = "GitHub did not answer"
_ROUND = "review_round"
_LEDGER = "ledger"
_SCHEMA = "schema_version"

_READ = MappingProxyType({
    _SCHEMA: 1,
    "pr_number": 4,
    _ROUND: 1,
    _LEDGER: {"ids": [7, 8]},
})
_WRITTEN = MappingProxyType({**_READ, _ROUND: 2})
_READ_BODY = marker(dict(_READ))
_WRITTEN_BODY = pinned_state_body(dict(_WRITTEN))
_CORRUPTED_BODY = "<!--orchestrator-state [] -->"
_NAN_BODY = PINNED_STATE_TEMPLATE.format(payload='{"review_round": NaN, "schema_version": 1}')

# What is left under the record's id once it is no longer the record: nothing,
# or a body a maintainer edited into prose.
_GONE = MappingProxyType({"deleted": (), "edited into prose": ("the state was here",)})

_TRUE_LEDGER = marker({_SCHEMA: 1, _LEDGER: [7, True]})
_INT_LEDGER = MappingProxyType({_SCHEMA: 1, _LEDGER: [7, 1]})
_RAW_READ = MappingProxyType({**_READ, "note": RAW_ORDINARY_QUOTE})

# A record another writer left, and the reading a rewrite was derived over:
# every pair Python calls equal and a reader does not, at any depth, and a
# comment that no longer parses at all -- among them a record rendered raw and
# then cut short, which only its marker still identifies, even where a value
# quotes the marker every other comment carries.
_MOVED = MappingProxyType({
    "null over absent": (marker({_SCHEMA: 1, _ROUND: None}), {_SCHEMA: 1}),
    "true over 1": (marker({_SCHEMA: 1, _ROUND: True}), {_SCHEMA: 1, _ROUND: 1}),
    "1.0 over 1": (marker({_SCHEMA: 1, _ROUND: 1.0}), {_SCHEMA: 1, _ROUND: 1}),
    "nested true over 1": (_TRUE_LEDGER, dict(_INT_LEDGER)),
    "unparsed": (_CORRUPTED_BODY, {_SCHEMA: 1}),
    "a constant JSON cannot spell": (_NAN_BODY, {_SCHEMA: 1, _ROUND: 1}),
    "a raw record cut short": (PINNED_STATE_TEMPLATE.format(payload=cut_short(dict(_RAW_READ))), dict(_RAW_READ)),
})

# Records that parse and are refused admission, as their comments carry them.
_UNSUPPORTED_BODY = marker({_SCHEMA: 2, _ROUND: 1})
_UNSUPPORTED = MappingProxyType({
    "unsupported schema version": _UNSUPPORTED_BODY,
    "missing schema version": marker({_ROUND: 1}, raw=True),
})

# A comment ahead of the record a stale id names, by its author and body, and
# what the edit answers and leaves the thread carrying: an authenticated one
# refused admission is the record every reader takes, while an outsider's is no
# record at all, nor is an ordinary comment of the bot's whose prose opens on
# the state marker, while the bot's array quoting the ordinary comment marker
# inside a string, or its record cut open in the middle of an escape, is a
# corrupted record like any other.
_ORDINARY_PROSE_BODY = PINNED_STATE_TEMPLATE.format(payload=ORDINARY_PROSE)
_QUOTING_ARRAY_BODY = PINNED_STATE_TEMPLATE.format(payload=json.dumps([ORCHESTRATOR_COMMENT_MARKER]))
_DANGLING_ESCAPE_BODY = PINNED_STATE_TEMPLATE.format(payload='{"review_round": "unfinished\\')
_AHEAD = MappingProxyType({
    "unsupported": (BOT, _UNSUPPORTED_BODY, (
        PinnedEdit.UNSUPPORTED, [(_AHEAD_ID, _UNSUPPORTED_BODY), (_RECORDED_ID, _READ_BODY)],
    )),
    "malformed": (BOT, _CORRUPTED_BODY, (
        PinnedEdit.MOVED, [(_AHEAD_ID, _CORRUPTED_BODY), (_RECORDED_ID, _READ_BODY)],
    )),
    "an outsider's unsupported": ("mallory", _UNSUPPORTED_BODY, (
        PinnedEdit.EDITED, [(_AHEAD_ID, _UNSUPPORTED_BODY), (_RECORDED_ID, _WRITTEN_BODY)],
    )),
    "the bot's ordinary prose": (BOT, _ORDINARY_PROSE_BODY, (
        PinnedEdit.EDITED, [(_AHEAD_ID, _ORDINARY_PROSE_BODY), (_RECORDED_ID, _WRITTEN_BODY)],
    )),
    "the bot's array quoting the ordinary marker": (BOT, _QUOTING_ARRAY_BODY, (
        PinnedEdit.MOVED, [(_AHEAD_ID, _QUOTING_ARRAY_BODY), (_RECORDED_ID, _READ_BODY)],
    )),
    "the bot's record cut open on a dangling escape": (BOT, _DANGLING_ESCAPE_BODY, (
        PinnedEdit.MOVED, [(_AHEAD_ID, _DANGLING_ESCAPE_BODY), (_RECORDED_ID, _READ_BODY)],
    )),
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


def _behind(author: str, body: str) -> FakeIssue:
    """The record, reading as derived, behind a comment `author` posted carrying `body`."""
    ahead = FakeComment(id=_AHEAD_ID, body=body, user=FakeUser(author))
    return _thread(ahead, bot_comment(_RECORDED_ID, _READ_BODY))


class _EditCase(unittest.TestCase):
    """The real client, and the rewrite every case sends through it."""

    def setUp(self) -> None:
        self.client = state_client()

    def edit(self, issue: FakeIssue, over: dict | None = None) -> tuple[PinnedEdit, _Thread]:
        """Rewrite the record as `_WRITTEN` over `over` (`_READ` unless named), and the thread behind the reply after.

        The reply is never touched and nothing lands ahead of it, whatever
        the answer.
        """
        derived = dict(_READ) if over is None else over
        answer = self.client.edit_pinned_state(
            issue, PinnedState(comment_id=_RECORDED_ID, state_data=dict(_WRITTEN)), over=derived,
        )
        reply, *behind = issue.comments
        self.assertEqual((reply.id, reply.body), (_REPLY_ID, _REPLY))
        return answer, [
            (comment.id, comment.body) for comment in behind
        ]


class EditPinnedStateTest(_EditCase):
    """In place, over the reading it was derived from, or not at all."""

    def test_a_record_read_as_derived_is_edited(self) -> None:
        # The one road that writes: the comment carries what the derivation
        # read, so it is edited where it stands and GitHub's answer carries
        # the body sent. Nothing is posted and the reply is left alone.
        issue = _thread(bot_comment(_RECORDED_ID, _READ_BODY))

        answer, thread = self.edit(issue)

        self.assertIs(answer, PinnedEdit.EDITED)
        self.assertEqual(thread, [(_RECORDED_ID, _WRITTEN_BODY)])
        self.assertEqual(self.client.read_pinned_state(issue).state_data, _WRITTEN)

    def test_a_record_gone_is_never_recreated(self) -> None:
        # Not the record any more, and the legacy writer's repost would pin a
        # comment nobody read. The thread is left exactly as it was.
        for case, bodies in _GONE.items():
            with self.subTest(case=case):
                issue = _thread(*(bot_comment(_RECORDED_ID, body) for body in bodies))

                answer, thread = self.edit(issue)

                self.assertIs(answer, PinnedEdit.MISSING)
                self.assertEqual(thread, [(_RECORDED_ID, body) for body in bodies])

        # An unattached state (comment_id None) is answered MISSING without creating.
        issue = _thread(bot_comment(_RECORDED_ID, _READ_BODY))
        answer = self.client.edit_pinned_state(
            issue, PinnedState(comment_id=None, state_data=dict(_WRITTEN)), over=dict(_READ),
        )
        self.assertIs(answer, PinnedEdit.MISSING)
        self.assertEqual(len(issue.comments), 2)

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
            answer, thread = self.edit(issue)

        self.assertIs(answer, PinnedEdit.UNREAD)
        self.assertEqual(thread, [(_RECORDED_ID, _READ_BODY)])

    def test_an_unconfirmed_edit_however_it_landed(self) -> None:
        # A lost response, a refused request, and an answer carrying another
        # body are one answer to the caller, who cannot tell which it got;
        # what the record carries afterwards is each one's own.
        for case, (failure, carried) in _UNCONFIRMED.items():
            with self.subTest(case=case):
                issue = _thread(_UnconfirmedComment.recorded(**failure))

                edited = self.edit(issue)

                self.assertEqual(edited, (PinnedEdit.UNCONFIRMED, [(_RECORDED_ID, carried)]))


class EditPinnedStateAdmissionTest(_EditCase):
    """Nothing is sent over a record refused admission, or for a state the next reading would refuse."""

    def test_a_record_refused_admission_stands(self) -> None:
        # Nothing is laid over a record the reader refuses, whatever reading
        # the rewrite was derived over.
        for case, carried in _UNSUPPORTED.items():
            with self.subTest(case=case):
                edited = self.edit(_thread(bot_comment(_RECORDED_ID, carried)))

                self.assertEqual(edited, (PinnedEdit.UNSUPPORTED, [(_RECORDED_ID, carried)]))

    def test_a_stale_id_stops_at_a_refused_record(self) -> None:
        # The id names a later comment that still reads as derived; the record
        # every reader takes is the one ahead of it, so that one decides.
        for case, (author, body, expected) in _AHEAD.items():
            with self.subTest(case=case):
                self.assertEqual(self.edit(_behind(author, body)), expected)

    def test_an_unknown_account_sends_nothing(self) -> None:
        # A client that does not know whose token it holds authenticates no
        # comment, so the record it names is no record it can find.
        issue = _thread(bot_comment(_RECORDED_ID, _READ_BODY))
        staged = PinnedState(comment_id=_RECORDED_ID, state_data=dict(_WRITTEN))

        answer = GitHubClient.__new__(GitHubClient).edit_pinned_state(issue, staged, over=dict(_READ))

        self.assertIs(answer, PinnedEdit.MISSING)
        self.assertEqual(issue.comments[-1].body, _READ_BODY)

    def test_a_refused_payload_is_not_sent(self) -> None:
        # The next reading would refuse what the edit pinned, so nothing is
        # sent over the record it was derived from.
        for refused in REFUSED_PAYLOADS:
            with self.subTest(refused=refused):
                issue = _thread(bot_comment(_RECORDED_ID, _READ_BODY))
                staged = PinnedState(comment_id=_RECORDED_ID, state_data={**_WRITTEN, **refused})

                answer = self.client.edit_pinned_state(issue, staged, over=dict(_READ))

                self.assertIs(answer, PinnedEdit.UNSUPPORTED)
                self.assertEqual(issue.comments[-1].body, _READ_BODY)


if __name__ == "__main__":
    unittest.main()
