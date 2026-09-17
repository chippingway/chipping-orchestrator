# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report this workflow cannot deliver, and the reply that answers it.

Two roads reach it. Before the push, a run that finished and handed over a
report nothing can record -- one past what the pinned comment holds, or none at
all -- so nothing is published and the commit stays in the worktree. After it, a
report bound to no publication this code reached: one asserted on somebody
else's pull request, and one asserted on the very description this publication
needs for its closing reference and attribution. There the branch and the pull
request stand and only the handoff is withheld. None of them discards what the
run wrote, and neither lets the work reach review without a report.

The record that never LANDED is the neighbouring module's,
`test_report_lost_record`: there the run reported and the pinned write failed,
so what the next tick recovers is committed work no record describes at all.

What answers any of them is a human's reply: the developer resumes and writes a
report that can be delivered, and the run that brings one back publishes the
commits already on the branch rather than parking as a question -- the park
itself being the debt that tells one from the other. On the description road
that reply buys both halves at once: the report goes in a comment, which is what
frees the body for the rewrite that names this implementation.
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
from tests.workflow.fixtures import _FAKE_WT, _TEST_SPEC, LABEL_VALIDATING, _agent, _open_pr_for
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.implementing import report_test_support as support

# The pull request the first tick opens, where one is opened at all: this
# client numbers the ones it opens from 1.
OPENED_PR = 1

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

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

# The report a resumed session writes in place of one that could not be
# delivered.
REPLACEMENT_REPORT = "Adds the thing, reported inline this time."


class UndeliverableReportTest(unittest.TestCase, support._ReportDeliveryMixin):
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

    def test_an_unrecordable_report_is_redelivered(self) -> None:
        # The park's own promise: a reply resumes the session, and the report
        # it writes then is the one that gets published. The resumed run makes
        # no commit -- the commit is already on the branch -- so what tells it
        # from a question is the debt the park itself records.
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

    def test_a_needed_description_is_freed(self) -> None:
        # The park a report verified on the publication's own description
        # takes, and what the reply buys. The resumed session writes its report
        # as text, so it goes in a COMMENT -- no report lives in the body any
        # more, and the rewrite that was withheld puts this issue's closing
        # reference and the session's name there after all.
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
        support.replies(github, issue, "put the report in a comment")

        self.redeliver(
            github, issue, support.ready_message(REPLACEMENT_REPORT),
        )

        posted = support.published_reports(github, DESCRIBED_PR)
        self.assertEqual(len(posted), 1)
        self.assertIn(REPLACEMENT_REPORT, posted[0].body)
        self.assertIn(f"Resolves #{support.REPORT_ISSUE}", reused.body)
        self.assertIn(support.DEV_SESSION, reused.body)
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

        posted = support.published_reports(github, OPENED_PR)
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
