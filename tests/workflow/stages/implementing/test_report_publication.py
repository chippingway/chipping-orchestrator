# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one initial publication does with the report its developer wrote.

The pull request the code reaches is the variable: one this tick opens and one
already open on the branch. On either of them the report has to end up
published, recorded as the one the pull request carries, and the issue reaches
`validating` only once both of those are true. The two ways a run can hand a
report over are the other variable -- one written for publication, and one the
developer says is already on the thread.

The pull request the size gate proved is already STANDING on the commit is the
recovery's world rather than this one's, and it is covered beside the
report-debt cases in `test_report_recovery`.

A reused pull request has one body this stage may not rewrite: the one a
verification names. The rewrite that makes a reused pull request describe this
implementation would replace the report published there, so the description is
preserved and the verification behind it finds what it read.
"""

from __future__ import annotations

import unittest

from orchestrator.github import developer_reports as _reports
from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import _TEST_SPEC, LABEL_VALIDATING, _open_pr_for
from tests.workflow.stages.implementing import report_test_support as support

REUSED_PR = 42

VERIFIED_PR = 55

HUMAN_REPORT_ID = 9100

DESCRIBED_PR = 63

# A description a human wrote and a developer then verified as this issue's
# report. It carries no dev-session attribution, which is exactly what would
# otherwise have the reuse rewrite it.
HUMAN_DESCRIPTION = "### Report\n\nThe branch adds the thing. Verified by hand."

FOREIGN_PR = 3

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"


class ReportPublicationTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_new_pr_carries_the_report(self) -> None:
        github, issue = self.seeded()

        self.deliver(github, issue, support.ready_message())

        opened = github.opened_prs[0]
        posted = support.published_reports(github, opened.number)
        self.assertEqual(len(posted), 1)
        self.assertIn(support.REPORT_TEXT, posted[0].body)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            recorded[support.CURRENT_RECORD],
            {
                "repo": _TEST_SPEC.slug,
                "pr": opened.number,
                "branch": support.BRANCH,
                "sha": support.PUBLISHED_SHA,
                "requirements": recorded["user_content_hash"],
                "revision": 1,
                "content": _reports.content_digest(support.REPORT_TEXT),
                "location_pr": opened.number,
                "location_comment": posted[0].id,
            },
        )
        self.assertEqual(
            recorded[support.HANDOFF_RECORD],
            {
                "receipt": f"issue-{support.REPORT_ISSUE}-report-1",
                "pr": opened.number,
                "revision": 1,
                "sha": support.PUBLISHED_SHA,
            },
        )
        # Both outstanding records are settled, and the issue only moves on
        # because they are.
        self.assertEqual(
            (
                recorded[support.DELIVERY_RECORD],
                recorded[support.PENDING_RECORD],
            ),
            (None, None),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_a_new_pr_body_defers_to_the_report(self) -> None:
        # The report comment is the authority, so the description carries what
        # only it can -- the closing reference and the attribution -- and no
        # unmarked, unversioned copy of the report beside it.
        github, issue = self.seeded()

        self.deliver(github, issue, support.ready_message())

        opened = github.opened_prs[0]
        self.assertIn(f"Resolves #{support.REPORT_ISSUE}", opened.body)
        self.assertIn(support.DEV_SESSION, opened.body)
        self.assertNotIn(support.LAST_MESSAGE_HEADING, opened.body)
        self.assertNotIn(support.REPORT_TEXT, opened.body)

    def test_a_reused_pr_carries_the_report(self) -> None:
        # A pull request already open on the branch -- a tick that died after
        # opening one, or an operator's -- is adopted rather than opened over,
        # and the report goes onto it.
        github, issue = self.seeded()
        reused = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=REUSED_PR,
        )
        github.existing_open_pr[support.BRANCH] = reused

        self.deliver(github, issue, support.ready_message())

        self.assertEqual(github.opened_prs, [])
        self.assertEqual(len(support.published_reports(github, REUSED_PR)), 1)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(recorded[support.CURRENT_RECORD]["pr"], REUSED_PR)
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )
        # The body is rewritten to name this implementation, and the rewrite
        # carries no copy of the report either.
        self.assertIn(f"Resolves #{support.REPORT_ISSUE}", reused.body)
        self.assertNotIn(support.LAST_MESSAGE_HEADING, reused.body)

    def test_a_verified_report_posts_nothing(self) -> None:
        # The developer read a report a human published and asserted it. The
        # location is re-read rather than believed, and nothing is posted.
        github, issue = self.seeded()
        reused = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=VERIFIED_PR,
        )
        github.existing_open_pr[support.BRANCH] = reused
        human = FakeComment(
            id=HUMAN_REPORT_ID,
            body="the human's own report",
            user=FakeUser("alice"),
        )
        reused.issue_comments.append(human)

        self.deliver(
            github,
            issue,
            support.verified_message(
                reused.number, human.body, comment_id=human.id,
            ),
        )

        self.assertEqual(github.posted_pr_comments, [])
        settled = github.pinned_data(support.REPORT_ISSUE)[
            support.CURRENT_RECORD
        ]
        self.assertEqual(
            (settled["content"], settled["location_comment"]),
            (_reports.content_digest(human.body), human.id),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_a_verified_description_survives(self) -> None:
        # The developer verified the report on this pull request's OWN body.
        # Rewriting it to name this implementation would destroy the only copy
        # of that report and leave the verification reading content that had
        # moved, so the description is preserved and the transaction settles.
        github, issue = self.seeded()
        reused = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=DESCRIBED_PR,
        )
        reused.body = HUMAN_DESCRIPTION
        github.existing_open_pr[support.BRANCH] = reused

        self.deliver(
            github,
            issue,
            support.verified_message(reused.number, HUMAN_DESCRIPTION),
        )

        self.assertEqual(github.edited_pr_bodies, [])
        self.assertEqual(reused.body, HUMAN_DESCRIPTION)
        self.assertEqual(github.posted_pr_comments, [])
        settled = github.pinned_data(support.REPORT_ISSUE)[
            support.CURRENT_RECORD
        ]
        self.assertEqual(
            (
                settled["location_pr"],
                settled["location_comment"],
                settled["content"],
            ),
            (
                DESCRIBED_PR,
                None,
                _reports.content_digest(HUMAN_DESCRIPTION),
            ),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_a_run_with_no_report_publishes_nothing(self) -> None:
        # Every developer prompt teaches the report contract, so a run that
        # finished, committed, and handed over no report is one this stage
        # holds rather than ships: published, a reviewer would be sent an
        # implementation nobody described, with no session left to ask.
        for described, message in (
            ("no marker at all", "implemented, nothing else to say"),
            ("a block nothing closed", "REPORT: READY\nhalf a report"),
            (
                "another repository",
                support.verified_message(
                    FOREIGN_PR, HUMAN_DESCRIPTION, slug=support.FOREIGN_SLUG,
                ),
            ),
        ):
            with self.subTest(message=described):
                github, issue = self.seeded()

                self.deliver(github, issue, message)

                recorded = github.pinned_data(support.REPORT_ISSUE)
                self.assertEqual(
                    (
                        github.opened_prs,
                        recorded.get(AWAITING_HUMAN),
                        recorded.get(PARK_REASON),
                    ),
                    ([], True, _report_delivery.UNDELIVERABLE_REPORT),
                )
                self.assertNotIn(
                    (support.REPORT_ISSUE, LABEL_VALIDATING),
                    github.label_history,
                )


if __name__ == "__main__":
    unittest.main()
