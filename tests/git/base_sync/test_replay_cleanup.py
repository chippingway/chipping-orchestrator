# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An unmoved replay anchor clears only when it has no unfinished work."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    attempts,
    replay_checkout_parks as _replay_checkout_parks,
    replay_cleanup as _replay_cleanup,
    snapshot,
)
from tests.git.base_sync import (
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)


class UnmovedHeadTest(seed.TransferCase):
    """A checkout on the anchor is a shortcut only where nothing is left.

    HEAD equalling the pinned anchor is two states at once: an attempt that
    got no further than pinning it, and one that got a long way and was UNDONE
    -- a reset whose park write was lost, or a hand at the checkout. Only the
    first may drop the anchor and hand the branch to a fresh rebase.
    """

    def setUp(self) -> None:
        super().setUp()
        # The anchor and the verdict, with no record of a replay: the shape
        # every case here starts from and adds one leftover to.
        self._fresh(pending_rewrite=seed.ABSENT)

    def test_an_unstarted_attempt_hands_the_tick_back(self) -> None:
        # Nothing was left behind, so the anchor costs the issue nothing and
        # the normal rebase flow does the work again on this same tick.
        self.assertFalse(self._answers(shortcut=True))

    def test_a_previous_rotation_is_not_a_rollback(self) -> None:
        # A settled transfer is never cleared, so an issue that ever earned
        # one would fail this test for the rest of its life.
        seed.settled(self.state)

        self.assertFalse(self._answers(shortcut=True))

    def test_every_leftover_is_finished_as_a_rollback(self) -> None:
        for described, recorded, granted, announced in (
            ("a recorded replay", seed.RECORDED, False, ""),
            ("a damaged record", seed.DAMAGED, False, ""),
            ("an unspent permission", seed.ABSENT, True, ""),
            ("a foreign announcement", seed.ABSENT, False, seed.REPLAYED_SHA),
            ("an anchor announcement", seed.ABSENT, False, seed.ACCEPTED_SHA),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=recorded)
                if granted:
                    seed.granted(self.state)
                if announced:
                    attempts._announces(self.context, announced)

                self.assertTrue(self._answers(shortcut=False))


    def _answers(self, *, shortcut: bool) -> bool:
        """Route the unmoved head and pin which of the two roads it takes."""
        cleared = MagicMock(return_value=False)
        parked = _recovery_cases._handled()
        with patch.object(
            snapshot, "_clear_unchanged_recovery", cleared,
        ), patch.object(_replay_checkout_parks, "_park_undone_recovery", parked):
            answered = _replay_cleanup._finish_an_unmoved_head(
                self.context, _recovery_cases._snapshot(local_head=seed.ACCEPTED_SHA),
            )
        taken, refused = (
            (cleared, parked) if shortcut else (parked, cleared)
        )
        taken.assert_called_once()
        refused.assert_not_called()
        return answered
