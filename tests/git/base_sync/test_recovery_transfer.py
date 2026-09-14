# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A refused recovery reset preserves the debt and anchor it could not retire."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.git import commands as _commands
from orchestrator.git.base_sync import (
    replay_recovery as _replay_recovery,
    transfers,
)
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)


class RefusedResetRetentionTest(seed.TransferCase):
    """A reset git refuses keeps the claim the park was taken over."""

    def test_a_foreign_debt_survives_a_refused_reset(self) -> None:
        # The reset is what abandons the replay, and so what licenses dropping
        # a debt naming anything else. Refused, the branch may still be where
        # the attempt left it, and the comment is the only account of both.
        self.state.set(_recovery_cases.ANCHOR_KEY, seed.ACCEPTED_SHA)
        seed.owes(self.state, seed.FOREIGN_SHA, seed.ACCEPTED_SHA)

        with patch.object(
            _commands, "_git_hardened", MagicMock(return_value=(
                fixtures._git_result(
                    returncode=fixtures.GIT_FAILURE_EXIT_CODE,
                )
            )),
        ):
            _replay_recovery._route_an_unpublished_head(
                self.context, _recovery_cases._snapshot(),
                transfers._carried_by(self.context, seed.REPLAYED_SHA),
            )

        pinned = self.context.gh.pinned_data(fixtures.ISSUE)
        self.assertEqual(pinned["late_approved_sha"], seed.FOREIGN_SHA)
        self.assertEqual(pinned["late_approved_lease"], seed.ACCEPTED_SHA)
        self.assertEqual(pinned[_recovery_cases.ANCHOR_KEY], seed.ACCEPTED_SHA)
        self.assertTrue(pinned["awaiting_human"])
