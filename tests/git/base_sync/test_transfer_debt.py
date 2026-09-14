# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publication debts are whole and belong to the interrupted attempt.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.git.base_sync import transfer_values as _transfer_values
from orchestrator.workflow.stages.implementing.state import _APPROVED_BASIS
from tests.git.base_sync import (
    transfers_test_support as seed,
)

# A debt standing with no permission beside it that this attempt's own gate
# did not leave: the commit and the head it is leased to, as `(commit, lease)`.
FOREIGN_DEBTS = MappingProxyType({
    "naming some other commit": (seed.FOREIGN_SHA, seed.ACCEPTED_SHA),
    "leased to some other head": (seed.REPLAYED_SHA, seed.FOREIGN_SHA),
})

# A debt standing beside a permission that does not agree with it. The two go
# down in one write, so either disagreement is a comment something took apart.
DISAGREEING_DEBTS = MappingProxyType({
    "owed for some other commit": (seed.FOREIGN_SHA, seed.ACCEPTED_SHA),
    "pinned to some other head": (seed.REPLAYED_SHA, seed.FOREIGN_SHA),
})


class TransferDebtTest(seed.TransferCase):
    """Only a whole debt tied to this replay may survive its classification."""

    def test_a_debt_that_does_not_agree(self) -> None:
        """A permit that grants re-writes both records, so both are asked."""
        for described, (commit, lease) in DISAGREEING_DEBTS.items():
            with self.subTest(described):
                self._fresh()
                seed.granted(self.state)
                seed.owes(self.state, commit, lease)

                self.assertEqual(self._carried(), _transfer_values._Handoff.UNVOUCHED)

    def test_a_debt_no_permission_explains(self) -> None:
        """Only the debt this attempt's own gate leaves is not a claim."""
        for described, (commit, lease) in FOREIGN_DEBTS.items():
            with self.subTest(described):
                self._fresh()
                seed.owes(self.state, commit, lease)

                self.assertEqual(self._carried(), _transfer_values._Handoff.UNVOUCHED)

    def test_an_unreadable_debt_with_no_permission(self) -> None:
        """A basis nothing can name is no debt anybody can tie to this."""
        seed.owes(self.state, seed.REPLAYED_SHA, seed.ACCEPTED_SHA)
        self.state.set(_APPROVED_BASIS, "a bypass nobody grants")

        self.assertEqual(self._carried(), _transfer_values._Handoff.UNVOUCHED)

    def test_this_attempts_own_debt_is_no_claim(self) -> None:
        """The ordinary gate records one for this replay before its push."""
        seed.owes(self.state, seed.REPLAYED_SHA, seed.ACCEPTED_SHA)

        self.assertEqual(self._carried(), _transfer_values._Handoff.UNRECORDED)

    def test_a_debt_whose_basis_cannot_be_named(self) -> None:
        """The third member of the group, which the two readers pass over."""
        seed.granted(self.state)
        self.state.set(_APPROVED_BASIS, "a bypass nobody grants")

        self.assertEqual(self._carried(), _transfer_values._Handoff.UNVOUCHED)
