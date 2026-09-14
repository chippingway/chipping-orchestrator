# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite with its receipt lost settles through a permitted, leased no-op.
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    landed_settlement as _landed_settlement,
    outcomes,
    publication,
    recovery_push as _recovery_push,
    replay_transfer_parks as _replay_transfer_parks,
    transfer_permits as _transfer_permits,
    transfers,
)
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)

_LANDED = _recovery_cases._snapshot(remote_head=seed.REPLAYED_SHA)


class LeasedNoOpTest(seed.TransferCase):
    """The permit is the only licence, and the rotation is read back after it."""

    def setUp(self) -> None:
        super().setUp()
        # The grant and its debt are on the comment; the receipt behind the
        # push that landed is what the crash lost.
        seed.granted(self.state)

    def test_the_no_op_is_entered_on_the_permit_alone(self) -> None:
        self._settles(_recovery_cases._pushed(landed=True))

        self.parked.assert_not_called()
        self.finalized.assert_called_once()
        entered = self.publishes.call_args.args[2]
        self.assertEqual(
            (entered.head, entered.candidate, entered.permit_only, entered.reconciling),
            (fixtures.PRE_REBASE_SHA, seed.REPLAYED_SHA, True, True),
        )

    def test_every_unsettled_no_op_holds_the_anchor(self) -> None:
        for described, published, terms, detail in (
            (
                "a permit refused ahead of the gate",
                None, {"permits": False}, _landed_settlement._REFUSED_PERMIT,
            ),
            (
                "a permit the gate refused",
                _recovery_cases._pushed(held=True, refused=True), {}, _landed_settlement._REFUSED_PERMIT,
            ),
            (
                "a no-op that did not land",
                _recovery_cases._pushed(), {}, _landed_settlement._REFUSED_NO_OP,
            ),
            (
                "a landing the verdict did not move with",
                _recovery_cases._pushed(landed=True), {"rotated": False},
                _recovery_push._UNROTATED.format(published=seed.REPLAYED_SHA),
            ),
        ):
            with self.subTest(described):
                self._settles(published, **terms)

                self.parked.assert_called_once()
                self.assertEqual(self.parked.call_args.args[2], detail)
                self.finalized.assert_not_called()
                self.assertEqual(self.publishes.called, published is not None)

    def test_a_hold_writes_only_what_the_gate_left(self) -> None:
        self._settles(_recovery_cases._pushed(held=True))

        self.parked.assert_not_called()
        self.finalized.assert_not_called()
        self.assertIn("late_rewrite_phase", self.context.gh.pinned_data(fixtures.ISSUE))

    def _settles(self, published, *, permits: bool = True, rotated: bool = True) -> None:
        """One receipting pass, with the permit, the gate, and the rotation answered."""
        self.publishes = MagicMock(return_value=published)
        gated = MagicMock()
        gated._publishes = self.publishes
        self.parked = _recovery_cases._handled()
        self.finalized = _recovery_cases._handled()
        with contextlib.ExitStack() as stack:
            for owner, name, stub in (
                (_transfer_permits, "_permits_the_publication", MagicMock(return_value=permits)),
                (publication, "_gated_publication", MagicMock(return_value=gated)),
                (transfers, "_rotated_onto", MagicMock(return_value=rotated)),
                (_replay_transfer_parks, "_park_unfinished_recovery", self.parked),
                (outcomes, "_finalize_already_published_recovery", self.finalized),
            ):
                stack.enter_context(patch.object(owner, name, stub))
            self.assertTrue(_landed_settlement._settle_published_recovery(self.context, _LANDED))
