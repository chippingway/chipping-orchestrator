# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The agent-message contract.

Two behaviors carry the weight here. A drift acknowledgement needs the
explicit `ACK:` marker, so a clarification question is never mistaken for
agreement. And `/orchestrator continue` is classified before it is obeyed, so
a content-free nudge retries a session failure but is refused on a park that
is waiting for a real answer.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, messages
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.interleaving import _RacesPastTheStep

_CONTINUE_COMMAND = "/orchestrator continue"
_SHA_LENGTH = 40
_COMMIT = "a" * _SHA_LENGTH
_REFUSAL_ISSUE_NUMBER = 1011
_WATERMARK_KEY = "last_action_comment_id"
_COMMAND_ID = 1
_GUIDANCE = "no -- rename the flag first"
_POST_ISSUE_COMMENT = "_post_issue_comment"


class DriftAckMarkerTest(unittest.TestCase):
    """A generic non-empty no-commit response is OFTEN a clarification
    question, not an ack. Only an explicit `ACK: ...` marker counts as
    acknowledgement; everything else leaves the caller on its park path."""

    def test_explicit_ack_marker_extracts_reason(self) -> None:
        msg = (
            "I reviewed the change.\n\n"
            "ACK: existing tests already cover the new requirement"
        )
        self.assertEqual(
            messages._drift_ack_reason(msg),
            "existing tests already cover the new requirement",
        )

    def test_ack_is_case_insensitive_and_last_wins(self) -> None:
        # Case insensitive (mirrors VERDICT parsing) and the LAST marker
        # wins so a sample/template `ACK:` quoted earlier in the message
        # doesn't override the agent's real concluding marker.
        msg = (
            "I considered ack: stale-template-text but on re-reading\n\n"
            "ack: real final justification"
        )
        self.assertEqual(
            messages._drift_ack_reason(msg), "real final justification",
        )

    def test_unmarked_prose_is_not_an_ack(self) -> None:
        for msg in (
            "Existing code already covers this; no change needed.",
            "Should I also handle the empty-input case?",
            "",
        ):
            with self.subTest(message=msg):
                self.assertIsNone(messages._drift_ack_reason(msg))


class ContinueCommandRecognitionTest(unittest.TestCase):
    """Which comments carry the operator command, and which of those carry
    nothing but the command."""

    def test_parser_matches_exact_continue_line(self) -> None:
        comments = [
            FakeComment(id=1, body=_CONTINUE_COMMAND),
            FakeComment(id=2, body="  /Orchestrator  Continue  "),
            FakeComment(id=3, body="/orchestrator continue\n"),
            FakeComment(id=4, body="please run `/orchestrator continue`"),
            FakeComment(id=5, body="please fix X\n/orchestrator continue"),
            FakeComment(id=6, body="/orchestrator continue\nthanks"),
            FakeComment(id=7, body="/orchestrator add-review-rounds 2"),
        ]

        matched = messages._parse_orchestrator_continue(comments)

        # Any comment carrying the command as an exact line matches -- including
        # one that also carries guidance (5, 6) -- so the command still fires
        # the replay. A prose mention in backticks (4) and a different command
        # (7) do not.
        matched_ids = [comment.id for comment in matched]
        self.assertEqual(matched_ids, [1, 2, 3, 5, 6])

    def test_bare_is_distinguished_from_guided(self) -> None:
        # `_is_bare_*` distinguishes a content-free nudge (whole body is the
        # command, whitespace ignored) from a comment that also carries
        # guidance -- the latter must not be refused/consumed as content-free.
        bare_bodies = (
            _CONTINUE_COMMAND,
            "  /Orchestrator  Continue  ",
            "/orchestrator continue\n",
        )
        guided_bodies = (
            "please fix X\n/orchestrator continue",
            "/orchestrator continue\nthanks",
            "please run `/orchestrator continue`",
        )
        for body in bare_bodies:
            with self.subTest(bare=body):
                self.assertTrue(
                    messages._is_bare_orchestrator_continue(
                        FakeComment(id=1, body=body),
                    ),
                )
        for body in guided_bodies:
            with self.subTest(guided=body):
                self.assertFalse(
                    messages._is_bare_orchestrator_continue(
                        FakeComment(id=1, body=body),
                    ),
                )


class AuthorizeOversizedRecognitionTest(unittest.TestCase):
    """Which comments carry the authorization, and what commit each names.

    Only a WHOLE comment is ever the command, because what it licenses is a
    bypass of the size gate: a line of it under a paragraph is text that
    mentions the command rather than a decision anybody made, and that
    paragraph reaches the stage as guidance instead.
    """

    def test_a_whole_comment_names_its_commit(self) -> None:
        named = {
            f"/orchestrator authorize-oversized {_COMMIT}": _COMMIT,
            f"  /Orchestrator  Authorize-Oversized  {_COMMIT}  ": _COMMIT,
            f"/orchestrator authorize-oversized {_COMMIT}\n": _COMMIT,
            # A malformed argument is still the command, and the caller owes
            # it an answer rather than reading it as somebody's requirements.
            "/orchestrator authorize-oversized the one above": "the one above",
            "/orchestrator authorize-oversized": "",
        }
        for body, commit in named.items():
            with self.subTest(body=body):
                self.assertEqual(
                    messages._authorized_oversized_candidate(
                        FakeComment(id=1, body=body),
                    ),
                    commit,
                )

    def test_less_than_the_whole_comment_is_prose(self) -> None:
        prose = (
            f"ship it\n/orchestrator authorize-oversized {_COMMIT}",
            f"/orchestrator authorize-oversized {_COMMIT}\nthanks",
            f"run `/orchestrator authorize-oversized {_COMMIT}`",
            _CONTINUE_COMMAND,
            "",
        )
        for body in prose:
            with self.subTest(body=body):
                self.assertIsNone(
                    messages._authorized_oversized_candidate(
                        FakeComment(id=1, body=body),
                    ),
                )


class ContinueCommandActionTest(unittest.TestCase):
    """`_continue_command_action` classifies an operator `/orchestrator
    continue` on a parked dev-session stage. Retryable session-failure parks
    with a content-free nudge retry; parks needing a real answer refuse;
    anything else (no command, or a command carrying guidance) passes through
    to the normal resume / drift path."""

    def test_retryable_park_bare_continue_retries(self) -> None:
        self.assertIn("agent_execution_failed", messages._CONTINUE_PARK_REASONS)
        for reason in sorted(messages._CONTINUE_PARK_REASONS):
            with self.subTest(reason=reason):
                self.assertEqual(
                    messages._continue_command_action(
                        [FakeComment(id=1, body=_CONTINUE_COMMAND)], reason,
                    ),
                    "retry",
                )

    def test_non_retryable_park_bare_continue_refuses(self) -> None:
        for reason in (None, "dirty_worktree", "diverged_branch"):
            with self.subTest(reason=reason):
                self.assertEqual(
                    messages._continue_command_action(
                        [FakeComment(id=1, body=_CONTINUE_COMMAND)], reason,
                    ),
                    "refuse",
                )

    def test_guidance_or_no_command_passes_through(self) -> None:
        # With guidance alongside the command, the normal resume/drift path
        # has to feed that guidance to the dev instead of consuming the
        # comment as a bare nudge.
        for body in (f"{_CONTINUE_COMMAND}\nrename the flag", "just a normal reply"):
            with self.subTest(body=body):
                self.assertEqual(
                    messages._continue_command_action(
                        [FakeComment(id=1, body=body)], "agent_silent",
                    ),
                    "passthrough",
                )


class RefuseParkedContinueTest(unittest.TestCase):
    """What a refusal consumes, which is the command it answers and our note.

    The command has to go, or the refusal re-fires and re-posts on every
    following tick. Nothing ELSE may go with it: what the caller classified is
    a batch it read before this call, and the minutes around a post are time a
    human can write real guidance in -- marked answered here, that guidance is
    consumed by a decision that never considered it and by an agent that never
    saw it.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_REFUSAL_ISSUE_NUMBER)
        self.github.add_issue(self.issue)
        self.issue.comments.append(
            FakeComment(id=_COMMAND_ID, body=_CONTINUE_COMMAND),
        )
        self.state = PinnedState(state_data={})

    def test_refusal_advances_the_watermark(self) -> None:
        messages._refuse_parked_continue(
            self.github, self.issue, self.state, list(self.issue.comments),
        )

        _issue_number, posted_body = self.github.posted_comments[-1]
        self.assertIn("needs your actual", posted_body)
        # Past BOTH the command and the refusal itself.
        self.assertEqual(
            self.state.get(_WATERMARK_KEY),
            self.github.latest_comment_id(self.issue),
        )

    def test_guidance_written_as_it_refuses_survives(self) -> None:
        refused = list(self.issue.comments)
        landed = []
        racing = _RacesPastTheStep(
            _comments._post_issue_comment, lambda: landed.append(self._reply()),
        )

        with patch.object(_comments, _POST_ISSUE_COMMENT, racing):
            messages._refuse_parked_continue(
                self.github, self.issue, self.state, refused,
            )

        # The command and our own note are crossed; the guidance written over
        # them is the next poll's to deliver.
        self.assertEqual(len(landed), 1)
        self.assertGreater(self.state.get(_WATERMARK_KEY), _COMMAND_ID)
        self.assertLess(self.state.get(_WATERMARK_KEY), landed[0])

    def _reply(self) -> int:
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, _GUIDANCE, user=FakeUser("alice")),
        )
        return identified


if __name__ == "__main__":
    unittest.main()
