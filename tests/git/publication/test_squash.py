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
TREE_FORMAT = "--pretty=%T"
SCRATCH_FILE = "scratch.txt"

# The switch the subject cases run under, set rather than inherited so an
# operator environment that turned it off cannot change what they read back,
# and the reference it ends each of their subjects in.
PR_REF_IN_SUBJECT = "PR_REF_IN_SUBJECT"
REFERENCE = f" (#{SQUASH_PR_NUMBER})"

# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"

# What the one commit a single-commit branch carries, the tracked issue's own
# reference -- the one number a publication takes OFF, since the pull request
# links this issue from its body -- and a reference to some other pull
# request, which is ordinary subject text the current one is still appended
# after.
SINGLE_SUBJECT = squash_support.SINGLE_SUBJECT
ISSUE_REFERENCE = squash_support.ISSUE_REFERENCE
ANOTHER_REFERENCE = " (#12)"


def _last_commit(worktree, pretty: str) -> str:
    """Read one `--pretty` field off the commit the squash left behind."""
    return squash_support.run_git(
        GIT_LOG,
        LAST_COMMIT,
        pretty,
        cwd=worktree,
    ).strip()


class _ReferencedSquashMixin:
    """One squash run with the pull-request reference switched on.

    Set rather than inherited, so an operator environment that turned the
    switch off cannot change what these cases read back.
    """

    def _referenced_squash(self, **squash_options):
        return self._squash(**squash_options, **{PR_REF_IN_SUBJECT: True})


class SquashSubjectSelectionTest(
    _ReferencedSquashMixin,
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

    def test_the_tracked_issue_reference_is_dropped(self) -> None:
        # The two ways the issue's number reaches a first commit subject: a
        # developer copied it out of recent history, and an earlier approval
        # round appended this pull request's beside it. The collapse keeps
        # neither, because the reference it writes names the pull request and
        # that request's own body is what links the issue.
        for first_subject in (
            f"fix: typo{ISSUE_REFERENCE}",
            f"fix: typo{ISSUE_REFERENCE}{REFERENCE}",
        ):
            with self.subTest(first_subject=first_subject):
                self._rebuild_topic((first_subject, "fix wording"), "i")

                squash_run = self._referenced_squash()

                self.assertTrue(squash_run.success, squash_run.error)
                self.assertEqual(squash_run.count, 2)
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


class SquashSingleCommitSubjectTest(
    _ReferencedSquashMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A branch of one commit, rewritten for its subject or left where it is.

    Nothing is collapsed on either road: the branch carries one commit before
    and one after. What decides between them is whether that subject already
    ends in this pull request's reference, so the rewrite is of the subject
    and the subject alone -- same tree, same reset, same gate, same leased
    push a collapse goes through.
    """

    def test_an_unreferenced_commit_is_rewritten(self) -> None:
        self._rebuild_single_commit()
        original_head = self._head_sha()
        original_tree = _last_commit(self.work, TREE_FORMAT)

        squash_run = self._referenced_squash()

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, 1)
        self.assertEqual(
            self._commits_on_branch(), [f"{SINGLE_SUBJECT}{REFERENCE}"],
        )
        # The subject is the whole of the rewrite: the commit the reviewer
        # approved is republished with the same tree under a new message.
        self.assertEqual(_last_commit(self.work, TREE_FORMAT), original_tree)
        pushed = squash_run.push_mock.call_args.kwargs
        self.assertEqual(pushed[REVISION], self._head_sha())
        self.assertEqual(pushed[LEASE], original_head)

    def test_a_foreign_reference_is_ordinary_text(self) -> None:
        # The formatter's own rule, one road over: only this pull request's
        # reference counts as already carried, so a subject naming another is
        # rewritten and the current reference is appended after it.
        self._rebuild_single_commit(f"{SINGLE_SUBJECT}{ANOTHER_REFERENCE}")

        squash_run = self._referenced_squash()

        self.assertEqual(squash_run.count, 1)
        self.assertEqual(
            self._commits_on_branch(),
            [f"{SINGLE_SUBJECT}{ANOTHER_REFERENCE}{REFERENCE}"],
        )

    def test_a_commit_carrying_the_issue_is_rewritten(self) -> None:
        # The shape a rewrite decided on the pull request alone calls
        # finished: one commit, already ending in this request's reference,
        # with the tracked issue's still standing ahead of it. Rewritten, and
        # the rewrite is idempotent -- the round after it finds nothing left
        # to do rather than stripping or appending again.
        for committed in (
            f"{SINGLE_SUBJECT}{ISSUE_REFERENCE}",
            f"{SINGLE_SUBJECT}{ISSUE_REFERENCE}{REFERENCE}",
        ):
            with self.subTest(committed=committed):
                self._rebuild_single_commit(committed)
                original_head = self._head_sha()

                squash_run = self._referenced_squash()

                self.assertTrue(squash_run.success, squash_run.error)
                self.assertEqual(squash_run.count, 1)
                self.assertEqual(
                    self._commits_on_branch(),
                    [f"{SINGLE_SUBJECT}{REFERENCE}"],
                )
                self.assertEqual(
                    squash_run.push_mock.call_args.kwargs[LEASE],
                    original_head,
                )
                rewritten = self._head_sha()

                second_round = self._referenced_squash()

                self.assertEqual(second_round.count, 0)
                second_round.push_mock.assert_not_called()
                self.assertEqual(self._head_sha(), rewritten)

    def test_a_referenced_commit_is_a_no_op(self) -> None:
        # The branch is already committed under the subject a publication
        # gives it, so there is nothing to rewrite and nothing to push.
        self._rebuild_single_commit(f"{SINGLE_SUBJECT}{REFERENCE}")
        original_head = self._head_sha()

        squash_run = self._referenced_squash()

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, 0)
        self.assertEqual(squash_run.sha, original_head)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), original_head)

    def test_a_branch_carrying_nothing_is_a_no_op(self) -> None:
        # No commit over the base is no commit to carry a subject either.
        self._rebuild_topic((), "n")
        original_head = self._head_sha()

        squash_run = self._referenced_squash()

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, 0)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), original_head)

    def test_a_second_round_doubles_nothing(self) -> None:
        # The approval that follows one this squash already published finds
        # the subject it wrote, so the rewrite is not made a second time.
        self._rebuild_single_commit()
        self._referenced_squash()
        rewritten = self._head_sha()

        squash_run = self._referenced_squash()

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, 0)
        squash_run.push_mock.assert_not_called()
        self.assertEqual(self._head_sha(), rewritten)
        self.assertEqual(
            self._commits_on_branch(), [f"{SINGLE_SUBJECT}{REFERENCE}"],
        )


class SquashSkipsRewriteTest(
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """Plan failures that must never reach the rewrite."""

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
