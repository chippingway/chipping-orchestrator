# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a completed run leaves behind, and the transaction it becomes.

Two halves, in the order they happen. A run's outcome is recorded before its
code is published, holding everything the session settled and nothing a pull
request decides -- and a record this build could not publish from is refused
where the run that wrote it is still there to be told. Then the publication
arrives and the record is bound to it: one write that drops the delivery and
records the transaction, or no write at all.
"""

from __future__ import annotations

import unittest

from orchestrator.github import comments as _trust
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine import report_record_test_support as support
from tests.workflow.fixtures import LABEL_IMPLEMENTING, _agent

ISSUE_NUMBER = 7

RECEIPT = "issue-7-report-1"

BASELINE = "user_content_hash"

# What a delivered report reads back as when the run wrote one for publication,
# and when it says a report is already on the thread.
DELIVERED = _records.DeliveredReport(
    receipt=RECEIPT,
    report_revision=1,
    mode=_records.ReportMode.PUBLISH,
    route=WorkflowLabel.IMPLEMENTING,
    requirements_revision=support.REQUIREMENTS,
    report="The branch adds the gate.\n\nVerified with the suite.",
)

ASSERTED = _records.DeliveredReport(
    receipt=RECEIPT,
    report_revision=1,
    mode=_records.ReportMode.VERIFY,
    route=WorkflowLabel.IMPLEMENTING,
    requirements_revision=support.REQUIREMENTS,
    location=ReportLocation(
        pr_number=support.PR_NUMBER, comment_id=support.COMMENT_ID,
    ),
    content_revision=support.CONTENT_DIGEST,
)


class DeliveredReportRecordTest(unittest.TestCase):
    def test_both_modes_round_trip(self) -> None:
        for delivered_report in (DELIVERED, ASSERTED):
            with self.subTest(mode=delivered_report.mode):
                state = PinnedState()

                self.assertTrue(_delivery_state.record_delivered_report(
                    state, delivered_report,
                ))

                self.assertTrue(
                    _delivery_state.carries_delivered_report(state),
                )
                self.assertEqual(
                    _delivery_state.read_delivered_report(state),
                    delivered_report,
                )

    def test_a_claim_is_not_an_absence(self) -> None:
        # A record cleared holds `null` and owes nothing; one a hand edit left
        # as something else owes a report nobody can describe, and the two may
        # never read the same.
        cleared = PinnedState()
        _delivery_state.clear_delivered_report(cleared)
        claimed = PinnedState(state_data={_records.DELIVERED_REPORT: []})

        self.assertFalse(_delivery_state.carries_delivered_report(cleared))
        self.assertTrue(_delivery_state.carries_delivered_report(claimed))
        for state in (cleared, claimed):
            with self.subTest(recorded=state.get(_records.DELIVERED_REPORT)):
                self.assertIsNone(
                    _delivery_state.read_delivered_report(state),
                )

    def test_an_unpublishable_report_is_refused(self) -> None:
        # Every refusal is the same answer -- a record describing a
        # publication this build could never make -- and none of them writes
        # anything, so the caller hears it while the run is still there.
        refused = (
            ("oversized", "x" * (_record_values.MAX_REPORT_TEXT + 1)),
            (
                "a quoted receipt marker",
                f"quoting {_trust.RECEIPT_MARKER_PREFIX}developer-report",
            ),
            ("text UTF-8 cannot carry", support.LONE_SURROGATE),
            ("nothing at all", "   "),
        )
        for described, text in refused:
            with self.subTest(report=described):
                state = PinnedState()

                self.assertFalse(_delivery_state.record_delivered_report(
                    state, _records.DeliveredReport(
                        receipt=RECEIPT,
                        report_revision=1,
                        mode=_records.ReportMode.PUBLISH,
                        route=WorkflowLabel.IMPLEMENTING,
                        requirements_revision=support.REQUIREMENTS,
                        report=text,
                    ),
                ))

                self.assertEqual(state.data, {})

    def test_a_locationless_verify_is_refused(self) -> None:
        # A location is what a verification is: with none there is nothing to
        # re-read, so the record is refused rather than written as a
        # publication with no text.
        state = PinnedState()

        self.assertFalse(_delivery_state.record_delivered_report(
            state, _records.DeliveredReport(
                receipt=RECEIPT,
                report_revision=1,
                mode=_records.ReportMode.VERIFY,
                route=WorkflowLabel.IMPLEMENTING,
                requirements_revision=support.REQUIREMENTS,
                content_revision=support.CONTENT_DIGEST,
            ),
        ))

        self.assertEqual(state.data, {})

    def test_a_record_past_the_comment_is_refused(self) -> None:
        # The record shares the comment with everything else this issue has
        # recorded, so what is measured is the write it would make.
        crowded = PinnedState(state_data={
            "crowded": "x" * (MAX_PINNED_BODY - len(DELIVERED.report)),
        })

        self.assertFalse(
            _delivery_state.record_delivered_report(crowded, DELIVERED),
        )

        self.assertFalse(
            _delivery_state.carries_delivered_report(crowded),
        )


class DeliveredReportBindingTest(unittest.TestCase):
    def test_binding_exchanges_the_records(self) -> None:
        state = PinnedState()
        _delivery_state.record_delivered_report(state, DELIVERED)

        self.assertTrue(_delivery_state.binds_delivered_report(
            state, DELIVERED, support.SUBJECT,
        ))

        self.assertFalse(_delivery_state.carries_delivered_report(state))
        self.assertEqual(
            _record_state.read_pending_report(state),
            _records.PendingReport(
                receipt=DELIVERED.receipt,
                subject=support.SUBJECT,
                report_revision=DELIVERED.report_revision,
                mode=DELIVERED.mode,
                route=DELIVERED.route,
                report=DELIVERED.report,
            ),
        )

    def test_a_refused_binding_writes_nothing(self) -> None:
        # A subject the transaction's own writer will not store, and a
        # verification asserting a report on another pull request. Neither may
        # half-apply: a delivery dropped with no transaction beside it is a
        # finished run's report lost.
        refused = (
            (
                "a subject naming no pull request",
                DELIVERED,
                _records.ReportSubject(
                    repo_slug=support.SLUG,
                    pr_number=0,
                    branch=support.BRANCH,
                    source_sha=support.SOURCE_SHA,
                    requirements_revision=support.REQUIREMENTS,
                ),
            ),
            ("a location on another pull request", ASSERTED, _records.ReportSubject(
                repo_slug=support.SLUG,
                pr_number=support.PR_NUMBER + 1,
                branch=support.BRANCH,
                source_sha=support.SOURCE_SHA,
                requirements_revision=support.REQUIREMENTS,
            )),
        )
        for described, delivered_report, subject in refused:
            with self.subTest(binding=described):
                state = PinnedState()
                _delivery_state.record_delivered_report(state, delivered_report)

                self.assertFalse(_delivery_state.binds_delivered_report(
                    state, delivered_report, subject,
                ))

                self.assertEqual(
                    _delivery_state.read_delivered_report(state),
                    delivered_report,
                )
                self.assertFalse(_record_state.carries_pending_report(state))

    def test_the_revision_moves_forward(self) -> None:
        # A settled report and an outstanding transaction each pin a revision
        # this issue has used: one because a settlement replaces the current
        # report, the other because a transaction's receipt is spelled from
        # its revision and may not be minted twice.
        state = PinnedState(state_data={BASELINE: support.REQUIREMENTS})
        _settlement.record_current_report(state, support.CURRENT)
        _record_state.record_pending_report(state, support.PUBLISHED)
        github, issue = _seeded_issue()

        _delivery.records_delivered_report(
            github, issue, state, _agent(last_message=_ready(DELIVERED.report)),
            WorkflowLabel.IMPLEMENTING,
        )

        recorded = _delivery_state.read_delivered_report(state)
        self.assertEqual(recorded.report_revision, support.REVISION + 1)
        self.assertEqual(recorded.receipt, f"issue-{ISSUE_NUMBER}-report-3")

    def test_the_delivery_is_durable(self) -> None:
        # The write is the owner's own, because what makes the report
        # recoverable is that it is on GitHub before the size gate reads the
        # candidate and before the push sends it.
        github, issue = _seeded_issue()
        state = github.read_pinned_state(issue)
        state.set(BASELINE, support.REQUIREMENTS)

        _delivery.records_delivered_report(
            github, issue, state, _agent(last_message=_ready(DELIVERED.report)),
            WorkflowLabel.IMPLEMENTING,
        )

        self.assertEqual(
            github.pinned_data(ISSUE_NUMBER)[_records.DELIVERED_REPORT],
            state.get(_records.DELIVERED_REPORT),
        )
        self.assertTrue(_delivery.owes_a_report(state))

    def test_no_outcome_records_nothing(self) -> None:
        # Every run that did not finish on a report outcome, and the
        # verification that names another repository -- which is a location
        # this workflow would re-read on somebody else's thread.
        seeded = _seeded_issue()
        messages = (
            ("no marker at all", "implemented"),
            ("a question", "which database should this use?"),
            ("a report block nothing closed", "REPORT: READY\nthe report"),
            ("another repository", (
                "REPORT: VERIFIED https://github.com/someone/else/pull/3"
                f" sha256:{support.CONTENT_DIGEST}"
            )),
        )
        for described, message in messages:
            with self.subTest(message=described):
                state = PinnedState(state_data={BASELINE: support.REQUIREMENTS})

                _delivery.records_delivered_report(
                    *seeded, state, _agent(last_message=message),
                    WorkflowLabel.IMPLEMENTING,
                )

                self.assertFalse(
                    _delivery_state.carries_delivered_report(state),
                )
                self.assertFalse(_delivery.owes_a_report(state))

    def test_no_baseline_records_nothing(self) -> None:
        # The requirements revision is the one member of a subject the run
        # settles, and a record without it is a transaction nothing could
        # prove again.
        github, issue = _seeded_issue()
        state = PinnedState()

        _delivery.records_delivered_report(
            github, issue, state, _agent(last_message=_ready(DELIVERED.report)),
            WorkflowLabel.IMPLEMENTING,
        )

        self.assertFalse(_delivery_state.carries_delivered_report(state))


def _ready(report: str) -> str:
    """A finished run's message, ending on a report ready for publication."""
    return f"done\n\nREPORT: READY\n{report}\nREPORT: END"


def _seeded_issue():
    """One open issue this delivery is recorded against."""
    github = FakeGitHubClient()
    issue = make_issue(ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
    github.add_issue(issue)
    return github, issue


if __name__ == "__main__":
    unittest.main()
