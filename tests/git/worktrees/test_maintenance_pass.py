# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one maintenance pass takes, what it refuses, and what it leaves behind.

The mutations are run for real: `worktree remove` against a tree on disk, a
leased delete against a bare repository, and a pinned `update-ref` against the
clone's own ref store. That is the whole point of the cases below -- what makes
this pass safe is that git and the remote refuse it when the world has moved,
and a fixture standing in for either would assert the pass's own reading back
at it.

What is asserted after a pass is the state of the host and the remote rather
than the calls it made, since that is what an operator is left with. The one
exception is the pair of failure cases, where a step that would not run is
installed on the owner that defines it: neither a bare repository nor a local
ref store can be made to turn a valid deletion down.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees import (
    maintenance_results as _maintenance_results,
    naming as _naming,
    paths,
    reclaim,
)
from orchestrator.git.worktrees.models import RetentionReason
from tests.git.worktrees import (
    maintenance_payloads as _maintenance_payloads,
    maintenance_test_support as _support,
)
from tests.git.worktrees.artifact_test_support import (
    DIGEST_COLLIDING_SLUGS,
    WIDGET_SLUG,
    _legacy_branch,
    _namespaced_branch,
    _spec,
)
from tests.git.worktrees.candidate_refs import _branch_at
from tests.git.worktrees.eligibility_test_support import (
    ISSUE_NUMBER,
    _terminal_issue,
)
from tests.support.git import (
    _run_git,
)

# The flat name an earlier layout left for this issue, and the listing a host
# that kept only it reads back as.
LEGACY_BRANCH = _legacy_branch(ISSUE_NUMBER)
FLAT_ONLY = (LEGACY_BRANCH,)

LOCK_SLUG, DIGEST_TWIN_SLUG = DIGEST_COLLIDING_SLUGS


class OrderedCleanupTest(_support._MaintenanceTestCase):
    """A cleared candidate loses its checkout, its remote branch, and its ref."""

    def test_every_artifact_of_a_cleared_one_goes(self) -> None:
        self.landed()
        worktree = self.settled_checkout()

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.RECLAIMED)
        self.assertFalse(worktree.exists())
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_a_branch_only_one_loses_both_copies(self) -> None:
        self.landed()

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_a_remote_only_one_loses_its_copy(self) -> None:
        # Nothing local proved it and nothing local is deleted: the branch is
        # found by the remote listing and cleared through the remote's own tip.
        self.landed()
        _branch_at(self.clone, self.branch, None)

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertEqual(self.remote_branches(), ())

    def test_a_pass_writes_nothing_to_the_issue(self) -> None:
        # The artifacts are the whole of what this pass owns: an issue that has
        # ended keeps every record of how it ended.
        self.landed()
        self.settled_checkout()

        self.only_result()

        self.assertEqual(self.gh.posted_comments, [])
        self.assertEqual(self.gh.label_history, [])
        self.assertEqual(self.gh.write_state_calls, 0)


class FlatLayoutPreservationTest(_support._MaintenanceTestCase):
    """What the layout before namespacing left is never taken.

    The flat `orchestrator/issue-<n>` branch and the `WORKTREES_DIR/issue-<n>`
    checkout are no configured repository's derivation, so no pass attributes
    or reclaims them -- whatever clone the checkout is a worktree of, and
    however cleanly its commit landed. They stay, here and on the remote, for
    an operator to dispose of.
    """

    def test_flat_artifacts_alone_are_left(self) -> None:
        # Landed on the base, on a clone this entry has to itself, beside a
        # sibling on a clone of its own: still no candidate at all.
        self.landed(LEGACY_BRANCH)
        flat = self.legacy_checkout(LEGACY_BRANCH)

        for specs in ((self.spec,), (self.spec, self.sibling_on_its_own_clone())):
            with self.subTest(specs=len(specs)):
                self.assertEqual(self.swept(self.discovered(specs)), ())
        self.assertTrue(flat.exists())
        self.assertEqual(self.local_branches(), FLAT_ONLY)
        self.assertEqual(self.remote_branches(), FLAT_ONLY)

    def test_a_checkout_behind_a_linked_parent_stays(self) -> None:
        # A per-repository directory that is a symlink to `WORKTREES_DIR` makes
        # the flat checkout -- clean, on the issue's own branch, its commit in
        # the base -- read as the issue's checkout to every reading of the tree
        # itself. Its path is not where the layout puts that checkout, so it is
        # foreign, and the whole candidate is kept with both branch copies.
        self.landed()
        flat = self.legacy_checkout()
        paths._repo_worktrees_root(self.spec).symlink_to(
            config.WORKTREES_DIR, target_is_directory=True,
        )

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(
            tuple(kept.reason for kept in swept.retentions),
            (RetentionReason.FOREIGN_CHECKOUT,),
        )
        self.assertTrue(flat.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_remote_only_flat_ref_is_left(self) -> None:
        self.landed(LEGACY_BRANCH)
        _branch_at(self.clone, LEGACY_BRANCH, None)

        self.assertEqual(self.swept(), ())
        self.assertEqual(self.remote_branches(), FLAT_ONLY)

    def test_a_mixed_layout_loses_its_current_half(self) -> None:
        # One issue under both layouts, on one commit the base carries: the
        # current checkout and branch go, and the flat ones beside them stay --
        # a dirty flat tree included, which no reading of this pass ever saw.
        tip = self.landed()
        _branch_at(self.clone, LEGACY_BRANCH, tip)
        self.world.publish(self.clone, LEGACY_BRANCH, tip)
        current = self.settled_checkout()
        flat = self.legacy_checkout(LEGACY_BRANCH)
        loose = flat / _maintenance_payloads.LOOSE_FILE
        loose.write_text(_maintenance_payloads.LOOSE_CONTENT)

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertEqual(swept.candidate.artifacts.branches, self.only_branch)
        self.assertFalse(current.exists())
        self.assertEqual(loose.read_text(), _maintenance_payloads.LOOSE_CONTENT)
        self.assertEqual(self.local_branches(), FLAT_ONLY)
        self.assertEqual(self.remote_branches(), FLAT_ONLY)


class SharedCloneCleanupTest(_support._MaintenanceTestCase):
    """A flat checkout on a shared clone keeps the branch it is standing on.

    Two entries over one clone, and a flat checkout standing on the issue's
    current branch. The scan reports the branch alone -- the tree is nobody's
    -- and the teardown's own reading of what this clone has checked out is
    what keeps it: deleting the ref would leave that tree holding a HEAD
    nothing resolves.
    """

    def setUp(self) -> None:
        super().setUp()
        self.specs = (self.spec, self.sibling_on_this_clone())

    def test_a_flat_checkout_on_the_branch_keeps_it(self) -> None:
        self.landed()
        flat = self.legacy_checkout()

        swept = self.swept(self.discovered(self.specs))

        self.assertEqual(len(swept), 1)
        self.assertEqual(swept[0].outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept[0].reason, _maintenance_results.MaintenanceReason.BRANCH_CHECKED_OUT)
        self.assertEqual(swept[0].subject, self.branch)
        self.assertTrue(flat.exists())
        self.assertEqual(
            _run_git("rev-parse", "--verify", "HEAD", cwd=flat).returncode, 0,
        )
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_flat_artifacts_are_left_there_too(self) -> None:
        self.landed(LEGACY_BRANCH)
        flat = self.legacy_checkout(LEGACY_BRANCH)

        self.assertEqual(self.swept(self.discovered(self.specs)), ())
        self.assertTrue(flat.exists())
        self.assertEqual(self.local_branches(), FLAT_ONLY)

    def test_another_issue_there_is_still_swept(self) -> None:
        # The branch a tree stands on keeps its own issue, not the
        # repositories sharing the clone.
        other = _namespaced_branch(WIDGET_SLUG, _maintenance_payloads.OTHER_ISSUE_NUMBER)
        self.gh.add_issue(_terminal_issue(_maintenance_payloads.OTHER_ISSUE_NUMBER))
        self.gh.seed_state(_maintenance_payloads.OTHER_ISSUE_NUMBER)
        tip = self.landed()
        self.legacy_checkout()
        _branch_at(self.clone, other, tip)
        self.world.publish(self.clone, other, tip)

        swept = self.swept(self.discovered(self.specs))

        self.assertEqual(
            tuple((answer.candidate.artifacts.issue_number, answer.outcome) for answer in swept),
            (
                (ISSUE_NUMBER, _maintenance_results.MaintenanceOutcome.RETAINED),
                (_maintenance_payloads.OTHER_ISSUE_NUMBER, _maintenance_results.MaintenanceOutcome.CLEANED),
            ),
        )
        self.assertEqual(self.local_branches(), self.only_branch)


class CollidingBranchCleanupTest(_support._MaintenanceTestCase):
    """A checkout on a branch two repositories derive alike is left whole.

    The digest suffix lets a crafted slug land on the branch name another entry
    derives while each keeps a checkout directory of its own. The branch is
    refused as ambiguous, and so is the tree standing on it: the directory
    settles nothing about whose work the tree holds.
    """

    def setUp(self) -> None:
        super().setUp()
        self.spec = _spec(LOCK_SLUG, self.clone)
        self.twin = _spec(DIGEST_TWIN_SLUG, self.clone)
        self.branch = _naming._branch_name(self.spec, ISSUE_NUMBER)
        # Publications are spelled against the world's own remote, so it is
        # this repository's for the case; the twin gets one of its own.
        self.world.remote = self.world.serve_beside(self.spec, "lock.git")
        self.world.serve_beside(self.twin, "twin.git")

    def kept_whole(self, twin) -> None:
        """Run a pass over both repositories, and hold that it took nothing."""
        self.landed()
        checkout = self.settled_checkout()

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.WARNING):
            swept = self.swept(self.discovered((self.spec, twin)))

        self.assertEqual(swept, ())
        self.assertTrue(checkout.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_the_checkout_and_its_branch_stay(self) -> None:
        # The collision this case is about: one branch, two directories.
        self.assertEqual(_naming._branch_name(self.twin, ISSUE_NUMBER), self.branch)
        self.assertNotEqual(
            paths._worktree_path(self.twin, ISSUE_NUMBER),
            paths._worktree_path(self.spec, ISSUE_NUMBER),
        )
        self.kept_whole(self.twin)

    def test_a_linked_target_shares_the_refusal(self) -> None:
        # The twin configured at a linked worktree of the clone rather than at
        # the clone itself: another path onto the same ref store, so the two
        # are still claimants on the same branches.
        linked = self.world.path("linked-target")
        _run_git("worktree", "add", "-q", "--detach", str(linked), "HEAD", cwd=self.clone)

        self.kept_whole(_spec(DIGEST_TWIN_SLUG, linked))


class RefusedStepTest(_support._MaintenanceTestCase):
    """A step that will not run stops the pass and leaves the rest discoverable."""

    def test_a_failed_remote_delete_keeps_the_ref(self) -> None:
        # The local ref is what the next discovery finds cheapest, so it is the
        # last thing to go -- and a remote delete that failed must not take it.
        self.landed()
        worktree = self.settled_checkout()

        with patch.object(
            reclaim, _maintenance_payloads.REMOTE_DELETE, side_effect=_support._refused_delete,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.FAILED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.REMOTE_DELETE_FAILED)
        self.assertEqual(swept.subject, self.branch)
        self.assertFalse(worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_failure_leaves_it_discoverable(self) -> None:
        self.landed()
        self.settled_checkout()

        with patch.object(
            reclaim, _maintenance_payloads.REMOTE_DELETE, side_effect=_support._refused_delete,
        ):
            self.only_result()

        self.assertEqual(
            self.only_candidate().artifacts.branches, self.only_branch,
        )

    def test_a_second_pass_finishes_the_rest(self) -> None:
        self.landed()
        self.settled_checkout()

        with patch.object(
            reclaim, _maintenance_payloads.REMOTE_DELETE, side_effect=_support._refused_delete,
        ):
            self.only_result()
        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_a_failed_local_delete_is_a_failure(self) -> None:
        self.landed()

        with patch.object(
            reclaim, "_delete_local_ref_at", side_effect=_support._refused_delete,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.FAILED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.LOCAL_DELETE_FAILED)
        self.assertEqual(self.remote_branches(), ())
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_remote_only_failure_stays_discoverable(self) -> None:
        # The one failure with no local evidence left to find it by: nothing
        # here holds this branch, so what re-discovers it is the next listing
        # of the remote and nothing else.
        self.landed()
        _branch_at(self.clone, self.branch, None)

        with patch.object(
            reclaim, _maintenance_payloads.REMOTE_DELETE, side_effect=_support._refused_delete,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.FAILED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.REMOTE_DELETE_FAILED)
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), self.only_branch)
        self.assertEqual(
            self.only_candidate().artifacts.branches, self.only_branch,
        )

    def test_a_transport_that_raises_is_a_failure(self) -> None:
        # The transport answers for what it recognizes and raises for what is
        # underneath it. An exception out of one candidate's delete would end
        # the pass for every candidate behind it, so it is answered here.
        self.landed()

        with (
            patch.object(
                reclaim.ref_transport,
                "_delete_remote_ref",
                side_effect=OSError("git could not be spawned"),
            ),
            self.assertLogs(reclaim.log.name, level=_maintenance_payloads.WARNING),
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.FAILED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.REMOTE_DELETE_FAILED)
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_checkout_that_stays_stops_the_pass(self) -> None:
        # Nothing past the checkout is touched, because a branch a worktree
        # still has checked out is one git will not let go of either.
        self.landed()
        worktree = self.settled_checkout()

        with patch.object(
            reclaim, "_remove_recognized_worktree", side_effect=_support._refused_delete,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.FAILED)
        self.assertEqual(
            swept.reason, _maintenance_results.MaintenanceReason.WORKTREE_REMOVAL_FAILED,
        )
        self.assertEqual(swept.subject, str(worktree))
        self.assertEqual(self.remote_branches(), self.only_branch)
        self.assertEqual(self.local_branches(), self.only_branch)


class RepeatedPassTest(_support._MaintenanceTestCase):
    """Running the pass again costs nothing and takes nothing twice."""

    def test_a_cleared_host_offers_no_candidate(self) -> None:
        self.landed()
        worktree = self.settled_checkout()

        self.only_result()
        second = self.swept()

        self.assertEqual(second, ())
        self.assertFalse(worktree.exists())

    def test_a_half_finished_teardown_is_finished(self) -> None:
        # What carries an interrupted pass across a restart is the artifacts
        # themselves: nothing was written down, and the discovery finds what is
        # left of the candidate exactly as it found the whole of it.
        self.landed()
        worktree = self.settled_checkout()

        with patch.object(
            reclaim, "_delete_local_ref_at", side_effect=_support._refused_delete,
        ):
            self.only_result()
        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertFalse(worktree.exists())
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_a_flat_copy_survives_every_pass(self) -> None:
        # One issue under both names, both copies on the commit the base
        # carries: the first pass takes the current branch on both hosts, and
        # the one after it finds nothing left to take.
        tip = self.landed()
        _branch_at(self.clone, LEGACY_BRANCH, tip)
        self.world.publish(self.clone, LEGACY_BRANCH, tip)

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertEqual(self.swept(), ())
        self.assertEqual(self.local_branches(), FLAT_ONLY)
        self.assertEqual(self.remote_branches(), FLAT_ONLY)


class OutcomeVocabularyTest(unittest.TestCase):
    """Every reason a pass can end on names exactly one outcome."""

    def test_every_reason_has_an_outcome(self) -> None:
        self.assertEqual(
            frozenset(_maintenance_results._OUTCOMES),
            frozenset(_maintenance_results.MaintenanceReason),
        )


if __name__ == "__main__":
    unittest.main()
