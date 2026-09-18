# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a publication does with the report its run delivered.

The delivery is exchanged for the transaction in one write made BEFORE anything
is posted, held to the whole subject -- repository, pull request, branch and
commit -- and what cannot be bound or settled is left on the comment rather
than discarded. Each case moves one term of an otherwise ordinary publication.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.developer_reports import content_digest
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_binding as _binding,
    report_delivery as _delivery,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    report_delivery_test_support as delivery_support,
    report_settled_fixture as settled_fixture,
    report_transaction_test_support as support,
)

# A description that closes nothing and names nobody, which a developer verified
# as the report: the one report this workflow cannot both keep and manage.
_DESCRIPTION_REPORT = "A report a maintainer wrote as the description."

# What a delivery nobody can read is written as.
_DAMAGED_DELIVERY = MappingProxyType({"revision": "damaged"})

_EDITED = "Edited while the report was on its way."

_GET_ISSUE = "get_issue"

_POST_REPORT = "_post_report"

_UNANSWERED = "GitHub did not answer the read"

# Each member of the subject a retry holds an outstanding transaction to.
_OTHER_PUBLICATIONS = (
    {"repo_slug": "someone/else"},
    {"branch": "another-branch"},
    {"commit": support.MOVED_SHA},
)


class _Publication(support.ReportTransactionCase):
    """One publication that has just happened, and the report delivered for it."""

    def delivers(self, **overrides) -> _records.DeliveredReport:
        """Record the report a finished run wrote, ahead of its publication."""
        delivered = replace(
            delivery_support.DELIVERED,
            requirements_revision=self.requirements(),
            **overrides,
        )
        _delivery_state.record_delivered_report(self.state, delivered)
        return delivered

    def verifies_the_description(self) -> None:
        """Record a verification of this pull request's own description."""
        self.pull_request.body = _DESCRIPTION_REPORT
        self.delivers(
            mode=_records.ReportMode.VERIFY,
            report="",
            location=ReportLocation(pr_number=support.PR_NUMBER),
            content_revision=content_digest(_DESCRIPTION_REPORT),
        )

    def edits_the_issue(self) -> None:
        """Move the requirements the way a human editing the body does."""
        body = self.issue.body
        self.issue.body = f"{body}\n\n{_EDITED}"

    def posts_under_an_edit(self, pull_request, body):
        """Post the report, with the issue edited while the request is out."""
        self.edits_the_issue()
        return self.posts(pull_request, body)

    def publishes(self, **moved) -> None:
        """Bind and publish onto the publication in hand, with any term moved."""
        published = {
            "pull_request": self.pull_request,
            "repo_slug": self.gh.repo_slug,
            "branch": support.BRANCH,
            "commit": support.SOURCE_SHA,
        }
        _binding.binds_and_publishes(
            self.gh, self.issue, self.state,
            _binding.ReportPublication(**(published | moved)),
        )

    def assert_parked_intact(self, record) -> None:
        """Parked for a human with the debt kept and the delivery untouched."""
        self.assertEqual(
            (
                self.state.get(support.AWAITING_HUMAN),
                self.state.get(support.PARK_REASON),
                self.state.get(_delivery.OWED_REPORT),
                self.state.get(_records.DELIVERED_REPORT),
                support.report_comments(self),
            ),
            (True, _delivery.UNDELIVERABLE_REPORT, True, record, []),
        )


class BoundPublicationTest(unittest.TestCase, _Publication):
    """The ordinary road, and the two ways a request on it goes unanswered."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_the_subject_is_bound_before_the_post(self) -> None:
        # GitHub refuses the comment, so what the tick leaves is the binding
        # alone: the delivery exchanged for a transaction naming every member
        # of the publication, already written, with nothing posted. The retry
        # binds nothing and settles that same transaction.
        delivered = self.delivers()
        self.gh.report_failures.refused.add(support.PR_NUMBER)

        self.publishes()

        written = self.gh.pinned_data(support.ISSUE_NUMBER)
        self.assertEqual(
            (
                _record_state.read_pending_report(self.state).subject,
                written[_records.DELIVERED_REPORT],
                written[_records.PENDING_REPORT],
                support.report_comments(self),
            ),
            (
                _records.ReportSubject(
                    repo_slug=self.gh.repo_slug,
                    pr_number=support.PR_NUMBER,
                    branch=support.BRANCH,
                    source_sha=support.SOURCE_SHA,
                    requirements_revision=delivered.requirements_revision,
                ),
                None,
                self.state.get(_records.PENDING_REPORT),
                [],
            ),
        )

        self.gh.report_failures.refused.discard(support.PR_NUMBER)
        self.publishes()

        support.assert_one_report(self)
        self.assertEqual(
            _settlement.read_handoff(self.state).receipt, delivered.receipt,
        )

    def test_a_lost_response_settles_once(self) -> None:
        # The comment landed and its response never arrived, so the
        # transaction stays owed over a report already on the thread. The
        # retry is scoped by the receipt and settles on that one comment.
        self.delivers()
        self.gh.report_failures.lost.add(support.PR_NUMBER)

        self.publishes()

        self.assertIsNotNone(_record_state.read_pending_report(self.state))
        self.assertIsNone(_settlement.read_handoff(self.state))

        self.gh.report_failures.lost.discard(support.PR_NUMBER)
        self.publishes()

        support.assert_one_report(self)
        self.assertIsNotNone(_settlement.read_handoff(self.state))

    def test_a_described_verification_settles(self) -> None:
        # The same verification that collides below is kept where the
        # description already closes the issue and names the session: nothing
        # is posted, and the settled location is the description itself.
        self.verifies_the_description()

        self.publishes(describes_the_issue=True)

        self.assertEqual(support.report_comments(self), [])
        self.assertEqual(
            _settlement.read_current_report(self.state).location,
            ReportLocation(pr_number=support.PR_NUMBER),
        )


class WithheldPublicationTest(unittest.TestCase, _Publication):
    """What is left owed, or parked, with nothing of the report discarded."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_moved_requirements_leave_it_owed(self) -> None:
        # The issue in hand was fetched before the developer ran, so the
        # requirements are read again: an edit since leaves the transaction
        # bound, unposted, and owed for the drift resume.
        self.delivers()
        self.edits_the_issue()

        self.publishes()

        support.assert_still_owed(self)

    def test_an_unread_issue_leaves_it_owed(self) -> None:
        # A re-read nobody could take proves nothing about the requirements,
        # so nothing is posted over it and the next call asks again.
        self.delivers()

        with patch.object(
            self.gh, _GET_ISSUE, side_effect=RuntimeError(_UNANSWERED),
        ):
            self.publishes()

        support.assert_still_owed(self)

    def test_an_edit_inside_the_post_stays_owed(self) -> None:
        # The requirements are proved once more after the request, since a post
        # is long enough for a human to edit the issue under it: the comment
        # is there, and the transaction stays owed for the drift resume.
        self.delivers()
        self.posts = self.gh._post_report

        with patch.object(self.gh, _POST_REPORT, self.posts_under_an_edit):
            self.publishes()

        support.assert_one_report(self)
        self.assertIsNotNone(_record_state.read_pending_report(self.state))
        self.assertIsNone(_settlement.read_handoff(self.state))

    def test_permanent_refusals_park_intact(self) -> None:
        # A record nobody can read, a verification on another pull request, and
        # one on the description this publication still needs for its closing
        # reference: each parks once, the delivery exactly as it stood.
        for refusal in ("damaged", "elsewhere", "collision"):
            with self.subTest(refusal=refusal):
                self.setUp()
                if refusal == "damaged":
                    self.state.set(
                        _records.DELIVERED_REPORT, dict(_DAMAGED_DELIVERY),
                    )
                elif refusal == "elsewhere":
                    self.delivers(
                        mode=_records.ReportMode.VERIFY,
                        report="",
                        location=ReportLocation(pr_number=support.OTHER_PR_NUMBER),
                        content_revision=content_digest(_DESCRIPTION_REPORT),
                    )
                else:
                    self.verifies_the_description()
                recorded = self.state.get(_records.DELIVERED_REPORT)

                self.publishes(describes_the_issue=False)

                self.assert_parked_intact(recorded)
                self.assertIsNone(self.state.get(_records.PENDING_REPORT))
                self.assertEqual(len(self.issue.comments), 1)

    def test_a_crowded_comment_takes_no_park(self) -> None:
        # A comment too full for the transaction is room the routes a report
        # still owed lets run give back, so nothing parks and nothing is lost.
        self.state = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_BINDING,
            {_records.DELIVERED_REPORT: delivery_support.delivered_object()},
        )
        recorded = self.state.get(_records.DELIVERED_REPORT)

        self.publishes()

        self.assertEqual(
            (
                self.state.get(_records.DELIVERED_REPORT),
                self.state.get(support.AWAITING_HUMAN),
                support.report_comments(self),
            ),
            (recorded, None, []),
        )


class OtherTransactionTest(unittest.TestCase, _Publication):
    """The transactions this publication is not the one to finish."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_another_publication_is_left_alone(self) -> None:
        # A retry only finishes the transaction about the publication in hand;
        # one naming another repository, pull request, branch or commit is the
        # reconciliation's to prove. An issue that delivered nothing does nothing.
        elsewhere = replace(self.pull_request, number=support.OTHER_PR_NUMBER)
        for moved in ({"pull_request": elsewhere}, *_OTHER_PUBLICATIONS, None):
            with self.subTest(moved=moved):
                self.setUp()
                if moved is not None:
                    self.record()

                self.publishes(**(moved or {}))

                self.assertEqual(support.report_comments(self), [])
                self.assertIsNone(_settlement.read_handoff(self.state))

    def test_a_newer_settlement_leaves_it_owed(self) -> None:
        # A settlement writes over the settled pair, so a pair already naming
        # a newer report is one this transaction may not replace.
        pending = self.record(route=WorkflowLabel.IMPLEMENTING)
        settled_fixture.records_current(
            self.state, pending.subject, settled_fixture.NEXT_REVISION,
        )
        settled_fixture.records_handoff(
            self.state, "issue-7-report-2", settled_fixture.NEXT_REVISION,
            support.SOURCE_SHA,
        )

        self.publishes()

        support.assert_nothing_published(self)


if __name__ == "__main__":
    unittest.main()
