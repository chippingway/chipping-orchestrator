# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How `squash` sequences the plan and the rewrite against a real repository."""

from __future__ import annotations

import unittest

from tests.git.publication import squash_git_support as squash_support
from tests.git.publication.squash_gate_support import SQUASH_PR_NUMBER, PublicationSeed

GIT_LOG = "log"
LAST_COMMIT = "-1"
SUBJECT_FORMAT = "--pretty=%s"
FULL_MESSAGE_FORMAT = "--pretty=%B"
SCRATCH_FILE = "scratch.txt"

# The switch the subject cases run under, set rather than inherited so an
# operator environment that turned it off cannot change what they read back,
# and the reference it ends each of their subjects in.
PR_REF_IN_SUBJECT = "PR_REF_IN_SUBJECT"
REFERENCE = f" (#{SQUASH_PR_NUMBER})"


def _last_commit(worktree, pretty: str) -> str:
    """Read one `--pretty` field off the commit the squash left behind."""
    return squash_support.run_git(
        GIT_LOG,
        LAST_COMMIT,
        pretty,
        cwd=worktree,
    ).strip()


class SquashSubjectSelectionTest(
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """The committed subject is the one the plan selected, referencing its PR."""

    def test_squash_collapses_three_commits_to_one(self) -> None:
        # First commit's subject ("fix: typo") is conventional-commit form,
        # so the squash subject reuses it and ends it in the pull request's
        # reference. The squash message is subject-only: the repo's
        # Conventional-Commits-subject-only rule forbids bodies on
        # orchestrator-authored commits.
        squash_run = self._referenced_squash()
        self.assertTrue(
            squash_run.success,
            f"expected success, got err={squash_run.error!r}",
        )
        self.assertIsNone(squash_run.error)
        self.assertEqual(squash_run.count, 3)
        self.assertTrue(squash_run.sha)

        commits = self._commits_on_branch()
        self.assertEqual(
            len(commits),
            1,
            f"expected one commit on top of base, got {commits!r}",
        )
        # Squash subject reuses the conventional-commit first subject.
        self.assertEqual(commits[0], f"fix: typo{REFERENCE}")
        # Body is empty (subject-only commit): the repo's commit-style
        # rule forbids a body or trailer on orchestrator-authored
        # commits, so the squash MUST NOT carry a `Squashed commits: -...`
        # listing.
        body = _last_commit(self.work, FULL_MESSAGE_FORMAT)
        self.assertEqual(body, f"fix: typo{REFERENCE}")
        self.assertNotIn("Squashed commits:", body)

    def test_issue_title_used_without_conventional(
        self,
    ) -> None:
        # Reset and rebuild the branch with non-conv-commit first subject.
        self._rebuild_topic(("typo fix", "feat: add foo"), "g")
        squash_run = self._referenced_squash(
            publication=PublicationSeed(
                issue=self._make_issue(title="rename frobnicator"),
            ),
        )
        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, 2)

        self.assertEqual(
            _last_commit(self.work, SUBJECT_FORMAT),
            f"feat: rename frobnicator{REFERENCE}",
        )

    def test_keeps_custom_prefix_first_subject(self) -> None:
        # A repo-local first-commit prefix that is NOT a Conventional type
        # (e.g. a careers site's `career:`) is reused verbatim as the squash
        # subject rather than discarded for a synthesized `feat: <title>`.
        self._rebuild_topic(
            ("career: add a senior role", "fix wording"),
            "c",
        )
        squash_run = self._referenced_squash(
            publication=PublicationSeed(
                issue=self._make_issue(title="hiring page"),
            ),
        )
        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, 2)
        self.assertEqual(
            _last_commit(self.work, SUBJECT_FORMAT),
            f"career: add a senior role{REFERENCE}",
        )

    def test_a_referenced_subject_is_not_doubled(self) -> None:
        # A second approval round reuses the subject the first one squashed
        # to, which already ends in this pull request's reference.
        self._rebuild_topic((f"fix: typo{REFERENCE}", "fix wording"), "r")
        squash_run = self._referenced_squash()
        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(
            _last_commit(self.work, FULL_MESSAGE_FORMAT),
            f"fix: typo{REFERENCE}",
        )

    def test_infers_prefix_from_base_history(self) -> None:
        # No reusable first-commit subject, so the squash subject is
        # synthesized -- and it honors the repo-local `event:` prefix that
        # dominates recent base-branch history instead of defaulting to
        # `feat:`.
        # Seed the base branch with a history dominated by `event:`.
        self._seed_inferred_prefix_history()
        squash_run = self._referenced_squash(
            publication=PublicationSeed(
                issue=self._make_issue(title="redesign the homepage"),
            ),
        )
        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, 2)
        self.assertEqual(
            _last_commit(self.work, SUBJECT_FORMAT),
            f"event: redesign the homepage{REFERENCE}",
        )

    def _referenced_squash(self, **squash_options):
        """One squash run with the pull-request reference switched on."""
        return self._squash(**squash_options, **{PR_REF_IN_SUBJECT: True})


class SquashSkipsRewriteTest(
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """Branch shapes and plan failures that must never reach the rewrite."""

    def test_squash_with_only_one_commit_is_a_no_op(self) -> None:
        # Reset to a single commit on top of base.
        self._rebuild_single_commit()
        original_head = self._head_sha()

        squash_run = self._squash()
        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, 0)
        self.assertEqual(squash_run.sha, original_head)
        # Single-commit branch must NOT trigger a push at all.
        squash_run.push_mock.assert_not_called()
        # HEAD unchanged.
        self.assertEqual(self._head_sha(), original_head)

    def test_dirty_worktree_aborts_before_reset(self) -> None:
        # An uncommitted change in the worktree (the agent left work
        # behind) is a refuse-to-rewrite signal: the helper must abort
        # WITHOUT touching HEAD so the dirty state is visible to the
        # operator. Without the pre-reset dirty check the soft-reset
        # would happen and the rollback would clobber the dirty changes.
        original_head = self._head_sha()
        (self.work / SCRATCH_FILE).write_text("uncommitted\n")

        squash_run = self._squash()
        self.assertFalse(squash_run.success)
        self.assertIn("uncommitted", squash_run.error or "")
        # HEAD untouched, dirty file preserved, no push attempted.
        self.assertEqual(self._head_sha(), original_head)
        self.assertTrue((self.work / SCRATCH_FILE).exists())
        squash_run.push_mock.assert_not_called()

    def test_dirty_single_commit_still_fails(self) -> None:
        # The dirty-tree refusal is a precondition for the whole helper,
        # not just the rewrite path. A one-commit branch (squash would
        # be a no-op) with an uncommitted file must still fail so the
        # caller parks awaiting_human; otherwise the manual merge could
        # land the head with the operator's scratch invisible on the PR.
        self._rebuild_single_commit()
        original_head = self._head_sha()
        (self.work / SCRATCH_FILE).write_text("uncommitted\n")

        squash_run = self._squash()
        self.assertFalse(squash_run.success)
        self.assertIsNone(squash_run.sha)
        self.assertEqual(squash_run.count, 0)
        self.assertIn("uncommitted", squash_run.error or "")
        # Single-commit + dirty path must NOT short-circuit to the
        # no-op success branch. HEAD untouched, dirty file preserved,
        # no push attempted.
        self.assertEqual(self._head_sha(), original_head)
        self.assertTrue((self.work / SCRATCH_FILE).exists())
        squash_run.push_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
