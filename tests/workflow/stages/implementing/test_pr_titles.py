# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for implementing pr titles behavior."""

from __future__ import annotations

import unittest

from tests.workflow.stages.implementing import pr_test_support as support

CONVENTIONAL_ISSUE = support.CONVENTIONAL_ISSUE
DEV_SESSION = support.DEV_SESSION
DONE_MESSAGE = support.DONE_MESSAGE
INFERRED_PREFIX_ISSUE = support.INFERRED_PREFIX_ISSUE
SPARKLY_COMMIT_SUBJECT = support.SPARKLY_COMMIT_SUBJECT
_ConventionalTitleFixtureMixin = support._ConventionalTitleFixtureMixin
_agent = support._agent


class ConventionalPrTitleTest(
    unittest.TestCase,
    _ConventionalTitleFixtureMixin,
):
    """`_on_commits` opens the PR with the title the `dev_pr` owner picks from
    the agent's first commit subject and the inferred repo prefix, and keeps
    traceability in the body."""

    def test_uses_selected_title_and_links_the_issue(self) -> None:
        # Both subjects reach the same title, since the PR title is the first
        # commit subject with no prefix added and the tracked issue's
        # reference taken off. A subject written under the commit-subject
        # contract carries no such reference; the second case is the one that
        # contract does not reach -- a commit made before it, or one written
        # by hand -- and the number belongs on the body's `Resolves` line.
        for case, first_subject in (
            ("no reference", SPARKLY_COMMIT_SUBJECT),
            (
                "an issue reference the contract forbids",
                f"{SPARKLY_COMMIT_SUBJECT} (#{CONVENTIONAL_ISSUE})",
            ),
        ):
            with self.subTest(case=case):
                self._assert_titled(first_subject)

    def test_inferred_repo_prefix_reaches_the_title(self) -> None:
        # First commit subject is unprefixed, so the handler must thread the
        # prefix `_infer_subject_prefix` read from base history into the
        # synthesized title instead of defaulting to `feat:`.
        gh, issue = self._seeded(issue_number=INFERRED_PREFIX_ISSUE)

        self._run_implementing(
            gh,
            issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=DONE_MESSAGE),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
            first_commit_subject="updated the listings",
            fallback_prefix="career",
        )

        self.assertEqual(gh.opened_prs[0].title, "career: add a sparkly thing")

    def _assert_titled(self, first_subject: str) -> None:
        # One client per case: each seeds, runs, and asserts on its own issue,
        # so a PR opened by one cannot be read back by the next.
        gh, issue = self._seeded(issue_number=CONVENTIONAL_ISSUE)

        self._run_implementing(
            gh,
            issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=DONE_MESSAGE),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
            first_commit_subject=first_subject,
        )

        self.assertEqual(len(gh.opened_prs), 1)
        pr = gh.opened_prs[0]
        self.assertEqual(pr.title, SPARKLY_COMMIT_SUBJECT)
        self.assertIn(f"Resolves #{issue.number}", pr.body)
