# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A history one of whose commits was written with no message at all.

`git commit --allow-empty-message` makes one, and it is the shape that pulls
the count and the subject list apart: it contributes no subject to the message
the squash is built from and one commit to the branch. Counted from the
subjects, a branch of three reads as two -- so the record a squash writes
before it rewrites is short, and the recovery that walks the history back
refuses a collapse it really did make as miscounted -- while a branch of two
reads as a single commit and takes the nothing-to-squash road, reporting
success without measuring or pushing anything.
"""
from __future__ import annotations

import unittest

from tests.workflow.stages.validating import squash_git_support as squash_support
from tests.workflow.stages.validating.squash_recovery_support import (
    APPROVED_COMMITS,
    KEY_COLLAPSE_COUNT,
    SquashRecoveryMixin,
)


class BlankSubjectHistoryRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """A history one of whose commits was written with no message at all.

    `git commit --allow-empty-message` makes one, and it contributes no
    subject to the message the squash is built from while contributing one to
    the branch. Counted from the subjects, the record is short -- and the
    recovery that walks the history back refuses it as miscounted, over a
    collapse it really did make.
    """

    def test_the_record_counts_the_commits(self) -> None:
        self._rebuilds_with_a_blank_subject()
        gate = self._gate_subject()

        self._crashes_after_the_commit(gate)

        pinned = self._pinned(gate)
        self.assertEqual(pinned[KEY_COLLAPSE_COUNT], APPROVED_COMMITS)

    def test_the_collapse_is_finished_on_that_count(self) -> None:
        self._rebuilds_with_a_blank_subject()
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, APPROVED_COMMITS)
        squash_run.push_mock.assert_called_once()

    def test_two_commits_are_still_squashed(self) -> None:
        # The same shortfall one commit lower: a branch of two where one was
        # written with no message reads as a single commit, and a single
        # commit is the nothing-to-squash road reporting success without
        # pushing anything.
        self._rebuilds_with_a_blank_subject()
        squash_support.run_git("reset", "--hard", "HEAD~1", cwd=self.work)

        squash_run = self._squashes(self._gate_subject())

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, APPROVED_COMMITS - 1)
        squash_run.push_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
