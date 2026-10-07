# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite whose receipt was lost settles through a permitted, leased no-op before it is finished.

The grant and its debt are on the comment and the push they licensed reached
PR #42, so what the crash lost is the receipt behind it. The permit, the gated
publication, and the rotation read back are answered, and the finish is stood
in for, since what these cases pin is what licenses the settlement and what a
settlement that did not happen leaves -- the park, and its reason.
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    landed_recovery as _landed_recovery,
    recovery_push as _recovery_push,
    transfer_permits as _transfer_permits,
    transfers,
)
from orchestrator.workflow.engine import rewrite_finish as _finish, rewrite_landed as _rewrite_landed
from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)
from tests.git.base_sync.gate_reads_support import _gate_reads
from tests.workflow.engine.rewrite_retry_permits_support import gated

_LANDED = _recovery_cases._snapshot(remote_head=seed.REPLAYED_SHA)

# The park a settlement that did not happen takes, with HEAD and the anchor kept.
_HELD = (True, fixtures.PARK_PUSH_FAILED)


class LeasedNoOpTest(seed.TransferCase):
    """The permit is the only licence, and the rotation is read back after it."""

    def setUp(self) -> None:
        # The checkout reads as the clean replay a verdict's landing is held to.
        _gate_reads(self)
        super().setUp()

    def test_the_no_op_is_entered_on_the_permit_alone(self) -> None:
        self._settles(_recovery_cases._pushed(landed=True))

        self.finished.assert_called_once()
        entered = self.publishes.call_args.args[2]
        self.assertEqual(
            (entered.head, entered.candidate, entered.permit_only, entered.reconciling),
            (fixtures.PRE_REBASE_SHA, seed.REPLAYED_SHA, True, True),
        )
        self.assertFalse(self._parked()[0])

    def test_every_unsettled_no_op_holds_the_anchor(self) -> None:
        for described, published, terms, detail in (
            (
                "a permit refused ahead of the gate",
                None, {"permits": False}, _landed_recovery._REFUSED_PERMIT,
            ),
            (
                "a permit the gate refused",
                _recovery_cases._pushed(held=True, refused=True), {}, _landed_recovery._REFUSED_PERMIT,
            ),
            (
                "a no-op that did not land",
                _recovery_cases._pushed(), {}, _landed_recovery._REFUSED_NO_OP,
            ),
            (
                "a landing the verdict did not move with",
                _recovery_cases._pushed(landed=True), {"rotated": False},
                _recovery_push._UNROTATED.format(published=seed.REPLAYED_SHA),
            ),
        ):
            with self.subTest(described):
                self._fresh()

                self._settles(published, **terms)

                self.assertEqual(self._parked(), _HELD)
                parks = self.context.gh.posted_comments
                self.assertIn(detail, parks[-1][1])
                self.finished.assert_not_called()
                self.assertEqual(self.publishes.called, published is not None)

    def test_a_hold_writes_only_what_the_gate_left(self) -> None:
        self._settles(_recovery_cases._pushed(held=True))

        self.finished.assert_not_called()
        self.assertFalse(self._parked()[0])
        self.assertIn("late_rewrite_phase", self.context.gh.pinned_data(fixtures.ISSUE))

    def _fresh(self, **terms) -> None:
        """The interrupted attempt afresh, its grant and debt on the comment and its push landed."""
        super()._fresh(**terms)
        seed.granted(self.state)

    def _settles(self, published, *, permits: bool = True, rotated: bool = True) -> None:
        """One pass of the landed road over the outstanding permission, its permit, gate, and rotation answered."""
        self.publishes = MagicMock() if published is None else gated(published)
        self.finished = MagicMock(return_value=True)
        with contextlib.ExitStack() as stack:
            for owner, name, stub in (
                (_transfer_permits, "_permits_the_publication", MagicMock(return_value=permits)),
                (_late_push, "_publishes", self.publishes),
                (transfers, "_rotated_onto", MagicMock(return_value=rotated)),
                (_finish, "finishes_the_recovery", self.finished),
            ):
                stack.enter_context(patch.object(owner, name, stub))
            carried = self._carried(_LANDED.head)
            self.assertTrue(_rewrite_landed.recovers(self.context, _LANDED, carried))

    def _parked(self) -> tuple:
        """Whether the issue waits on a human, and why, as the comment durably says."""
        durable = self.context.gh.pinned_data(fixtures.ISSUE)
        return bool(durable.get(fixtures.KEY_AWAITING_HUMAN)), durable.get(fixtures.KEY_PARK_REASON)
