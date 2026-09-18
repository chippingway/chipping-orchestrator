# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a report reads as AFTER it was posted or settled, posting nothing.

A settled record says what the pull request carried once; only a fresh reading
of the exact location says it still does -- the text, the whole header, and an
author this deployment trusts. The same reading taken of an OWED transaction is
what tells a debt a retry can pay from one no retry ever will.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.developer_reports import content_digest
from orchestrator.github.pull_request_reports import ReportLocation, ReportPresence
from orchestrator.workflow.engine import (
    report_evidence as _evidence,
    report_publishing as _publishing,
    report_records as _records,
    report_settlement_state as _settlement,
)
from tests.support.fakes import FakeUser
from tests.workflow.engine import report_transaction_test_support as support

_HUMAN_REPORT = "A report a maintainer wrote as the description."

_AUTHOR = "alice"

_ALLOWLIST = "ALLOWED_ISSUE_AUTHORS"


class _Readings(support.ReportTransactionCase):
    """One transaction, settled or left owed, and the fresh reading of it."""

    def verification(self) -> _records.PendingReport:
        """Owe a verification of this pull request's own description."""
        self.pull_request.body = _HUMAN_REPORT
        self.pull_request.user = FakeUser(_AUTHOR)
        return self.record(
            mode=_records.ReportMode.VERIFY,
            report="",
            location=ReportLocation(pr_number=support.PR_NUMBER),
            content_revision=content_digest(_HUMAN_REPORT),
        )

    def posted_and_unsettled(self) -> _records.PendingReport:
        """The crash window: the report on the thread, the record still owed."""
        pending = self.record()
        interrupted = self.state.data.copy()
        self.reconcile()
        self.state.data = interrupted
        return pending

    def still_carries(self) -> ReportPresence:
        """Read the settled report again where the settlement recorded it."""
        return _publishing.still_carries(
            self.gh, self.state, _settlement.read_current_report(self.state),
        )


class SettledReadingTest(unittest.TestCase, _Readings):
    """A settled report is trusted only as far as its location still reads."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_published_report_is_held_to_its_header(self) -> None:
        # Recognized at the recorded comment by re-rendering it. An edit to the
        # words, and a consistent rewrite keeping the words while claiming
        # another commit, both read as CHANGED; an unanswered read as nothing.
        self.record()
        self.reconcile()
        landed = self.pull_request.issue_comments[-1]
        settled = landed.body
        self.assertIs(self.still_carries(), ReportPresence.PRESENT)

        for rewritten in (
            f"{settled}\n\nEdited once it settled.",
            settled.replace(support.SOURCE_SHA, support.MOVED_SHA),
        ):
            with self.subTest(rewritten=rewritten != settled):
                self.assertNotEqual(rewritten, settled)
                landed.body = rewritten
                self.assertIs(self.still_carries(), ReportPresence.CHANGED)

        self.pull_request.issue_comments.remove(landed)
        self.assertIs(self.still_carries(), ReportPresence.ABSENT)
        self.gh.report_failures.unreadable.add(support.PR_NUMBER)
        self.assertIs(self.still_carries(), ReportPresence.UNCONFIRMED)

    def test_a_verified_report_needs_its_author(self) -> None:
        # Content still hashing to the digest is a report only while its author
        # is one this deployment trusts, as the verification itself required.
        self.verification()
        self.reconcile()
        self.assertIs(self.still_carries(), ReportPresence.PRESENT)

        self.pull_request.user = FakeUser("mallory")
        with patch.object(config, _ALLOWLIST, (_AUTHOR,)):
            self.assertIs(self.still_carries(), ReportPresence.CHANGED)


class UnpayableDebtTest(unittest.TestCase, _Readings):
    """Which owed transactions no retry settles, as the thread stands."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def refuses_for_good(self, pending: _records.PendingReport) -> bool:
        """Ask of this case's pull request, which must see nothing posted."""
        posted = support.reports_posted(self)
        refused = _evidence.refuses_for_good(self.gh, pending, self.pull_request)
        self.assertEqual(support.reports_posted(self), posted)
        return refused

    def test_an_edited_publication_is_unpayable(self) -> None:
        # Unposted, or posted and intact, a retry still settles it. Our comment
        # under the receipt no longer rendering as the report is content a
        # human owns; a thread nobody could read decides nothing.
        self.assertFalse(self.refuses_for_good(self.pending()))
        pending = self.posted_and_unsettled()
        self.assertFalse(self.refuses_for_good(pending))

        landed = self.pull_request.issue_comments[-1]
        landed.body = f"{landed.body}\n\nedited by a human"
        self.assertTrue(self.refuses_for_good(pending))

        self.gh.report_failures.unreadable.add(support.PR_NUMBER)
        self.assertFalse(self.refuses_for_good(pending))

    def test_a_moved_verification_is_unpayable(self) -> None:
        # Changed, gone, or written by somebody untrusted: each a definite
        # answer about a place a human owns. An unanswered read is not one.
        pending = self.verification()
        self.assertFalse(self.refuses_for_good(pending))

        with patch.object(config, _ALLOWLIST, ("somebody-else",)):
            self.assertTrue(self.refuses_for_good(pending))
        self.pull_request.body = f"{_HUMAN_REPORT} And a sentence more."
        self.assertTrue(self.refuses_for_good(pending))

        self.gh.report_failures.unreadable.add(support.PR_NUMBER)
        self.assertFalse(self.refuses_for_good(pending))


if __name__ == "__main__":
    unittest.main()
