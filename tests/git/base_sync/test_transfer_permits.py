# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The recovery permit is asked over the exact frozen publication entry.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    transfer_permits as _transfer_permits,
)
from orchestrator.git.verification import status as _worktree_status
from orchestrator.workflow.late_split import rewrite_values as _rewrite_values
from orchestrator.workflow.stages.implementing import (
    late_transfer as _transfer,
)
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)


class PermitEntryTest(seed.TransferCase):
    """The publication the permit is re-asked over is this tick's own read."""

    def setUp(self) -> None:
        super().setUp()
        seed.granted(self.state)

    def test_an_unenterable_publication_refuses(self) -> None:
        # The entry is the pull request read before any effect, and the terms
        # the record claims are checked against it. Nothing to check them
        # against is a refusal rather than a fall-through.
        carried = MagicMock()

        with patch.object(
            _transfer, "_carried_over", carried,
        ), patch.object(
            _worktree_status, "_worktree_status",
            MagicMock(return_value=_recovery_cases._UNREADABLE_TREE),
        ):
            permitted = _transfer_permits._permits_the_publication(
                self.context, seed.REPLAYED_SHA,
            )

        self.assertFalse(permitted)
        carried.assert_not_called()

    def test_the_permit_reads_the_frozen_entry(self) -> None:
        carried = MagicMock(return_value="carried")

        with patch.object(_transfer, "_carried_over", carried), patch.object(
            _worktree_status, "_worktree_status",
            MagicMock(return_value=_worktree_status._WorktreeStatus(
                readable=True,
            )),
        ):
            permitted = _transfer_permits._permits_the_publication(
                self.context, seed.REPLAYED_SHA, _rewrite_values.LateRewrite(),
            )

        self.assertTrue(permitted)
        gate = carried.call_args.args[0]
        self.assertEqual(gate.entry.pr_number, fixtures.PR_NUMBER)
        self.assertEqual(gate.candidate, seed.REPLAYED_SHA)
        self.assertTrue(gate.reconciling)
