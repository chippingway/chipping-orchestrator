# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When an unanswered auto-rebase anchor holds a stage handler back.

The refresh settles an interrupted rebase ahead of every handler, on the ticks
that reach it. A tick that does not -- a pull request that would not read --
leaves the anchor standing, and the handler behind the dispatcher would spawn
an agent over a replay no push has published. These pin the hold and, as
closely, the three shapes a hold would deadlock: a label the refresh answers
without a read, a freeze that keeps the refresh away until the dispatcher
answers it, and a park only its own stage can release.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator.git.base_sync import refresh_selection
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import make_issue

ISSUE = 7

ANCHOR = "be40e5ba" * 5

ANCHOR_KEY = "pending_auto_base_rebase_push_sha"

# A worktree nothing reads on the labels these cases take: the one freeze
# that asks a checkout is scoped to stages the refresh does not drive.
WORKTREE = Path("/tmp/base-sync-dispatch-hold-wt")

AUTO_REBASE_PARK = "auto_base_rebase_push_failed"

STAGE_PARK = "review_cap"


def _holds(label=WorkflowLabel.VALIDATING, **pinned) -> bool:
    """Whether dispatch defers for this label and pinned comment."""
    return refresh_selection._recovery_holds_dispatch(
        make_issue(ISSUE, label=str(label)), label,
        PinnedState(data={ANCHOR_KEY: ANCHOR, **pinned}), WORKTREE,
    )


class RecoveryDispatchHoldTest(unittest.TestCase):
    """The hold, and each shape in which holding would be a deadlock."""

    def test_an_anchor_holds_every_refreshed_stage(self) -> None:
        for label in (
            WorkflowLabel.VALIDATING, WorkflowLabel.IN_REVIEW,
            WorkflowLabel.FIXING, WorkflowLabel.DOCUMENTING,
        ):
            with self.subTest(label=label):
                self.assertTrue(_holds(label))

    def test_no_anchor_holds_nothing(self) -> None:
        self.assertFalse(refresh_selection._recovery_holds_dispatch(
            make_issue(ISSUE, label=str(WorkflowLabel.VALIDATING)),
            WorkflowLabel.VALIDATING, PinnedState(data={}), WORKTREE,
        ))

    def test_an_unrefreshed_label_is_not_held(self) -> None:
        # The refresh clears or strands an anchor there with no pull request
        # to read, so there is no transient refusal for a hold to wait out.
        self.assertFalse(_holds(WorkflowLabel.IMPLEMENTING))

    def test_a_record_freezing_refresh_is_not_held(self) -> None:
        # The refresh skips a branch holding one, and the dispatcher's own
        # reconciliation is what answers it -- held here, neither ever runs.
        self.assertFalse(_holds(late_candidate_sha=ANCHOR))

    def test_a_park_its_own_stage_left_is_not_held(self) -> None:
        # The refresh leaves such a park intact, so only the handler can
        # take it down.
        self.assertFalse(
            _holds(awaiting_human=True, park_reason=STAGE_PARK),
        )

    def test_a_park_the_refresh_left_is_held(self) -> None:
        # Every stage handler short-circuits on one, and the reply that
        # releases it is the refresh's own to recognize.
        self.assertTrue(
            _holds(awaiting_human=True, park_reason=AUTO_REBASE_PARK),
        )


if __name__ == "__main__":
    unittest.main()
