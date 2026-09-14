# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Both directions of the comment owner.

The write side keeps the ledger every "is this comment ours?" scan reads: one
bounded id list spanning both comment surfaces, plus the hidden marker that
outlives eviction from it.

The read side is where `ALLOWED_ISSUE_AUTHORS` becomes a trust boundary. Every
conversation-carrying agent prompt draws its thread text through
`_recent_comments_text`, so an untrusted author's comment has to be dropped
whole -- body and any URLs it carries -- before a coding agent can act on it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments, prompt_context as _prompt_context
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.engine import comment_trust_test_support as trust

_LEDGER_KEY = "orchestrator_comment_ids"
_LEDGER_ISSUE_NUMBER = 1010
_LEDGER_PR_NUMBER = 77
_THREAD_ISSUE_NUMBER = 1011
_ISSUE_BODY = "picking up"


class OrchestratorCommentLedgerTest(unittest.TestCase):
    """One bounded id list and one marker cover both surfaces we post to."""

    def setUp(self) -> None:
        self.gh = FakeGitHubClient()
        self.issue = make_issue(_LEDGER_ISSUE_NUMBER)
        self.gh.add_issue(self.issue)
        self.state = PinnedState(state_data={})

    def test_both_surfaces_land_in_one_id_list(self) -> None:
        # Issue and PR-conversation comments share the IssueComment id space,
        # so the scans that filter "ours" only ever consult this one list.
        issue_comment = comments._post_issue_comment(
            self.gh, self.issue, self.state, _ISSUE_BODY,
        )
        pr_comment = comments._post_pr_comment(
            self.gh, _LEDGER_PR_NUMBER, self.state, "rebased onto base",
        )

        posted_ids = [issue_comment.id, pr_comment.id]
        self.assertEqual(self.state.get(_LEDGER_KEY), posted_ids)
        self.assertEqual(comments._orchestrator_ids(self.state), set(posted_ids))

    def test_every_posted_body_carries_the_marker(self) -> None:
        # The marker is what identifies a bot comment once its id has aged out
        # of the list below, so it has to be on the body that actually shipped
        # -- appended to the caller's text, not in place of it.
        comments._post_issue_comment(self.gh, self.issue, self.state, _ISSUE_BODY)
        comments._post_pr_comment(self.gh, _LEDGER_PR_NUMBER, self.state, "rebased")

        marker = comments._ORCH_COMMENT_MARKER
        issue_body = self.gh.posted_comments[-1][1]
        self.assertIn(marker, issue_body)
        self.assertTrue(issue_body.startswith(_ISSUE_BODY))
        self.assertIn(marker, self.gh.posted_pr_comments[-1][1])

    def test_marker_is_idempotent_on_double_wrap(self) -> None:
        # A caller that passes a body already carrying the marker (a helper
        # chain forwarding a pre-built body) must not get a second copy.
        marked = comments._with_orch_marker("hi")

        twice = comments._with_orch_marker(marked)

        self.assertEqual(marked, twice)
        self.assertEqual(twice.count(comments._ORCH_COMMENT_MARKER), 1)

    def test_ledger_evicts_the_oldest_ids_at_the_cap(self) -> None:
        # A long-lived issue would grow the pinned comment unboundedly without
        # this; the newest ids are the ones a fresh feedback scan can still see.
        cap = comments._ORCH_COMMENT_ID_CAP
        self.state.set(_LEDGER_KEY, list(range(cap)))

        comments._track_orchestrator_comment(self.state, cap)

        retained = list(range(1, cap + 1))
        self.assertEqual(self.state.get(_LEDGER_KEY), retained)


class RecentCommentsTrustFilterTest(unittest.TestCase):
    """The thread read is where the allowlist stops an injected comment."""

    def test_outsider_dropped_allowed_kept(self) -> None:
        with patch.object(config, trust.ALLOWLIST_CONFIG, (trust.ALLOWED_AUTHOR,)):
            text = _prompt_context._recent_comments_text(trust.issue_with_comments())

        self.assertNotIn(trust.MALICIOUS_URL, text)
        self.assertNotIn(trust.PATCH_INSTRUCTION, text)
        self.assertIn(trust.ALLOWED_MARKER, text)

    def test_empty_allowlist_keeps_the_full_thread(self) -> None:
        # The filter is opt-in: with no allowlist configured the outsider's
        # comment still reaches the prompt (legacy single-user behavior).
        with patch.object(config, trust.ALLOWLIST_CONFIG, ()):
            text = _prompt_context._recent_comments_text(trust.issue_with_comments())

        self.assertIn(trust.MALICIOUS_URL, text)
        self.assertIn(trust.ALLOWED_MARKER, text)


class ThreadTextParagraphsTest(unittest.TestCase):
    """Quoted comments reach a prompt as separate paragraphs.

    The prompt builders assemble their own sections around this text with the
    same break, so a thread that ran together with the sections framing it
    would read to the agent as one undifferentiated block.
    """

    def test_kept_comments_are_joined_by_a_blank_line(self) -> None:
        issue = make_issue(
            _THREAD_ISSUE_NUMBER,
            comments=[
                FakeComment(1, "please rebase", FakeUser("alice")),
                FakeComment(2, "and squash", FakeUser("bob")),
            ],
        )

        with patch.object(config, trust.ALLOWLIST_CONFIG, ()):
            text = _prompt_context._recent_comments_text(issue)

        self.assertEqual(text, "@alice: please rebase\n\n@bob: and squash")


class QuoteCommentLineTest(unittest.TestCase):
    """`_quote_comment_line` is the shared `@author[label]: body` formatter the
    resume/followup prompt builders and the fresh-comment stage handlers fold
    each already-selected comment through."""

    def test_author_body_label_and_fallbacks(self) -> None:
        cases = (
            (FakeComment(1, "please rebase", FakeUser("alice")), "", "@alice: please rebase"),
            (FakeComment(2, "on the PR", FakeUser("bob")), " (PR comment)",
             "@bob (PR comment): on the PR"),
            (FakeComment(3, "no account", None), "", "@user: no account"),
            (FakeComment(4, None, FakeUser("carol")), "", "@carol: "),
        )
        for comment, label, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    _prompt_context._quote_comment_line(comment, label), expected,
                )


if __name__ == "__main__":
    unittest.main()
