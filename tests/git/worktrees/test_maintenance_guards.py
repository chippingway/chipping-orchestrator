# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claims and recent activity retain a candidate before mutation."""
from __future__ import annotations

import os
import time
from unittest.mock import PropertyMock, patch

from orchestrator.git.worktrees import (
    activity_evidence as _activity_evidence,
    maintenance,
    maintenance_results as _maintenance_results,
    reclaim,
)
from orchestrator.git.worktrees.models import ProbeAnswer
from tests.git.worktrees import (
    artifact_git as _artifact_git,
    maintenance_guard_support as _guard_support,
    maintenance_host as _maintenance_host,
    maintenance_payloads as _maintenance_payloads,
    maintenance_test_support as _support,
)
from tests.git.worktrees.eligibility_test_support import (
    ISSUE_NUMBER,
)
from tests.support.git import (
    _run_git,
)
from tests.support.writer_claims import claimable, held_elsewhere, unusable_namespace

# The reads that classify a candidate and the three teardown steps, each on
# the owner the pass calls it through.
_READS = ("get_issue", "read_pinned_state")

_TEARDOWN = ("_remove_recognized_worktree", "_delete_remote_branch_at", "_delete_local_ref_at")

_STEPS = (*_READS, *_TEARDOWN)

# What a second writer asking at every call of a step is answered, while the
# pass holds the issue.
_REFUSED_EVERY_TIME = frozenset((False,))

# The ways a writer claim is refused: another poller holds it, its namespace
# takes no lock, and the repository id it is keyed on would not read.
_REFUSALS = ("held elsewhere", "unusable namespace", "unkeyed")


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


class WriterClaimTest(_support._MaintenanceTestCase):
    """The issue's writer claim is held from the first reading of the issue through the teardown."""

    def setUp(self) -> None:
        super().setUp()
        self.landed()
        self.worktree = self.settled_checkout()

    def test_a_refused_claim_keeps_it_unread(self) -> None:
        # Every refusal is answered alike: nothing about the issue is read, and
        # nothing it holds on the host or the remote is touched.
        for name, refusal in zip(_REFUSALS, self.refusals(), strict=True):
            with (
                self.subTest(refusal=name),
                refusal,
                patch.object(self.gh, "get_issue", wraps=self.gh.get_issue) as fetched,
            ):
                swept = self.only_result()
                fetched.assert_not_called()

            self.assertEqual(
                (swept.outcome, swept.reason, swept.subject),
                (
                    _maintenance_results.MaintenanceOutcome.RETAINED,
                    _maintenance_results.MaintenanceReason.WRITER_CLAIM_REFUSED,
                    f"#{ISSUE_NUMBER}",
                ),
            )
            self.assertTrue(self.worktree.exists())
            self.assertEqual(self.local_branches(), self.only_branch)
            self.assertEqual(self.remote_branches(), self.only_branch)

    def test_the_claim_spans_reading_to_teardown(self) -> None:
        # Each read the classification takes and each teardown step finds the
        # issue held, so no other writer on this host could have moved what the
        # deletions are spent on -- and the claim is given back once they ran.
        seen: dict[str, list[bool]] = {}
        self.probed(self.gh, _READS, seen)
        self.probed(reclaim, _TEARDOWN, seen)

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.CLEANED)
        self.assertFalse(self.worktree.exists())
        claimable_at = {step: set(seen[step]) for step in _STEPS}
        self.assertEqual(claimable_at, dict.fromkeys(_STEPS, _REFUSED_EVERY_TIME))
        self.assertTrue(claimable(self.gh.repo_id, ISSUE_NUMBER))

    def refusals(self) -> tuple:
        """One context per refusal `_REFUSALS` names, in its order, each keyed on this case's issue."""
        return (
            held_elsewhere(self.gh.repo_id, ISSUE_NUMBER),
            unusable_namespace(),
            patch.object(type(self.gh), "repo_id", new_callable=PropertyMock, side_effect=RuntimeError("no id")),
        )

    def probed(self, owner, steps, seen) -> None:
        """Wrap each of `steps` on `owner` in a probe recording, by step, whether a second writer could claim."""
        key = (self.gh.repo_id, ISSUE_NUMBER)
        for step in steps:
            seen[step] = []
            probe = _guard_support.ClaimProbe(getattr(owner, step), key, seen[step])
            self.enterContext(patch.object(owner, step, probe))
