# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a report reads as AFTER it was posted or settled, posting nothing.

A settled record says what the pull request carried once; only a fresh reading
of the exact location says it still does -- the text, the whole header, and an
author this deployment trusts. The same reading taken of an OWED transaction is
what tells a debt a retry can pay from one no retry ever will.
"""

from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import developer_reports as _reports
from orchestrator.github.developer_reports import content_digest
from orchestrator.github.pull_request_reports import ReportLocation, ReportPresence
from orchestrator.workflow.engine import (
    report_evidence as _evidence,
    report_records as _records,
    report_settled_reading as _settled_reading,
    report_settlement_state as _settlement,
)
from tests.support.fakes import FakeUser, UnreadableUser
from tests.workflow.engine import report_transaction_test_support as support

_HUMAN_REPORT = "A report a maintainer wrote as the description."

_AUTHOR = "alice"

_ALLOWLIST = "ALLOWED_ISSUE_AUTHORS"

_STRANGER = "mallory"

# The member of the settled record saying which road settled the report.
_MODE = "mode"

_GITHUB_LOG = "orchestrator.github"

_WARNING = "WARNING"

# The two counts a published report's header carries, and one of more digits
# than Python converts.
_COUNT_RE = re.compile(":pr=[0-9]+:")

_REVISION_RE = re.compile(":revision=[0-9]+:")

_DIGITS = 5000

_UNCONVERTIBLE = "1" * _DIGITS


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
        return _settled_reading.still_carries(
            self.gh, self.state, _settlement.read_current_report(self.state),
        )

    def published(self):
        """Settle a publication, and hand back the comment it landed as."""
        self.record()
        self.reconcile()
        return self.pull_request.issue_comments[-1]

    def forgets_the_road(self) -> None:
        """Leave the settled record as one written before it named its road."""
        settled = dict(self.state.get(_records.CURRENT_REPORT))
        settled.pop(_MODE, None)
        self.state.set(_records.CURRENT_REPORT, settled)

    def rendered_as_settled(self, text: str) -> str:
        """`text` under the very header the settled report went out with."""
        current = _settlement.read_current_report(self.state)
        return _reports.render_developer_report(_reports.DeveloperReport(
            pr_number=current.subject.pr_number,
            source_sha=current.subject.source_sha,
            requirements_revision=current.subject.requirements_revision,
            report_revision=current.report_revision,
            receipt=support.RECEIPT,
            text=text,
        ))


class SettledReadingTest(unittest.TestCase, _Readings):
    """A settled report is trusted only as far as its location still reads."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_published_report_is_held_to_its_header(self) -> None:
        # Recognized at the recorded comment by re-rendering it. An edit to the
        # words, a consistent rewrite keeping the words while claiming another
        # commit, and the header taken off altogether -- which leaves the bare
        # text, hashing to the digest still -- each read as CHANGED.
        landed = self.published()
        settled = landed.body
        self.assertIs(self.still_carries(), ReportPresence.PRESENT)

        for rewritten in (
            f"{settled}\n\nEdited once it settled.",
            settled.replace(support.SOURCE_SHA, support.MOVED_SHA),
            support.REPORT_TEXT,
            # A header claiming a count of more digits than Python converts,
            # in a comment GitHub still holds: no report, and nothing raised.
            _COUNT_RE.sub(f":pr={_UNCONVERTIBLE}:", settled, count=1),
            _REVISION_RE.sub(f":revision={_UNCONVERTIBLE}:", settled, count=1),
        ):
            with self.subTest(rewritten=rewritten):
                self.assertNotEqual(rewritten, settled)
                landed.body = rewritten
                self.assertIs(self.still_carries(), ReportPresence.CHANGED)

        self.pull_request.issue_comments.remove(landed)
        self.assertIs(self.still_carries(), ReportPresence.ABSENT)
        self.gh.report_failures.unreadable.add(support.PR_NUMBER)
        self.assertIs(self.still_carries(), ReportPresence.UNCONFIRMED)

    def test_a_published_report_is_held_to_its_author(self) -> None:
        # A comment rendering exactly as the report is ours only while we wrote
        # it: a stranger's copy is CHANGED, an author nobody could read decides
        # nothing, and the allowlist is not what our own login is held to.
        landed = self.published()
        with patch.object(config, _ALLOWLIST, (_AUTHOR,)):
            self.assertIs(self.still_carries(), ReportPresence.PRESENT)

        landed.user = FakeUser(_STRANGER)
        self.assertIs(self.still_carries(), ReportPresence.CHANGED)
        landed.user = UnreadableUser()
        self.assertIs(self.still_carries(), ReportPresence.UNCONFIRMED)

    def test_an_unrecorded_road_reads_its_location(self) -> None:
        # A settlement written before it named its road: a comment is held to
        # the rendering, so the bare text does not pass as a verification.
        landed = self.published()
        self.forgets_the_road()
        self.assertIs(self.still_carries(), ReportPresence.PRESENT)

        landed.body = support.REPORT_TEXT
        self.assertIs(self.still_carries(), ReportPresence.CHANGED)

    def test_a_verified_report_needs_its_author(self) -> None:
        # Content still hashing to the digest is a report only while its author
        # is one this deployment trusts, as the verification itself required --
        # recorded road or not, since a description can only have been verified.
        self.verification()
        self.reconcile()
        for recorded in (True, False):
            with self.subTest(recorded=recorded):
                self.assertIs(self.still_carries(), ReportPresence.PRESENT)
                with patch.object(config, _ALLOWLIST, (_STRANGER,)):
                    self.assertIs(self.still_carries(), ReportPresence.CHANGED)
                self.forgets_the_road()

    def test_a_description_is_never_a_publication(self) -> None:
        # A publication only ever lands as a comment. A description rewritten
        # into a report under the settled header is a change to what was
        # verified there, whoever wrote it -- and a record claiming a
        # publication settled ON a description is one nothing here wrote.
        self.verification()
        self.reconcile()
        self.pull_request.body = self.rendered_as_settled(_HUMAN_REPORT)
        self.assertIs(self.still_carries(), ReportPresence.CHANGED)

        settled = dict(self.state.get(_records.CURRENT_REPORT))
        settled[_MODE] = str(_records.ReportMode.PUBLISH)
        self.state.set(_records.CURRENT_REPORT, settled)
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

    def test_an_unread_publication_author_holds(self) -> None:
        # Who wrote the comment under the receipt is a request of its own, and
        # one GitHub would not answer is a reading nobody took: the debt stays
        # one a retry can pay, and nothing is raised out of the tick.
        pending = self.posted_and_unsettled()
        self.pull_request.issue_comments[-1].user = UnreadableUser()

        with self.assertLogs(_GITHUB_LOG, _WARNING):
            refused = self.refuses_for_good(pending)

        self.assertFalse(refused)

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
