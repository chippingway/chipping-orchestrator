# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why a rewrite the pull request already carries may not be finished, read off the comment and the checkout.

The git owner names the reason; the workflow's road parks on it
(`tests/workflow/engine/test_rewrite_landed.py`). Every case here is one head
the remote and the checkout agree on past the anchor, and what decides it is
the attempt's record, the mark, the transfer beside them, and -- under a
verdict only -- whether the checkout reads clean.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.base_sync import (
    landed_recovery as _landed_recovery,
    transfer_publication as _transfer_publication,
)
from orchestrator.git.verification.status import _WorktreeStatus
from tests.git.base_sync import (
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)

_CLEAN = _WorktreeStatus(readable=True)
_UNCOMMITTED = _WorktreeStatus(readable=True, paths=("scratch.txt",))
_UNREADABLE = _WorktreeStatus(readable=False)

_UNPROVEN = _landed_recovery._UNPROVEN_LANDING.format(published=seed.REPLAYED_SHA)


class _LandingCase(seed.TransferCase):
    """An interrupted rebase of an adjudicated head whose push PR #42 already carries."""

    def _why(self, status: _WorktreeStatus = _CLEAN) -> str:
        """The reason the landed replay may not be finished over a checkout reading `status`, or ""."""
        head = seed.REPLAYED_SHA
        return _landed_recovery._unfinishable(self.context, head, self._carried(head), status)


class AccountedLandingTest(_LandingCase):
    """A landing the comment accounts for has no reason to hold it."""

    def test_an_accounted_landing_may_be_finished(self) -> None:
        for described, recorded, records, status in (
            # No verdict: nothing to account for and no tree to prove.
            ("an ordinary landing over any tree", None, (), _UNREADABLE),
            ("a settled transfer over a clean tree", seed.RECORDED, (seed.settled,), _CLEAN),
            # The receipt, the paid debt, and the rotation are what the leased
            # no-op owes, not what it has to show.
            ("an outstanding permission", seed.RECORDED, (seed.granted,), _CLEAN),
            # The replay the permit alone published, vouched for by the
            # permission that licensed it.
            ("a replay in flight its permission vouches for", seed.DECLARED, (seed.granted,), _CLEAN),
        ):
            with self.subTest(described):
                if recorded is None:
                    self.context = seed.context()
                else:
                    self._fresh(pending_rewrite=recorded)
                for record in records:
                    record(self.context.state)

                self.assertEqual(self._why(status), "")


class UnaccountedLandingTest(_LandingCase):
    """Every landing nobody can account for is named for the human who has to reconcile it."""

    def test_a_foreign_mark_holds_the_route(self) -> None:
        _recovery_cases._announced(self.context, seed.FOREIGN_SHA)

        self.assertEqual(self._why(), _landed_recovery._FOREIGN_MARK)

    def test_an_unrecorded_landing_is_nobody_s(self) -> None:
        # The remote and the checkout agreeing proves only that they agree.
        for described, recorded in (
            ("a record naming another head", replace(seed.RECORDED, sha=seed.FOREIGN_SHA)),
            ("a damaged record", seed.DAMAGED),
            ("no record at all", seed.ABSENT),
            ("terms in flight with no permission to vouch", seed.DECLARED),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=recorded)

                self.assertEqual(self._why(), _UNPROVEN)

    def test_a_verdict_needs_a_clean_tree(self) -> None:
        # Under a verdict only; a tree nobody could read is not a clean one.
        seed.settled(self.state)
        for described, status in (
            ("uncommitted work", _UNCOMMITTED),
            ("a tree nobody could read", _UNREADABLE),
        ):
            with self.subTest(described):
                self.assertEqual(self._why(status), _landed_recovery._LOOSE_TREE)

    def test_an_unaccounted_transfer_holds_the_route(self) -> None:
        # A settled transfer whose debt still stands is a write that did not
        # land whole; a mark beside a permission still outstanding is too.
        seed.settled(self.state)
        seed.owes(self.state, seed.REPLAYED_SHA, seed.ACCEPTED_SHA)

        self.assertEqual(self._why(), _transfer_publication._UNPAID.format(owed=seed.REPLAYED_SHA))

        self._fresh()
        seed.granted(self.state)
        _recovery_cases._announced(self.context, seed.REPLAYED_SHA)

        self.assertEqual(self._why(), _landed_recovery._ANNOUNCED_UNSETTLED)
