# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A tick whose base refresh could not reach an interrupted rebase.

The refresh answers a pinned auto-rebase anchor ahead of every handler, but a
pull request that would not read returns before its recovery runs. What is
left for the dispatcher is an issue standing on a replay no push published,
with a handler about to spawn an agent over it -- and the boundary pinned here
is that the tick stops there, while a park its own stage owns still gets to the
handler that can release it, and a checkout that is not on disk is restored
rather than handed to one.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import pr as _pr
from orchestrator.git.verification import probes as _probes
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    paths as _worktree_paths,
)
from orchestrator.workflow.engine import dispatch
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _FAKE_WT, _TEST_SPEC

ISSUE = 7

PR_NUMBER = 42

ANCHOR = "be40e5ba" * 5

ANCHOR_KEY = "pending_auto_base_rebase_push_sha"

VALIDATING = WorkflowLabel.VALIDATING

# The refresh's own read of the pull request, failing the way a transient
# GitHub error does.
_UNREADABLE_PR = RuntimeError("502 from GitHub")


class _InterruptedRebaseCase(unittest.TestCase):
    """A `validating` issue whose rebase died before its grant or its push.

    The attempt pinned its anchor and the terms it was made under, and got no
    further than that: no permission, no debt, no generation -- nothing the
    dispatcher's reconciliation would ever stop a tick for on its own. Its
    checkout is on disk and standing on a commit this store holds.
    """

    def setUp(self) -> None:
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=str(VALIDATING))
        self.gh.add_issue(self.issue)
        self.checkout = Path(self.enterContext(
            tempfile.TemporaryDirectory(prefix="orch-dispatch-recovery-"),
        ))
        for name, answer in (("_head_sha", ANCHOR), ("_commit_present", True)):
            patcher = patch.object(
                _probes, name, MagicMock(return_value=answer),
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def _seed(self, **pinned) -> None:
        self.gh.seed_state(
            ISSUE,
            pr_number=PR_NUMBER,
            branch="orchestrator/acme__widget/issue-7",
            pending_auto_base_rebase_push_sha=ANCHOR,
            pending_auto_base_rebase_rewrite_pr=PR_NUMBER,
            pending_auto_base_rebase_rewrite_stage=str(VALIDATING),
            **pinned,
        )

    def _refreshes_with_an_unreadable_pr(self) -> None:
        """The refresh pass that returns before its recovery can run."""
        with patch.object(self.gh, "get_pr", side_effect=_UNREADABLE_PR):
            _pr._sync_pr_worktree_to_base(
                self.gh, _TEST_SPEC, self.issue,
                self.gh.read_pinned_state(self.issue), _FAKE_WT, PR_NUMBER, 0,
            )

    def _stops(self, checkout: Path | None = None) -> bool:
        """Whether the dispatcher stops this tick short of its handler."""
        with patch.object(
            _worktree_paths, "_worktree_path",
            MagicMock(return_value=checkout or self.checkout),
        ):
            return dispatch._record_stops_the_tick(
                self.gh, _TEST_SPEC, self.issue, VALIDATING,
                self.gh.read_pinned_state(self.issue),
            )


class DeferredRecoveryTest(_InterruptedRebaseCase):
    """The tick the refresh could not finish is not handed to a reviewer."""

    def test_an_unanswered_anchor_stops_the_tick(self) -> None:
        self._seed()
        self._refreshes_with_an_unreadable_pr()

        # The refresh left the anchor exactly where the crash did...
        pinned = self.gh.pinned_data(ISSUE)
        self.assertEqual(pinned.get(ANCHOR_KEY), ANCHOR)
        # ...and the dispatcher defers to it rather than spawning the
        # reviewer over a replay no push has published.
        self.assertTrue(self._stops())

    def test_without_one_the_handler_runs(self) -> None:
        # What says the stop above is the anchor's and nothing else's.
        self.gh.seed_state(ISSUE, pr_number=PR_NUMBER)

        self.assertFalse(self._stops())

    def test_a_park_its_stage_owns_is_not_deadlocked(self) -> None:
        # The refresh leaves a stage's park intact rather than rebasing past
        # it, so holding the handler that can release it would hold for good.
        self._seed(awaiting_human=True, park_reason="review_cap")
        self._refreshes_with_an_unreadable_pr()

        self.assertFalse(self._stops())

    def test_an_absent_checkout_is_held_and_restored(self) -> None:
        # The refresh walks only the checkouts on disk, and the handler would
        # rebuild this one onto the unpublished replay -- so the tick holds and
        # the dispatcher restores it for the next refresh to walk.
        self._seed()
        restore = MagicMock()

        with patch.object(_worktree_creation, "_ensure_pr_worktree", restore):
            self.assertTrue(self._stops(self.checkout / "gone"))

        restore.assert_called_once()
        self.assertEqual(restore.call_args.args[1], ISSUE)

    def test_a_restore_that_fails_still_holds(self) -> None:
        # The next tick tries again; this one still runs no handler.
        self._seed()
        refused = MagicMock(side_effect=RuntimeError("worktree add failed"))

        with patch.object(
            _worktree_creation, "_ensure_pr_worktree", refused,
        ), self.assertLogs("orchestrator.workflow", level="ERROR"):
            self.assertTrue(self._stops(self.checkout / "gone"))


if __name__ == "__main__":
    unittest.main()
