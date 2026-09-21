# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned fields a held candidate's route bookkeeping may close.

The late domain spells that vocabulary as literals so it does not import the
four stage packages that own these keys, and that is exactly what lets the two
drift. Caught here, a key added to a route without being added to the reader
fails a test; missed, it fails at a RETRY -- where an unknown member makes the
reader drop the whole group, so a hold's round is never closed and the next
re-entry reruns a developer over feedback that was already answered.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import spends as _spends
from orchestrator.workflow.stages.conflicts import state as _conflicts_state
from orchestrator.workflow.stages.documenting import (
    state as _documenting_state,
)
from orchestrator.workflow.stages.fixing import state as _fixing_state
from orchestrator.workflow.stages.fixing.bookmarks import (
    _cleared_pending_fix_bookmarks,
)
from orchestrator.workflow.stages.validating import state as _validating_state

# Every pinned field a route hands the gate to close on its behalf, read off
# the owners that name them rather than spelled again here.
_ROUTE_SPEND_KEYS = (
    _conflicts_state._SETTLED_OUTCOME,
    _conflicts_state._SETTLED_SHA,
    _conflicts_state._REVIEW_ROUND,
    _documenting_state._SETTLED_DOCS_SHA,
    _fixing_state._REVIEW_ROUND,
    _fixing_state._PENDING_FIX_AT,
    # Not a round or a bookmark: the mark a fixing report transaction's own
    # settlement raises so the tick behind it knows the round is over. It
    # rides the same group because it has to land in the same write.
    _fixing_state._SETTLED_ROUND,
    _validating_state._REVIEW_ROUND,
    *(key for key, _cleared in _cleared_pending_fix_bookmarks()),
)


class SpendableFieldVocabularyTest(unittest.TestCase):
    """Every route's bookkeeping is a field the reader will hand back."""

    def test_every_route_spends_a_known_field(self) -> None:
        for owed in _ROUTE_SPEND_KEYS:
            with self.subTest(owed=owed):
                self.assertIn(owed, _spends.SPENDABLE_FIELDS)

    def test_the_vocabulary_names_nothing_else(self) -> None:
        # A key nothing writes is one nothing should accept back either: it is
        # a field a hand-edited record could set through a retry, and the
        # bound list is the whole of what stops that.
        self.assertEqual(
            _spends.SPENDABLE_FIELDS, frozenset(_ROUTE_SPEND_KEYS),
        )


if __name__ == "__main__":
    unittest.main()
