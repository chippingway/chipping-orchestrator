# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claims, changed tips, incomplete proofs, and process stops that retain artifacts."""
from __future__ import annotations

import os
import time
from unittest.mock import patch

from orchestrator.git.worktrees import (
    activity_evidence as _activity_evidence,
    checkout_listing as _checkout_listing,
    eligibility,
    maintenance,
    maintenance_results as _maintenance_results,
)
from orchestrator.git.worktrees.models import ProbeAnswer, ProvenTip, RetentionReason
from tests.git.worktrees import (
    artifact_git as _artifact_git,
    maintenance_guard_support as _guard_support,
    maintenance_host as _maintenance_host,
    maintenance_payloads as _maintenance_payloads,
    maintenance_stop_support as _maintenance_stop,
    maintenance_test_support as _support,
)
from tests.git.worktrees.artifact_test_support import WIDGET_SLUG, _namespaced_branch
from tests.git.worktrees.candidate_host_test_support import _unlink_backlink
from tests.git.worktrees.candidate_refs import _branch_at, _track_file
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
            self.spec, self.world.path(_maintenance_payloads.INSPECTED_DIR), self.branch,
        )

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.BRANCH_CHECKED_OUT)
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
            self.spec, self.world.path(_maintenance_payloads.INSPECTED_DIR), self.branch,
        )
        _unlink_backlink(dropped)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.WARNING):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_UNREADABLE)
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
            _checkout_listing, "_checked_out_branches", return_value=None,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_UNREADABLE)
        self.assertEqual(self.local_branches(), self.only_branch)


class GuardedCandidateTest(_support._MaintenanceTestCase):
    """Everything in front of the mutation keeps the artifacts where they are."""

    def setUp(self) -> None:
        super().setUp()
        self.landed()
        self.worktree = self.settled_checkout()
        self.long_ago = time.time() - _maintenance_host.SETTLED_SECONDS

    def assert_untouched(self, swept) -> None:
        """The candidate is kept, and every artifact is still where it was."""
        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertTrue(self.worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_an_issue_being_run_is_left_alone(self) -> None:
        swept = self.only_result(claimed=_guard_support._always_claimed)

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.ACTIVE_CLAIM)
        self.assertEqual(swept.subject, f"#{ISSUE_NUMBER}")

    def test_a_guard_that_raises_is_read_as_a_claim(self) -> None:
        with self.assertLogs(maintenance.log.name, level=_maintenance_payloads.WARNING):
            swept = self.only_result(claimed=_guard_support._unanswerable_claim)

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.CLAIM_UNREADABLE)

    def test_a_checkout_touched_lately_is_left_alone(self) -> None:
        # The tree is clean and the classification clears it; what keeps it is
        # that somebody was in it moments ago.
        (self.worktree / _maintenance_payloads.LOOSE_FILE).write_text(_maintenance_payloads.LOOSE_CONTENT)
        (self.worktree / _maintenance_payloads.LOOSE_FILE).unlink()

        swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.RECENT_ACTIVITY)

    def test_a_just_committed_checkout_is_left_alone(self) -> None:
        # The tree is clean, the commit is in the base, and the directory's own
        # timestamp is old -- a commit does not move it. What keeps the
        # checkout is the index and reflog that commit rewrote.
        _run_git(
            "commit", "-q", "--allow-empty", "-m", "an agent's own round",
            cwd=self.worktree,
        )
        self.world.publish(self.clone, self.branch, self.branch)
        self.world.publish(self.clone, _artifact_git.BASE_BRANCH, self.branch)
        os.utime(self.worktree, (self.long_ago, self.long_ago))

        swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.RECENT_ACTIVITY)
        self.assertEqual(swept.subject, str(self.worktree))

    def test_an_untimeable_checkout_is_left_alone(self) -> None:
        # The last gate fails closed like every one before it: a tree nobody
        # could time is not one to delete on the strength of the reads that
        # did answer.
        with patch.object(
            _activity_evidence,
            "_quiet_checkout",
            return_value=ProbeAnswer.UNREADABLE,
        ):
            swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.ACTIVITY_UNREADABLE)


class RetainedByClassificationTest(_support._MaintenanceTestCase):
    """A candidate the classification keeps is reported with its own reasons."""

    def assert_kept_for(self, swept, reason: RetentionReason) -> None:
        """The pass reports the classification's answer, in its vocabulary."""
        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.UNPROVEN)
        self.assertEqual(
            tuple(kept.reason for kept in swept.retentions), (reason,),
        )
        self.assertEqual(swept.subject, swept.retentions[0].subject)

    def test_a_dirty_tree_keeps_the_whole_candidate(self) -> None:
        self.landed()
        worktree = self.settled_checkout()
        (worktree / _maintenance_payloads.LOOSE_FILE).write_text(_maintenance_payloads.LOOSE_CONTENT)

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.WORKTREE_DIRTY)
        self.assertTrue(worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_tree_hiding_files_keeps_it(self) -> None:
        # `worktree remove` would take these down without a word, which is why
        # the classification asks about them and the pass never gets a proof.
        _track_file(self.clone, _maintenance_payloads.IGNORE_FILE, f"{_maintenance_payloads.HIDDEN_FILE}\n")
        self.landed()
        worktree = self.settled_checkout()
        (worktree / _maintenance_payloads.HIDDEN_FILE).write_text(_maintenance_payloads.HIDDEN_CONTENT)

        with self.assertLogs(maintenance.log.name, level=_maintenance_payloads.INFO_LEVEL):
            swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.WORKTREE_IGNORED)
        self.assertTrue((worktree / _maintenance_payloads.HIDDEN_FILE).exists())

    def test_an_open_pull_request_keeps_the_branches(self) -> None:
        tip = self.landed()
        self.gh.existing_open_pr[self.branch] = _pull_request(
            _maintenance_payloads.PR_NUMBER, self.branch, tip, state=OPEN_PR_STATE,
        )

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.OPEN_PULL_REQUEST)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_an_issue_that_has_not_ended_keeps_it(self) -> None:
        self.landed()
        self.gh = _github(_terminal_issue(
            closed=False, label_names=(_maintenance_payloads.IMPLEMENTING_LABEL,),
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

        swept = self.reclaimed(ProvenTip(self.branch, _maintenance_payloads.OTHER_SHA))

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_MOVED)
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
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_MOVED)
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_checkout_that_moved_is_kept(self) -> None:
        # A worktree holds its HEAD and its own reflog, so removing it takes
        # whatever that HEAD names -- and an agent that committed since the
        # proof has moved it to something nobody cleared.
        self.landed()
        worktree = self.settled_checkout()

        swept = self.reclaimed(
            ProvenTip(str(worktree), _maintenance_payloads.OTHER_SHA),
            ProvenTip(self.branch, _maintenance_payloads.OTHER_SHA),
        )

        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_MOVED)
        self.assertEqual(swept.subject, str(worktree))
        self.assertTrue(worktree.exists())
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_checkout_with_no_proof_is_kept(self) -> None:
        self.landed()
        worktree = self.settled_checkout()

        swept = self.reclaimed(ProvenTip(self.branch, _maintenance_payloads.OTHER_SHA))

        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_UNREADABLE)
        self.assertTrue(worktree.exists())

    def test_a_branch_no_proof_names_is_kept(self) -> None:
        # A branch the classification cleared nothing for: it found the name on
        # neither host, and a name that is gone at one reading can be back at
        # the next. Nothing about it was established, so nothing about it may
        # be deleted -- however plainly it is standing there now.
        self.landed()

        swept = self.reclaimed()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_UNREADABLE)
        self.assertEqual(swept.subject, self.branch)
        self.assertEqual(self.remote_branches(), self.only_branch)
        self.assertEqual(self.local_branches(), self.only_branch)


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
        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.INFO_LEVEL):
            swept = self.swept(going=_guard_support._stopping)

        self.assert_nothing_taken(swept)

    def test_an_unreadable_continuation_stops_it(self) -> None:
        # Fails closed like every other question in front of a deletion: a run
        # that cannot say whether it is still going is not permission to act.
        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.WARNING):
            swept = self.swept(going=_guard_support._unanswerable_continuation)

        self.assert_nothing_taken(swept)

    def test_a_stop_while_classifying_takes_nothing(self) -> None:
        # The window the per-candidate reading alone would leave open: the
        # candidate clears every gate, the run is stopped while its readings
        # are being taken, and the teardown behind them is what must not run.
        stopping = _maintenance_stop.Stopping()
        with (
            patch.object(
                eligibility,
                _maintenance_payloads._CLASSIFY_ATTR,
                _maintenance_stop.StopsWhileClassifying(stopping),
            ),
            self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.INFO_LEVEL),
        ):
            swept = self.swept(going=stopping)

        self.assert_nothing_taken(swept)

    def test_the_answer_is_taken_per_candidate(self) -> None:
        # Two candidates of one repository and two readings each -- once
        # before the candidate, once before it is acted on -- with the stop
        # arriving after the first candidate was taken: the second is left
        # exactly as the discovery found it.
        second = _namespaced_branch(WIDGET_SLUG, _maintenance_payloads.OTHER_ISSUE_NUMBER)
        _branch_at(self.clone, second, self.tip)
        self.world.publish(self.clone, second, self.tip)
        going = _maintenance_stop.StoppedAfter(2)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.INFO_LEVEL):
            swept = self.swept(going=going)

        self.assertEqual(
            [answer.outcome for answer in swept],
            [_maintenance_results.MaintenanceOutcome.CLEANED],
        )
        self.assertEqual(going.asked, [True, True, False])
        self.assertEqual(self.remote_branches(), (second,))
