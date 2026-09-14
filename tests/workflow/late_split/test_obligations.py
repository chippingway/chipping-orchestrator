# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The external obligations' identity, consumer, and opacity rules."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split.formats import InvalidLateValue
from orchestrator.workflow.late_split.obligations import (
    LateObligations,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from tests.workflow.late_split import generation_test_support as _support

_BRANCH = "orchestrator/issue-1"
_OTHER_BRANCH = "orchestrator/issue-2"


class ResourceLedgerTest(unittest.TestCase):
    """The ledger records one entry per resource, however often it is written."""

    def test_repeating_a_resource_updates_its_entry(self) -> None:
        pending = LateResource(
            kind=LateResourceKind.SNAPSHOT_REF, target=_support.SNAPSHOT_REF,
        )
        reconciled = LateResource(
            kind=LateResourceKind.SNAPSHOT_REF,
            target=_support.SNAPSHOT_REF,
            resource_state=LateResourceState.RECONCILED,
        )
        recorded = LateObligations().with_resource(pending).with_resource(reconciled)
        self.assertEqual(recorded.resources, (reconciled,))

    def test_a_different_target_is_its_own_entry(self) -> None:
        first = LateResource(
            kind=LateResourceKind.BRANCH, target=_BRANCH,
        )
        second = LateResource(
            kind=LateResourceKind.BRANCH, target=_OTHER_BRANCH,
        )
        recorded = LateObligations().with_resource(first).with_resource(second)
        self.assertEqual(recorded.resources, (first, second))

    def test_only_an_issue_number_is_a_consumer(self) -> None:
        # The ledger decides whether a snapshot may be reclaimed, so a value
        # nobody can ask GitHub about may not be converted into one.
        for damaged in (True, 2.5, "7", 0, -3):
            with self.subTest(damaged=damaged), self.assertRaises(InvalidLateValue):
                LateObligations().with_consumers((damaged,))

    def test_consumers_are_deduplicated_and_ordered(self) -> None:
        # The reclamation sweep walks this ledger, so a child recorded twice
        # would be asked about twice.
        recorded = LateObligations().with_consumers((7, 3)).with_consumers((3, 5))
        self.assertEqual(recorded.consumers, (3, 5, 7))


class ObligationOpacityTest(unittest.TestCase):
    """An obligation this binary cannot type is one nothing may read past."""

    def test_a_typed_record_owes_nothing_opaque(self) -> None:
        self.assertFalse(LateObligations().is_opaque)

    def test_either_ledger_makes_the_record_opaque(self) -> None:
        for held in ("opaque_resources", "opaque_consumers"):
            with self.subTest(ledger=held):
                self.assertTrue(
                    LateObligations(**{held: "[1]"}).is_opaque,
                )


if __name__ == "__main__":
    unittest.main()
