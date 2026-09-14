# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Checkout evidence selects a replay retry or the divergence fallback.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.base_sync import (
    transfer_values as _transfer_values,
)
from tests.git.base_sync import (
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)


class CheckoutRouteTest(seed.TransferCase):
    """One checkout the pull request is not standing on selects one road."""


    def test_a_record_that_disowns_the_checkout_parks(self) -> None:
        for described, pending in (
            ("in pieces", seed.DAMAGED),
            ("naming another commit", replace(seed.RECORDED, sha=_recovery_cases._MOVED)),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=pending)
                _recovery_cases._assert_selects(self, "_park_unrecorded_recovery")

    def test_a_recorded_replay_is_retried(self) -> None:
        retried = _recovery_cases._assert_selects(self, _recovery_cases.RETRY_PUSH)

        # The record already names the checkout, so the permit is not the
        # only thing that could vouch for it.
        self.assertIs(retried.call_args.kwargs.get("permit_alone"), False)

    def test_a_replay_in_flight_is_retried(self) -> None:
        # The window between `git rebase` returning and the write that names
        # what it produced: the terms are on the comment, no id names the
        # head, and the verdict is the only thing that can vouch for it.
        self._fresh(pending_rewrite=seed.DECLARED)

        retried = _recovery_cases._assert_selects(self, _recovery_cases.RETRY_PUSH)

        self.assertIs(retried.call_args.kwargs.get("permit_alone"), True)
        self.assertEqual(
            retried.call_args.args[2], _transfer_values._Handoff.UNRECORDED,
        )

    def test_this_routes_own_grant_reopens_that_road(self) -> None:
        # The retry above persists its permission before it pushes, so a crash
        # there leaves terms with no head beside an outstanding grant. Refused
        # as the plain in-flight window, this route would park every crash its
        # own durable write caused -- on counts that read a replay as
        # divergence -- and leave the permission with nothing to spend it.
        self._fresh(pending_rewrite=seed.DECLARED)
        seed.granted(self.state)

        retried = _recovery_cases._assert_selects(self, _recovery_cases.RETRY_PUSH)

        self.assertEqual(
            retried.call_args.args[2], _transfer_values._Handoff.OUTSTANDING,
        )


    def test_a_moved_remote_falls_back_to_the_counts(self) -> None:
        for described, counts, answer in (
            ("no reading happened", {}, "_reject_unknown_recovery_comparison"),
            ("commits of its own", {"behind": 1}, "_park_diverged_recovery"),
            ("strictly ahead", {"ahead": 1}, _recovery_cases.RETRY_PUSH),
        ):
            with self.subTest(described):
                self._fresh()
                _recovery_cases._assert_selects(self,
                    answer, _recovery_cases._snapshot(remote_head=_recovery_cases._MOVED, **counts),
                )
