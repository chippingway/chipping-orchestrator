# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a damaged settled record, or another route's park, does to a transaction.

The current report and the handoff are both things a settlement WRITES OVER, so
reading a damaged one as an absence is worse than reading no record at all: the
next transaction replaces it the moment it settles -- after its report has been
posted, which is when the evidence an operator would have repaired it from is
gone. Both are therefore asked for their presence before anything is proved.

Two READABLE settled records that contradict each other are the same hazard
one step on. They are written in one write off one pending record, so a pair
naming two pull requests, two revisions or two commits is one nothing here
produced -- and under a PREVIOUS transaction's receipt nothing else would ever
ask: that pair is not compared against the record in hand, so a disagreement
left standing is replaced by the very next settlement.

The park is the mirror of the same care. The pinned flags are single, so a park
this owner takes over one another route already holds replaces an obligation a
stage is still waiting on -- and the retirement behind this owner would then
clear `awaiting_human` for a question nobody answered. Standing down costs
nothing: the issue is already held awaiting a human, which is what this park
would have asked for.
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

_AGENT_TIMEOUT = "agent_timeout"

# The receipt a PREVIOUS transaction on this issue settled under, which is what
# makes the pair below one nothing compares against the record in hand.
_EARLIER_RECEIPT = "issue-7-report-0"

_SETTLED_REVISION = 1

_NEXT_REVISION = 2

_COMMENT_ID = 8080


class CompanionDamageTest(unittest.TestCase, support.ReportTransactionCase):
    """A settled record that is claimed and unreadable stops the tick."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)
        self.record()

    def test_a_damaged_current_report_is_preserved(self) -> None:
        # Read as an absence it would be silently replaced by this settlement,
        # after the report had already been posted.
        unreadable = {"revision": 1}
        self.state.set(_records.CURRENT_REPORT, unreadable)

        self.assertTrue(self.reconcile())

        self.assertEqual(self.state.get(_records.CURRENT_REPORT), unreadable)
        self.assertEqual(
            self.state.get(support.PARK_REASON), support.PARK_DAMAGED,
        )
        support.assert_nothing_published(self)

    def test_a_damaged_handoff_is_preserved(self) -> None:
        # Read as an absence it would be a completed transaction nobody can
        # recognize, and its report would be published a second time.
        damaged = {"receipt": support.RECEIPT}
        self.state.set(_records.REPORT_HANDOFF, damaged)

        self.assertTrue(self.reconcile())

        self.assertEqual(self.state.get(_records.REPORT_HANDOFF), damaged)
        support.assert_nothing_published(self)

    def test_a_handoff_with_no_current_report_parks(self) -> None:
        # The two are written in ONE write, so a handoff without a current
        # report is a settlement that never happened. Believed on the receipt
        # alone it would drop this record while the pull request carries
        # nothing -- the outcome the whole transaction exists to prevent.
        _settlement.record_handoff(self.state, _records.ReportHandoff(
            receipt=support.RECEIPT,
            pr_number=support.PR_NUMBER,
            report_revision=1,
            source_sha=support.SOURCE_SHA,
        ))

        self.assertTrue(self.reconcile())

        self.assertEqual(
            self.state.get(support.PARK_REASON), support.PARK_DAMAGED,
        )
        support.assert_nothing_published(self)


class DisagreeingCompanionTest(unittest.TestCase, support.ReportTransactionCase):
    """A settled pair that contradicts itself is a human's to resolve."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_companions_on_different_commits_park(self) -> None:
        # Under an EARLIER receipt, which is where nothing else asks: the pair
        # is not compared against the record in hand, so left alone it would be
        # replaced by this settlement rather than seen.
        self._settled(source_sha=support.MOVED_SHA)
        self.record(report_revision=_NEXT_REVISION)

        self.assertTrue(self.reconcile())

        self.assertEqual(
            self.state.get(support.PARK_REASON), support.PARK_DAMAGED,
        )
        support.assert_nothing_published(self)

    def test_a_handoff_on_another_subject_parks(self) -> None:
        # The handoff carries this transaction's receipt and agrees with the
        # current report on everything it can carry -- the pull request, the
        # revision, the commit. What disagrees is the rest of the SUBJECT, so
        # only holding the current report to the whole of it catches this, and
        # read as a completion it would drop a record never published.
        pending = self.pending()
        elsewhere = _records.ReportSubject(
            repo_slug=pending.subject.repo_slug,
            pr_number=support.PR_NUMBER,
            branch=f"{support.BRANCH}-rewritten",
            source_sha=support.SOURCE_SHA,
            requirements_revision=pending.subject.requirements_revision,
        )
        self._current(elsewhere, pending.report_revision)
        self._handoff(support.RECEIPT, pending.report_revision, support.SOURCE_SHA)
        self.record()

        self.assertTrue(self.reconcile())

        self.assertEqual(
            self.state.get(support.PARK_REASON), support.PARK_DAMAGED,
        )
        support.assert_nothing_published(self)

    def _settled(self, *, source_sha: str) -> None:
        """A finished earlier transaction whose handoff names another commit."""
        self._current(self.pending().subject, _SETTLED_REVISION)
        self._handoff(_EARLIER_RECEIPT, _SETTLED_REVISION, source_sha)

    def _current(self, subject: _records.ReportSubject, revision: int) -> None:
        """Record what the pull request is said to carry now."""
        _settlement.record_current_report(self.state, _records.CurrentReport(
            subject=subject,
            report_revision=revision,
            content_revision=content_digest(support.REPORT_TEXT),
            location=ReportLocation(
                pr_number=subject.pr_number, comment_id=_COMMENT_ID,
            ),
        ))

    def _handoff(self, receipt: str, revision: int, source_sha: str) -> None:
        """Record the receipt one transaction is said to have finished under."""
        _settlement.record_handoff(self.state, _records.ReportHandoff(
            receipt=receipt,
            pr_number=support.PR_NUMBER,
            report_revision=revision,
            source_sha=source_sha,
        ))


class ForeignParkTest(unittest.TestCase, support.ReportTransactionCase):
    """A park another route took is never replaced by this owner's."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_foreign_park_is_not_overwritten(self) -> None:
        # Overwritten, the stage waiting on `agent_timeout` loses its
        # obligation -- and the retirement behind this owner would then clear
        # `awaiting_human` for a question nobody answered.
        self.state.set(support.AWAITING_HUMAN, True)
        self.state.set(support.PARK_REASON, _AGENT_TIMEOUT)
        self.state.set(_records.PENDING_REPORT, {"receipt": support.RECEIPT})
        posted = len(self.gh.posted_comments)

        self.assertTrue(self.reconcile())

        self.assertEqual(self.state.get(support.PARK_REASON), _AGENT_TIMEOUT)
        self.assertTrue(self.state.get(support.AWAITING_HUMAN))
        self.assertEqual(len(self.gh.posted_comments), posted)
        self.assertTrue(_record_state.carries_pending_report(self.state))


if __name__ == "__main__":
    unittest.main()
