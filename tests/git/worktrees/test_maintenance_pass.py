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

from orchestrator.git.worktrees import (
    maintenance_results as _maintenance_results,
    probes,
    reclaim,
)
from orchestrator.git.worktrees.models import RetentionReason
from tests.git.worktrees import (
    maintenance_payloads as _maintenance_payloads,
    maintenance_test_support as _support,
)
from tests.git.worktrees.artifact_test_support import WIDGET_SLUG, _legacy_branch, _namespaced_branch
from tests.git.worktrees.candidate_refs import _branch_at
from tests.git.worktrees.eligibility_test_support import (
    ISSUE_NUMBER,
    _terminal_issue,
)
from tests.workflow.stages.question.question_real_git_test_support import (
    _run_git,
)


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


class LegacyLayoutCleanupTest(_support._MaintenanceTestCase):
    """A checkout the layout before namespacing left is taken like any other."""

    def test_a_flat_checkout_goes_with_its_branch(self) -> None:
        legacy = _legacy_branch(ISSUE_NUMBER)
        self.landed(legacy)
        worktree = self.legacy_checkout(legacy)

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertFalse(worktree.exists())
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_both_checkout_layouts_go_in_one_pass(self) -> None:
        # Both trees are the issue's, so both come down together: a pass that
        # answered `cleaned` having taken one of them would leave the other
        # standing with nothing left for a later discovery to find it by.
        legacy = _legacy_branch(ISSUE_NUMBER)
        tip = self.landed()
        _branch_at(self.clone, legacy, tip)
        self.world.publish(self.clone, legacy, tip)
        current = self.settled_checkout()
        flat = self.legacy_checkout(legacy)

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertFalse(current.exists())
        self.assertFalse(flat.exists())
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_a_dirty_flat_checkout_keeps_it(self) -> None:
        # The tree the current-layout report never saw is judged like the one
        # it did: what is loose in it keeps every artifact of the issue.
        legacy = _legacy_branch(ISSUE_NUMBER)
        tip = self.landed()
        _branch_at(self.clone, legacy, tip)
        self.world.publish(self.clone, legacy, tip)
        self.settled_checkout()
        flat = self.legacy_checkout(legacy)
        (flat / _maintenance_payloads.LOOSE_FILE).write_text(_maintenance_payloads.LOOSE_CONTENT)

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.UNPROVEN)
        self.assertEqual(
            tuple(kept.reason for kept in swept.retentions),
            (RetentionReason.WORKTREE_DIRTY,),
        )
        self.assertTrue(flat.exists())
        self.assertEqual(self.remote_branches(), (self.branch, legacy))


class SharedCloneCleanupTest(_support._MaintenanceTestCase):
    """An unattributable flat checkout takes its whole issue out of the pass.

    Two entries over one clone, and a flat checkout standing on one of that
    issue's branches. Nothing on disk says which entry made the tree, so
    nothing may take it -- and the branch it is standing on may not go either.
    A pass that reported the branch alone would delete the ref under a live
    checkout and answer `cleaned`, leaving that tree holding a HEAD nothing
    resolves and no artifact any later discovery could find it by.
    """

    def setUp(self) -> None:
        super().setUp()
        self.specs = (self.spec, self.sibling_on_this_clone())

    def test_an_ambiguous_flat_checkout_stops_it(self) -> None:
        self.landed()
        flat = self.legacy_checkout()

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.WARNING):
            swept = self.swept(self.discovered(self.specs))

        self.assertEqual(swept, ())
        self.assertTrue(flat.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_the_tree_left_alone_still_has_a_head(self) -> None:
        # What the branch deletion would have cost: the checkout is standing on
        # that ref, so taking it leaves the tree pointing at nothing.
        self.landed()
        flat = self.legacy_checkout()

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.WARNING):
            self.swept(self.discovered(self.specs))

        self.assertEqual(
            _run_git("rev-parse", "--verify", "HEAD", cwd=flat).returncode, 0,
        )

    def test_an_unreadable_sibling_keeps_the_tree(self) -> None:
        # The sibling that would have made the tree ambiguous is the one whose
        # own clone did not answer. Nothing ruled it out, so nothing here is
        # settled -- and the checkout the pass would otherwise have removed is
        # still standing afterwards.
        self.landed()
        flat = self.legacy_checkout()

        with (
            patch.object(
                probes,
                "_checkout_clone",
                side_effect=_support._CloneOfAllBut(self.specs[1]),
            ),
            self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.WARNING),
        ):
            swept = self.swept(self.discovered(self.specs))

        self.assertEqual(swept, ())
        self.assertTrue(flat.exists())
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_another_issue_there_is_still_swept(self) -> None:
        # The refusal is about the issue whose tree nobody can attribute, not
        # about the repositories sharing the clone.
        other = _namespaced_branch(WIDGET_SLUG, _maintenance_payloads.OTHER_ISSUE_NUMBER)
        self.gh.add_issue(_terminal_issue(_maintenance_payloads.OTHER_ISSUE_NUMBER))
        self.gh.seed_state(_maintenance_payloads.OTHER_ISSUE_NUMBER)
        tip = self.landed()
        self.legacy_checkout()
        _branch_at(self.clone, other, tip)
        self.world.publish(self.clone, other, tip)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.WARNING):
            swept = self.swept(self.discovered(self.specs))

        self.assertEqual(len(swept), 1)
        self.assertEqual(swept[0].outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertEqual(
            swept[0].candidate.artifacts.issue_number, _maintenance_payloads.OTHER_ISSUE_NUMBER,
        )
        self.assertEqual(self.local_branches(), self.only_branch)


class DistinctCloneCleanupTest(_support._MaintenanceTestCase):
    """A second configured repository does not strand the flat checkout.

    The end of the reading the discovery takes: attributed to the clone it is
    a worktree of, the tree comes down with its branches instead of being left
    on a host that answered `cleaned`.
    """

    def test_a_flat_checkout_goes_beside_a_sibling(self) -> None:
        legacy = _legacy_branch(ISSUE_NUMBER)
        self.landed(legacy)
        worktree = self.legacy_checkout(legacy)
        specs = (self.spec, self.sibling_on_its_own_clone())

        swept = self.swept(self.discovered(specs))

        self.assertEqual(len(swept), 1)
        self.assertEqual(swept[0].outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertFalse(worktree.exists())
        self.assertEqual(self.discovered(specs), ())


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

    def test_both_layouts_go_in_one_pass(self) -> None:
        # One issue under two names, which is what a migration leaves: both
        # copies stand on the commit the base carries, and one pass takes all
        # four of them.
        legacy = _legacy_branch(ISSUE_NUMBER)
        tip = self.landed()
        _branch_at(self.clone, legacy, tip)
        self.world.publish(self.clone, legacy, tip)

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())
        self.assertEqual(swept.candidate.artifacts.spec.slug, WIDGET_SLUG)


class OutcomeVocabularyTest(unittest.TestCase):
    """Every reason a pass can end on names exactly one outcome."""

    def test_every_reason_has_an_outcome(self) -> None:
        self.assertEqual(
            frozenset(_maintenance_results._OUTCOMES),
            frozenset(_maintenance_results.MaintenanceReason),
        )


if __name__ == "__main__":
    unittest.main()
