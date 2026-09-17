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

The other road here is the requirements moving while the run that reported on
them worked. Nothing is published then either: the report answers an issue that
has changed, and what supersedes it is the resume the edit earns.

A report this workflow cannot deliver AT ALL is the neighbouring module's,
`test_report_undeliverable`: those roads publish no code either, and what
answers them is a reply rather than a poll.
"""

from __future__ import annotations

import unittest

from tests.workflow.fixtures import LABEL_VALIDATING, _agent
from tests.workflow.stages.implementing import report_test_support as support

# The pull request the first tick opens: this client numbers the ones it opens
# from 1, and the failure a case is about has to be registered against a number
# before the request that meets it is made.
OPENED_PR = 1

RUN_AGENT = "run_agent"

PUBLISHED_SHA_KEY = "implementing_published_sha"

APPROVED_SHA_KEY = "late_approved_sha"

AWAITING_HUMAN = "awaiting_human"

PUSH_BRANCH = "_push_branch"

# The edit a human makes to the issue while a run is working.
EDITED_BODY = "the requirements moved while the agent was running"


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

    def test_edited_requirements_hold_the_report(self) -> None:
        # A human edited the issue while the developer worked, so the report
        # answers requirements the issue no longer has. Publishing it would
        # stamp it with the revision its run was handed and hand it to a
        # reviewer as current, so it is left owed for the drift resume -- and
        # the work is not handed on either.
        github, issue = self.seeded()

        self._run_implementing(
            github,
            issue,
            run_agent=_EditsTheIssue(issue, support.ready_message()),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
        )

        self.assertEqual(len(github.opened_prs), 1)
        self.assertEqual(support.published_reports(github, OPENED_PR), [])
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertIsNotNone(recorded[support.PENDING_RECORD])
        self.assertNotIn(support.CURRENT_RECORD, recorded)
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )


class _EditsTheIssue:
    """A developer run a human edits the issue's body underneath.

    The edit lands where the window this is about is: after the drift check
    that opened the tick and before anything the publication reads, which is
    exactly a human typing while an agent works.
    """

    def __init__(self, issue, message: str) -> None:
        self._issue = issue
        self._message = message

    def __call__(self, *_args, **_kwargs):
        """Edit the issue, then answer as the run that reported on it."""
        self._issue.body = EDITED_BODY
        return _agent(
            session_id=support.DEV_SESSION, last_message=self._message,
        )


if __name__ == "__main__":
    unittest.main()
