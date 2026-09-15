# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Squash preparation probes and message selection on the `planning` owner."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import commands
from orchestrator.git.publication import planning, titles
from orchestrator.git.verification import probes as verification_probes, status as _worktree_status
from tests.git.publication.publication_helpers import (
    GIT_HELPER,
    WORKTREE,
    _git_result,
    _spec,
)
from tests.support.fakes import make_issue

BASE_SHA = "base1234"
ORIGINAL_HEAD = "head5678"
PLAN_ISSUE = 60
PLAN_PR = 61
PLAN_PR_REFERENCE = f" (#{PLAN_PR})"
ISSUE_TITLE = "add a sparkly thing"
PREFIXED_SUBJECT = "fix: typo"
PLAIN_SUBJECT = "add foo"
GIT_FAILURE_EXIT_CODE = 128
PREPARATION_ERROR = planning._SquashPreparationError
HEAD_HELPER = "_head_sha"
DIRTY_HELPER = "_worktree_dirty_files"
INFER_HELPER = "_infer_subject_prefix"


def _failed_git(stderr: str) -> MagicMock:
    """Serve a single failed git read carrying `stderr`."""
    return MagicMock(
        side_effect=[
            _git_result(returncode=GIT_FAILURE_EXIT_CODE, stderr=stderr),
        ],
    )


class SquashBaseShaTest(unittest.TestCase):
    """`_squash_base_sha` reads the merge base the rewrite resets onto."""

    def test_merge_base_honors_the_spec_remote(self) -> None:
        git = MagicMock(side_effect=[_git_result(stdout=f"{BASE_SHA}\n")])
        with patch.object(commands, GIT_HELPER, git):
            base_sha = planning._squash_base_sha(
                _spec(base_branch="master", remote_name="private"),
                WORKTREE,
            )
        self.assertEqual(base_sha, BASE_SHA)
        self.assertIn("private/master", git.call_args.args)

    def test_failed_merge_base_carries_the_git_detail(self) -> None:
        git = _failed_git("fatal: bad revision\n")
        with patch.object(commands, GIT_HELPER, git), self.assertRaisesRegex(PREPARATION_ERROR, "bad revision"):
            planning._squash_base_sha(_spec(), WORKTREE)

    def test_empty_merge_base_refuses_to_plan(self) -> None:
        # Unrelated histories exit 0 with no output; an empty base would
        # otherwise become the `reset --soft` target and drop the branch.
        git = MagicMock(side_effect=[_git_result(stdout="\n")])
        with patch.object(commands, GIT_HELPER, git), self.assertRaisesRegex(PREPARATION_ERROR, "empty"):
            planning._squash_base_sha(_spec(), WORKTREE)


class SquashSubjectsTest(unittest.TestCase):
    """`_squash_subjects` reads the topic commits oldest-first."""

    def test_orders_subjects_over_the_base_range(self) -> None:
        git = MagicMock(
            side_effect=[
                _git_result(stdout=f"{PREFIXED_SUBJECT}\n\n{PLAIN_SUBJECT}\n"),
            ],
        )
        with patch.object(commands, GIT_HELPER, git):
            subjects = planning._squash_subjects(WORKTREE, BASE_SHA)
        # Blank log lines are dropped so they cannot become a squash subject.
        self.assertEqual(subjects, (PREFIXED_SUBJECT, PLAIN_SUBJECT))
        self.assertIn(f"{BASE_SHA}..HEAD", git.call_args.args)

    def test_failed_log_carries_the_git_detail(self) -> None:
        git = _failed_git("fatal: bad object\n")
        with patch.object(commands, GIT_HELPER, git), self.assertRaisesRegex(PREPARATION_ERROR, "bad object"):
            planning._squash_subjects(WORKTREE, BASE_SHA)


class SquashMessageTest(unittest.TestCase):
    """`_squash_message` builds the subject-only squash commit message."""

    def test_reusable_first_subject_is_kept_verbatim(self) -> None:
        infer = MagicMock()
        with patch.object(titles, INFER_HELPER, infer):
            message = self._message(PREFIXED_SUBJECT)
        self.assertEqual(message, f"{PREFIXED_SUBJECT}\n")
        # A reusable subject needs no synthesized one, so the base-history
        # read that prefix inference costs is skipped entirely.
        infer.assert_not_called()

    def test_unprefixed_subject_uses_inferred_prefix(self) -> None:
        with patch.object(titles, INFER_HELPER, return_value="event"):
            message = self._message(PLAIN_SUBJECT)
        self.assertEqual(message, f"event: {ISSUE_TITLE}\n")

    def test_both_roads_end_in_one_reference(self) -> None:
        # Equality with the whole message is what rules out a body or trailer
        # riding along, and the last case is a first subject an earlier
        # approval round already squashed to.
        for first_subject, subject in (
            (PREFIXED_SUBJECT, PREFIXED_SUBJECT),
            (PLAIN_SUBJECT, f"event: {ISSUE_TITLE}"),
            (f"{PREFIXED_SUBJECT}{PLAN_PR_REFERENCE}", PREFIXED_SUBJECT),
        ):
            with (
                self.subTest(first_subject=first_subject),
                patch.object(titles, INFER_HELPER, return_value="event"),
            ):
                self.assertEqual(
                    self._message(first_subject, PLAN_PR),
                    f"{subject}{PLAN_PR_REFERENCE}\n",
                )

    def _message(
        self, first_subject: str, pr_number: int | None = None,
    ) -> str:
        return planning._squash_message(
            _spec(),
            WORKTREE,
            make_issue(PLAN_ISSUE, title=ISSUE_TITLE),
            (first_subject, PLAIN_SUBJECT),
            pr_number,
        )


class PrepareSquashTest(unittest.TestCase):
    """`_prepare_squash` collects the plan while the branch is still intact."""

    def test_multi_commit_plan_pins_head_and_message(self) -> None:
        plan = self._prepare(self._git_reading(PREFIXED_SUBJECT, PLAIN_SUBJECT))
        self.assertEqual(plan.base_sha, BASE_SHA)
        self.assertEqual(plan.original_head, ORIGINAL_HEAD)
        self.assertEqual(plan.subjects, (PREFIXED_SUBJECT, PLAIN_SUBJECT))
        self.assertEqual(plan.count, 2)
        self.assertEqual(plan.message, f"{PREFIXED_SUBJECT}{PLAN_PR_REFERENCE}\n")

    def test_single_commit_plan_carries_no_message(self) -> None:
        # Nothing to squash, so no message is built -- the caller reads the
        # subject count and returns the untouched head.
        plan = self._prepare(self._git_reading(PREFIXED_SUBJECT))
        self.assertEqual(plan.subjects, (PREFIXED_SUBJECT,))
        self.assertEqual(plan.count, 1)
        self.assertEqual(plan.message, "")

    def test_unreadable_head_aborts_before_log_read(self) -> None:
        self._assert_aborts_after_merge_base("original HEAD", head="")

    def test_dirty_worktree_aborts_before_log_read(self) -> None:
        # The agent left work behind; refusing here keeps the uncommitted
        # files visible instead of letting the rewrite's rollback clobber them.
        self._assert_aborts_after_merge_base(
            "uncommitted changes",
            dirty=("scratch.txt",),
        )

    def _assert_aborts_after_merge_base(
        self,
        expected_detail: str,
        **guard_overrides,
    ) -> None:
        git = self._git_reading(PREFIXED_SUBJECT, PLAIN_SUBJECT)
        with self.assertRaisesRegex(PREPARATION_ERROR, expected_detail):
            self._prepare(git, **guard_overrides)
        # Only the merge-base read happened: both guards sit ahead of the
        # count and the log alike.
        self.assertEqual(git.call_count, 1)

    def _git_reading(self, *subjects: str) -> MagicMock:
        """Serve the merge-base read, the commit count, then the log.

        The count is walked in its own reading rather than derived from the
        log below it, because a commit written with no message contributes no
        subject and still contributes one commit.
        """
        return MagicMock(
            side_effect=[
                _git_result(stdout=f"{BASE_SHA}\n"),
                _git_result(stdout=f"{len(subjects)}\n"),
                _git_result(
                    stdout="".join(
                        f"{subject}\n" for subject in subjects
                    ),
                ),
            ],
        )

    def _prepare(
        self,
        git: MagicMock,
        *,
        head: str = ORIGINAL_HEAD,
        dirty: tuple[str, ...] = (),
    ) -> planning._SquashPlan:
        with (
            patch.object(commands, GIT_HELPER, git),
            patch.object(
                verification_probes, HEAD_HELPER, return_value=head,
            ),
            patch.object(
                _worktree_status, DIRTY_HELPER, return_value=list(dirty),
            ),
        ):
            return planning._prepare_squash(
                _spec(),
                WORKTREE,
                make_issue(PLAN_ISSUE, title=ISSUE_TITLE),
                PLAN_PR,
            )


if __name__ == "__main__":
    unittest.main()
