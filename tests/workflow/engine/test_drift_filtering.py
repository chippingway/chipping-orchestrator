# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Workflow drift comment-filter and marker tests."""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import comments, content_hash as _content_hash
from tests.workflow.engine import drift_test_support as support


class OrchCommentMarkerSurvivesIdCapTest(unittest.TestCase):
    """Reviewer point 3: `orchestrator_comment_ids` is capped, but the
    hash scans every comment. Once an old orchestrator-comment id is
    evicted from the cap, an id-only filter would start including the
    bot comment in the hash and trigger false drift on every dispatch. The body
    marker (`_ORCH_COMMENT_MARKER`) must keep the hash stable."""

    def test_unknown_id_bot_comment_is_excluded(
        self,
    ) -> None:
        # Simulate an orchestrator comment whose id has been evicted
        # from the bounded cap. Its body still carries the marker
        # (because every orchestrator comment is posted with it), so
        # the hash filter must drop it.
        bot_body = f"picking this up\n\n{comments._ORCH_COMMENT_MARKER}"
        bot = support.FakeComment(
            id=support._EVICTED_BOT_COMMENT_ID,
            body=bot_body,
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        human = support.FakeComment(
            id=support._HUMAN_COMMENT_ID,
            body="please reconsider",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        issue_with_just_human = support.make_issue(1, comments=[human])
        issue_with_both = support.make_issue(1, comments=[bot, human])
        # `orchestrator_ids` is EMPTY (the id was evicted from the cap),
        # but the hash must still match because the marker identifies
        # the bot comment.
        self.assertEqual(
            _content_hash._compute_user_content_hash(
                issue_with_just_human, set()
            ),
            _content_hash._compute_user_content_hash(
                issue_with_both, set()
            ),
        )


class HashFiltersBotUsersTest(unittest.TestCase):
    """Reviewer point 2: third-party Bot/App accounts (Dependabot,
    Renovate, CI bots) post comments structurally on long-lived issues.
    The hash must filter them by GitHub's `user.type == "Bot"` flag so
    a periodic bot comment doesn't re-trigger drift every time it
    posts. Login matching is intentionally avoided because the
    orchestrator PAT may be shared with a human reviewer's account."""

    def test_bot_authored_comment_is_filtered(self) -> None:
        # A Dependabot-style comment must NOT affect the hash even
        # though its body is unique and its id is not tracked.
        human = support.FakeComment(
            id=support._BOT_FILTER_HUMAN_COMMENT_ID,
            body="real human comment",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        bot_comment = support.FakeComment(
            id=support._BOT_FILTER_BOT_COMMENT_ID,
            body="Bumps `requests` from 2.31.0 to 2.32.0",
            user=support.FakeUser("dependabot[bot]", type="Bot"),
        )
        issue_with_just_human = support.make_issue(1, comments=[human])
        issue_with_bot = support.make_issue(1, comments=[human, bot_comment])
        self.assertEqual(
            _content_hash._compute_user_content_hash(
                issue_with_just_human, set()
            ),
            _content_hash._compute_user_content_hash(
                issue_with_bot, set()
            ),
        )

    def test_user_type_human_still_contributes(self) -> None:
        # A regular human user's `type == "User"` must NOT be filtered.
        comment = support.FakeComment(
            id=support._TYPED_HUMAN_COMMENT_ID,
            body="adds an acceptance criterion",
            user=support.FakeUser(support.TRUSTED_AUTHOR, type="User"),
        )
        empty = support.make_issue(1)
        with_human = support.make_issue(1, comments=[comment])
        self.assertNotEqual(
            _content_hash._compute_user_content_hash(empty, set()),
            _content_hash._compute_user_content_hash(with_human, set()),
        )


class HashFiltersBareOperatorCommandTest(unittest.TestCase):
    """A whole-comment operator command is a control, not requirements.

    Each is written on an issue the tick that answers it is about to hand
    straight to a stage handler -- the stage below on a run grant, the stage
    an authorized publication continues at on the other -- so a hash that
    counted one would report a body edit nobody made, on the one tick where
    the issue is going back to work.
    """

    def test_the_bare_command_leaves_the_hash_alone(self) -> None:
        # In both modes: the legacy algorithm the flag reproduces predates
        # both commands, so a baseline recomputed WITH one would fail to
        # recognize itself and report the control as an edit.
        silent = support.make_issue(1)
        for command in support.OPERATOR_COMMANDS:
            commanded = self._issue_with(command)
            for legacy in (False, True):
                with self.subTest(command=command, legacy=legacy):
                    self.assertEqual(
                        _content_hash._compute_user_content_hash(
                            silent, set(), include_bare_continue=legacy,
                        ),
                        _content_hash._compute_user_content_hash(
                            commanded, set(), include_bare_continue=legacy,
                        ),
                    )

    def test_guidance_beside_the_command_still_counts(self) -> None:
        # Words beside the command are requirements, and the drift road they
        # open is how they reach the agent that has to act on them.
        for command in support.OPERATOR_COMMANDS:
            with self.subTest(command=command):
                guided = self._issue_with(
                    f"{command}\n\nalso handle empty input",
                )
                self.assertNotEqual(
                    _content_hash._compute_user_content_hash(
                        support.make_issue(1), set(),
                    ),
                    _content_hash._compute_user_content_hash(guided, set()),
                )

    def _issue_with(self, body: str):
        return support.make_issue(1, comments=[support.FakeComment(
            id=support._ADD_AGENT_RUNS_COMMENT_ID,
            body=body,
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )])


if __name__ == "__main__":
    unittest.main()
