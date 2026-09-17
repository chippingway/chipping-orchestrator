# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PINNED_STATE_MARKER,
    PINNED_STATE_TEMPLATE,
    PinnedState,
    pinned_state_body,
)
from tests.github.pinned_state_test_support import (
    BOT,
    bot_comment,
    marker,
    state_client,
)
from tests.support.fakes import FakeComment, FakeUser, make_issue

REAL_BRANCH = "orchestrator/chippingway__orchestrator/issue-5"
_ATTACKER_BRANCH = "orchestrator/evil"
_BRANCH_KEY = "branch"
_DEV_AGENT_KEY = "dev_agent"
_PINNED_COMMENT_ID = 200

# A comment that QUOTES the state marker rather than being the state comment:
# what a park notice explaining this orchestrator's own pinned comment looks
# like on the thread, and what the marker test cannot tell from the real one.
_QUOTING_BODY = f"the schema in {PINNED_STATE_MARKER} blocks it"

# What ends the comment the payload is wrapped in, and a value that carries
# it: an agent's explanation, a preserved pull-request body, a human's own
# words all reach the record as somebody wrote them.
_COMMENT_CLOSE = "-->"

_BLOCKER_KEY = "late_result_split_blocker"

_TERMINATING_VALUE = f"the marker {_COMMENT_CLOSE} ends it"

# How many terminators one value carries where escaping every one would cost
# more than the comment GitHub takes while the payload as it was stored is
# well inside it. What a record an older binary accepted at the ceiling looks
# like: a preserved pull-request body is where they come by the thousand.
_TERMINATORS = 16384

_TERMINATOR_RUN = _COMMENT_CLOSE * _TERMINATORS


class ReadPinnedStateTrustsAuthorTest(unittest.TestCase):
    """`read_pinned_state` must authenticate durable state to the account
    backing the token. A third party who can comment on the issue must not be
    able to preempt the real pinned state with a forged marker comment
    (CWE-345)."""

    def test_foreign_marker_before_state_is_ignored(self) -> None:
        # An attacker posts (or edits an older comment to carry) the hidden
        # state marker before the orchestrator's real pinned comment. GitHub
        # keeps the original author on an edit, so "edited older comment" is
        # the same case: the foreign author is skipped regardless of order.
        attacker = FakeComment(
            id=1,
            body=marker({_BRANCH_KEY: _ATTACKER_BRANCH, _DEV_AGENT_KEY: "pwn"}),
            user=FakeUser("mallory"),
        )
        legit = FakeComment(
            id=_PINNED_COMMENT_ID,
            body=marker({_BRANCH_KEY: REAL_BRANCH, _DEV_AGENT_KEY: "claude"}),
            user=FakeUser(login=BOT),
        )
        issue = make_issue(5, comments=[attacker, legit])

        state = state_client().read_pinned_state(issue)

        # The orchestrator's own comment wins, not the earlier forged one.
        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)
        self.assertEqual(state.get(_DEV_AGENT_KEY), "claude")

    def test_bad_foreign_marker_cannot_shadow_state(self) -> None:
        # A foreign marker with unparseable JSON would, under the old
        # first-marker-wins parser, early-return empty state and shadow the
        # real one. The author gate skips it before its body is parsed.
        attacker = FakeComment(
            id=1,
            body="<!--orchestrator-state {bad json}-->",
            user=FakeUser("mallory"),
        )
        legit = bot_comment(
            _PINNED_COMMENT_ID,
            marker({_BRANCH_KEY: REAL_BRANCH}),
        )
        issue = make_issue(5, comments=[attacker, legit])

        state = state_client().read_pinned_state(issue)

        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)

    def test_only_foreign_marker_yields_empty_state(self) -> None:
        # With no orchestrator-authored marker present, nothing is trusted:
        # the parser reports no pinned state (comment_id None) so the caller
        # creates a fresh state comment rather than adopting the forgery.
        attacker = FakeComment(
            id=1,
            body=marker({_BRANCH_KEY: _ATTACKER_BRANCH, "pr_number": 999}),
            user=FakeUser("mallory"),
        )
        issue = make_issue(5, comments=[attacker])

        state = state_client().read_pinned_state(issue)

        self.assertIsNone(state.comment_id)
        self.assertEqual(state.data, {})

    def test_bot_authored_state_is_trusted(self) -> None:
        # Legacy pinned comments were authored by this same account, so author
        # matching keeps honoring them with no migration step.
        bot_user = FakeUser(BOT)
        legit = FakeComment(
            id=_PINNED_COMMENT_ID,
            body=marker({_BRANCH_KEY: REAL_BRANCH, "review_round": 2}),
            user=bot_user,
        )
        issue = make_issue(5, comments=[legit])

        state = state_client().read_pinned_state(issue)

        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.get("review_round"), 2)
        self.assertTrue(state.parsed)

    def test_bad_trusted_marker_keeps_comment_id(self) -> None:
        # A corrupted orchestrator-authored comment still resolves to its id
        # (with empty data) so `write_pinned_state` re-targets and overwrites
        # it instead of leaking a duplicate pinned comment.
        #
        # The empty payload is a stand-in, not a reading, and it says so: an
        # issue nothing was ever recorded for resolves to the same `{}`, and
        # a caller deciding on the absence of a recorded branch or pull
        # request would otherwise be deciding on a record it never read.
        legit = bot_comment(
            _PINNED_COMMENT_ID,
            "<!--orchestrator-state {bad json}-->",
        )
        issue = make_issue(5, comments=[legit])

        state = state_client().read_pinned_state(issue)

        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.data, {})
        self.assertFalse(state.parsed)

    def test_missing_login_uses_marker_only_scan(self) -> None:
        # Clients built via `__new__` in tests have no `_bot_login`; the parser
        # must not raise and falls back to the marker-only scan there.
        client = GitHubClient.__new__(GitHubClient)
        legit = FakeComment(
            id=_PINNED_COMMENT_ID,
            body=marker({_BRANCH_KEY: REAL_BRANCH}),
            user=FakeUser("anyone"),
        )
        issue = make_issue(5, comments=[legit])

        state = client.read_pinned_state(issue)

        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)


class ReadPinnedStateRequiresStateOnlyBodyTest(unittest.TestCase):
    """Author match is necessary but not sufficient. An ordinary bot-authored
    comment -- `_post_issue_comment` posts decomposer/agent text that is
    attacker-influenced, and does so BEFORE the real state comment exists on a
    manually-labeled issue -- that embeds a `<!--orchestrator-state ...-->`
    substring must not be mistaken for state. Only a comment whose ENTIRE body
    is the marker (what `write_pinned_state` emits) is trusted.

    What that comment CARRIES is the second half of the same question. A body
    that is the marker alone is the state comment whatever payload sits in it,
    and a payload no state can be read out of is reported as one rather than
    passed over -- passed over, it would read as an issue that recorded
    nothing at all. A payload carrying the wrapper's own terminator is the
    sharp case of that, since it would leave the body no longer being the
    marker alone -- and everything after it visible on the issue."""

    def test_a_terminating_value_closes_nothing(self) -> None:
        # An agent's explanation, a preserved pull-request body, a human's own
        # words: none is this owner's to sanitize, so what is escaped is the
        # serialized form. Left raw, the comment ends inside the payload and
        # the rest of the record is issue text a human reads.
        body = pinned_state_body({_BLOCKER_KEY: _TERMINATING_VALUE})

        closes_at = len(body) - len(_COMMENT_CLOSE)
        self.assertEqual(body.index(_COMMENT_CLOSE), closes_at)

    def test_a_terminating_value_reads_back_whole(self) -> None:
        # Escaped in the serialized form and nowhere else: what a reader
        # decodes is the value somebody actually wrote.
        written = pinned_state_body({_BLOCKER_KEY: _TERMINATING_VALUE})
        issue = make_issue(5, comments=[
            bot_comment(_PINNED_COMMENT_ID, written),
        ])
        client = state_client()

        state = client.read_pinned_state(issue)

        self.assertEqual(state.get(_BLOCKER_KEY), _TERMINATING_VALUE)

    def test_an_unescapable_payload_is_stored_raw(self) -> None:
        # The escape is five characters an occurrence, and a record already on
        # an issue never paid them. Refusing the write it puts past the limit
        # would lose the record the next tick reads; writing the payload as it
        # was stored renders the comment the way the binary that accepted it
        # rendered it, and the object form spans the terminator on the way
        # back.
        written = pinned_state_body({_BLOCKER_KEY: _TERMINATOR_RUN})
        issue = make_issue(5, comments=[
            bot_comment(_PINNED_COMMENT_ID, written),
        ])
        client = state_client()

        state = client.read_pinned_state(issue)

        self.assertLessEqual(len(written), MAX_PINNED_BODY)
        self.assertIn(_COMMENT_CLOSE * 2, written)
        self.assertEqual(state.get(_BLOCKER_KEY), _TERMINATOR_RUN)

    def test_embedded_bot_marker_is_not_state(self) -> None:
        # Adversarial shape: forged marker at position 0, then the
        # orchestrator-comment marker that `_post_issue_comment` always
        # appends -- the trailing marker alone makes the body not state-only.
        forged = marker({_BRANCH_KEY: _ATTACKER_BRANCH, _DEV_AGENT_KEY: "pwn"})
        ordinary = bot_comment(
            1,
            f"{forged}\n\n<!--orchestrator-comment-->",
        )
        issue = make_issue(5, comments=[ordinary])

        state = state_client().read_pinned_state(issue)

        # No real state comment exists yet, so nothing is adopted.
        self.assertIsNone(state.comment_id)
        self.assertEqual(state.data, {})

    def test_marker_embedded_in_prose_is_not_state(self) -> None:
        forged = marker({"pr_number": 999})
        ordinary = bot_comment(
            1,
            f"decomposer says this fits one context {forged}",
        )
        issue = make_issue(5, comments=[ordinary])

        client = state_client()
        state = client.read_pinned_state(issue)

        self.assertIsNone(state.comment_id)
        self.assertEqual(state.data, {})

    def test_a_non_object_payload_is_not_a_reading(self) -> None:
        # Valid JSON the bot could have written that no state can be read out
        # of: a truncated write, a hand-edited comment. The comment is still
        # identified -- the id is what lets the next write overwrite the
        # corruption in place -- but the empty payload standing in for it is
        # not offered as a reading, since an issue that recorded nothing
        # resolves to exactly the same `{}`.
        client = state_client()
        for payload in ("[]", '"x"', "7", "null", "{bad json}"):
            with self.subTest(payload=payload):
                corrupt = bot_comment(
                    _PINNED_COMMENT_ID,
                    PINNED_STATE_TEMPLATE.format(payload=payload),
                )

                state = client.read_pinned_state(
                    make_issue(5, comments=[corrupt]),
                )

                self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
                self.assertEqual(state.data, {})
                self.assertFalse(state.parsed)

    def test_embedded_marker_cannot_shadow_state(self) -> None:
        forged = marker({_BRANCH_KEY: _ATTACKER_BRANCH})
        ordinary = bot_comment(
            1,
            f"{forged}\n\n<!--orchestrator-comment-->",
        )
        legit = bot_comment(
            _PINNED_COMMENT_ID,
            marker({_BRANCH_KEY: REAL_BRANCH}),
        )
        issue = make_issue(5, comments=[ordinary, legit])

        state = state_client().read_pinned_state(issue)

        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)


class CommentsAfterExcludesStateTest(unittest.TestCase):
    """Which comment the thread read leaves out, and how it decides.

    Two questions wear the same answer most of the time and are not the same
    question. A reader after CONVERSATION wants the pinned comment gone and
    has no id to name it by, so the marker in a body stands in. A reader after
    a receipt it posted itself can name that comment -- and must, because the
    marker test also hides every comment merely QUOTING the marker, which is
    exactly what a notice explaining this orchestrator's own state comment
    does.
    """

    def test_the_marker_stands_in_for_no_id(self) -> None:
        issue = make_issue(5, comments=[
            bot_comment(1, marker({_BRANCH_KEY: REAL_BRANCH})),
            bot_comment(2, _QUOTING_BODY),
        ])

        read = state_client().comments_after(issue, None)

        self.assertEqual([issue_comment.id for issue_comment in read], [])

    def test_a_named_state_leaves_a_quote_visible(self) -> None:
        # The receipt case: the pinned comment goes by id, and the sentence
        # quoting its marker is the one comment the caller is looking for.
        issue = make_issue(5, comments=[
            bot_comment(1, marker({_BRANCH_KEY: REAL_BRANCH})),
            bot_comment(2, _QUOTING_BODY),
        ])

        read = state_client().comments_after(issue, None, state_comment_id=1)

        self.assertEqual([issue_comment.id for issue_comment in read], [2])

    def test_the_watermark_still_bounds_it(self) -> None:
        issue = make_issue(5, comments=[
            bot_comment(1, marker({_BRANCH_KEY: REAL_BRANCH})),
            bot_comment(2, _QUOTING_BODY),
            bot_comment(3, "said afterwards"),
        ])

        read = state_client().comments_after(issue, 2, state_comment_id=1)

        self.assertEqual([issue_comment.id for issue_comment in read], [3])


class PinnedStateKeywordTest(unittest.TestCase):
    """`state_data` and `data` name one payload, whichever spelling built it.

    Live issues are read back through both, so the two have to be the same
    dict rather than two copies that drift apart on the next write.
    """

    def test_keywords_share_data_attribute(self) -> None:
        state_data = {_BRANCH_KEY: REAL_BRANCH}
        descriptive_state = PinnedState(state_data=state_data)
        legacy_state = PinnedState(data=state_data)

        self.assertIs(descriptive_state.data, state_data)
        self.assertIs(legacy_state.state_data, state_data)

    def test_data_assignment_updates_internal_state(self) -> None:
        pinned_state = PinnedState()
        replacement = {"review_round": 2}

        pinned_state.data = replacement

        self.assertIs(pinned_state.state_data, replacement)

    def test_invalid_keywords(self) -> None:
        with self.assertRaises(TypeError):
            PinnedState(state_data={}, data={})
        with self.assertRaises(TypeError):
            PinnedState(payload={})


if __name__ == "__main__":
    unittest.main()
