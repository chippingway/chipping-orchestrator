# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report that did not reach its pull request, and what the stage does then.

The ordinary window is the one every publication has: the branch is on the
remote, a pull request carries it, and the comment the report goes in is a
separate request that GitHub can refuse or accept without saying so. What the
stage owes there is to keep the work exactly where it is -- unhanded-on,
unparked, and recorded as still owing a report -- so the next poll finishes it
with no developer run, no second pull request, and no second report. That retry
runs over the world the first tick left, which is the world the size gate calls
DELIVERED: the receipt names the commit, and the pull request is standing on
it, so the push moves nothing and the bookkeeping is all that is left.

The other two roads are the report this workflow cannot deliver at all. One is
answered before anything is published, where holding costs nothing; the other
after the push, where the code stands and only the handoff is withheld. Neither
discards what the run wrote, and neither lets the work reach review without it.
"""

from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_record_values as _record_values,
)
from tests.workflow.fixtures import LABEL_VALIDATING, _open_pr_for
from tests.workflow.stages.implementing import report_test_support as support

# The pull request the first tick opens: this client numbers the ones it opens
# from 1, and the failure a case is about has to be registered against a number
# before the request that meets it is made.
OPENED_PR = 1

RUN_AGENT = "run_agent"

PUSH_BRANCH = "_push_branch"

PUBLISHED_SHA_KEY = "implementing_published_sha"

APPROVED_SHA_KEY = "late_approved_sha"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

# The pull request a verification names, which is not the one this issue's code
# reaches: the transaction has to be about one pull request, so a report
# asserted on another cannot be bound to this publication at all.
OTHER_PR = 4200

# The comment on it the developer says carries that report.
OTHER_REPORT_ID = 9200


class ReportDebtTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_refused_report_holds_the_handoff(self) -> None:
        github, issue = self.seeded()
        github.report_failures.refused.add(OPENED_PR)

        self.deliver(github, issue, support.ready_message())

        # The code is published: the branch went out, the pull request is open,
        # and the receipt names both.
        self.assertEqual(len(github.opened_prs), 1)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (recorded[PUBLISHED_SHA_KEY], recorded[APPROVED_SHA_KEY]),
            (support.PUBLISHED_SHA, support.PUBLISHED_SHA),
        )
        self.assertEqual(support.published_reports(github, OPENED_PR), [])
        # The report is not, so the transaction stands and the work is not
        # handed on -- and nothing is parked, because nothing here needs a
        # human.
        self.assertIsNotNone(recorded[support.PENDING_RECORD])
        self.assertNotIn(support.CURRENT_RECORD, recorded)
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )
        self.assertFalse(recorded.get(AWAITING_HUMAN))

    def test_the_next_tick_publishes_the_report(self) -> None:
        github, issue = self.seeded()
        github.report_failures.refused.add(OPENED_PR)
        self.deliver(github, issue, support.ready_message())
        github.report_failures.refused.clear()
        # What the push left on the remote, which is what makes this the
        # gate's delivered road: the pull request is standing on the commit
        # the receipt names, so the retry publishes nothing new.
        github.get_pr(OPENED_PR).head.sha = support.PUBLISHED_SHA

        mocks = self.republish(github, issue)

        mocks[RUN_AGENT].assert_not_called()
        # Leased against the commit itself, which only the delivered road
        # does: the gate admitted the candidate because that pull request is
        # already standing on it, so the push sends nothing and a tip somebody
        # moved in the window is refused rather than force-overwritten.
        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs["force_with_lease"],
            support.PUBLISHED_SHA,
        )
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                len(github.opened_prs),
                len(support.published_reports(github, OPENED_PR)),
                recorded[support.PENDING_RECORD],
                recorded[support.CURRENT_RECORD]["pr"],
            ),
            (1, 1, None, OPENED_PR),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_a_lost_response_is_not_reposted(self) -> None:
        # GitHub accepted the comment and the answer never came back, so the
        # first tick cannot say the report is there. The retry reads the thread
        # by this transaction's receipt and finds what landed.
        github, issue = self.seeded()
        github.report_failures.lost.add(OPENED_PR)

        self.deliver(github, issue, support.ready_message())
        landed = support.published_reports(github, OPENED_PR)
        self.assertEqual(len(landed), 1)
        github.get_pr(OPENED_PR).head.sha = support.PUBLISHED_SHA

        self.republish(github, issue)

        self.assertEqual(len(support.published_reports(github, OPENED_PR)), 1)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertIsNone(recorded[support.PENDING_RECORD])
        # The comment this orchestrator posted is recorded as the report's own
        # location and in its own comment ledger, so no later scan reads the
        # report back as somebody's fresh feedback.
        self.assertEqual(
            (
                recorded[support.CURRENT_RECORD]["location_comment"],
                landed[0].id in recorded["orchestrator_comment_ids"],
            ),
            (landed[0].id, True),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_an_unrecordable_report_publishes_nothing(self) -> None:
        # A report past what the pinned comment can carry is one nothing could
        # ever publish -- the record is what a later tick would publish from --
        # and the run that wrote it has ended. Held before the size gate and
        # the push, the refusal costs nothing: the commit is still in the
        # worktree and a reply resumes the session that writes it again.
        github, issue = self.seeded()
        oversized = "x" * (_record_values.MAX_REPORT_TEXT + 1)

        mocks = self.deliver(github, issue, support.ready_message(oversized))

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(github.opened_prs, [])
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertNotIn(support.DELIVERY_RECORD, recorded)
        self.assertEqual(
            (recorded.get(AWAITING_HUMAN), recorded.get(PARK_REASON)),
            (True, _report_delivery.UNDELIVERABLE_REPORT),
        )
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_an_unbindable_report_is_held(self) -> None:
        # The developer asserted a report on another pull request, so the
        # transaction can never be about the publication this code reached.
        # The code stands, the report stays recorded, the work is not handed
        # on, and a human is told once.
        github, issue = self.seeded()
        _open_pr_for(github, issue_number=support.REPORT_ISSUE, pr_number=OTHER_PR)

        self.deliver(
            github,
            issue,
            support.verified_message(
                OTHER_PR, OTHER_REPORT_ID, "somebody else's report",
            ),
        )

        self.assertEqual(len(github.opened_prs), 1)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertIsNotNone(recorded[support.DELIVERY_RECORD])
        self.assertEqual(
            (recorded.get(AWAITING_HUMAN), recorded.get(PARK_REASON)),
            (True, _report_delivery.UNDELIVERABLE_REPORT),
        )
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )


if __name__ == "__main__":
    unittest.main()
