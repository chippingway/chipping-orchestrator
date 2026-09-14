# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Replay transfer records refuse contradictory or already receipted publication.
"""
from __future__ import annotations

from dataclasses import replace

from tests.git.base_sync import (
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)


class TransferRouteTest(seed.TransferCase):
    """Debt, permission, and receipt evidence select the recovery refusal."""

    def test_a_debt_no_grant_explains_parks(self) -> None:
        # The refresh lets an approval leased to this anchor through, since it
        # is ordinarily the gate's own record of this replay. One naming some
        # other commit is not, and read as no transfer the replay is pushed and
        # the gate's write replaces the only account of the push it records.
        seed.owes(self.state, seed.FOREIGN_SHA, seed.ACCEPTED_SHA)

        _recovery_cases._assert_selects(self, _recovery_cases.UNVOUCHED)

    def test_publication_evidence_reads_as_a_rollback(self) -> None:
        # Either record proves the remote carried this commit, so a remote
        # back on the anchor has been rolled back and cannot be retried.
        for record in (seed.settled, seed.receipted):
            with self.subTest(record=record.__name__):
                self._fresh()
                record(self.state)

                _recovery_cases._assert_selects(self, "_park_rolled_back_recovery")


    def test_a_transfer_nobody_can_vouch_for_parks(self) -> None:
        # A permission naming a commit this checkout is not standing on is a
        # claim nothing can check, and every other road from here would leave
        # the ordinary gate to measure an adjudicated change again.
        seed.granted(self.state, replace(seed.GRANTED, to_sha=seed.NEWER_SHA))

        _recovery_cases._assert_selects(self, _recovery_cases.UNVOUCHED)

    def test_a_grant_from_another_attempt_still_parks(self) -> None:
        # The permission is what vouches for the head above, so one this
        # build cannot tie to the attempt in hand vouches for nothing.
        self._fresh(pending_rewrite=seed.DECLARED)
        seed.granted(self.state, replace(seed.GRANTED, source_stage=seed.OTHER_STAGE))

        _recovery_cases._assert_selects(self, _recovery_cases.UNVOUCHED)
