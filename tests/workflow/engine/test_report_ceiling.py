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

import itertools
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
)
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _publication_state,
)
from tests.workflow.engine import report_transaction_test_support as support

# What a crowding case fills the rest of the comment with.
_FILLER = "filler"

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

# The widest a commit and an identity are recorded at, which is what the
# measurement reserves a receipt's members at.
_WIDEST_COMMIT = "f" * max(_formats.COMMIT_LENGTHS)

_WIDEST_IDENTITY = _record_values.MAX_RECORDED_NUMBER

# A receipt no writer here produces, past every spelling its readers accept and
# so past everything the reservation can model. What a hand edit or an older
# binary leaves on a comment the record still has to fit beside.
_FOREIGN_WIDTH = 8 * max(_formats.COMMIT_LENGTHS)

_FOREIGN_COMMIT = "f" * _FOREIGN_WIDTH

_FOREIGN_IDENTITY = int("9" * _FOREIGN_WIDTH)

# The two reports a ceiling is measured with. Which WRITE a record is refused
# on turns on this: a report that says almost nothing leaves the settlement
# binding, and one near the ceiling leaves the record's own write binding, so a
# case carrying only one of them measures only one of the two.
_REPORTS = (
    ("shortest", "r"),
    ("near the ceiling", "r" * (_record_values.MAX_REPORT_TEXT // 2)),
)


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
        for world, held, seed, report in _WORLDS:
            with self.subTest(world=world):
                self._settles_from(held, seed, self.pending(report=report))

    def _settles_from(self, held: tuple, seed, owed) -> None:
        """Record at the ceiling in one world, then let everything follow."""
        self._crowded_by(held, seed, owed)
        _publishes_the_code(self)
        self._assert_within_the_comment()

        with _posting_wide(self):
            self.assertFalse(self.reconcile())

        support.assert_one_report(self)
        self.assertIsNone(_record_state.read_pending_report(self.state))
        self._assert_within_the_comment()

    def _crowded_by(self, held: tuple, seed, owed) -> None:
        """Seed one world and record the largest transaction it will carry."""
        self.setUp()
        seed(self)
        self.state.set(support.LEDGER, list(held))
        self.state.set(_FILLER, "y" * _largest_filler(self, owed))

        self.assertTrue(_record_state.record_pending_report(self.state, owed))
        # The record's OWN write, before anything follows it. A long report
        # makes this the binding one, and a comment already carrying a receipt
        # spelled wider than any this build writes makes the reserved world the
        # smaller of the two -- so a measurement taken only there accepts a
        # record that is past the ceiling the moment it lands.
        self._assert_within_the_comment()

    def _assert_within_the_comment(self) -> None:
        """The pinned state is one GitHub would still accept as a comment."""
        self.assertLessEqual(
            len(pinned_state_body(self.state.data)), MAX_PINNED_BODY,
        )



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


def _seeds_a_foreign_receipt(case) -> None:
    """A receipt wider than any spelling this build records one at.

    The reservation REPLACES what is there, so against this the reserved world
    is the SMALLER of the two and a measurement taken only there accepts a
    record whose own write is past the ceiling the moment it lands. Nothing
    here produces these values -- a hand edit and an older binary are what put
    them on a comment -- which is the whole point: a record has to fit the
    comment as it actually stands, not only the comment a writer would leave.

    The gate's own write replaces all three, so the receipt is sound again by
    the time anything reads it.
    """
    case.state.set(support.PUBLISHED_SHA, _FOREIGN_COMMIT)
    case.state.set(support.PUBLISHED_PR, _FOREIGN_IDENTITY)
    case.state.set(support.PUBLISHED_LEASE, _FOREIGN_COMMIT)


# The three receipts a record can be written against, by what the gate's own
# write then costs the comment -- or gives back, for the one spelled wider than
# anything this build records.
_RECEIPTS = (
    ("absent", _seeds_no_receipt),
    ("an earlier publication", _seeds_an_earlier_receipt),
    ("wider than anything recorded", _seeds_a_foreign_receipt),
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
        crowded = PinnedState(comment_id=1, state_data={
            **case.state.data, _FILLER: "y" * tried,
        })
        if _record_state.record_pending_report(crowded, pending):
            low = tried
        else:
            high = tried - 1
    return low


# Every world a ceiling is measured in: each ledger, beside each receipt,
# carrying each report. Flat rather than nested at the case, so what a failure
# names is the one world it happened in.
_WORLDS = tuple(
    (f"{ledger} ledger, {receipt} receipt, {size} report", held, seed, report)
    for (ledger, held), (receipt, seed), (size, report)
    in itertools.product(_LEDGERS, _RECEIPTS, _REPORTS)
)


def _publishes_the_code(case) -> None:
    """The receipt the publication gate writes when it pushes the commit."""
    _publication_state._record_publication(
        case.state, support.SOURCE_SHA, _WIDEST_COMMIT, support.PR_NUMBER,
    )


def _posting_wide(case):
    """Land the published comment under an id as wide as GitHub issues."""
    return patch.object(case.gh, "_next_comment_id", return_value=_POSTED_ID)


if __name__ == "__main__":
    unittest.main()
