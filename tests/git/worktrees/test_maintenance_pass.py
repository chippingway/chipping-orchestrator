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

import os
import time
import unittest
from unittest.mock import patch

from orchestrator.git.worktrees import (
    eligibility,
    maintenance,
    probes,
    reclaim,
)
from orchestrator.git.worktrees.models import (
    MaintenanceOutcome,
    MaintenanceReason,
    ProbeAnswer,
    ProvenTip,
    RetentionReason,
)
from tests.git.worktrees import maintenance_test_support as _support
from tests.git.worktrees.artifact_test_support import (
    BASE_BRANCH,
    WIDGET_SLUG,
    _legacy_branch,
    _namespaced_branch,
)
from tests.git.worktrees.candidate_host_test_support import (
    _branch_at,
    _track_file,
    _unlink_backlink,
)
from tests.git.worktrees.eligibility_test_support import (
    ISSUE_NUMBER,
    OPEN_PR_STATE,
    _github,
    _pull_request,
    _terminal_issue,
)
from tests.workflow.stages.question.question_real_git_test_support import (
    _run_git,
)

PR_NUMBER = 42
WARNING = "WARNING"
INFO_LEVEL = "INFO"
LOOSE_FILE = "left-behind.txt"
LOOSE_CONTENT = "an agent's unfinished work\n"
IGNORE_FILE = ".gitignore"
HIDDEN_FILE = "secrets.env"
HIDDEN_CONTENT = "TOKEN=an operator's own\n"
IMPLEMENTING_LABEL = "workflow:implementing"
OTHER_ISSUE_NUMBER = 315
# The classification a stop is driven through, named on its own owner.
_CLASSIFY_ATTR = "_classify_artifacts"
# Where an operator puts a worktree to look at a finished branch.
INSPECTED_DIR = "inspected"
OBJECT_ID_LENGTH = 40
# The teardown step several cases install a refusal on.
REMOTE_DELETE = "_delete_remote_branch_at"
# A commit no artifact of this issue is standing on: what a proof taken a
# moment before the mutation is worth once somebody has pushed.
OTHER_SHA = "b" * OBJECT_ID_LENGTH


class OrderedCleanupTest(_support._MaintenanceTestCase):
    """A cleared candidate loses its checkout, its remote branch, and its ref."""

    def test_every_artifact_of_a_cleared_one_goes(self) -> None:
        self.landed()
        worktree = self.settled_checkout()

        swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.CLEANED)
        self.assertEqual(swept.reason, MaintenanceReason.RECLAIMED)
        self.assertFalse(worktree.exists())
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_a_branch_only_one_loses_both_copies(self) -> None:
        self.landed()

        swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.CLEANED)
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_a_remote_only_one_loses_its_copy(self) -> None:
        # Nothing local proved it and nothing local is deleted: the branch is
        # found by the remote listing and cleared through the remote's own tip.
        self.landed()
        _branch_at(self.clone, self.branch, None)

        swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.CLEANED)
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

        self.assertEqual(swept.outcome, MaintenanceOutcome.CLEANED)
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

        self.assertEqual(swept.outcome, MaintenanceOutcome.CLEANED)
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
        (flat / LOOSE_FILE).write_text(LOOSE_CONTENT)

        swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, MaintenanceReason.UNPROVEN)
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

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=WARNING):
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

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=WARNING):
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
            self.assertLogs(_support.LIFECYCLE_LOGGER, level=WARNING),
        ):
            swept = self.swept(self.discovered(self.specs))

        self.assertEqual(swept, ())
        self.assertTrue(flat.exists())
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_another_issue_there_is_still_swept(self) -> None:
        # The refusal is about the issue whose tree nobody can attribute, not
        # about the repositories sharing the clone.
        other = _namespaced_branch(WIDGET_SLUG, OTHER_ISSUE_NUMBER)
        self.gh.add_issue(_terminal_issue(OTHER_ISSUE_NUMBER))
        self.gh.seed_state(OTHER_ISSUE_NUMBER)
        tip = self.landed()
        self.legacy_checkout()
        _branch_at(self.clone, other, tip)
        self.world.publish(self.clone, other, tip)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=WARNING):
            swept = self.swept(self.discovered(self.specs))

        self.assertEqual(len(swept), 1)
        self.assertEqual(swept[0].outcome, MaintenanceOutcome.CLEANED)
        self.assertEqual(
            swept[0].candidate.artifacts.issue_number, OTHER_ISSUE_NUMBER,
        )
        self.assertEqual(self.local_branches(), self.only_branch)


class CheckedOutBranchTest(_support._MaintenanceTestCase):
    """A branch some tree of the clone is standing on is never deleted.

    The safety `update-ref -d` gives up for its commit pin. The trees that can
    be on a branch are not only the ones a scan names: an operator adding a
    worktree to look at a finished branch is standing on it just as squarely,
    and nothing about the per-issue paths would ever report that.
    """

    def test_a_worktree_elsewhere_keeps_the_branch(self) -> None:
        self.landed()
        inspected = self.world.checkout_at(
            self.spec, self.world.path(INSPECTED_DIR), self.branch,
        )

        swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, MaintenanceReason.BRANCH_CHECKED_OUT)
        self.assertEqual(swept.subject, self.branch)
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(
            _run_git("rev-parse", "--verify", "HEAD", cwd=inspected).returncode,
            0,
        )

    def test_a_worktree_git_dropped_keeps_the_branch(self) -> None:
        # `worktree list` passes over a linked worktree whose backlink is
        # missing -- exit zero, nothing on stderr, one fewer worktree -- while
        # that tree goes on working and goes on holding its branch. The listing
        # is counted against the clone's own entries for exactly this.
        self.landed()
        dropped = self.world.checkout_at(
            self.spec, self.world.path(INSPECTED_DIR), self.branch,
        )
        _unlink_backlink(dropped)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=WARNING):
            swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, MaintenanceReason.TIP_UNREADABLE)
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(
            _run_git("rev-parse", "--verify", "HEAD", cwd=dropped).returncode,
            0,
        )

    def test_a_listing_that_failed_keeps_the_branch(self) -> None:
        # Without it nothing establishes that no tree is standing on the ref,
        # which is the one thing this read is spent on.
        self.landed()

        with patch.object(
            maintenance.evidence, "_checked_out_branches", return_value=None,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, MaintenanceReason.TIP_UNREADABLE)
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
        self.assertEqual(swept[0].outcome, MaintenanceOutcome.CLEANED)
        self.assertFalse(worktree.exists())
        self.assertEqual(self.discovered(specs), ())


class GuardedCandidateTest(_support._MaintenanceTestCase):
    """Everything in front of the mutation keeps the artifacts where they are."""

    def setUp(self) -> None:
        super().setUp()
        self.landed()
        self.worktree = self.settled_checkout()
        self.long_ago = time.time() - _support.SETTLED_SECONDS

    def assert_untouched(self, swept) -> None:
        """The candidate is kept, and every artifact is still where it was."""
        self.assertEqual(swept.outcome, MaintenanceOutcome.RETAINED)
        self.assertTrue(self.worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_an_issue_being_run_is_left_alone(self) -> None:
        swept = self.only_result(claimed=_support._always_claimed)

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, MaintenanceReason.ACTIVE_CLAIM)
        self.assertEqual(swept.subject, f"#{ISSUE_NUMBER}")

    def test_a_guard_that_raises_is_read_as_a_claim(self) -> None:
        with self.assertLogs(maintenance.log.name, level=WARNING):
            swept = self.only_result(claimed=_support._unanswerable_claim)

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, MaintenanceReason.CLAIM_UNREADABLE)

    def test_a_checkout_touched_lately_is_left_alone(self) -> None:
        # The tree is clean and the classification clears it; what keeps it is
        # that somebody was in it moments ago.
        (self.worktree / LOOSE_FILE).write_text(LOOSE_CONTENT)
        (self.worktree / LOOSE_FILE).unlink()

        swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, MaintenanceReason.RECENT_ACTIVITY)

    def test_a_just_committed_checkout_is_left_alone(self) -> None:
        # The tree is clean, the commit is in the base, and the directory's own
        # timestamp is old -- a commit does not move it. What keeps the
        # checkout is the index and reflog that commit rewrote.
        _run_git(
            "commit", "-q", "--allow-empty", "-m", "an agent's own round",
            cwd=self.worktree,
        )
        self.world.publish(self.clone, self.branch, self.branch)
        self.world.publish(self.clone, BASE_BRANCH, self.branch)
        os.utime(self.worktree, (self.long_ago, self.long_ago))

        swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, MaintenanceReason.RECENT_ACTIVITY)
        self.assertEqual(swept.subject, str(self.worktree))

    def test_an_untimeable_checkout_is_left_alone(self) -> None:
        # The last gate fails closed like every one before it: a tree nobody
        # could time is not one to delete on the strength of the reads that
        # did answer.
        with patch.object(
            maintenance.evidence,
            "_quiet_checkout",
            return_value=ProbeAnswer.UNREADABLE,
        ):
            swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, MaintenanceReason.ACTIVITY_UNREADABLE)


class RetainedByClassificationTest(_support._MaintenanceTestCase):
    """A candidate the classification keeps is reported with its own reasons."""

    def assert_kept_for(self, swept, reason: RetentionReason) -> None:
        """The pass reports the classification's answer, in its vocabulary."""
        self.assertEqual(swept.outcome, MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, MaintenanceReason.UNPROVEN)
        self.assertEqual(
            tuple(kept.reason for kept in swept.retentions), (reason,),
        )
        self.assertEqual(swept.subject, swept.retentions[0].subject)

    def test_a_dirty_tree_keeps_the_whole_candidate(self) -> None:
        self.landed()
        worktree = self.settled_checkout()
        (worktree / LOOSE_FILE).write_text(LOOSE_CONTENT)

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.WORKTREE_DIRTY)
        self.assertTrue(worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_tree_hiding_files_keeps_it(self) -> None:
        # `worktree remove` would take these down without a word, which is why
        # the classification asks about them and the pass never gets a proof.
        _track_file(self.clone, IGNORE_FILE, f"{HIDDEN_FILE}\n")
        self.landed()
        worktree = self.settled_checkout()
        (worktree / HIDDEN_FILE).write_text(HIDDEN_CONTENT)

        with self.assertLogs(maintenance.log.name, level=INFO_LEVEL):
            swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.WORKTREE_IGNORED)
        self.assertTrue((worktree / HIDDEN_FILE).exists())

    def test_an_open_pull_request_keeps_the_branches(self) -> None:
        tip = self.landed()
        self.gh.existing_open_pr[self.branch] = _pull_request(
            PR_NUMBER, self.branch, tip, state=OPEN_PR_STATE,
        )

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.OPEN_PULL_REQUEST)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_an_issue_that_has_not_ended_keeps_it(self) -> None:
        self.landed()
        self.gh = _github(_terminal_issue(
            closed=False, label_names=(IMPLEMENTING_LABEL,),
        ))

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.ISSUE_OPEN)
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_an_unaccounted_commit_keeps_it(self) -> None:
        # Published, never merged, and no pull request carries it: the one copy
        # of that work is the branch this pass was asked about.
        self.published()

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.UNACCOUNTED_COMMITS)
        self.assertEqual(self.remote_branches(), self.only_branch)


class ExactTipTest(_support._MaintenanceTestCase):
    """Nothing is deleted that is not standing exactly where it was proved.

    The proof is handed to the teardown directly here, which is the only way to
    put a case between the classification and the mutation: in production the
    two are one call, and what separates them is a push or a commit landing in
    the microseconds between.
    """

    def reclaimed(self, *proven: ProvenTip):
        """Run the teardown over this host's candidate with a stated proof."""
        candidates = self.discovered()
        self.assertEqual(len(candidates), 1)
        return maintenance._reclaimed(candidates[0], proven)

    def test_a_branch_the_remote_has_moved_is_kept(self) -> None:
        self.landed()

        swept = self.reclaimed(ProvenTip(self.branch, OTHER_SHA))

        self.assertEqual(swept.outcome, MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, MaintenanceReason.TIP_MOVED)
        self.assertEqual(swept.subject, self.branch)
        self.assertEqual(self.remote_branches(), self.only_branch)
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_moved_local_branch_survives(self) -> None:
        # The remote's copy is proved and goes; the local ref is standing on a
        # commit nobody cleared, so the pinned delete never runs.
        tip = self.landed()
        self.world.unpublish(self.clone, self.branch)
        moved = self.world.commit_on(
            self.clone, self.branch, start=self.branch,
        )

        swept = self.reclaimed(ProvenTip(self.branch, tip))

        self.assertNotEqual(moved, tip)
        self.assertEqual(swept.reason, MaintenanceReason.TIP_MOVED)
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_checkout_that_moved_is_kept(self) -> None:
        # A worktree holds its HEAD and its own reflog, so removing it takes
        # whatever that HEAD names -- and an agent that committed since the
        # proof has moved it to something nobody cleared.
        self.landed()
        worktree = self.settled_checkout()

        swept = self.reclaimed(
            ProvenTip(str(worktree), OTHER_SHA),
            ProvenTip(self.branch, OTHER_SHA),
        )

        self.assertEqual(swept.reason, MaintenanceReason.TIP_MOVED)
        self.assertEqual(swept.subject, str(worktree))
        self.assertTrue(worktree.exists())
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_checkout_with_no_proof_is_kept(self) -> None:
        self.landed()
        worktree = self.settled_checkout()

        swept = self.reclaimed(ProvenTip(self.branch, OTHER_SHA))

        self.assertEqual(swept.reason, MaintenanceReason.TIP_UNREADABLE)
        self.assertTrue(worktree.exists())

    def test_a_branch_no_proof_names_is_kept(self) -> None:
        # A branch the classification cleared nothing for: it found the name on
        # neither host, and a name that is gone at one reading can be back at
        # the next. Nothing about it was established, so nothing about it may
        # be deleted -- however plainly it is standing there now.
        self.landed()

        swept = self.reclaimed()

        self.assertEqual(swept.outcome, MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, MaintenanceReason.TIP_UNREADABLE)
        self.assertEqual(swept.subject, self.branch)
        self.assertEqual(self.remote_branches(), self.only_branch)
        self.assertEqual(self.local_branches(), self.only_branch)


class RefusedStepTest(_support._MaintenanceTestCase):
    """A step that will not run stops the pass and leaves the rest discoverable."""

    def test_a_failed_remote_delete_keeps_the_ref(self) -> None:
        # The local ref is what the next discovery finds cheapest, so it is the
        # last thing to go -- and a remote delete that failed must not take it.
        self.landed()
        worktree = self.settled_checkout()

        with patch.object(
            reclaim, REMOTE_DELETE, side_effect=_support._refused_delete,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.FAILED)
        self.assertEqual(swept.reason, MaintenanceReason.REMOTE_DELETE_FAILED)
        self.assertEqual(swept.subject, self.branch)
        self.assertFalse(worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_failure_leaves_it_discoverable(self) -> None:
        self.landed()
        self.settled_checkout()

        with patch.object(
            reclaim, REMOTE_DELETE, side_effect=_support._refused_delete,
        ):
            self.only_result()

        self.assertEqual(
            self.only_candidate().artifacts.branches, self.only_branch,
        )

    def test_a_second_pass_finishes_the_rest(self) -> None:
        self.landed()
        self.settled_checkout()

        with patch.object(
            reclaim, REMOTE_DELETE, side_effect=_support._refused_delete,
        ):
            self.only_result()
        swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.CLEANED)
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())

    def test_a_failed_local_delete_is_a_failure(self) -> None:
        self.landed()

        with patch.object(
            reclaim, "_delete_local_ref_at", side_effect=_support._refused_delete,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.FAILED)
        self.assertEqual(swept.reason, MaintenanceReason.LOCAL_DELETE_FAILED)
        self.assertEqual(self.remote_branches(), ())
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_remote_only_failure_stays_discoverable(self) -> None:
        # The one failure with no local evidence left to find it by: nothing
        # here holds this branch, so what re-discovers it is the next listing
        # of the remote and nothing else.
        self.landed()
        _branch_at(self.clone, self.branch, None)

        with patch.object(
            reclaim, REMOTE_DELETE, side_effect=_support._refused_delete,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.FAILED)
        self.assertEqual(swept.reason, MaintenanceReason.REMOTE_DELETE_FAILED)
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
            self.assertLogs(reclaim.log.name, level=WARNING),
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, MaintenanceOutcome.FAILED)
        self.assertEqual(swept.reason, MaintenanceReason.REMOTE_DELETE_FAILED)
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

        self.assertEqual(swept.outcome, MaintenanceOutcome.FAILED)
        self.assertEqual(
            swept.reason, MaintenanceReason.WORKTREE_REMOVAL_FAILED,
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

        self.assertEqual(swept.outcome, MaintenanceOutcome.CLEANED)
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

        self.assertEqual(swept.outcome, MaintenanceOutcome.CLEANED)
        self.assertEqual(self.local_branches(), ())
        self.assertEqual(self.remote_branches(), ())
        self.assertEqual(swept.candidate.artifacts.spec.slug, WIDGET_SLUG)


class Stopping:
    """A continuation a test flips, standing in for the signal that flips it."""

    def __init__(self) -> None:
        self.going = True

    def __call__(self) -> bool:
        return self.going


class StopsWhileClassifying:
    """A classification the run is stopped during, on the real classifier.

    Where a signal really lands. The readings are where a candidate's seconds
    go -- the issue, its pull requests, what the remote carries -- and the
    verdict they end at is what every deletion behind them would be pinned to,
    so a stop that arrives in the middle of them is the one that must not be
    answered by going ahead and deleting.
    """

    def __init__(self, stopping: Stopping) -> None:
        self._stopping = stopping
        self._real = eligibility._classify_artifacts

    def __call__(self, gh, artifacts):
        verdict = self._real(gh, artifacts)
        self._stopping.going = False
        return verdict


class StoppedAfter:
    """A continuation that goes on for a fixed number of candidates.

    What a signal landing mid-repository looks like from inside the pass, and
    the reason the answer is asked per candidate: the caller says yes to the
    candidates before the stop and no to every one behind it, and `asked` is
    the record of how often it was put.
    """

    def __init__(self, allowed: int) -> None:
        self.asked: list[bool] = []
        self._allowed = allowed

    def __call__(self) -> bool:
        going = len(self.asked) < self._allowed
        self.asked.append(going)
        return going


class InterruptedPassTest(_support._MaintenanceTestCase):
    """A pass that may no longer act stops where it is, having taken nothing.

    The candidate would otherwise be cleaned: its tip is one the base carries,
    its checkout has been quiet, and nothing holds a claim on the issue. What
    keeps every artifact is the run being on its way out, which is asked before
    the candidate rather than after it -- and asked again for each candidate
    behind it, so a stop lands between two of them rather than a repository
    later.
    """

    def setUp(self) -> None:
        super().setUp()
        self.tip = self.landed()
        self.worktree = self.settled_checkout()

    def assert_nothing_taken(self, swept) -> None:
        """No answer for the candidate, and every artifact still in place."""
        self.assertEqual(swept, ())
        self.assertTrue(self.worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_stopped_run_takes_nothing(self) -> None:
        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=INFO_LEVEL):
            swept = self.swept(going=_support._stopping)

        self.assert_nothing_taken(swept)

    def test_an_unreadable_continuation_stops_it(self) -> None:
        # Fails closed like every other question in front of a deletion: a run
        # that cannot say whether it is still going is not permission to act.
        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=WARNING):
            swept = self.swept(going=_support._unanswerable_continuation)

        self.assert_nothing_taken(swept)

    def test_a_stop_while_classifying_takes_nothing(self) -> None:
        # The window the per-candidate reading alone would leave open: the
        # candidate clears every gate, the run is stopped while its readings
        # are being taken, and the teardown behind them is what must not run.
        stopping = Stopping()
        with (
            patch.object(
                eligibility,
                _CLASSIFY_ATTR,
                StopsWhileClassifying(stopping),
            ),
            self.assertLogs(_support.LIFECYCLE_LOGGER, level=INFO_LEVEL),
        ):
            swept = self.swept(going=stopping)

        self.assert_nothing_taken(swept)

    def test_the_answer_is_taken_per_candidate(self) -> None:
        # Two candidates of one repository and two readings each -- once
        # before the candidate, once before it is acted on -- with the stop
        # arriving after the first candidate was taken: the second is left
        # exactly as the discovery found it.
        second = _namespaced_branch(WIDGET_SLUG, OTHER_ISSUE_NUMBER)
        _branch_at(self.clone, second, self.tip)
        self.world.publish(self.clone, second, self.tip)
        going = StoppedAfter(2)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=INFO_LEVEL):
            swept = self.swept(going=going)

        self.assertEqual(
            [answer.outcome for answer in swept],
            [MaintenanceOutcome.CLEANED],
        )
        self.assertEqual(going.asked, [True, True, False])
        self.assertEqual(self.remote_branches(), (second,))


class OutcomeVocabularyTest(unittest.TestCase):
    """Every reason a pass can end on names exactly one outcome."""

    def test_every_reason_has_an_outcome(self) -> None:
        self.assertEqual(
            frozenset(maintenance._OUTCOMES),
            frozenset(MaintenanceReason),
        )


if __name__ == "__main__":
    unittest.main()
