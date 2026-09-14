# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trust policy for GitHub-authored content: `is_trusted_author` /
`filter_trusted` gate workflow-driving comments on the
`ALLOWED_ISSUE_AUTHORS` allowlist (empty disables the filter, populated
matches logins case-insensitively, bots follow the same login rule),
`carries_reserved_marker` refuses content claiming a receipt of ours, and
`authored_by_us` decides whether a receipt read back off a thread is one this
orchestrator wrote."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.comments import (
    authored_by_us,
    carries_reserved_marker,
    filter_trusted,
    is_trusted_author,
)
from tests.support.fakes import FakeComment, FakeUser

_ALLOWED_LOGIN = "alice"
_BOT_ACCOUNT_TYPE = "Bot"

_BOT_LOGIN = "orchestrator"


class IsTrustedAuthorTest(unittest.TestCase):
    def test_empty_allowlist_trusts_everyone(self) -> None:
        # Legacy single-user behavior: with no allowlist configured every
        # author -- human, bot, or a comment whose user failed to load --
        # is trusted, so opting out changes nothing.
        for user in (
            FakeUser("stranger"),
            FakeUser("dependabot[bot]", type=_BOT_ACCOUNT_TYPE),
            None,
        ):
            with self.subTest(user=user):
                self.assertTrue(is_trusted_author(user, allowed=()))

    def test_populated_allowlist_gates_by_login(self) -> None:
        # A configured allowlist trusts only its logins, matched
        # case-insensitively on both sides; an unlisted login, an empty
        # login, and a missing user are all untrusted.
        allowed = (_ALLOWED_LOGIN, "Bob")
        cases = [
            (FakeUser(_ALLOWED_LOGIN), True),
            (FakeUser("Alice"), True),
            (FakeUser("BOB"), True),
            (FakeUser("stranger"), False),
            (FakeUser(""), False),
            (None, False),
        ]
        for user, expected in cases:
            with self.subTest(user=user):
                self.assertEqual(
                    is_trusted_author(user, allowed=allowed), expected
                )

    def test_bot_gated_by_login_not_by_type(self) -> None:
        # Bot-ness alone neither grants nor denies trust: an allowlisted
        # bot login supplies workflow-driving content, a non-listed bot
        # (a stray CI / dependency bot) does not.
        allowed = ("automation-bot",)
        self.assertTrue(
            is_trusted_author(
                FakeUser("automation-bot", type=_BOT_ACCOUNT_TYPE), allowed=allowed
            )
        )
        self.assertFalse(
            is_trusted_author(
                FakeUser("dependabot[bot]", type=_BOT_ACCOUNT_TYPE), allowed=allowed
            )
        )

    def test_defaults_to_config_allowlist(self) -> None:
        # `allowed=None` reads `config.ALLOWED_ISSUE_AUTHORS` so callers
        # pick up the operator's configuration without threading it through.
        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_ALLOWED_LOGIN,)):
            self.assertTrue(is_trusted_author(FakeUser("Alice")))
            self.assertFalse(is_trusted_author(FakeUser("mallory")))
        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", ()):
            self.assertTrue(is_trusted_author(FakeUser("mallory")))


class FilterTrustedTest(unittest.TestCase):
    def test_empty_allowlist_keeps_all_in_order(self) -> None:
        comments = [
            FakeComment(1, "a", FakeUser("x")),
            FakeComment(
                2,
                "b",
                FakeUser("dependabot[bot]", type=_BOT_ACCOUNT_TYPE),
            ),
        ]
        self.assertEqual(filter_trusted(comments, allowed=()), comments)

    def test_allowlist_drops_untrusted_keeps_order(self) -> None:
        allowed = (_ALLOWED_LOGIN,)
        comments = [
            FakeComment(1, "ok", FakeUser("Alice")),
            FakeComment(2, "bad", FakeUser("stranger")),
            FakeComment(3, "no-user", None),
        ]
        kept = filter_trusted(comments, allowed=allowed)
        self.assertEqual([comment.id for comment in kept], [1])

    def test_defaults_to_config_allowlist(self) -> None:
        comments = [
            FakeComment(1, "a", FakeUser(_ALLOWED_LOGIN)),
            FakeComment(2, "b", FakeUser("mallory")),
        ]
        with patch.object(
            config,
            "ALLOWED_ISSUE_AUTHORS",
            (_ALLOWED_LOGIN,),
        ):
            self.assertEqual(
                [comment.id for comment in filter_trusted(comments)],
                [1],
            )


class AuthoredByUsTest(unittest.TestCase):
    """Whose comment a receipt read back off a thread has to be.

    Separate from the allowlist above: a trusted human is still not this
    orchestrator, and a receipt is a claim that WE already did something.
    """

    def test_only_our_own_login_is_a_receipt(self) -> None:
        # The allowlist has nothing to say here -- the operator writing the
        # commands is trusted and is still not the author of our receipts.
        for login, ours in ((_BOT_LOGIN, True), (_ALLOWED_LOGIN, False)):
            with self.subTest(login=login):
                self.assertIs(
                    authored_by_us(
                        FakeComment(id=1, body="said", user=FakeUser(login)),
                        bot_login=_BOT_LOGIN,
                    ),
                    ours,
                )

    def test_an_author_that_did_not_load_is_not_ours(self) -> None:
        self.assertFalse(
            authored_by_us(
                FakeComment(id=1, body="said", user=None),
                bot_login=_BOT_LOGIN,
            ),
        )

    def test_no_login_takes_the_content_alone(self) -> None:
        # A client with no authenticated login of its own has nothing to check,
        # so the content is the whole of the receipt -- the same fallback the
        # pinned-state read takes rather than a check that always fails.
        self.assertTrue(
            authored_by_us(
                FakeComment(id=1, body="said", user=FakeUser(_ALLOWED_LOGIN)),
                bot_login=None,
            ),
        )


class ReservedMarkerTest(unittest.TestCase):
    """What content somebody else wrote may not claim to be.

    Every hidden receipt this orchestrator writes shares one prefix, and each
    is a claim that a step already happened. A body search cannot tell a
    quoted one from a stamped one, so content carrying one is refused where it
    is declared.
    """

    def test_it_finds_a_marker_anywhere_in_the_text(self) -> None:
        for written in (
            "<!--orchestrator-late-child:issue=1:cycle=1:generation=1:index=0-->",
            "scope\n\n<!--orchestrator-late-split:cycle=1:generation=1-->\n",
            "leading text <!--orchestrator-state trailing text",
        ):
            with self.subTest(written=written):
                self.assertTrue(carries_reserved_marker(written))

    def test_ordinary_prose_and_comments_pass(self) -> None:
        for written in (
            "the first slice",
            "<!-- a note the author left -->",
            "mentions orchestrator markers without carrying one",
        ):
            with self.subTest(written=written):
                self.assertFalse(carries_reserved_marker(written))

    def test_what_is_not_text_carries_nothing(self) -> None:
        # A caller validating somebody else's structure: an absent title is
        # not a forged one.
        for written in (None, 7, ["<!--orchestrator-state"]):
            with self.subTest(written=written):
                self.assertFalse(carries_reserved_marker(written))


if __name__ == "__main__":
    unittest.main()
