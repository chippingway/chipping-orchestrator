# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When an unanswered auto-rebase anchor holds a stage handler back.

The refresh settles an interrupted rebase ahead of every handler, on the ticks
that reach it. A tick that does not -- a base fetch that failed, a pull request
that would not read -- leaves the anchor standing, and the handler behind the
dispatcher would spawn an agent over a replay no push has published. These pin
the hold and, as closely, the two shapes a hold would deadlock -- a freeze the
dispatcher answers, and a park only its own stage can release -- beside the
labels the refresh never answers for, which hold whatever the checkout.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import recovery_holds
from orchestrator.git.verification import probes as _probes
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import make_issue

ISSUE = 7

ANCHOR = "be40e5ba" * 5

ANCHOR_KEY = "pending_auto_base_rebase_push_sha"

AUTO_REBASE_PARK = "auto_base_rebase_push_failed"

STAGE_PARK = "review_cap"

# Every kind of park an anchor can stand beside: the refresh's own, a stage's
# review cap, and the two that freeze a branch on a commit its stage still owes.
_EVERY_PARK = (
    AUTO_REBASE_PARK, STAGE_PARK, "agent_timeout", "late_measurement_failed",
)

# The name of a checkout that is not on disk, under the one that is.
MISSING = "gone"

# The stages a relabel can move an attempt onto that the refresh does not
# drive, the read-only conversation stages it skips outright among them.
_UNREFRESHED = (
    WorkflowLabel.IMPLEMENTING, WorkflowLabel.RESOLVING_CONFLICT,
    WorkflowLabel.QUESTION, WorkflowLabel.DISCUSSION,
)


class _HoldCase(unittest.TestCase):
    """A checkout on disk whose HEAD is a commit this store holds."""

    def setUp(self) -> None:
        self.worktree = Path(self.enterContext(
            tempfile.TemporaryDirectory(prefix="orch-dispatch-hold-"),
        ))
        self.head = self._probed("_head_sha", ANCHOR)
        self.present = self._probed("_commit_present", True)

    def _probed(self, name: str, answer) -> MagicMock:
        """Answer one checkout probe for the rest of the test."""
        probe = MagicMock(return_value=answer)
        patcher = patch.object(_probes, name, probe)
        patcher.start()
        self.addCleanup(patcher.stop)
        return probe

    def _holds(
        self, label=WorkflowLabel.VALIDATING, worktree=None, **pinned,
    ) -> bool:
        """Whether dispatch defers for this label, checkout, and comment."""
        return recovery_holds._recovery_holds_dispatch(
            make_issue(ISSUE, label=str(label)), label,
            PinnedState(data={ANCHOR_KEY: ANCHOR, **pinned}),
            worktree or self.worktree,
        )


class RecoveryDispatchHoldTest(_HoldCase):
    """The hold, and each record or park in which holding is a deadlock."""

    def test_an_anchor_holds_every_refreshed_stage(self) -> None:
        for label in (
            WorkflowLabel.VALIDATING, WorkflowLabel.IN_REVIEW,
            WorkflowLabel.FIXING, WorkflowLabel.DOCUMENTING,
        ):
            with self.subTest(label=label):
                self.assertTrue(self._holds(label))

    def test_no_anchor_holds_nothing(self) -> None:
        self.assertFalse(self._holds(**{ANCHOR_KEY: None}))

    def test_every_unrefreshed_label_is_held(self) -> None:
        # A refresh whose fetch failed answers nothing there, and a read-only
        # stage is skipped without an answer at all -- so the handler holds
        # whatever the checkout, and nothing about the checkout is read to say
        # so: the dispatcher takes the ineligible road itself.
        for label in _UNREFRESHED:
            for worktree in (self.worktree, self.worktree / MISSING):
                with self.subTest(label=label, on_disk=worktree.is_dir()):
                    self.assertTrue(self._holds(label, worktree))
        self.head.assert_not_called()

    def test_a_record_freezing_refresh_is_not_held(self) -> None:
        # The refresh skips a branch holding one, and the dispatcher's own
        # reconciliation is what answers it -- held here, neither ever runs.
        self.assertFalse(self._holds(late_candidate_sha=ANCHOR))

    def test_an_unrefreshed_late_claim_is_held(self) -> None:
        # Nothing waits on the refresh there, since the dispatcher answers the
        # anchor itself -- so a generation the reconciliation leaves standing,
        # one an adjudication is still deciding, releases nothing.
        self.assertTrue(self._holds(
            WorkflowLabel.DECOMPOSING, late_candidate_sha=ANCHOR,
        ))

    def test_a_record_nothing_reconciles_is_held(self) -> None:
        # The refresh freezes on this one too, but no owner ahead of the
        # handler answers it -- so it is set aside for the recovery beside an
        # anchor rather than letting the handler through.
        self.assertTrue(self._holds(read_only_baseline_sha=ANCHOR))

    def test_every_park_is_held(self) -> None:
        # A park the refresh left is released by a reply the refresh itself
        # recognizes, and every other is taken down by a handler that runs
        # straight on into its agent -- a timeout re-run, a widened cap, a
        # retried reading -- so the refresh answers first, and a missing
        # checkout is restored under any of them.
        for park_reason in _EVERY_PARK:
            for worktree in (self.worktree, self.worktree / MISSING):
                with self.subTest(park=park_reason, on_disk=worktree.is_dir()):
                    self.assertTrue(self._holds(
                        worktree=worktree,
                        awaiting_human=True,
                        park_reason=park_reason,
                    ))


class UnreachableCheckoutTest(_HoldCase):
    """Which checkouts the refresh cannot walk, and which still hold."""

    def test_an_absent_checkout_is_still_held(self) -> None:
        # The refresh never walks it, but its handler would rebuild it from the
        # local branch -- which may be the unpublished replay -- and hand that
        # to an agent. So it holds, and the dispatcher brings it back.
        self.assertTrue(self._holds(worktree=self.worktree / MISSING))
        self.head.assert_not_called()

    def test_an_unreadable_head_is_held_for_retry(self) -> None:
        # Until the refresh has answered it, a handler let through would run
        # over an anchor no road has read -- a failed base fetch returns before
        # the refresh walks anything at all.
        self.head.return_value = ""

        self.assertTrue(self._holds())

    def test_a_missing_head_commit_is_held_for_retry(self) -> None:
        # A ref pointed at an object this store does not hold still names
        # one, and it is exactly the checkout whose lag cannot be counted.
        self.present.return_value = False

        self.assertTrue(self._holds())

    def test_a_parked_unreadable_head_is_released(self) -> None:
        # The park is the refresh's answer; past it every stage handler stands
        # down on its own and the reply that retries is the refresh's.
        self.present.return_value = False

        self.assertFalse(
            self._holds(awaiting_human=True, park_reason=AUTO_REBASE_PARK),
        )

    def test_a_freeze_releases_a_missing_checkout(self) -> None:
        # The dispatcher's reconciliation answers the record that freezes the
        # refresh, and it is behind the hold.
        self.assertFalse(self._holds(
            worktree=self.worktree / MISSING, late_candidate_sha=ANCHOR,
        ))


if __name__ == "__main__":
    unittest.main()
