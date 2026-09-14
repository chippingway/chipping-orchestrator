# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a settlement postponed by a hold may not take with it when it lands.

A settle arriving while a worker holds the issue is recorded rather than
taken, and the recorded one is discharged as the last hold goes. The two are
one critical section, and this is why: between them this owner would be
holding neither a hold nor the reading, and a poll is another thread.

So a close latched in that gap is a reading the discharged settlement would
erase -- along with the memo saying its receipt is already on the thread, and
with the generation moved twice for a single settlement, which is exactly how
a thread that already carries a receipt earns a second one. All of it for a
reading that belongs to the NEXT observation rather than the one being
discharged.

Driven by a lock that lets the race in at the first release it sees, because
that is the seam: one acquisition means the poll arrives after the settlement,
and two mean it arrives between them.
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    observation_receipts as _observation_receipts,
    observation_state as _observation_state,
    observations,
    publication_holds as _publication_holds,
)
from tests.workflow.observation_support import ObservedCloseCase

_SLUG = "acme/widget"
_ISSUE = 7710

# The registry name the instrumented lock is installed over.
_LOCK = "_lock"


class _RacesTheFirstRelease:
    """A lock that lets one thing happen the first time it is given back.

    Wraps the real one, so every other caller is serialized exactly as it was
    and the race runs where no lock is held -- which is the only place another
    thread could ever have run.
    """

    def __init__(self, wrapped, raced) -> None:
        self._wrapped = wrapped
        self._raced = raced
        self.releases = 0

    def __enter__(self):
        return self._wrapped.__enter__()

    def __exit__(self, *closing):
        answered = self._wrapped.__exit__(*closing)
        self.releases += 1
        if self.releases == 1:
            self._raced()
        return answered


class DeferredSettlementRaceTest(ObservedCloseCase, unittest.TestCase):
    """The reading a discharged settlement may not reach.

    One hold, one settle postponed under it, and a poll arriving as that hold
    is given back. What it observes is a close of its own, and nothing about
    the settlement being discharged is about that close.
    """

    def setUp(self) -> None:
        self._fresh_process()
        _publication_holds.claim_publication(_SLUG, _ISSUE)
        observations.settle_close(_SLUG, _ISSUE)

    def test_a_close_latched_in_the_gap_survives(self) -> None:
        # Released and settled apart, the poll's fresh reading lands in
        # between and the settlement taken for the reading BEFORE it erases
        # one it was never about.
        self._released_while(self._polls)

        self.assertTrue(observations.close_observed(_SLUG, _ISSUE))

    def test_its_receipt_memo_survives_too(self) -> None:
        # And the memo saying that reading's receipt is already on the thread.
        # Taken with it, the generation has moved twice for one settlement,
        # the memo is refused as stale, and the next poll posts a second
        # receipt onto a thread that already carries one.
        self._released_while(self._polls)

        self.assertIsNone(_observation_receipts.claim_receipt_post(_SLUG, _ISSUE))

    def test_nothing_arriving_still_settles(self) -> None:
        # The other side, so the critical section is about the gap rather
        # than about the postponed settlement having stopped landing: with no
        # poll in it, the drop the hold recorded is taken as the hold goes.
        _publication_holds.release_publication(_SLUG, _ISSUE)

        self.assertFalse(observations.close_observed(_SLUG, _ISSUE))

    def _polls(self) -> None:
        """One poll observing a close of its own, receipt and all."""
        observations.observe_close(_SLUG, _ISSUE)
        _observation_receipts.receipt_written(
            _observation_receipts.claim_receipt_post(_SLUG, _ISSUE),
        )

    def _released_while(self, races) -> None:
        """Give the hold back, with that poll landing at the first release."""
        with patch.object(
            _observation_state, _LOCK, _RacesTheFirstRelease(threading.Lock(), races),
        ):
            _publication_holds.release_publication(_SLUG, _ISSUE)


if __name__ == "__main__":
    unittest.main()
