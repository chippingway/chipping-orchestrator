# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a requirements-drift resume under review does with the report it writes.

The report is recorded before the size gate and the push, stamped with the
requirements revision the drift check handed the resume, and published once the
code is out -- or at once, for a report that needed no commit. A commit with no
report is held, an `ACK:` and a question keep their own roads, and a run that
did not finish records nothing. An edit or comment landing while the agent is
out is answered by the next resume rather than stamped onto this report. A
commit left unpublished for want of its report stays so until a reply brings
one, whatever else the replies say. A report alone is recorded only over a
clean tree, and one verified on the pull request's description is kept only
where that body still closes the issue and names the session.
"""

from __future__ import annotations

import unittest

from orchestrator import config
from orchestrator.github import developer_reports as _developer_reports
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow import drift_reports as world
from tests.workflow.fixtures import LABEL_VALIDATING, TEST_REPO_SLUG, _agent, _named_description

ISSUE = 1_793

PR = 17_930

RUN_AGENT = "run_agent"

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

REVIEW_ROUND = "review_round"

WATERMARK = "last_action_comment_id"

CURRENT = "current"

ACK_REPLY = "ACK: the existing commits already cover the edited criteria."

QUESTION_REPLY = "Should the new criterion replace the old one or sit beside it?"

# What a reviewer that ran says: no verdict, so it parks and nothing else runs.
REVIEW_REPLY = "Looked it over."

LOOSE_PATH = "scratch.txt"

# What the park a resume under review takes may not tell the human reading its
# pull request, and what it says about that pull request instead.
NEVER_OPENED = "no pull request was opened"

STILL_STANDS = "the pull request still stands on the commit it already carried"

# The description the implementation opened the pull request with, and one a
# human rewrote into a report that neither closes the issue nor names the session.
NAMED_DESCRIPTION = "\n\n".join((
    _named_description(ISSUE, world.DEV_SESSION, "claude"),
    "### Report",
    "The edited criteria are met.",
))

HUMAN_DESCRIPTION = "### Report\n\nThe edited criteria are met, verified by hand."


class DriftReportPublicationTest(unittest.TestCase, world._DriftReportMixin):
    def test_a_commit_publishes_its_report(self) -> None:
        # The requirements edit answered with a commit: the report the session
        # wrote reaches the pull request beside the code, about the pushed
        # commit and the requirements the resume was handed, and the round is
        # spent -- while the reviewer waits for the next tick.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        handed = world.handed_revision(self.issue)

        mocks = self.drift(world.reported())

        mocks[RUN_AGENT].assert_called_once()
        self.assertEqual(len(self.published_reports()), 1)
        current = self.records()[CURRENT]
        self.assertEqual(
            (current.subject.pr_number, current.subject.source_sha,
             current.subject.requirements_revision, current.report_revision),
            (PR, world.FIXED_HEAD, handed, 1),
        )
        self.assertEqual(
            (self.pinned()[REVIEW_ROUND], self.pinned().get(AWAITING_HUMAN)),
            (1, False),
        )
        self.assertEqual(self.github.label_history, [])

    def test_a_report_alone_goes_onto_the_same_head(self) -> None:
        # The drift prompt asks for a report whenever the report has to change,
        # and a report needs no commit to be delivered: it is published on the
        # head the pull request already carries, and the round is not spent.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        mocks = self.drift(world.reported(), committed=False)

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(
            self.records()[CURRENT].subject.source_sha, world.PUBLISHED_HEAD,
        )
        self.assertEqual(
            (self.pinned()[REVIEW_ROUND], self.pinned().get(AWAITING_HUMAN)),
            (0, False),
        )

    def test_a_commit_with_no_report_is_held(self) -> None:
        # Work nobody described is not pushed at all: the commit stays in the
        # worktree and the issue parks for the reply that resumes the session.
        # What the notice says is withheld is this road's: the pull request the
        # human is reading is open, and only what the run just added is held.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        mocks = self.drift("fixed the criteria")

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            (self.pinned().get(AWAITING_HUMAN), self.pinned().get(PARK_REASON)),
            (True, _report_delivery.UNDELIVERABLE_REPORT),
        )
        self.assertEqual(self.published_reports(), [])
        notice = _park_notice(self)
        self.assertIn(STILL_STANDS, notice)
        self.assertNotIn(NEVER_OPENED, notice)

    def test_the_report_is_recorded_before_the_push(self) -> None:
        # A push that fails leaves the report on the pinned comment, stamped
        # with the revision the resume was handed, and nothing on the pull
        # request -- the review stays held until a publication carries both.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        handed = world.handed_revision(self.issue)

        self.drift(world.reported(), push_branch=False)

        delivered = self.records()["delivered"]
        self.assertEqual(
            (delivered.requirements_revision, delivered.report),
            (handed, world.REPORT_TEXT),
        )
        self.assertEqual(self.pinned()[PARK_REASON], "push_failed")
        self.assertEqual(self.published_reports(), [])

    def test_acks_and_questions_keep_their_roads(self) -> None:
        # Neither is a report: an `ACK:` is posted as one and stays unparked,
        # a question parks as one, and neither records anything to publish.
        for reply, parked in ((ACK_REPLY, False), (QUESTION_REPLY, True)):
            with self.subTest(reply=reply):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)

                self.drift(reply, committed=False)

                self.assertEqual(bool(self.pinned().get(AWAITING_HUMAN)), parked)
                self.assertEqual(set(self.records().values()), {None})

    def test_runs_that_did_not_finish_record_nothing(self) -> None:
        # An interrupted run is retried next tick with nothing persisted, and
        # a timed-out one parks as a timeout: neither is a report anybody
        # finished, so neither leaves one to publish, and neither pushes.
        for run in ({"interrupted": True}, {"timed_out": True}):
            with self.subTest(run=run):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)

                mocks = self.drift(_agent(
                    session_id=world.DEV_SESSION,
                    last_message=world.reported(),
                    **run,
                ))

                mocks[PUSH_BRANCH].assert_not_called()
                self.assertEqual(set(self.records().values()), {None})


class DriftReportConcurrencyTest(unittest.TestCase, world._DriftReportMixin):
    def test_a_change_mid_run_is_answered_next_tick(self) -> None:
        # An edit or a comment landing while the agent is out moves the issue
        # past what the resume was handed -- an edit on the issue as GitHub
        # answers it NOW, not on the object the tick fetched before the run.
        # The pushed commit's report keeps the revision it was written against
        # and is left owed, never posted, rather than stamped with the later
        # one, and the comment stays unconsumed; the next tick
        # resumes the session on the change, and the report it writes -- a
        # second revision on the same commit -- is the one that settles.
        for change in ("edit", "comment"):
            with self.subTest(change=change):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                handed = world.handed_revision(self.issue)

                self.drift(self.mid_run(change, world.reported()))

                pending = self.records()["pending"].subject
                self.assertEqual(
                    (pending.source_sha, pending.requirements_revision),
                    (world.FIXED_HEAD, handed),
                )
                self.assertLess(self.pinned()[WATERMARK], world.LATER_COMMENT_ID)
                self.assertEqual(self.published_reports(), [])

                self.drift(world.reported(world.LATER_REPORT_TEXT), committed=False)

                self._assert_second_revision_settled(handed)

    def _assert_second_revision_settled(self, handed: str) -> None:
        current = self.records()[CURRENT]
        self.assertEqual(
            (current.report_revision, current.subject.source_sha,
             current.subject.requirements_revision),
            (2, world.FIXED_HEAD, world.handed_revision(self.issue)),
        )
        self.assertNotEqual(current.subject.requirements_revision, handed)
        self.assertEqual(len(self.published_reports(world.LATER_REPORT_TEXT)), 1)
        self.assertEqual(self.published_reports(), [])


class DriftReportDebtTest(unittest.TestCase, world._DriftReportMixin):
    def test_a_missing_report_is_owed_until_written(self) -> None:
        # A resume committed and wrote no report, so its commit stayed in the
        # worktree. A reply that only says `ACK:` does not pay that debt: the
        # commit is not published, and the review holds and parks for it.
        # Only the reply that brings a report publishes the commit, with that
        # report, and the reviewer runs once the pull request carries it.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.drift("fixed the criteria")
        world.human_reply(self)

        self.drift(ACK_REPLY, **world.STRANDED)[PUSH_BRANCH].assert_not_called()

        self._assert_the_debt_holds_the_review()
        world.human_reply(self)

        self.drift(world.reported(), **world.STRANDED)[PUSH_BRANCH].assert_called_once()

        # The debt is this stage's own: nothing was published when the resume
        # parked, so the head the reply finally lands is one no reviewer has
        # read, and it spends the round every fix that reaches the pull
        # request spends.
        self.assertEqual(self.pinned()[REVIEW_ROUND], 1)
        self._assert_reviewed_once_published()

    def _assert_the_debt_holds_the_review(self) -> None:
        """The debt outlives the `ACK:`, and parks the next review for a reply."""
        self.assertTrue(_report_delivery.owes_a_report(
            PinnedState(state_data=self.pinned()),
        ))
        held = self.drift(REVIEW_REPLY, head_shas=(world.FIXED_HEAD,))
        held[RUN_AGENT].assert_not_called()
        self.assertEqual(
            (self.pinned().get(AWAITING_HUMAN), self.pinned().get(PARK_REASON)),
            (True, _report_delivery.UNDELIVERABLE_REPORT),
        )

    def _assert_reviewed_once_published(self) -> None:
        """The report lands on the pull request, and the reviewer runs behind it."""
        self.reconcile()
        self.assertEqual(len(self.published_reports()), 1)
        reviewed = self.drift(REVIEW_REPLY, committed=False)
        self.assertEqual(reviewed[RUN_AGENT].call_args[0][0], config.REVIEW_AGENT)


class DriftReportCheckoutTest(unittest.TestCase, world._DriftReportMixin):
    def test_a_dirty_report_alone_parks_until_clean(self) -> None:
        # A report with no commit over a checkout carrying loose work would
        # describe something the pull request does not carry, and could never
        # settle. So nothing is recorded and the run parks on the tree; the
        # reply resumes the session, and its report over a clean tree is the
        # one published before the reviewer runs.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        self.drift(world.reported(), committed=False, dirty_files=(LOOSE_PATH,))

        self.assertTrue(self.pinned().get(AWAITING_HUMAN))
        self.assertEqual(set(self.records().values()), {None})
        world.human_reply(self, "cleaned up the scratch file")
        self.drift(world.reported(), committed=False)
        self.assertEqual(len(self.published_reports()), 1)
        reviewed = self.drift(REVIEW_REPLY, committed=False)
        self.assertEqual(reviewed[RUN_AGENT].call_args[0][0], config.REVIEW_AGENT)

    def test_a_verified_description_names_the_issue(self) -> None:
        # A report the developer verified on the pull request's own
        # description is kept only where that body still closes the issue and
        # names the session -- read again, not assumed. There it settles with
        # nothing posted; anywhere else the binding parks, since keeping it
        # would cost the pull request both lines and no description is
        # rewritten.
        for body, settles in ((NAMED_DESCRIPTION, True), (HUMAN_DESCRIPTION, False)):
            with self.subTest(settles=settles):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.pull_request.body = body

                self.drift(_verified(body), committed=False)

                current = self.records()[CURRENT]
                self.assertEqual(
                    (current is not None, self.pinned().get(PARK_REASON)),
                    (settles, None if settles else _report_delivery.UNDELIVERABLE_REPORT),
                )
                self.assertFalse(any(
                    body in (posted.body or "")
                    for posted in self.pull_request.issue_comments
                ))


def _park_notice(case) -> str:
    """What the park this tick took said to the human."""
    return next(
        body for _, body in reversed(case.github.posted_comments)
        if "developer run finished" in body
    )


def _verified(body: str) -> str:
    """A resume's message asserting the report is this pull request's description."""
    return (
        f"done\n\nREPORT: VERIFIED https://github.com/{TEST_REPO_SLUG}/pull/{PR} "
        f"sha256:{_developer_reports.content_digest(body)}"
    )
