# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a settlement by one road is the completion of a record on the other.

A settlement copies its record's mode, so the road is one more member a replay
has to find agreeing before it drops a pending record as finished. Seeded by
hand here, because nothing this build does writes the contradiction: a pair that
says it VERIFIED, carrying everything a publication of the record in hand would
have left.
"""

from __future__ import annotations

import unittest

from orchestrator.github.developer_reports import content_digest
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from tests.workflow.engine import report_transaction_test_support as support

# A comment no test posted, for a settlement seeded by hand to point at.
_SETTLED_ELSEWHERE = 4242

# The member of the settled record saying which road settled the report.
_MODE = "mode"

# The road the seeded settlement's record says it took, as the comment spells
# it, beside whether the transaction parks on it: a contradiction does, and so
# does a `null` naming no road, while the legacy record without the member does
# not.
_ROADS = (
    ({_MODE: str(_records.ReportMode.VERIFY)}, True),
    ({_MODE: None}, True),
    ({}, False),
)


def _settle_elsewhere(case: support.ReportTransactionCase, road: dict) -> None:
    """Leave the settled pair a publication of the case's record would leave.

    The subject, the revision, the digest of its text and its receipt, at a
    comment no test posted, with its road spelled on the comment as `road`
    has it.
    """
    pending = case.pending()
    _settlement.record_current_report(case.state, _records.CurrentReport(
        subject=pending.subject,
        report_revision=pending.report_revision,
        content_revision=content_digest(pending.report),
        location=ReportLocation(
            pr_number=pending.subject.pr_number, comment_id=_SETTLED_ELSEWHERE,
        ),
    ))
    case.state.set(
        _records.CURRENT_REPORT, case.state.get(_records.CURRENT_REPORT) | road,
    )
    _settlement.record_handoff(case.state, _records.ReportHandoff(
        receipt=pending.receipt,
        pr_number=pending.subject.pr_number,
        report_revision=pending.report_revision,
        source_sha=pending.subject.source_sha,
    ))


class SettledRoadTest(unittest.TestCase, support.ReportTransactionCase):
    """A replay believes a settlement only by the road its record takes."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_settlement_by_the_other_road_parks(self) -> None:
        # Believed, the report is dropped as posted with nothing posted. Held
        # to its road, the debt stands and a human is told, and a road spelled
        # `null` is one nothing here wrote rather than a legacy record: only a
        # settlement without the member was written before any named one, and
        # completes the record still.
        for road, parks in _ROADS:
            with self.subTest(road=road):
                self.setUp()
                _settle_elsewhere(self, road)
                self.record()

                held = self.reconcile()

                owed = _record_state.read_pending_report(self.state)
                parked = self.state.get(support.PARK_REASON)
                self.assertEqual(
                    (held, owed is not None, parked == support.PARK_DAMAGED),
                    (parks, parks, parks),
                )
                self.assertEqual(support.report_comments(self), [])


if __name__ == "__main__":
    unittest.main()
