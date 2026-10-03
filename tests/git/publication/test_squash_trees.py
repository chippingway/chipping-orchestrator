# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every head an approval squash publishes carries the approved head's full tree.

That is the premise the evidence an approval rests on is carried across the
squash by: the commit published in the approved head's place reads, through
the very probe the carry-forward decision reads trees with, as the tree the
reviewer's commands ran on -- for a collapse, for a one-commit branch
rewritten for its subject alone, and for a collapse an interrupted tick left
for the recovery to publish. The decision proves it again on every carry; what
is pinned here is that the squash keeps it, so a squash that did not would be
caught here rather than refused there as evidence nobody can carry.

Real git against a real bare remote, so the trees compared are the objects the
rewrite really made.
"""
from __future__ import annotations

import unittest

from orchestrator.git.verification import probes as _probes
from tests.git.publication import squash_git_support as squash_support
from tests.git.publication.squash_recovery_support import SquashRecoveryMixin

PR_REF_IN_SUBJECT = "PR_REF_IN_SUBJECT"


class _ApprovedTreeMixin(squash_support.SquashGitFixtureMixin):
    """The real repository a squash runs against, and the approved head and tree it reads first."""

    def _approved(self) -> tuple[str, str]:
        head = self._head_sha()
        return head, _probes._tree_sha(self.work, head)

    def _assert_publishes_the_tree(self, approved: tuple[str, str], published: str) -> None:
        """`published` is another commit than the approved head, carrying its tree."""
        head, tree = approved
        self.assertNotEqual(published, head)
        self.assertEqual(_probes._tree_sha(self.work, published), tree)


class RewrittenTreeTest(_ApprovedTreeMixin, unittest.TestCase):
    """A collapse publishes another commit over the same tree."""

    def test_a_collapse_keeps_the_tree(self) -> None:
        approved = self._approved()

        squash_run = self._squash(**{PR_REF_IN_SUBJECT: True})

        self.assertTrue(squash_run.success, squash_run.error)
        self.assertGreater(squash_run.count, 1)
        self._assert_publishes_the_tree(approved, squash_run.sha)


class RecoveredTreeTest(SquashRecoveryMixin, _ApprovedTreeMixin, unittest.TestCase):
    """The recovery of an interrupted collapse publishes the tree the approved head left."""

    def test_a_recovered_collapse_keeps_the_tree(self) -> None:
        gate = self._gate_subject()
        approved = self._approved()
        self._crashes_after_the_commit(gate)

        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success, squash_run.error)
        self._assert_publishes_the_tree(approved, squash_run.sha)


if __name__ == "__main__":
    unittest.main()
