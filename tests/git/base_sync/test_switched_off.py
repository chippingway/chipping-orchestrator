# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a base refresh does on an install with the size gate switched off.

`DECOMPOSE=off` decides what ENTERS the gate, and both seams here enter it
with fresh work: the commit a rebase rewrites the branch into, and the commit
an interrupted tick left ahead of the remote. No developer ran on either, and
that is exactly the fact these cases pin down as the WRONG one to answer the
switch with -- nothing on the pinned comment asked for either commit to be
read, so neither is a reading this gate already took.

Read as reconciliations they would be measured anyway, which is the failure an
operator who turned the gate off would meet as a pull request nobody grew
being routed into an adjudication it never opted into.
"""

from __future__ import annotations

import contextlib
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import persistence, recovery_push as _recovery_push
from orchestrator.git.verification import status as _worktree_status
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    refresh_test_support as support,
)
from tests.git.base_sync.gate_reads_support import (
    _gate_reads,
    _gate_switched_off,
    _oversized_count,
)
from tests.git.base_sync.refresh_scenarios import (
    PUSH_PATCH,
    _clean_rebase_scenario,
)

ISSUE = 7

PUSH_BRANCH = "_push_branch"
DIRTY_FILES = "_worktree_dirty_files"
FINALIZE_HELPER = "_finalize_recovered_rebase"

LABEL_VALIDATING = "workflow:validating"
LABEL_DECOMPOSING = "workflow:decomposing"


class SwitchedOffRebaseTest(
    support._SyncWorktreeWithBaseFixture, unittest.TestCase,
):
    """The rebase half: fresh work, not a reading this gate ever took."""

    def test_an_oversized_rebase_still_publishes(self) -> None:
        self._seed_pr_issue(label=LABEL_VALIDATING)
        counted = _oversized_count()

        with _gate_switched_off(counted):
            scenario = _clean_rebase_scenario()
            scenario.run(self)

        counted.assert_not_called()
        scenario[PUSH_PATCH].assert_called_once()
        self.assertNotIn((ISSUE, LABEL_DECOMPOSING), self.gh.label_history)
        self.assertIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)


class SwitchedOffRecoveryPushTest(unittest.TestCase):
    """The recovery half: a commit an interrupted tick left unpushed.

    Its own class because the seam is reached without a refresh running at
    all -- the recovery owns the tick -- and what it needs seeded is the
    comparison it found rather than a worktree behind its base.
    """

    def setUp(self) -> None:
        _gate_reads(self)

    def test_an_oversized_recovery_still_publishes(self) -> None:
        counted = _oversized_count()
        push = MagicMock(return_value=True)

        with _gate_switched_off(counted), self._push_patches(push):
            pushed = _recovery_push._retry_recovery_push(
                fixtures._recovery_context(), fixtures._snapshot(ahead=1),
            )

        self.assertTrue(pushed)
        counted.assert_not_called()
        push.assert_called_once()

    @contextlib.contextmanager
    def _push_patches(self, push):
        """A clean checkout, a watched push, and a finalize that is a no-op."""
        with patch.object(
            _worktree_status, DIRTY_FILES, MagicMock(return_value=[]),
        ), patch.object(branch_transport, PUSH_BRANCH, push), patch.object(
            persistence,
            FINALIZE_HELPER,
            MagicMock(return_value=True),
        ):
            yield


if __name__ == "__main__":
    unittest.main()
