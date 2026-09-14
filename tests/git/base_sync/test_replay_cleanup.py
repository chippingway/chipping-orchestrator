# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Unmoved and relabelled attempts clear only evidence that strands nothing.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    attempts,
    replay_checkout_parks as _replay_checkout_parks,
    replay_cleanup as _replay_cleanup,
    snapshot,
)
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.late_split import rewrites as _rewrites
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
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


class IneligibleLabelTest(seed.TransferCase):
    """A relabel off the refreshed stages clears only what strands nothing.

    Nothing under such a label comes back to fetch or compare, so the anchor
    is either dropped or parked over -- and dropped over anything the attempt
    left, that record is stranded with nothing naming what the branch would go
    back to.
    """

    def setUp(self) -> None:
        super().setUp()
        self._fresh(pending_rewrite=seed.ABSENT)
        self.state.set(_recovery_cases.ANCHOR_KEY, seed.ACCEPTED_SHA)

    def test_an_untouched_anchor_is_cleared(self) -> None:
        self._answers(seed.ACCEPTED_SHA).assert_called_once()

        self.assertFalse(self.state.get(fixtures.KEY_AWAITING_HUMAN))

    def test_a_rotation_moved_past_is_cleared(self) -> None:
        # A settled rotation is never cleared, so once a later adjudication
        # accepts fresh work it describes a commit nothing exempts. Read as a
        # push still owed, every untouched attempt this issue makes would park
        # under a relabel with nothing it did left to release it.
        seed.settled(self.state)
        _rewrites.forget_transfer_proof(self.state)
        seed.adjudicated(self.state, accepted=seed.NEWER_SHA)
        self.state.set(_recovery_cases.ANCHOR_KEY, seed.NEWER_SHA)
        self.context = replace(
            self.context, pending_pre_rebase_sha=seed.NEWER_SHA,
        )

        self._answers(seed.NEWER_SHA).assert_called_once()

        self.assertFalse(self.state.get(fixtures.KEY_AWAITING_HUMAN))


    def test_every_leftover_is_kept(self) -> None:
        for described, recorded, granted, announced, head in (
            ("a recorded replay", seed.RECORDED, False, "", seed.ACCEPTED_SHA),
            ("a damaged record", seed.DAMAGED, False, "", seed.ACCEPTED_SHA),
            ("an announcement", seed.ABSENT, False, seed.REPLAYED_SHA, seed.ACCEPTED_SHA),
            ("an unspent permission", seed.ABSENT, True, "", seed.ACCEPTED_SHA),
            ("a moved checkout", seed.ABSENT, False, "", seed.REPLAYED_SHA),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=recorded)
                self.state.set(_recovery_cases.ANCHOR_KEY, seed.ACCEPTED_SHA)
                if granted:
                    seed.granted(self.state)
                if announced:
                    attempts._announces(self.context, announced)

                self._assert_stranded(head)

    def test_the_stranded_park_is_taken_once(self) -> None:
        # Every poll under the wrong label comes back to the same comment, and
        # a park said again would ratchet the watermark past the reply that
        # releases it.
        self.context = replace(self.context, pending_rewrite=seed.RECORDED)

        self._answers(seed.ACCEPTED_SHA)
        self._answers(seed.ACCEPTED_SHA)

        self.assertEqual(len(self.context.gh.posted_comments), 1)


    def _assert_stranded(self, head: str) -> None:
        """The anchor and the park both stand, and nothing was cleared."""
        self._answers(head).assert_not_called()

        pinned = self.context.gh.pinned_data(fixtures.ISSUE)
        self.assertEqual(pinned[_recovery_cases.ANCHOR_KEY], seed.ACCEPTED_SHA)
        self.assertTrue(pinned[fixtures.KEY_AWAITING_HUMAN])
        self.assertEqual(
            pinned[fixtures.KEY_PARK_REASON], "auto_base_rebase_failed",
        )

    def _answers(self, head: str) -> MagicMock:
        """Answer the relabelled anchor over `head`, handing back the clear."""
        cleared = _recovery_cases._handled()
        with patch.object(
            snapshot, "_clear_ineligible_recovery", cleared,
        ), patch.object(
            _verification_probes, "_head_sha", MagicMock(return_value=head),
        ):
            self.assertTrue(_replay_cleanup._answers_an_ineligible_label(
                replace(self.context, label=_recovery_cases._RESOLVING),
            ))
        return cleared
