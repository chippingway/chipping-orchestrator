# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the report records read back as, and what a comment may carry.

The compatibility cases matter most: these keys arrive on issues that are
already running, and an issue that has never seen them has to read back as one
that owes nothing rather than as one whose obligation nobody can describe.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PinnedState,
    pinned_state_body,
)
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import report_record_test_support as support

_OTHER_ROUND = 2


class LegacyCompatibilityTest(unittest.TestCase):
    """An issue that predates these records owes nothing and loses nothing."""

    def test_no_report_keys_owes_nothing(self) -> None:
        state = PinnedState()

        self.assertFalse(_record_state.carries_pending_report(state))
        self.assertIsNone(support.reads_back(state))
        self.assertIsNone(_settlement.read_current_report(state))
        self.assertIsNone(_settlement.read_handoff(state))

    def test_a_cleared_record_reads_as_absent(self) -> None:
        state = PinnedState()
        _record_state.record_pending_report(state, support.PUBLISHED)
        _record_state.clear_pending_report(state)

        self.assertIsNone(support.reads_back(state))

    def test_other_keys_are_untouched(self) -> None:
        state = PinnedState(state_data={
            "pr_number": support.PR_NUMBER,
            support.REVIEW_ROUND: _OTHER_ROUND,
        })

        _record_state.record_pending_report(state, support.PUBLISHED)

        self.assertEqual(state.get("pr_number"), support.PR_NUMBER)
        self.assertEqual(state.get(support.REVIEW_ROUND), _OTHER_ROUND)


class RoundTripTest(unittest.TestCase):
    """Each record reads back exactly what was written."""

    def test_a_publication_round_trips(self) -> None:
        state = PinnedState()
        _record_state.record_pending_report(state, support.PUBLISHED)

        self.assertTrue(_record_state.carries_pending_report(state))
        self.assertEqual(support.reads_back(state), support.PUBLISHED)

    def test_a_verification_round_trips(self) -> None:
        state = PinnedState()
        _record_state.record_pending_report(state, support.VERIFIED)

        self.assertEqual(support.reads_back(state), support.VERIFIED)

    def test_a_described_verification_round_trips(self) -> None:
        described = _records.PendingReport(
            receipt=support.RECEIPT,
            subject=support.SUBJECT,
            report_revision=1,
            mode=_records.ReportMode.VERIFY,
            route=WorkflowLabel.IN_REVIEW,
            location=ReportLocation(pr_number=support.PR_NUMBER),
            content_revision=support.CONTENT_DIGEST,
        )
        state = PinnedState()
        _record_state.record_pending_report(state, described)

        self.assertEqual(support.reads_back(state), described)

    def test_a_settlement_round_trips(self) -> None:
        state = PinnedState()
        current = _records.CurrentReport(
            subject=support.SUBJECT,
            report_revision=2,
            content_revision=support.CONTENT_DIGEST,
            location=ReportLocation(
                pr_number=support.PR_NUMBER, comment_id=support.COMMENT_ID,
            ),
        )
        handoff = _records.ReportHandoff(
            receipt=support.RECEIPT,
            pr_number=support.PR_NUMBER,
            report_revision=2,
            source_sha=support.SOURCE_SHA,
        )

        _settlement.record_current_report(state, current)
        _settlement.record_handoff(state, handoff)

        self.assertEqual(_settlement.read_current_report(state), current)
        self.assertEqual(_settlement.read_handoff(state), handoff)


class BoundedRecordTest(unittest.TestCase):
    """A record describing a publication this build could not make is refused."""

    def test_a_report_past_the_ceiling_refuses(self) -> None:
        state = support.damaged(
            support.PUBLISHED,
            report="x" * (_record_values.MAX_REPORT_TEXT + 1),
        )

        self.assertIsNone(support.reads_back(state))

    def test_a_report_quoting_a_marker_refuses(self) -> None:
        # A thread is searched for receipts by substring, so a report carrying
        # one would read to that search as the step it names.
        state = support.damaged(
            support.PUBLISHED,
            report="I added <!--orchestrator-developer-report: too",
        )

        self.assertIsNone(support.reads_back(state))

    def test_an_unsettleable_record_is_refused(self) -> None:
        # The settling write happens AFTER the report is posted, so a record
        # accepted at the ceiling and settled past it would leave a published
        # comment, a record still claiming it is owed, and a retry that fails
        # identically for the rest of the issue's life.
        measured = PinnedState()
        _record_state.record_pending_report(measured, support.PUBLISHED)
        recorded = measured.get(_records.PENDING_REPORT)
        room = (
            MAX_PINNED_BODY
            - len(pinned_state_body(measured.data))
            - _record_state._SETTLEMENT_RESERVE // 2
        )
        crowded = PinnedState(state_data={"filler": "y" * room})

        self.assertFalse(
            _record_state.record_pending_report(crowded, support.PUBLISHED),
        )
        # The record itself would have fitted: it is the room settlement needs
        # that this refusal is about.
        self.assertLessEqual(
            len(pinned_state_body({
                **crowded.data, _records.PENDING_REPORT: recorded,
            })),
            MAX_PINNED_BODY,
        )

    def test_an_unfittable_record_is_not_written(self) -> None:
        half = MAX_PINNED_BODY // 2
        state = PinnedState(state_data={"filler": "y" * half})
        oversized = _records.PendingReport(
            receipt=support.RECEIPT,
            subject=support.SUBJECT,
            report_revision=1,
            mode=_records.ReportMode.PUBLISH,
            route=WorkflowLabel.VALIDATING,
            report="z" * half,
        )

        self.assertFalse(
            _record_state.record_pending_report(state, oversized),
        )
        self.assertFalse(_record_state.carries_pending_report(state))


if __name__ == "__main__":
    unittest.main()
