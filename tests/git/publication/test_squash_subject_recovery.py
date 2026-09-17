# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A tick coming back to a half-finished rewrite of one commit's subject.

The recovery beside this file is about a branch a squash collapsed: several
commits replaced by one, so the interrupted branch at least has a different
number of commits on it than the record counts. This is the shape with none of
that. A branch of one commit rewritten to reference its pull request is one
commit before the reset and one after, under a subject of the same form and
over the same tree -- so nothing about the checkout says a rewrite was begun,
and the record the squash wrote before it ran is the whole of what tells a
tick which of the two it is looking at.

It is the same record, written and proved exactly as a collapse's is, which is
what these cases pin down: the terms go down before the reset, an untouched
branch is rewritten afresh, a rewrite that landed locally is published as it
was committed rather than referenced twice, and one the remote already carries
is the leased no-op it should be. The branch carrying BOTH numbers is run
through the same arc, because it is the one shape a rewrite asked about the
pull request alone would call finished and hand back unrewritten.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from tests.git.publication import (
    squash_crash_doubles as _squash_crashes,
    squash_git_support as squash_support,
    squash_recovery_support as _support,
)
from tests.git.publication.squash_recovery_support import SquashRecoveryMixin

# The switch a one-commit branch's only rewrite hangs on, set rather than
# inherited so an operator environment that turned it off cannot decide what
# these cases are about.
PR_REF_IN_SUBJECT = "PR_REF_IN_SUBJECT"

# What such a rewrite replaces, and the subject it commits.
REWRITTEN_COMMITS = 1

REFERENCED_SUBJECT = (
    f"{squash_support.SINGLE_SUBJECT}{squash_support.PR_REFERENCE}"
)

# The subject a developer commit and an earlier publication each wrote half
# of: this pull request's reference is already on it, and the tracked issue's
# is still standing ahead of that.
BOTH_NUMBERS_SUBJECT = (
    f"{squash_support.SINGLE_SUBJECT}"
    f"{squash_support.ISSUE_REFERENCE}"
    f"{squash_support.PR_REFERENCE}"
)


class RewrittenSubjectRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """An interrupted rewrite of the subject on a one-commit branch.

    The shape the branch itself cannot show anything about: one commit before
    the reset and one after, under a subject of the same form, with the same
    tree under both. Only the record says which of the two a tick is looking
    at -- and it is the same record, proved the same way, that a collapse of
    several commits leaves.
    """

    def setUp(self) -> None:
        super().setUp()
        self._rebuild_single_commit()
        self.enterContext(patch.object(config, PR_REF_IN_SUBJECT, True))

    def test_a_one_commit_rewrite_records_its_terms(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()

        self._crashes_before_the_reset(gate)

        pinned = self._pinned(gate)
        self.assertEqual(pinned[_support.KEY_COLLAPSE_HEAD], accepted)
        self.assertEqual(pinned[_support.KEY_COLLAPSE_BASE_SHA], self._base_sha())
        self.assertEqual(pinned[_support.KEY_COLLAPSE_COUNT], REWRITTEN_COMMITS)

    def test_an_untouched_branch_is_rewritten_afresh(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, REWRITTEN_COMMITS)
        self.assertEqual(
            squash_run.push_mock.call_args.kwargs[_support.LEASE], accepted,
        )
        self.assertEqual(self._commits_on_branch(), [REFERENCED_SUBJECT])

    def test_both_numbers_are_rewritten_afresh(self) -> None:
        # The shape the pull request's reference alone cannot tell from a
        # finished one. Interrupted before the reset, the next tick plans it
        # over again -- and the plan it takes owes the same rewrite the dead
        # one did, so the published subject sheds the tracked issue rather
        # than going out with both numbers on it.
        self._rebuild_single_commit(BOTH_NUMBERS_SUBJECT)
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_before_the_reset(gate)

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, REWRITTEN_COMMITS)
        self.assertEqual(
            squash_run.push_mock.call_args.kwargs[_support.LEASE], accepted,
        )
        self.assertEqual(self._commits_on_branch(), [REFERENCED_SUBJECT])

    def test_an_unpushed_rewrite_is_published(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._crashes_after_the_commit(gate)
        rewritten = self._head_sha()

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, REWRITTEN_COMMITS)
        pushed = squash_run.push_mock.call_args.kwargs
        self.assertEqual(pushed[_squash_crashes.REVISION], rewritten)
        self.assertEqual(pushed[_support.LEASE], accepted)
        # The commit already on the branch is what goes out, so the subject is
        # the one the interrupted tick committed and the reference on it is
        # not written a second time.
        self.assertEqual(self._head_sha(), rewritten)
        self.assertEqual(self._commits_on_branch(), [REFERENCED_SUBJECT])

    def test_a_landed_rewrite_is_a_leased_no_op(self) -> None:
        # The far side of the window: the push landed and the receipt never
        # did, so the pull request already carries the rewritten commit while
        # the record still says the rewrite is outstanding.
        gate = self._gate_subject()
        self._crashes_after_the_push(gate)
        rewritten = self._head_sha()

        squash_run = self._squashes(
            self._next_tick(gate), push_result=self._publishes(gate),
        )

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertEqual(squash_run.count, REWRITTEN_COMMITS)
        pushed = squash_run.push_mock.call_args.kwargs
        self.assertEqual(pushed[_squash_crashes.REVISION], rewritten)
        self.assertEqual(pushed[_support.LEASE], rewritten)
        self.assertEqual(self._commits_on_branch(), [REFERENCED_SUBJECT])


if __name__ == "__main__":
    unittest.main()
