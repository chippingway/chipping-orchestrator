# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retiring evidence: only the record the comment holds, and only where the comment can carry it.

A retirement moves a record into the history index. Asked of a transaction the
comment does not record -- one minted and never recorded, or one a later record
has replaced -- it writes nothing: indexing the first would put a revision in
history that no floor covers, and retiring the second would drop the
transaction that IS recorded. A history entry is larger than the record it
replaces, so a retirement the comment could not carry is refused rather than
reported done, and the state is left as it was.
"""
from __future__ import annotations

import copy
import functools
import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_record_test_support as support

# The filler a crowding case fills the rest of the comment with.
_FILLER = "filler"


def _issue() -> PinnedState:
    """The pinned comment of an issue with a pull request and no evidence yet."""
    return PinnedState(comment_id=1, state_data={"pr_number": support.PR_NUMBER})


class StoredRecordTest(unittest.TestCase):
    """Only the transaction the comment records is abandoned."""

    def test_an_unrecorded_mint_is_not_abandoned(self) -> None:
        # Indexed, its revision would sit in history above a floor that never
        # covered it, and every later mint would refuse. An issue recording
        # nothing has nothing to drop either.
        state = _issue()
        unrecorded = support.minted(state)

        for stale in (unrecorded, None):
            with self.subTest(named=stale is not None):
                self.assertFalse(_settlement.retire_pending_evidence(state, stale))
        self.assertEqual(state.data, _issue().data)
        self.assertEqual(support.minted(state).revision, unrecorded.revision)

    def test_a_replaced_transaction_is_not_abandoned(self) -> None:
        # Nor is a readable record dropped unnamed: dropping without an entry
        # is for a record nobody can read.
        state = _issue()
        replaced = support.recorded(state)
        standing = support.recorded(state)
        before = copy.deepcopy(state.data)

        for stale in (replaced, None):
            with self.subTest(named=stale is not None):
                self.assertFalse(_settlement.retire_pending_evidence(state, stale))
        self.assertEqual(state.data, before)

        self.assertTrue(_settlement.retire_pending_evidence(state, standing))
        self.assertIsNone(_record_state.read_pending_evidence(state))
        self.assertEqual(
            [(entry.receipt, entry.retired) for entry in _settlement.read_evidence_history(state)],
            [
                (replaced.receipt, _records.Retirement.ABANDONED),
                (standing.receipt, _records.Retirement.ABANDONED),
            ],
        )


class CommentLimitTest(unittest.TestCase):
    """A retirement fills the comment at most, and one past it writes nothing."""

    def test_an_invalidation_stops_at_the_comment(self) -> None:
        settled = _issue()
        support.settles(settled)

        self._stops_at_the_comment(settled, _settlement.retire_current_evidence)

    def test_an_abandonment_stops_at_the_comment(self) -> None:
        recorded = _issue()
        pending = support.recorded(recorded)

        self._stops_at_the_comment(
            recorded, functools.partial(_settlement.retire_pending_evidence, pending=pending),
        )

    def _stops_at_the_comment(self, base: PinnedState, retire) -> None:
        """`retire` over `base` crowded to fill the comment exactly, then one character past it."""
        probe = PinnedState(state_data=base.data | {_FILLER: ""})
        self.assertTrue(retire(probe))
        filling = "y" * (MAX_PINNED_BODY - len(pinned_state_body(probe.data)))
        fitting = PinnedState(state_data=base.data | {_FILLER: filling})
        past = PinnedState(state_data=base.data | {_FILLER: f"{filling}y"})
        before = copy.deepcopy(past.data)

        self.assertTrue(retire(fitting))
        self.assertEqual(len(pinned_state_body(fitting.data)), MAX_PINNED_BODY)
        self.assertFalse(retire(past))
        self.assertEqual(past.data, before)


if __name__ == "__main__":
    unittest.main()
