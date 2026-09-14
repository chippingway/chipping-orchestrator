# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A granted transfer with a controlled recovery publication.
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    persistence,
    publication,
    recovery_push as _recovery_push,
    replay_transfer_parks as _replay_transfer_parks,
    transfer_evidence as _transfer_evidence,
    transfer_permits as _transfer_permits,
    transfers,
)
from orchestrator.git.verification import status as _worktree_status
from tests.git.base_sync import (
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)


class _LicensedRetryCase(seed.TransferCase):
    """A granted transfer with the permit and gated publication controlled."""

    def setUp(self) -> None:
        super().setUp()
        # The permission the interrupted grant left, which is what every case
        # below but the two that start over is decided on.
        seed.granted(self.state)

    def _parks(self, park: str, **retry) -> MagicMock:
        """Run the retry and pin the single park it takes."""
        parked = _recovery_cases._handled()
        with patch.object(_replay_transfer_parks, park, parked):
            self.assertTrue(self._retry(**retry))
        parked.assert_called_once()
        return parked

    def _retries(self, **retry):
        """Run the retry and hand back the terms the gate was entered on."""
        publishes = MagicMock(return_value=_recovery_cases._pushed(landed=True))
        with patch.object(transfers, "_rotated_onto", _recovery_cases._handled()):
            self.assertTrue(self._retry(publishes=publishes, **retry))
        return publishes.call_args.args[2]

    def _retry(
        self,
        *,
        publishes=None,
        permits=None,
        reconstructed=None,
        published=None,
        permit_alone: bool = False,
    ) -> bool:
        """One reissued push, with the gate and the permit answered."""
        gated = MagicMock()
        gated._publishes = publishes or MagicMock(
            return_value=published or _recovery_cases._pushed(),
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(
                _transfer_permits, "_permits_the_publication", permits or _recovery_cases._handled(),
            ))
            if reconstructed is not None:
                stack.enter_context(patch.object(
                    _transfer_evidence, "_reconstructed", reconstructed,
                ))
            stack.enter_context(patch.object(
                publication, "_gated_publication",
                MagicMock(return_value=gated),
            ))
            stack.enter_context(patch.object(
                persistence, "_finalize_recovered_rebase",
                MagicMock(return_value=True),
            ))
            stack.enter_context(patch.object(
                _worktree_status, "_worktree_dirty_files",
                MagicMock(return_value=[]),
            ))
            return _recovery_push._retry_recovery_push(
                self.context, _recovery_cases._snapshot(),
                transfers._carried_by(self.context, seed.REPLAYED_SHA),
                permit_alone=permit_alone,
            )
