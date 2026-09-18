# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report this workflow cannot deliver, and the reply that answers it.

Before the push: a report nothing can record, or none at all -- nothing is
published. After it: a report bound to another pull request, or verified on the
description this publication needs -- only the handoff is withheld. A reply
resumes the developer, and a report it brings back publishes the commits
already on the branch, the recorded debt telling it from a question.
`test_report_lost_record` covers the record whose write never landed.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_record_values as _record_values,
)
from orchestrator.workflow.stages.implementing import (
    disposition as _disposition,
    models as _models,
)
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
    LABEL_VALIDATING,
    SHA_LENGTH,
    _agent,
    _open_pr_for,
)
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.implementing import report_test_support as support

# The pull request the first tick opens, where one is opened at all: this
# client numbers the ones it opens from 1.
OPENED_PR = 1

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

AGENT_TIMEOUT = "agent_timeout"

_UNDELIVERABLE = _report_delivery.UNDELIVERABLE_REPORT

# Where a resumed session's checkout stood before it committed and timed out.
EARLIER_HEAD = "f" * SHA_LENGTH

# The pull request a verification names, which is not the one this issue's code
# reaches: the transaction has to be about one pull request, so a report
# asserted on another cannot be bound to this publication at all.
OTHER_PR = 4200

# The comment on it the developer says carries that report.
OTHER_REPORT_ID = 9200

# The pull request already open on the branch whose own description a
# verification names, and the description it carries: a human's, saying neither
# of the things this publication needs a description to say.
DESCRIBED_PR = 4300

HUMAN_DESCRIPTION = "### Report\n\nThe branch adds the thing. Verified by hand."

# What that description sits under once this implementation is named above it.
EARLIER_HEADING = "_Description before this implementation:_"

# The report a resumed session writes in place of one that could not be
# delivered.
REPLACEMENT_REPORT = "Adds the thing, reported inline this time."

# The revision that replacement goes out under wherever the report it replaces
# was RECORDED: it moves past the delivery still standing, so its receipt is
# its own rather than the one the refused record already spelled.
REPLACEMENT_REVISION = 2


class UndeliverableReportTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_an_unrecordable_report_publishes_nothing(self) -> None:
        # A report past what the pinned comment carries could never publish,
        # so it is held before the gate and the push, costing nothing.
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

    def test_an_unrecordable_report_is_redelivered(self) -> None:
        # The park's own promise: a reply resumes the session, and the report
        # it writes then is the one that gets published. The resumed run makes
        # no commit -- the commit is already on the branch -- so what tells it
        # from a question is the debt the park records beside its reason.
        github, issue = self.seeded()
        oversized = "x" * (_record_values.MAX_REPORT_TEXT + 1)
        self.deliver(github, issue, support.ready_message(oversized))
        support.replies(github, issue, "please report in a paragraph")

        self.redeliver(
            github, issue, support.ready_message(REPLACEMENT_REPORT),
        )

        posted = support.published_reports(github, OPENED_PR)
        self.assertEqual(len(posted), 1)
        self.assertIn(REPLACEMENT_REPORT, posted[0].body)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                len(github.opened_prs),
                recorded[support.DELIVERY_RECORD],
                recorded[support.PENDING_RECORD],
                recorded.get(AWAITING_HUMAN),
                recorded.get(PARK_REASON),
            ),
            (1, None, None, False, None),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_a_failed_resume_keeps_the_debt(self) -> None:
        # The debt outlives its park: a resumed session that timed out parks as
        # a timeout, or -- having committed -- parks for the report, and the
        # report the next reply brings back publishes rather than asks.
        for committed, parked in ((False, AGENT_TIMEOUT), (True, _UNDELIVERABLE)):
            with self.subTest(committed=committed):
                github, issue = self.seeded()
                self.deliver(github, issue, support.ready_message(
                    "x" * (_record_values.MAX_REPORT_TEXT + 1),
                ))
                support.replies(github, issue, "please report in a paragraph")
                self._run_implementing(
                    github, issue,
                    run_agent=_agent(session_id=support.DEV_SESSION, timed_out=True),
                    has_new_commits=True,
                    head_shas=(EARLIER_HEAD if committed else support.PUBLISHED_SHA,
                               support.PUBLISHED_SHA),
                    dirty_files=(),
                    push_branch=True,
                )
                pinned = github.pinned_data(support.REPORT_ISSUE)
                self.assertEqual(
                    (pinned[AWAITING_HUMAN], pinned[PARK_REASON]), (True, parked),
                )
                if committed:
                    github.get_pr(OPENED_PR).head.sha = support.PUBLISHED_SHA
                support.replies(github, issue, "try once more")

                self.redeliver(
                    github, issue, support.ready_message(REPLACEMENT_REPORT),
                )

                self.assertEqual(
                    len(support.published_reports(github, OPENED_PR)), 1,
                )
                self.assertIn(
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
                OTHER_PR,
                "somebody else's report",
                comment_id=OTHER_REPORT_ID,
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

    def test_a_freed_description_is_named_above(self) -> None:
        # Held, the body is untouched; the reply's report goes in a COMMENT,
        # and the freed description gets the two lines above every word.
        github, issue, reused = self._collided_on_the_description()
        self.assertEqual(
            (github.edited_pr_bodies, github.label_history), ([], []),
        )
        support.replies(github, issue, "put the report in a comment")

        self.redeliver(
            github, issue, support.ready_message(REPLACEMENT_REPORT),
        )

        self.assertEqual(
            (
                len(support.published_reports(
                    github, DESCRIBED_PR, REPLACEMENT_REVISION,
                )),
                reused.body.startswith(f"Resolves #{support.REPORT_ISSUE}"),
                support.DEV_SESSION in reused.body,
                reused.body.endswith(f"{EARLIER_HEADING}\n\n{HUMAN_DESCRIPTION}"),
            ),
            (1, True, True, True),
        )
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                recorded[support.DELIVERY_RECORD],
                recorded[support.PENDING_RECORD],
                recorded.get(AWAITING_HUMAN),
            ),
            (None, None, False),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def test_a_replacement_report_needs_no_commit(self) -> None:
        # The park asked for a report, so a resumed session that writes one
        # and touches no file is answering it rather than asking a question:
        # its report replaces the one that could not be delivered, and the
        # commits already on the branch are what it goes out with.
        github, issue = self.seeded()
        _open_pr_for(github, issue_number=support.REPORT_ISSUE, pr_number=OTHER_PR)
        self.deliver(
            github,
            issue,
            support.verified_message(
                OTHER_PR,
                "somebody else's report",
                comment_id=OTHER_REPORT_ID,
            ),
        )
        github.get_pr(OPENED_PR).head.sha = support.PUBLISHED_SHA
        support.replies(github, issue)

        self.redeliver(
            github, issue, support.ready_message(REPLACEMENT_REPORT),
        )

        posted = support.published_reports(
            github, OPENED_PR, REPLACEMENT_REVISION,
        )
        self.assertEqual(len(posted), 1)
        self.assertIn(REPLACEMENT_REPORT, posted[0].body)
        recorded = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (
                recorded[support.DELIVERY_RECORD],
                recorded[support.PENDING_RECORD],
                recorded.get(AWAITING_HUMAN),
                recorded.get(PARK_REASON),
            ),
            (None, None, False, None),
        )
        self.assertIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )


    def _collided_on_the_description(self):
        """Park a verification on the reused pull request's own description.

        The description is a human's and says neither thing a publication
        needs it to, so the binding holds the work over it; the pull request
        is then left standing on the pushed commit, as the push left it.
        """
        github, issue = self.seeded()
        reused = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=DESCRIBED_PR,
        )
        reused.body = HUMAN_DESCRIPTION
        github.existing_open_pr[support.BRANCH] = reused
        self.deliver(
            github,
            issue,
            support.verified_message(DESCRIBED_PR, HUMAN_DESCRIPTION),
        )
        reused.head.sha = support.PUBLISHED_SHA
        return github, issue, reused


class ReportOnlyReplyTest(unittest.TestCase):
    """The seam that tells a report answering a debt from a question.

    Asked of the disposition directly, because the ordinary road into it is a
    reply that moves the requirements hash and therefore goes to the drift
    resume instead. What reaches this one is every other resume -- a bare
    `/orchestrator continue`, a reply that changed nothing a human wrote -- and
    it has to read a report the same way.
    """

    def test_an_owed_report_publishes_unmoved_work(self) -> None:
        for described, message, publishes in (
            ("a report", support.ready_message(), True),
            ("a question", "which database should this use?", False),
        ):
            with self.subTest(reply=described):
                self.assertEqual(
                    self._left_commits(support.owing_state(), message),
                    publishes,
                )

    def test_an_issue_owing_nothing_reads_a_question(self) -> None:
        # The debt is what makes a no-commit report a publication, so an issue
        # that owes none reads the same reply exactly as it always did.
        self.assertFalse(
            self._left_commits(PinnedState(), support.ready_message()),
        )

    def _left_commits(self, state, message: str) -> bool:
        """What the disposition makes of a run whose head never moved."""
        prepared = _models._PreparedDevRun(
            agent_result=_agent(
                session_id=support.DEV_SESSION, last_message=message,
            ),
            before_sha=support.PUBLISHED_SHA,
            paused=False,
            worktree=_FAKE_WT,
        )
        with seam_patch("_has_new_commits", MagicMock(return_value=True)), \
                seam_patch(
                    "_head_sha", MagicMock(return_value=support.PUBLISHED_SHA),
                ):
            return _disposition._run_left_commits(_TEST_SPEC, state, prepared)


if __name__ == "__main__":
    unittest.main()
