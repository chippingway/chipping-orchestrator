# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When an unanswered auto-rebase anchor holds a stage handler back.

The refresh settles an interrupted rebase ahead of every handler, on the ticks
that reach it. A tick that does not -- a pull request that would not read --
leaves the anchor standing, and the handler behind the dispatcher would spawn
an agent over a replay no push has published. These pin the hold and, as
closely, every shape a hold would deadlock: a label the refresh answers
without a read, a freeze that keeps the refresh away until the dispatcher
answers it, a park only its own stage can release, and a checkout the refresh
cannot reach at all.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import refresh_selection
from orchestrator.git.verification import probes as _probes
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import make_issue

ISSUE = 7

ANCHOR = "be40e5ba" * 5

ANCHOR_KEY = "pending_auto_base_rebase_push_sha"

AUTO_REBASE_PARK = "auto_base_rebase_push_failed"

STAGE_PARK = "review_cap"


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
        return refresh_selection._recovery_holds_dispatch(
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

    def test_an_unrefreshed_label_is_not_held(self) -> None:
        # The refresh clears or strands an anchor there with no pull request
        # to read, so there is no transient refusal for a hold to wait out.
        self.assertFalse(self._holds(WorkflowLabel.IMPLEMENTING))

    def test_a_record_freezing_refresh_is_not_held(self) -> None:
        # The refresh skips a branch holding one, and the dispatcher's own
        # reconciliation is what answers it -- held here, neither ever runs.
        self.assertFalse(self._holds(late_candidate_sha=ANCHOR))

    def test_a_park_its_own_stage_left_is_not_held(self) -> None:
        # The refresh leaves such a park intact, so only the handler can
        # take it down.
        self.assertFalse(
            self._holds(awaiting_human=True, park_reason=STAGE_PARK),
        )

    def test_a_park_the_refresh_left_is_held(self) -> None:
        # Every stage handler short-circuits on one, and the reply that
        # releases it is the refresh's own to recognize.
        self.assertTrue(
            self._holds(awaiting_human=True, park_reason=AUTO_REBASE_PARK),
        )


class UnreachableCheckoutTest(_HoldCase):
    """A checkout the refresh cannot take a recovery in holds nothing."""

    def test_an_absent_checkout_is_not_held(self) -> None:
        # The refresh walks the directories that exist, so an anchor over a
        # missing one is never reached -- and the handler is what makes it.
        self.assertFalse(self._holds(worktree=self.worktree / "gone"))

    def test_an_unreadable_head_is_not_held(self) -> None:
        self.head.return_value = ""

        self.assertFalse(self._holds())

    def test_a_missing_head_commit_is_not_held(self) -> None:
        # A ref pointed at an object this store does not hold still names
        # one, and it is exactly the checkout whose lag cannot be counted.
        self.present.return_value = False

        self.assertFalse(self._holds())


if __name__ == "__main__":
    unittest.main()
