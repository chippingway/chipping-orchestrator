# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A refused carry abandoned into history, with the approval it was recorded for.

Only the transaction the comment records is abandoned, and only a carry -- a
run on another commit than the head it answers for -- takes the approval with
it: its subject written null, and only while that approval is the one the
carry was recorded for, so a replacement another road put in its place
stands. A run on the head it answers for is abandoned alone, and a
transaction the comment does not record is left as it stands. Over the
comment read afresh, a transaction another road recorded meanwhile is never
written away, and a comment filled to its limit still takes the approval's
retirement, which only shrinks it.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import (
    report_record_state as _report_record_state,
    review_subjects as _review_subjects,
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support

# A field another road fills the pinned comment to its limit with.
FILLER = "filler"


class CarryAbandonmentTest(unittest.TestCase, support.VerificationEvidenceCase):
    """What abandoning a transaction leaves of it and of the approval beside it."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.state.set(_review_subjects.APPROVED_SUBJECT, self.subject.recorded())
        self.gh.write_pinned_state(self.issue, self.state)

    def test_a_carry_takes_its_approval(self) -> None:
        for name, carried, approval in (
            ("a carry", True, None),
            ("a run on its own head", False, self.subject.recorded()),
        ):
            with self.subTest(name):
                self.setUp()
                binding = self.binding().retargeted(support.SQUASHED_SHA) if carried else self.binding()
                pending = self.record(binding)

                self.assertTrue(_carries.abandons(self.state, pending))

                self.assertEqual(
                    (
                        _record_state.read_pending_evidence(self.state),
                        [entry.retired for entry in _settlement.read_evidence_history(self.state)],
                        self.state.get(_review_subjects.APPROVED_SUBJECT),
                    ),
                    (None, [_records.Retirement.ABANDONED], approval),
                )

    def test_only_the_recorded_transaction_goes(self) -> None:
        # Minted and never recorded, or recorded on the comment after this
        # tick read it: the comment is not this transaction's to abandon, and
        # neither it nor the approval is touched.
        carry = self.binding().retargeted(support.SQUASHED_SHA)
        unrecorded = _record_state.mint_pending_evidence(self.state, support.ISSUE_NUMBER, carry, ())
        self.assertFalse(_carries.abandons(self.state, unrecorded))

        tick = self.gh.read_pinned_state(self.issue)
        pending = self.record(carry, onto=tick)
        self.record(onto=self.gh.read_pinned_state(self.issue))

        self.assertFalse(_carries.abandons_afresh(self.gh, self.issue, tick, pending))
        self.assertEqual(
            self.gh.read_pinned_state(self.issue).get(_review_subjects.APPROVED_SUBJECT),
            self.subject.recorded(),
        )

    def test_a_replacement_approval_stands(self) -> None:
        # Another road put an approval of another subject in place of the one
        # the carry was recorded for: the carry is abandoned, the replacement
        # left as it stands.
        replacement = {**self.subject.recorded(), "sha": support.REBASED_SHA}
        pending = self.record(self.binding().retargeted(support.SQUASHED_SHA))
        self.state.set(_review_subjects.APPROVED_SUBJECT, replacement)

        self.assertTrue(_carries.abandons(self.state, pending))

        self.assertEqual(self.state.get(_review_subjects.APPROVED_SUBJECT), replacement)

    def test_a_full_comment_still_retires_it(self) -> None:
        # Filled to its limit by another road: the approval's retirement only
        # shrinks the comment, so it is written over the comment read afresh,
        # and what it frees takes the carry's entry too.
        pending = self.record(self.binding().retargeted(support.SQUASHED_SHA))
        self.state.set(FILLER, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(self.state.data))
        self.state.set(FILLER, "y" * room)
        self.gh.write_pinned_state(self.issue, self.state)

        self.assertFalse(_carries.abandons_afresh(self.gh, self.issue, self.state, pending))

        written = self.gh.read_pinned_state(self.issue)
        self.assertEqual(
            (
                written.get(_review_subjects.APPROVED_SUBJECT),
                _record_state.read_pending_evidence(written),
                _report_record_state.fits_the_comment(written.data),
            ),
            (None, None, True),
        )


if __name__ == "__main__":
    unittest.main()
