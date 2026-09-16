# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a record accepted at the comment's ceiling still has room to finish.

A pinned comment is one GitHub comment, and a transaction is recorded before
anything it describes has happened. So the record is accepted only where the
writes that FOLLOW it still fit beside it, and each of those is a write this
guard cannot take back once it has been made.

Two of them land between the record and the settlement. Publishing the report
records the comment it landed as, so the drift hash and the feedback scans pass
over this orchestrator's own text. And an issue whose commit is not published
yet stands down to the publication gate, which pushes and writes the receipt
naming that commit, the head it replaced, and the pull request it went onto.
Either one unaccounted for is a comment past the ceiling after the report is
already on the thread -- and a write that then fails identically for the rest of
the issue's life.

Each case crowds the comment rather than growing the report, because a long
report makes the PENDING write the binding one and the settlement that drops it
is then nowhere near the ceiling. Crowded around a report that says almost
nothing, what a record is accepted or refused on is the writes this module is
about.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PinnedState,
    pinned_state_body,
)
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _publication_state,
)
from tests.workflow.engine import report_transaction_test_support as support

# What a crowding case fills the rest of the comment with.
_FILLER = "filler"

# A report that says something and almost nothing else, so that what a crowded
# comment refuses on is the settling write rather than the record it drops.
_SHORTEST_REPORT = "r"

# The two ledgers a settlement is measured against: one with nothing in it, and
# one already holding the widest id there is to reserve. The writer that
# records a comment is idempotent, so a measurement reserving an id the ledger
# already holds reserves nothing while the real publication -- landing under an
# id of its own -- adds an entry anyway.
_LEDGERS = (
    ("empty", ()),
    ("holding the widest id", (_record_values.MAX_RECORDED_NUMBER,)),
)

# The id the published comment lands under while a ceiling is being measured:
# as wide as this domain records one, and neither of the two a reservation
# would pick, so what a case measures is a real entry rather than the modelled
# one happening to coincide with it. Left at the single-digit ids a fresh
# double hands out, the slack between a modelled widest id and a real narrow
# one absorbs the entry these cases are about.
_POSTED_ID = 9000000000000000001

# The head the simulated push replaced, at the widest a commit is recorded at,
# which is the one receipt member a record cannot know in advance.
_REPLACED_HEAD = "f" * max(_formats.COMMIT_LENGTHS)


class CeilingTransactionTest(unittest.TestCase, support.ReportTransactionCase):
    """A transaction accepted at the ceiling is one its settlement fits in."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        _record_state.clear_pending_report(self.state)

    def test_a_ceiling_record_finishes(self) -> None:
        # Both writes together, over both shapes each of them can meet. The
        # ledger's second shape is the collision its reservation has to answer:
        # the writer that records a comment is idempotent, so reserving an id
        # the ledger already holds reserves nothing while the publication --
        # landing under an id of its own -- adds an entry anyway.
        #
        # The gate's write is asserted before the reconciliation as well as
        # after it, because those are two separate failures: a receipt the
        # comment cannot carry is refused where the push has already happened,
        # and a settlement it cannot carry is refused where the report is
        # already on the thread.
        #
        # Every case runs the whole sequence, so nothing a reservation models
        # goes unspent: slack left by a write a case skipped is slack that
        # absorbs the shortfall another case is about, and the case then passes
        # over its own bug.
        for ledger, held in _LEDGERS:
            for receipt, seed in _RECEIPTS:
                with self.subTest(ledger=ledger, receipt=receipt):
                    self._settles_from(held, seed)

    def _settles_from(self, held: tuple, seed) -> None:
        """Record at the ceiling in one world, then let everything follow."""
        self._crowded_by(held, seed)
        _publishes_the_code(self)
        self._assert_within_the_comment()

        with _posting_wide(self):
            self.assertFalse(self.reconcile())

        support.assert_one_report(self)
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self._assert_within_the_comment()

    def _crowded_by(self, held: tuple, seed) -> None:
        """Seed one world and record the largest transaction it will carry."""
        self.setUp()
        seed(self)
        self.state.set(support.LEDGER, list(held))
        self.state.set(
            _FILLER, "y" * _largest_filler(self, self._at_the_ceiling()),
        )

        self.assertTrue(_record_state.record_pending_report(
            self.state, self._at_the_ceiling(),
        ))

    def _assert_within_the_comment(self) -> None:
        """The pinned state is one GitHub would still accept as a comment."""
        self.assertLessEqual(
            len(pinned_state_body(self.state.data)), MAX_PINNED_BODY,
        )

    def _at_the_ceiling(self) -> _records.PendingReport:
        """The transaction each crowding case is measured with."""
        return self.pending(report=_SHORTEST_REPORT)



def _seeds_no_receipt(case) -> None:
    """An issue that has published nothing, so the gate writes all three keys."""
    for member in (
        support.PUBLISHED_SHA, support.PUBLISHED_PR, support.PUBLISHED_LEASE,
    ):
        case.state.data.pop(member, None)


def _seeds_an_earlier_receipt(case) -> None:
    """A receipt from a previous publication, which the gate replaces."""
    case.state.set(support.PUBLISHED_SHA, support.MOVED_SHA)
    case.state.set(support.PUBLISHED_PR, support.PR_NUMBER)
    case.state.set(support.PUBLISHED_LEASE, None)


# The two receipts a record can be written against, by what the gate's own
# write then costs the comment.
_RECEIPTS = (
    ("absent", _seeds_no_receipt),
    ("an earlier publication", _seeds_an_earlier_receipt),
)


def _largest_filler(case, pending) -> int:
    """How much other state this issue can carry and still record one.

    Searched rather than computed, because what it has to find is the exact
    character the record is refused at: a case crowding to anything short of
    that measures a comment with room to spare, which is a comment the write
    it is about would have fitted in anyway.
    """
    low, high = 0, MAX_PINNED_BODY
    while low < high:
        tried = (low + high + 1) // 2
        if _records_beside(case, pending, tried):
            low = tried
        else:
            high = tried - 1
    return low


def _records_beside(case, pending, filling: int) -> bool:
    """Whether the transaction fits beside `filling` characters of state."""
    crowded = PinnedState(comment_id=1, state_data={
        **case.state.data, _FILLER: "y" * filling,
    })
    return _record_state.record_pending_report(crowded, pending)


def _publishes_the_code(case) -> None:
    """The receipt the publication gate writes when it pushes the commit."""
    _publication_state._record_publication(
        case.state, support.SOURCE_SHA, _REPLACED_HEAD, support.PR_NUMBER,
    )


def _posting_wide(case):
    """Land the published comment under an id as wide as GitHub issues."""
    return patch.object(case.gh, "_next_comment_id", return_value=_POSTED_ID)


if __name__ == "__main__":
    unittest.main()
