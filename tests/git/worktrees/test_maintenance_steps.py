# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What each teardown step refuses on its own, before any pass composes them.

The pass reads the world and then acts on it, and between those two things a
race can put anything at all in front of the mutation. What stands there is not
the pass's reading -- it is git's and the remote's, at the moment of the write:
a removal that does not force, a delete leased to a commit, and a ref deletion
that names both the value it expects and its refusal to follow a symbolic name.

Each of the three is driven here against a real tree, a real bare repository,
and a real ref store, with the world moved out from under it first. A double
would prove only that the arguments were assembled.
"""

from __future__ import annotations

import unittest

from orchestrator.git.worktrees import reclaim
from tests.git.worktrees.artifact_git import BASE_BRANCH
from tests.git.worktrees.candidate_refs import _revision, _symbolic_ref
from tests.git.worktrees.maintenance_test_support import _MaintenanceTestCase

LOOSE_FILE = "left-behind.txt"
LOOSE_CONTENT = "an agent's unfinished work\n"
SYMBOLIC_BRANCH = "orchestrator/acme__widget/issue-900"
LIFECYCLE_WARNING = "WARNING"


class UnforcedRemovalTest(_MaintenanceTestCase):
    """A checkout comes down only while it is carrying nothing of its own."""

    def test_a_tree_written_in_since_is_refused(self) -> None:
        # git's own refusal is the last thing between a reading taken seconds
        # ago and a deletion, which is why the removal is never forced.
        self.landed()
        worktree = self.settled_checkout()
        (worktree / LOOSE_FILE).write_text(LOOSE_CONTENT)

        with self.assertLogs(reclaim.log.name, level=LIFECYCLE_WARNING):
            removed = reclaim._remove_recognized_worktree(self.spec, worktree)

        self.assertFalse(removed)
        self.assertTrue((worktree / LOOSE_FILE).exists())

    def test_a_clean_tree_comes_down(self) -> None:
        self.landed()
        worktree = self.settled_checkout()

        self.assertTrue(
            reclaim._remove_recognized_worktree(self.spec, worktree),
        )
        self.assertFalse(worktree.exists())

    def test_a_checkout_already_gone_is_the_step_done(self) -> None:
        # What every repeat of a half-finished teardown meets, and reporting it
        # as a failure would keep the candidate reported forever.
        self.landed()
        worktree = self.settled_checkout()
        reclaim._remove_recognized_worktree(self.spec, worktree)

        self.assertTrue(
            reclaim._remove_recognized_worktree(self.spec, worktree),
        )


class PinnedLocalDeleteTest(_MaintenanceTestCase):
    """A local branch goes only as itself, and only at the commit that was proved."""

    def test_a_branch_that_moved_survives(self) -> None:
        tip = self.landed()
        moved = self.world.commit_on(
            self.clone, self.branch, start=self.branch,
        )

        with self.assertLogs(reclaim.log.name, level=LIFECYCLE_WARNING):
            deleted = reclaim._delete_local_ref_at(
                self.spec, self.branch, tip,
            )

        self.assertFalse(deleted)
        self.assertEqual(_revision(self.clone, self.branch), moved)

    def test_a_branch_at_the_proved_commit_goes(self) -> None:
        tip = self.landed()

        self.assertTrue(
            reclaim._delete_local_ref_at(self.spec, self.branch, tip),
        )
        self.assertEqual(self.local_branches(), ())

    def test_an_absent_branch_is_not_a_deletion(self) -> None:
        # `update-ref` has nothing to delete and says so; the pass reads what
        # the branch is at before it gets here, so an absence is its answer.
        tip = self.landed()
        reclaim._delete_local_ref_at(self.spec, self.branch, tip)

        with self.assertLogs(reclaim.log.name, level=LIFECYCLE_WARNING):
            deleted = reclaim._delete_local_ref_at(
                self.spec, self.branch, tip,
            )

        self.assertFalse(deleted)

    def test_a_symbolic_name_is_deleted_as_itself(self) -> None:
        # A deletion that dereferenced would take the branch the name resolves
        # to and leave the name behind -- so a symbolic ref planted under an
        # orchestrator branch name would redirect the teardown onto the base.
        base = _revision(self.clone, BASE_BRANCH)
        _symbolic_ref(self.clone, SYMBOLIC_BRANCH, BASE_BRANCH)

        reclaim._delete_local_ref_at(self.spec, SYMBOLIC_BRANCH, base)

        self.assertEqual(_revision(self.clone, BASE_BRANCH), base)
        self.assertNotIn(SYMBOLIC_BRANCH, self.local_branches())


class LeasedRemoteDeleteTest(_MaintenanceTestCase):
    """A remote branch goes only while the remote still holds the proved commit."""

    def test_a_branch_pushed_past_is_refused(self) -> None:
        # The lease is what makes this safe rather than the reading in front of
        # it: between the two, somebody else's push lands.
        tip = self.landed()
        pushed = self.world.commit_on(
            self.clone, self.branch, start=self.branch,
        )
        self.world.publish(self.clone, self.branch, pushed)

        with self.assertLogs(reclaim.ref_transport.log.name, level="ERROR"):
            deleted = reclaim._delete_remote_branch_at(
                self.spec, self.branch, tip,
            )

        self.assertFalse(deleted)
        self.assertEqual(self.remote_branches(), (self.branch,))

    def test_a_branch_still_at_the_proved_commit_goes(self) -> None:
        tip = self.landed()

        self.assertTrue(
            reclaim._delete_remote_branch_at(self.spec, self.branch, tip),
        )
        self.assertEqual(self.remote_branches(), ())


if __name__ == "__main__":
    unittest.main()
