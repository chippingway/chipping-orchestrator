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
    report_commit_test_support as commit_support,
    report_delivery_test_support as delivery_support,
    report_settled_fixture as settled_fixture,
    report_transaction_test_support as support,
)
from tests.workflow.fixtures import _agent

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

# Fields other roads write that a binding never decides on: another domain's
# evidence and verdict, a usage total, and a feedback watermark.
_ANOTHER_ROAD = MappingProxyType({
    "verification_evidence_current": {"revision": 3},
    "review_returned_verdict": {"round": 2},
    "issue_total_tokens": 150,
    support.PR_WATERMARK: 60,
})

_AWAITING = support.AWAITING_HUMAN

# The pinned fields a publication is resolved from, and a usage total the tick
# folds a run into while another road leaves it as no total at all.
_PR_NUMBER = "pr_number"

_BRANCH = "branch"

_TOKENS = "issue_total_tokens"

_TICK_TOKENS = 130

# Evidence another road settles while the tick holds its reading.
_EVIDENCE_FIELD = "verification_evidence_current"

_EVIDENCE_SINCE = MappingProxyType({_EVIDENCE_FIELD: {"revision": 3}})

# The comment a verification names on the pull request it targets.
_COMMENT_ID = 8800

# How another road repoints the publication a refusal's park was prepared
# against while its notice is out: the pull request, the branch, or the
# code-publication receipt.
_REPOINTED = (
    {_PR_NUMBER: support.OTHER_PR_NUMBER},
    {_BRANCH: "another-branch"},
    {support.PUBLISHED_PR: support.OTHER_PR_NUMBER, support.PUBLISHED_SHA: support.MOVED_SHA},
)

# How the comment moves under a tick about to bind its delivery, each of which
# the binding may not land on: a report record moved, a field the tick staged
# moved another way, and a comment no longer the one the tick read.
_MOVES_UNDER_IT = (
    ("a newer delivery", lambda case: commit_support.another_road(
        case.gh, case.issue, **{_records.DELIVERED_REPORT: delivery_support.delivered_object(
            replace(delivery_support.REDELIVERED, requirements_revision=case.requirements()),
        )},
    )),
    ("an outstanding transaction", lambda case: commit_support.another_road(
        case.gh, case.issue, **{
            _records.PENDING_REPORT: delivery_support.outstanding_comment()[_records.PENDING_REPORT],
        },
    )),
    ("a settled report", lambda case: commit_support.another_road(
        case.gh, case.issue, **{_records.CURRENT_REPORT: "settled since"},
    )),
    ("a park the tick took down", lambda case: commit_support.another_road(
        case.gh, case.issue, **{_AWAITING: "parked again"},
    )),
    ("a repointed pull request", lambda case: commit_support.another_road(
        case.gh, case.issue, **{_PR_NUMBER: support.OTHER_PR_NUMBER, _BRANCH: "another-branch"},
    )),
    ("a moved code-publication receipt", lambda case: commit_support.another_road(
        case.gh, case.issue, **{support.PUBLISHED_PR: support.OTHER_PR_NUMBER},
    )),
    ("a usage total another road made a flag", lambda case: (
        case.state.set(_TOKENS, _TICK_TOKENS),
        commit_support.another_road(case.gh, case.issue, **{_TOKENS: True}),
    )),
    ("a replaced comment", lambda case: case.gh.seed_state(
        case.issue, **case.gh.pinned_data(case.issue.number),
    )),
    ("an unreadable comment", lambda case: case.gh.pinned_failures.unreadable.add(
        case.issue.number,
    )),
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

    def pins(self) -> None:
        """Pin what the case recorded on the issue, as the tick that read it holds it."""
        commit_support.pinned((self.gh, self.issue), self.state)

    def publishes(self, **moved) -> None:
        """Bind and publish onto the publication in hand, with any term moved.

        The first publication pins whatever the case recorded on the issue, as
        the tick that read it holds it: the binding lands over that comment.
        """
        if self.state.synced is None:
            self.pins()
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
        # still owed lets run give back, so nothing parks and nothing is lost --
        # and since it is the very comment the tick read, the tick's own
        # writes behind the refusal are not withheld from it.
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
                self.state.withheld,
            ),
            (recorded, None, [], False),
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


class GuardedBindingTest(unittest.TestCase, _Publication):
    """The exchange lands over the comment as it stands, decided on what the tick read.

    Another road may write the comment between the tick's reading and the
    binding. What it wrote beside the two records the binding swaps survives;
    a report record moving under it, or a field the tick staged moving another
    way, binds nothing, posts nothing, and parks nothing; and a binding GitHub
    took and never confirmed is published by the next entry, bound once.
    """

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_another_road_s_fields_survive(self) -> None:
        # GitHub refuses the post, so what the comment shows is the binding
        # alone: the transaction in, the delivery out, and every field the
        # other road wrote meanwhile as it wrote it.
        delivered = self.delivers()
        self.pins()
        commit_support.another_road(self.gh, self.issue, **_ANOTHER_ROAD)
        self.gh.report_failures.refused.add(support.PR_NUMBER)

        self.publishes()

        pinned = self.gh.pinned_data(support.ISSUE_NUMBER)
        self.assertEqual(
            (
                {field: pinned[field] for field in _ANOTHER_ROAD},
                pinned[_records.DELIVERED_REPORT],
                _record_state.read_pending_report(self.state).receipt,
            ),
            (dict(_ANOTHER_ROAD), None, delivered.receipt),
        )
        self.assertEqual(self.state.data, pinned)

    def test_a_comment_moved_under_it_binds_nothing(self) -> None:
        # The delivery stays where the tick holds it, and the comment as the
        # other road left it, for the next tick to bind afresh.
        for described, moves in _MOVES_UNDER_IT:
            with self.subTest(moved=described):
                self.setUp()
                self.delivers()
                self.state.set(_AWAITING, True)
                self.pins()
                self.state.set(_AWAITING, False)
                moves(self)
                found = self.gh.pinned_data(support.ISSUE_NUMBER)
                held = dict(self.state.data)

                self.publishes()

                self.assertEqual(
                    (self.gh.pinned_data(support.ISSUE_NUMBER), self.state.data, self.gh.posted_comments),
                    (found, held, []),
                )
                self.assertEqual(support.report_comments(self), [])

    def test_the_fresh_comment_s_room_leaves_it_owed(self) -> None:
        # The tick's reading has room for the transaction; the comment another
        # road has since filled does not. Nothing is written or parked: room is
        # what the routes behind a report still owed give back.
        self.state = delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_REDELIVERY * 4,
            {_records.DELIVERED_REPORT: delivery_support.delivered_object()},
        )
        self.pins()
        crowding = delivery_support.crowded_comment(delivery_support.CROWDED_FOR_BINDING).get(
            delivery_support.CROWDING,
        )
        found = commit_support.another_road(self.gh, self.issue, **{delivery_support.CROWDING: crowding})

        self.publishes()

        self.assertEqual(
            (self.gh.pinned_data(support.ISSUE_NUMBER), self.gh.posted_comments, self.state.withheld),
            (found, [], True),
        )
        self.assertTrue(_delivery_state.carries_delivered_report(self.state))

    def test_a_lost_binding_is_not_bound_again(self) -> None:
        # GitHub took the exchange and its answer never came back: nothing is
        # posted on it. The next entry reads the transaction rather than the
        # delivery, and publishes that one report at the run's own revision.
        delivered = self.delivers()
        self.pins()
        self.gh.pinned_failures.lost.add(support.ISSUE_NUMBER)

        self.publishes()

        self.assertEqual(support.report_comments(self), [])
        self.gh.pinned_failures.lost.discard(support.ISSUE_NUMBER)
        self.state = self.gh.read_pinned_state(self.issue)
        self.assertIsNone(self.state.get(_records.DELIVERED_REPORT))
        self.publishes()
        self._assert_published_once(delivered)

    def test_a_lost_record_is_bound_on_the_next_entry(self) -> None:
        # The run's record landed with its answer lost, so the tick that wrote
        # it ended there. The next entry binds and publishes that record --
        # no second run wrote anything, and no second revision is minted.
        self.state.set(delivery_support.BASELINE, self.requirements())
        self.pins()
        self.gh.pinned_failures.lost.add(support.ISSUE_NUMBER)
        self.assertTrue(_delivery.recording_stops_the_tick(
            self.gh, self.issue, self.state,
            _agent(last_message=delivery_support.ready(delivery_support.DELIVERED.report)),
            WorkflowLabel.IMPLEMENTING,
        ))
        self.gh.pinned_failures.lost.discard(support.ISSUE_NUMBER)

        self.state = self.gh.read_pinned_state(self.issue)
        self.publishes()

        self._assert_published_once(replace(
            delivery_support.DELIVERED, requirements_revision=self.requirements(),
        ))

    def _assert_published_once(self, delivered: _records.DeliveredReport) -> None:
        """One report on the pull request, settled under `delivered`'s own receipt and revision."""
        support.assert_one_report(self)
        handoff = _settlement.read_handoff(self.state)
        self.assertEqual(
            (handoff.receipt, handoff.report_revision),
            (delivered.receipt, delivered.report_revision),
        )


class EditWindowTest(unittest.TestCase, _Publication):
    """A binding whose comment moves after the commit read it, and before its edit."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_a_move_under_the_edit_binds_nothing(self) -> None:
        # The candidate was derived and its room checked over a reading another
        # road has since written past, so the edit is refused as moved: nothing
        # is bound or posted, the delivery stays where the tick holds it, and
        # nothing the tick writes behind the refusal lands either.
        self.delivers()
        self.pins()

        with commit_support.under_the_edit(self.gh, self.issue, **_ANOTHER_ROAD):
            self.publishes()

        pinned = self.gh.pinned_data(support.ISSUE_NUMBER)
        self.assertEqual(
            (
                {field: pinned[field] for field in _ANOTHER_ROAD},
                pinned.get(_records.PENDING_REPORT),
                self.gh.posted_pr_comments,
                _delivery_state.carries_delivered_report(self.state),
                self.state.withheld,
            ),
            (dict(_ANOTHER_ROAD), None, [], True, True),
        )


class FreshReadingTest(unittest.TestCase, _Publication):
    """What the comment as it stands decides for a binding and its park, over what the tick read."""

    def setUp(self) -> None:
        support.ReportTransactionCase.setUp(self)

    def test_room_given_back_binds_and_keeps_it(self) -> None:
        # The tick read a comment with no room for the transaction; another
        # road has since given that room back and settled evidence. The
        # binding is measured on the comment it lands on, so it binds and the
        # report goes out, and the evidence survives the tick's own write
        # behind it.
        self.delivers()
        self.state.set(delivery_support.CROWDING, delivery_support.crowded_comment(
            delivery_support.CROWDED_FOR_BINDING,
        ).get(delivery_support.CROWDING))
        self.pins()
        commit_support.another_road(
            self.gh, self.issue, **{delivery_support.CROWDING: ""}, **_EVIDENCE_SINCE,
        )

        self.publishes()
        self.gh.write_pinned_state(self.issue, self.state)

        pinned = self.gh.read_pinned_state(self.issue)
        support.assert_one_report(self)
        self.assertEqual(
            (pinned.get(_records.DELIVERED_REPORT), pinned.get(_EVIDENCE_FIELD)),
            (None, _EVIDENCE_SINCE[_EVIDENCE_FIELD]),
        )

    def test_a_repointed_publication_parks_nothing(self) -> None:
        # A verification on PR #13 is unbindable to PR #12 -- but the comment
        # has since been pointed at #13, so that refusal was judged against a
        # publication that is no longer the issue's: no notice and no park,
        # and the comment stands as the other road left it for the next tick.
        self.delivers(
            mode=_records.ReportMode.VERIFY, report="",
            location=ReportLocation(pr_number=support.OTHER_PR_NUMBER, comment_id=_COMMENT_ID),
            content_revision=content_digest(_DESCRIPTION_REPORT),
        )
        self.state.set(_PR_NUMBER, support.PR_NUMBER)
        self.pins()
        found = commit_support.another_road(self.gh, self.issue, **{
            _PR_NUMBER: support.OTHER_PR_NUMBER, support.PUBLISHED_PR: support.OTHER_PR_NUMBER,
        })

        self.publishes()

        self.assertEqual(
            (self.gh.pinned_data(support.ISSUE_NUMBER), self.gh.posted_comments, self.state.withheld),
            (found, [], True),
        )

    def test_a_move_under_the_notice_parks_nothing(self) -> None:
        # The same verification, with the comment still naming PR #12 when the
        # park is prepared, so its notice goes out. Another road points the
        # comment at another pull request, branch or receipt before the park
        # lands: the park was decided on a publication that is no longer the
        # issue's, so it is refused, the newer publication stands, and nothing
        # the tick writes behind the refusal puts the old one back.
        for repointed in _REPOINTED:
            with self.subTest(repointed=repointed):
                self.setUp()
                self.delivers(
                    mode=_records.ReportMode.VERIFY, report="",
                    location=ReportLocation(pr_number=support.OTHER_PR_NUMBER, comment_id=_COMMENT_ID),
                    content_revision=content_digest(_DESCRIPTION_REPORT),
                )
                self.state.set(_PR_NUMBER, support.PR_NUMBER)
                self.state.set(_BRANCH, support.BRANCH)
                self.pins()
                found = self.gh.read_pinned_state(self.issue).data

                with commit_support.behind(self.gh, self.issue, commit_support.NOTICE, **repointed):
                    self.publishes()
                self.gh.write_pinned_state(self.issue, self.state)

                self.assertEqual(
                    (
                        len(self.gh.posted_comments),
                        self.gh.read_pinned_state(self.issue).data,
                        self.state.withheld,
                    ),
                    (1, {**found, **repointed}, True),
                )


if __name__ == "__main__":
    unittest.main()
