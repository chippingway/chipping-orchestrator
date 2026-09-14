# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The recovery push measures ordinary candidates and requires permits for transfers.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.git.measurement import commits as _measurement_commits
from tests.git.base_sync import (
    recovery_push_test_support as _recovery_push_test_support,
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)


class LicensedRetryTest(_recovery_push_test_support._LicensedRetryCase):
    """What the permit decides for a push nothing else may license."""


    def test_assembled_evidence_reaches_the_permit(self) -> None:
        # The grant never landed, so the evidence is re-derived and handed to
        # the permit -- and the gate behind it is told the permit is the whole
        # of what may let this push out.
        self._fresh(pending_rewrite=seed.DECLARED)
        rebuilt = seed.GRANTED
        permits = _recovery_cases._handled()

        entered = self._retries(
            reconstructed=MagicMock(return_value=rebuilt), permits=permits,
        )

        self.assertIs(permits.call_args.args[2], rebuilt)
        self.assertIs(entered.rewrite, rebuilt)
        self.assertTrue(entered.permit_only)

    def test_a_standing_permission_is_the_evidence(self) -> None:
        # The record IS the evidence there, so nothing is assembled and the
        # gate re-asks the permission the grant left.
        entered = self._retries(permits=_recovery_cases._handled())

        self.assertIsNone(entered.rewrite)
        self.assertTrue(entered.permit_only)
        self.assertEqual(entered.candidate, seed.REPLAYED_SHA)

    def test_an_ordinary_replay_is_still_measured(self) -> None:
        # An issue carrying no verdict has no transfer to license anything,
        # so the reissued push is the cumulative gate's as it always was.
        self.context = seed.context()

        entered = self._retries()

        self.assertFalse(entered.permit_only)


class RefusedRetryTest(_recovery_push_test_support._LicensedRetryCase):
    """A replay publishes only under its required permit."""

    def test_a_replay_no_verdict_can_prove_parks(self) -> None:
        # In flight, with evidence that will not assemble: measuring says how
        # big a change is, never whose it is, so there is nothing left to
        # publish it on.
        self._fresh(pending_rewrite=seed.DECLARED)

        with patch.object(
            _measurement_commits, "_freeze_base_commit",
            MagicMock(return_value=_recovery_cases._NO_BASE),
        ):
            self._parks("_park_unproven_replay_recovery", permit_alone=True)

    def test_a_refused_permit_parks_unmeasured(self) -> None:
        self._parks(
            "_park_refused_permit_recovery",
            permits=MagicMock(return_value=False),
        )

    def test_a_permit_the_gate_refuses_parks_too(self) -> None:
        # The permit is asked twice -- here and inside the gate -- so one that
        # stops holding in between is refused there rather than measured.
        self._parks(
            "_park_refused_permit_recovery",
            published=_recovery_cases._pushed(held=True, refused=True),
        )

    def test_a_push_that_moved_no_verdict_parks(self) -> None:
        # The push went out and the rotation did not ride it, so the
        # permission is still outstanding and the anchor stays pinned.
        parked = self._parks(_recovery_cases.UNFINISHED, published=_recovery_cases._pushed(landed=True))

        self.assertIn(seed.REPLAYED_SHA, parked.call_args.args[2])
