# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a pull request that is over does to a transaction it cannot act on.

The park is the one answer the tick that takes it cannot take back, and the
stage terminal that drains a merged or closed pull request runs BEHIND the
guard that takes it. So every refusal this owner makes over its own RECORDS has
to stand behind the pull-request reading: taken ahead of it, a transaction owed
to work that has already merged parks instead of retiring and strands the issue
in front of the handler that would have finished it -- for as long as the
damage stands, which for a record nothing here produced is until a human
notices.

Each case is written twice over: once against a pull request that has ended,
where the record is dropped, and once against the same damage on a live one,
where it parks. The second is what makes the first mean something -- without it
a retirement could as easily be damage that stopped being damage.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
)
from tests.workflow.engine import (
    report_settled_fixture as fixture,
    report_transaction_test_support as support,
)


class EndedPullRequestTest(unittest.TestCase, support.ReportTransactionCase):
    """Work that is over retires the transaction whatever the records say."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_an_ending_retires_past_refusals(self) -> None:
        for damage, seed in _REFUSALS:
            for ending, over in _ENDED:
                with self.subTest(damage=damage, ending=ending):
                    self.setUp()
                    seed(self)
                    setattr(self.pull_request, ending, over)

                    self.assertFalse(self.reconcile())

                    self._assert_retired()

    def test_the_same_damage_parks_while_open(self) -> None:
        # The control the retirements are read against: nothing above is
        # retiring because the damage stopped being damage.
        for damage, seed in _REFUSALS:
            with self.subTest(damage=damage):
                self.setUp()
                seed(self)

                self.assertTrue(self.reconcile())

                support.assert_parked(self)
                self.assertTrue(
                    _record_state.carries_pending_report(self.state),
                )

    def _assert_retired(self) -> None:
        """The record is dropped, nothing was posted, and no park was taken."""
        self.assertEqual(support.report_comments(self), [])
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self.assertIsNone(self.state.get(support.PARK_REASON))


def _seeds_a_damaged_companion(case) -> None:
    """A current report claimed on the comment that nobody can read back."""
    case.state.set(
        _records.CURRENT_REPORT, {"revision": fixture.SETTLED_REVISION},
    )
    case.record()


def _seeds_a_disagreeing_handoff(case) -> None:
    """A handoff under this receipt naming another publication entirely."""
    pending = case.pending()
    fixture.records_current(
        case.state, pending.subject, pending.report_revision,
    )
    fixture.records_handoff(
        case.state, support.RECEIPT, pending.report_revision, support.MOVED_SHA,
    )
    case.record()


def _seeds_a_stale_record(case) -> None:
    """A newer report already recorded for this pull request."""
    fixture.records_current(
        case.state, case.pending().subject, fixture.NEXT_REVISION,
    )
    fixture.records_handoff(
        case.state, fixture.EARLIER_RECEIPT, fixture.NEXT_REVISION,
        support.SOURCE_SHA,
    )
    case.record()


# Every shape that parks a live transaction, by the damage it stands for. Each
# has to retire rather than park once the pull request is over.
_REFUSALS = (
    ("damaged companion", _seeds_a_damaged_companion),
    ("disagreeing handoff", _seeds_a_disagreeing_handoff),
    ("stale record", _seeds_a_stale_record),
)

# The two ways a pull request is over, paired with the attribute each is read
# off.
_ENDED = (("merged", True), ("state", "closed"))


if __name__ == "__main__":
    unittest.main()
