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

import json
import unittest
from dataclasses import dataclass
from itertools import product
from types import MappingProxyType

from orchestrator.github import client as _github_client, pinned_refusal as _pinned_refusal
from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from orchestrator.github.pinned_state import PINNED_STATE_TEMPLATE, PinnedState
from orchestrator.workflow.engine import comments as _engine_comments
from tests.github.pinned_state_test_support import (
    BOT,
    ORDINARY_PROSE,
    RAW_TERMINATORS,
    REFUSED_PAYLOADS,
    bot_comment,
    cut_short,
    marker,
    state_client,
)
from tests.support.fakes import FakeComment, FakeIssue, FakeUser, make_issue

_ISSUE = 5
_BRANCH_KEY = "branch"
_ROUND_KEY = "review_round"
_BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-5"
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
_SCHEMA_VERSION = "schema_version"
_RECORD_BODY = (
    '<!--orchestrator-state {"branch": '
    '"orchestrator/chippingway__chipping-orchestrator/issue-5", "schema_version": 1}-->'
)
_REWRITTEN_BODY = (
    '<!--orchestrator-state {"branch": '
    '"orchestrator/chippingway__chipping-orchestrator/issue-5", "review_round": 2, "schema_version": 1}-->'
)

_RECORD = MappingProxyType({_BRANCH_KEY: _BRANCH, _SCHEMA_VERSION: 1})
_RECORD_DICT = dict(_RECORD)
_REWRITTEN = MappingProxyType({_BRANCH_KEY: _BRANCH, _ROUND_KEY: 2, _SCHEMA_VERSION: 1})
_STALE_ID = 999
# A current pin ahead of the record, the one every reader takes.
_CURRENT_ID = 100

# Authenticated records the reader refuses, as their comments carry them.
_UNSUPPORTED_BODY = marker({_SCHEMA_VERSION: 2, _BRANCH_KEY: _BRANCH})
_REFUSED_RECORDS = MappingProxyType({
    "unsupported version": _UNSUPPORTED_BODY,
    "missing version": marker({_BRANCH_KEY: _BRANCH}, raw=True),
    "malformed": "<!--orchestrator-state {bad json}-->",
    "a constant JSON cannot spell": PINNED_STATE_TEMPLATE.format(payload='{"schema_version": 1, "usage_total": NaN}'),
    "an array carrying the terminator": PINNED_STATE_TEMPLATE.format(payload='["-->"]'),
    "an array quoting the ordinary marker": PINNED_STATE_TEMPLATE.format(
        payload=json.dumps([ORCHESTRATOR_COMMENT_MARKER]),
    ),
    "an object cut open on a dangling escape": PINNED_STATE_TEMPLATE.format(
        payload='{"schema_version": 1, "note": "unfinished\\',
    ),
    "a raw record cut short": PINNED_STATE_TEMPLATE.format(
        payload=cut_short({_SCHEMA_VERSION: 1, _BRANCH_KEY: _BRANCH, "note": RAW_TERMINATORS}),
    ),
    "a raw record quoting the ordinary marker, cut short": PINNED_STATE_TEMPLATE.format(
        payload=cut_short({
            _SCHEMA_VERSION: 1, _BRANCH_KEY: _BRANCH, "note": f"{ORCHESTRATOR_COMMENT_MARKER}{RAW_TERMINATORS}",
        }),
    ),
})

# Comments ahead of any record that carry the state marker and are no record:
# a third party's forgery, and ones the orchestrator posted whose text an agent
# opened with the marker and prose -- shaped as an array or an object -- that
# carries the ordinary comment marker outside any JSON string.
_NOT_RECORDS = MappingProxyType({
    "a third party's": FakeComment(
        id=1, body=marker({_BRANCH_KEY: _ATTACKER_BRANCH}), user=FakeUser("mallory"),
    ),
    "an ordinary bot comment's": bot_comment(1, _engine_comments._with_orch_marker(
        PINNED_STATE_TEMPLATE.format(payload=f'["x"] {ORCHESTRATOR_COMMENT_MARKER} ordinary explanation '),
    )),
    "an ordinary bot comment's prose": bot_comment(1, _engine_comments._with_orch_marker(
        PINNED_STATE_TEMPLATE.format(payload=ORDINARY_PROSE),
    )),
})


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


@dataclass
class _EditedOnRead(FakeIssue):
    """A thread whose last comment a maintainer rewrites to `edit` as it is read, counting the reads.

    The rewrite lands on every read, so a writer deciding on one read and
    landing from another would be the one to tell the two apart.
    """

    edit: str | None = None
    reads: int = 0

    def get_comments(self) -> list[FakeComment]:
        """The thread as GitHub answers it, with the maintainer's rewrite already on it."""
        self.reads += 1
        if self.edit is not None:
            self.comments[-1].body = self.edit
        return super().get_comments()


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
        state = PinnedState(state_data=dict(_RECORD))

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
        # the id every reader and watermark already has -- with no record
        # ahead of it, and behind an ordinary comment whose prose opens on a
        # forged marker, which is no record to stop the write at.
        for ahead in ((), (_NOT_RECORDS["an ordinary bot comment's prose"],)):
            with self.subTest(ahead=len(ahead)):
                record = bot_comment(_RECORDED_ID, _RECORD_BODY)
                reply = _human_reply()
                issue = _issue(*ahead, reply, record)
                state = PinnedState(comment_id=_RECORDED_ID, state_data=dict(_REWRITTEN))

                self.client.write_pinned_state(issue, state)

                self.assertEqual(
                    [comment.id for comment in issue.comments],
                    [*(comment.id for comment in ahead), _REPLY_ID, _RECORDED_ID],
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
        state = PinnedState(comment_id=_RECORDED_ID, state_data=dict(_RECORD))

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
        state = PinnedState(state_data=dict(_RECORD))

        self.client.write_pinned_state(issue, state)
        created = self.client.read_pinned_state(issue)
        self.client.write_pinned_state(issue, PinnedState(
            comment_id=state.comment_id, state_data=dict(_REWRITTEN),
        ))
        edited = self.client.read_pinned_state(issue)

        self.assertEqual(created.comment_id, state.comment_id)
        self.assertEqual(created.state_data, _RECORD)
        self.assertEqual(edited.comment_id, state.comment_id)
        self.assertEqual(edited.state_data, _REWRITTEN)
        self.assertTrue(edited.parsed)

    def test_what_was_read_or_written_is_remembered(self) -> None:
        # A state remembers what the comment carried the last time it was
        # written over it or read from it, and nothing staged on it afterwards
        # moves that: a guarded commit tells the tick's own changes from the
        # comment's by it. A state built in memory has read nothing.
        issue = _issue(_human_reply())
        state = PinnedState(state_data=dict(_RECORD))
        built = state.synced

        self.client.write_pinned_state(issue, state)
        state.set(_ROUND_KEY, 2)
        read = self.client.read_pinned_state(issue)
        read.set(_BRANCH_KEY, _ATTACKER_BRANCH)

        self.assertEqual(
            (built, json.loads(state.synced), json.loads(read.synced)),
            (None, _RECORD_DICT, _RECORD_DICT),
        )

    def test_a_forged_record_is_not_the_one_written(self) -> None:
        # The marker reached the thread before the orchestrator ever recorded
        # anything, which is the window a manually labelled issue sits in. The
        # write posts its own record, and the read that follows has to come
        # back with THAT comment: adopting the forgery would hand the next
        # tick somebody else's branch out of its own durable state, and
        # refusing it as a record would leave the issue with none at all.
        for case, forged in _NOT_RECORDS.items():
            with self.subTest(case=case):
                issue = _issue(forged)
                state = PinnedState(state_data=dict(_RECORD))

                self.client.write_pinned_state(issue, state)
                read = self.client.read_pinned_state(issue)

                self.assertEqual(len(issue.comments), 2)
                self.assertEqual(read.comment_id, state.comment_id)
                self.assertEqual(read.get(_BRANCH_KEY), _BRANCH)


class UnwrittenStateTest(unittest.TestCase):
    """States the whole-state writer sends nothing for, whatever the thread carries."""

    def test_a_withheld_state_writes_nothing(self) -> None:
        # The comment moved under the decision the state was taken on, so
        # writing it whole would put back what another road wrote: the writer
        # sends nothing, the record stands as it was, and the state is handed
        # back untouched.
        record = bot_comment(_RECORDED_ID, _RECORD_BODY)
        issue = _issue(_human_reply(), record)
        state = PinnedState(comment_id=_RECORDED_ID, state_data=dict(_REWRITTEN))
        state.withheld = True

        written = state_client().write_pinned_state(issue, state)

        self.assertEqual(
            (written, record.body, len(issue.comments), state.synced),
            (state, _RECORD_BODY, 2, None),
        )

    def test_an_unknown_account_writes_nothing(self) -> None:
        # A client that does not know whose token it holds authenticates no
        # comment, so it could not tell a refused record from none: it neither
        # rewrites the record its state names nor posts one beside it.
        client = _github_client.GitHubClient.__new__(_github_client.GitHubClient)
        for comment_id in (_RECORDED_ID, None):
            with self.subTest(comment_id=comment_id):
                record = bot_comment(_RECORDED_ID, _RECORD_BODY)
                issue = _issue(_human_reply(), record)
                state = PinnedState(comment_id=comment_id, state_data=dict(_REWRITTEN))

                self.assertIs(client.write_pinned_state(issue, state), state)

                self.assertEqual(record.body, _RECORD_BODY)
                self.assertEqual((len(issue.comments), state.synced), (2, None))


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
        state = PinnedState(state_data=dict(_RECORD))

        self.client.write_pinned_state(issue, state)

        self.assertEqual(
            self.client.latest_comment_id(issue), state.comment_id,
        )


class WritePinnedStateAdmissionTest(unittest.TestCase):
    """Admission rules applied to write_pinned_state."""

    def setUp(self) -> None:
        self.client = state_client()

    def assert_writes_nothing(self, issue: FakeIssue, staged: PinnedState, *, refused: bool = False) -> None:
        """Write `staged` with nothing on the thread edited or posted: answered unchanged, or raising where `refused`.

        Over a record admission refuses the write raises `RecordRefused`
        rather than answering, so a caller cannot go on to what the write was
        for over a record nobody can read.
        """
        before = [(comment.id, comment.body) for comment in issue.comments]

        if refused:
            with self.assertRaises(_pinned_refusal.RecordRefused):
                self.client.write_pinned_state(issue, staged)
        else:
            self.assertIs(self.client.write_pinned_state(issue, staged), staged)

        self.assertEqual([(comment.id, comment.body) for comment in issue.comments], before)
        self.assertIsNone(staged.synced)

    def test_first_write_stamps_schema_version(self) -> None:
        # A genuinely new pin carrying no schema_version is stamped with schema_version: 1
        issue = _issue(_human_reply())
        fresh_state = PinnedState(state_data={"branch": _BRANCH})

        self.client.write_pinned_state(issue, fresh_state)

        self.assertEqual(fresh_state.state_data.get(_SCHEMA_VERSION), 1)
        self.assertEqual(len(issue.comments), 2)
        posted = issue.comments[-1]
        self.assertIn('"schema_version": 1', posted.body)

    def test_a_refused_record_is_never_written_over(self) -> None:
        # Whatever id the caller holds -- the record's, none, or a stale one --
        # the refused record stays as it is, nothing is posted beside it, and
        # the write raises.
        for case, comment_id in product(_REFUSED_RECORDS, (_RECORDED_ID, None, _STALE_ID)):
            with self.subTest(case=case, comment_id=comment_id):
                record = bot_comment(_RECORDED_ID, _REFUSED_RECORDS[case])
                staged = PinnedState(comment_id=comment_id, state_data={_BRANCH_KEY: _BRANCH, _SCHEMA_VERSION: 1})
                self.assert_writes_nothing(_issue(_human_reply(), record), staged, refused=True)

    def test_a_refused_target_behind_the_pin_stands(self) -> None:
        # The caller's id names a refused record behind the current pin every
        # reader takes: what the write would rewrite is admitted too, not only
        # the pin ahead of it.
        for case, body in _REFUSED_RECORDS.items():
            with self.subTest(case=case):
                current = bot_comment(_CURRENT_ID, _RECORD_BODY)
                staged = PinnedState(comment_id=_RECORDED_ID, state_data=dict(_REWRITTEN))
                thread = _issue(_human_reply(), current, bot_comment(_RECORDED_ID, body))
                self.assert_writes_nothing(thread, staged, refused=True)

    def test_a_write_lands_from_the_read_it_admits(self) -> None:
        # One walk both admits the record and finds it, so what the thread
        # carries on that read decides: a record a maintainer turned refused
        # by then stands and the write raises, and a current one is rewritten,
        # with no second read for either to change between.
        for edit, landed in ((_UNSUPPORTED_BODY, _UNSUPPORTED_BODY), (None, _REWRITTEN_BODY)):
            with self.subTest(edited=edit is not None):
                issue = _EditedOnRead(
                    _ISSUE,
                    comments=[_human_reply(), bot_comment(_RECORDED_ID, _RECORD_BODY)],
                    commenter=FakeUser(BOT),
                    edit=edit,
                )

                staged = PinnedState(comment_id=_RECORDED_ID, state_data=dict(_REWRITTEN))

                try:
                    self.client.write_pinned_state(issue, staged)
                except _pinned_refusal.RecordRefused:
                    self.assertIsNotNone(edit, "only a record turned refused raises")
                else:
                    self.assertIsNone(edit, "a record turned refused raises")

                self.assertEqual(issue.reads, 1)
                self.assertEqual(issue.comments[-1].body, landed)

    def test_a_refused_payload_is_not_written(self) -> None:
        # The next reading would refuse what it pinned, so neither a supported
        # record nor an issue with none is written for it; only a missing
        # version is stamped.
        for refused, recorded in product(REFUSED_PAYLOADS, (True, False)):
            with self.subTest(refused=refused, recorded=recorded):
                thread = (bot_comment(_RECORDED_ID, _RECORD_BODY),) if recorded else ()
                staged = PinnedState(comment_id=_RECORDED_ID, state_data={_BRANCH_KEY: "changed", **refused})
                self.assert_writes_nothing(_issue(_human_reply(), *thread), staged)


if __name__ == "__main__":
    unittest.main()
