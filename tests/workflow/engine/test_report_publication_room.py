# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Room reserved when a record was accepted can be spent before it settles.

The acceptance measurement is about the pinned comment as it stood. But a
transaction this guard cannot complete STANDS DOWN on purpose -- that is what
keeps an issue from sitting in front of the routes that would fix it -- and
every one of those routes writes to that same comment. A park taken, a retry
notice recorded, a ledger entry added, a watermark advanced: each is work
entitled to the room, and between them they can spend what the record reserved.

The comment they leave is still one GitHub accepts. What no longer fits is the
SETTLEMENT on top of it, which is larger than the record it drops by the
content digest, the exact location, and the whole handoff beside them.

Measured only at acceptance, the report is posted and the write that would
record it is past the ceiling: a comment on the thread, a record still claiming
it is owed, and a retry failing in exactly the same place for the rest of the
issue's life. So the room is proved again on the tick that would use it, before
anything is posted -- where a refusal still costs nothing.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import report_record_state as _record_state
from tests.workflow.engine import report_transaction_test_support as support

# What a case crowds the rest of the comment with.
_FILLER = "filler"

_CROWDING = "y"

# A park a stage takes while a transaction waits behind this guard, and how
# many comments the route that took it recorded posting.
_AGENT_TIMEOUT = "agent_timeout"

_NOTICES = 64

# An id as wide as GitHub issues one, which is what the entries of a ledger
# grown by a busy thread look like.
_POSTED_ID = 9000000000000000001

# The shortest report there is, so the SETTLEMENT is the binding write rather
# than the record's own. A long report makes the record bind, and the growth
# would then be refused at a measurement about the record instead of the one
# this module is about.
_SHORTEST_REPORT = "r"


class GrowthBeforePublicationTest(unittest.TestCase, support.ReportTransactionCase):
    """A record accepted with room settles; one whose room was spent does not."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        _record_state.clear_pending_report(self.state)
        self.owed = self.pending(report=_SHORTEST_REPORT)

        self.assertTrue(
            _record_state.record_pending_report(self.state, self.owed),
        )

    def test_the_accepted_record_settles_as_it_stands(self) -> None:
        # The control the refusal below is read against. Without it, a
        # transaction refused after the growth could as easily be one the
        # fixture never had room for in the first place.
        self.assertFalse(self.reconcile())

        support.assert_one_report(self)
        self._assert_within_the_comment()

    def test_growth_after_acceptance_posts_nothing(self) -> None:
        self._grows_the_comment()

        self.assertFalse(self.reconcile())

        # Nothing posted, nothing written, and the transaction still owed: the
        # tick after the routes below give the room back is the one that
        # settles it.
        support.assert_still_owed(self)
        self.assertEqual(self.gh.write_state_calls, 0)

    def _grows_the_comment(self) -> None:
        """Spend the room the record reserved, on writes entitled to spend it.

        A park a route behind this guard took and the comments it recorded
        posting, and then the comment topped up to the most GitHub will take.
        Nothing here is damage -- the body that comes out is valid, which is
        the whole point: what the acceptance measured is simply not what the
        settlement now has to fit into.
        """
        self.state.set(support.AWAITING_HUMAN, True)
        self.state.set(support.PARK_REASON, _AGENT_TIMEOUT)
        self.state.set(support.LEDGER, [
            _POSTED_ID - recorded for recorded in range(_NOTICES)
        ])
        self.state.set(_FILLER, _CROWDING * self._largest_valid_filler())

        self._assert_within_the_comment()

    def _largest_valid_filler(self) -> int:
        """How much more this comment carries and stays one GitHub accepts.

        Searched against the rendered body rather than against any writer
        under test, so what the case pins is the ceiling itself: the comment
        that comes out is valid, and the settlement is what no longer fits
        beside it.
        """
        low, high = 0, MAX_PINNED_BODY
        while low < high:
            tried = (low + high + 1) // 2
            crowded = {**self.state.data, _FILLER: _CROWDING * tried}
            if len(pinned_state_body(crowded)) <= MAX_PINNED_BODY:
                low = tried
            else:
                high = tried - 1
        return low

    def _assert_within_the_comment(self) -> None:
        """The pinned state is one GitHub would still accept as a comment."""
        self.assertLessEqual(
            len(pinned_state_body(self.state.data)), MAX_PINNED_BODY,
        )


if __name__ == "__main__":
    unittest.main()
