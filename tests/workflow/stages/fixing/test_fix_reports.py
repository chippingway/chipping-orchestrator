# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a parked fix round's resume does with the report it writes.

The resume on the far side of a park is the rest of the round the reviewer
opened, so it answers the same contract: a commit is published under the report
of it, a report with no code in it goes onto the head the pull request already
carries, and a commit an earlier round left unpublished passes the size gate
before anything settles on it. Either handover clears the park and the
automated-fix bookmarks, hands the issue back to `validating`, and spends
exactly one fix round -- the route's own, reset for the human-feedback road and
bumped for the reviewer's -- however many ticks the report takes to reach the
pull request. The ordinary non-actionable `ACK:` keeps its own road back to
`in_review`.

The feedback the round answered rides the report on the one road where the
report is the whole handover, so the readers move in the write that settles it
and not before: a report the pull request has not got is no answer to the
comments behind it.

A round the PROCESS did not survive is the sibling module's
(`test_fix_report_crashes.py`): what it left is durable rather than a reply, and
the tick that reads it finishes that round instead of running another.
"""

from __future__ import annotations

import unittest

from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow import (
    drift_reports as _drift_world,
    fix_report_crashes as crashes,
    fix_reports as world,
)
from tests.workflow.fixtures import (
    LABEL_FIXING,
    LABEL_IN_REVIEW,
    LABEL_VALIDATING,
)

ISSUE = 1_794

PR = 17_940

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

REVIEW_ROUND = "review_round"

REVIEWER_ANCHOR = "pending_fix_reviewer_comment_id"

PENDING_FIX_AT = "pending_fix_at"

# The two readers a round's issue-thread half answers to: the PR-side cursor
# the next fixing rescan reads, and the issue-action boundary every other
# stage's awaiting-human resume delivers from.
PR_LAST_COMMENT_ID = "pr_last_comment_id"

ISSUE_ACTION_ID = "last_action_comment_id"

CURRENT = "current"

PENDING = "pending"

# What the in_review route records beside the feedback that sent the issue
# here, and which is the discriminator between the two routes' round
# accounting.
FEEDBACK_AT = "2026-05-24T00:00:00+00:00"

FEEDBACK_ID = 4_000

# The round the human-feedback route is entered on, which its own handover
# resets rather than bumps: the approval it carried was for the prior head.
SPENT_ROUNDS = 2

ACK_REPLY = "ACK: the comments name no actionable change."




class ParkedFixReportTest(unittest.TestCase, world._FixReportMixin):
    """The reviewer's round, finished by the resume a human's reply earns."""

    def test_a_reply_that_reports_needs_no_commit(self) -> None:
        # The round asked a question and parked; the reply says the answer is
        # words rather than code. The report it writes goes onto the head the
        # pull request already carries, the park and the replay anchor come off,
        # the issue goes back for a fresh review of that same head, and the
        # round the reviewer opened is spent exactly once.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)

        mocks = self.parked_resume(world.reported(), committed=False)

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            (self.records()[CURRENT].subject.source_sha,
             len(self.published_reports())),
            (world.PUBLISHED_HEAD, 1),
        )
        self.assertEqual(
            (*_handover(self), self.pinned().get(REVIEWER_ANCHOR)),
            (1, False, None),
        )
        self.assertIn((ISSUE, LABEL_VALIDATING), self.github.label_history)

    def test_a_committed_resume_publishes_its_report(self) -> None:
        # The reply asked for more code, and the resume that answers it is held
        # to the report contract before the gate reads the candidate: the report
        # reaches the pull request about the commit it sends, and the park the
        # round was standing on comes off with the handover.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self, "the helper should move")

        mocks = self.parked_resume(world.reported())

        mocks[PUSH_BRANCH].assert_called_once()
        self.assertEqual(
            (self.records()[CURRENT].subject.source_sha,
             len(self.published_reports())),
            (world.FIXED_HEAD, 1),
        )
        self.assertEqual(_handover(self), (1, False))
        self.assertIn((ISSUE, LABEL_FIXING), self.github.label_history)
        self.assertIn((ISSUE, LABEL_VALIDATING), self.github.label_history)

    def test_a_withheld_commit_passes_the_gate(self) -> None:
        # The round committed and could not report, so nothing was published and
        # the commit stayed in the checkout. The reply brings the report, and
        # the commit reaches the pull request the way every candidate does --
        # through the size gate -- with the report bound to that publication and
        # the round spent on the head the reviewer will read.
        _withheld_then_reported(self)

        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)
        self.assertEqual(_round(self), 1)
        self.assertEqual(
            (self.records()[CURRENT].subject.source_sha,
             len(self.published_reports())),
            (world.FIXED_HEAD, 1),
        )

    def test_the_replay_counts_one_round(self) -> None:
        # The round settled its own report, and the reconciliation ahead of
        # every later handler reads the same comment. Replayed over it, twice,
        # it posts no second report and counts no second round: what a
        # settlement applies is the pair the transaction froze, not a counter
        # it reads again.
        _withheld_then_reported(self)

        self.reconcile()
        self.reconcile()

        self.assertEqual(
            (self.records()[CURRENT].subject.source_sha,
             len(self.published_reports()), _round(self)),
            (world.FIXED_HEAD, 1, 1),
        )
        self.assertIsNone(self.pinned()[_report_delivery.UNREPORTED_WORK])

class ParkedFixHandoverTest(unittest.TestCase, world._FixReportMixin):
    """What a handover costs, and when -- and what it will not act on."""

    def test_the_handover_waits_for_the_report(self) -> None:
        # The round the report IS the handover for buys nothing until that
        # report is on the pull request, so nothing of the handover is written
        # before it lands: settled, the reply the round answered is recorded as
        # read, the reviewer round is spent and the replay anchor is dropped, by
        # the one write that settles the report. Left owed -- here a human
        # editing the issue while the agent was out, which the transaction
        # refuses to publish against -- none of it is, so the round can be
        # finished again rather than having been charged for a report no
        # reviewer has.
        for run, settles in ((world.reported(), True), (None, False)):
            with self.subTest(settles=settles):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.requested_fix(world.QUESTION_REPLY, committed=False)
                world.replied(self)
                answered = max(reply.id for reply in self.issue.comments)

                self.parked_resume(
                    run or self.mid_run("edit", world.reported()),
                    committed=False,
                )

                self.assertEqual(
                    (
                        self.pinned().get(PR_LAST_COMMENT_ID) == answered,
                        self.pinned().get(ISSUE_ACTION_ID) == answered,
                        _round(self) == 1,
                        self.pinned().get(REVIEWER_ANCHOR) is None,
                        len(self.published_reports()),
                        (ISSUE, LABEL_VALIDATING) in self.github.label_history,
                    ),
                    (settles, settles, settles, settles, int(settles), settles),
                )

    def test_a_reply_reaching_for_a_report_is_no_ack(self) -> None:
        # A message carrying BOTH a report block and an `ACK:` line is one
        # broken contract rather than two answers. Read as the acknowledgement,
        # it would clear the bookmarks and hand the pull request back to
        # `in_review` over work whose report nothing carries; read as what it
        # is, the round parks for a human like every other reply this road
        # cannot act on.
        _seed_human_feedback(self)

        self.parked_resume(
            f"{world.reported()}\n\n{ACK_REPLY}", committed=False,
        )

        self.assertTrue(self.pinned()[AWAITING_HUMAN])
        self.assertEqual(self.github.label_history, [])
        self.assertIsNotNone(self.pinned()[PENDING_FIX_AT])
        self.assertEqual(set(self.records().values()), {None})

    def test_a_park_consumes_what_it_was_given(self) -> None:
        # The park is durable the moment it is taken, so the input the prompt
        # delivered rides that same write -- here the terminal park a report
        # earns over a checkout this host PROVED is carrying something, which
        # no later poll takes back and no road here publishes over. Left to a
        # caller's write behind it, a process dying in between leaves the issue
        # awaiting a human over feedback that still reads as unanswered, which
        # the next tick reads as fresh and resumes the developer over again
        # with nobody having replied.
        #
        # The recorded report is RELEASED into that same write, because a
        # record left standing is one the very next tick publishes the moment
        # the tree is clean -- which is the decision this notice is asking a
        # human to make. The DEBT outlives it, so the review stays held.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)
        answered = max(reply.id for reply in self.issue.comments)

        with crashes.dying_after_the_park(self):
            self.parked_resume(
                world.reported(), committed=False, dirty_files=("stray.py",),
            )

        self.assertEqual(
            (self.pinned()[AWAITING_HUMAN], self.pinned()[PARK_REASON],
             self.pinned()[_report_delivery.OWED_REPORT]),
            (True, _report_delivery.UNDELIVERABLE_REPORT, True),
        )
        self.assertEqual(self.pinned().get(PR_LAST_COMMENT_ID), answered)
        self.assertEqual(set(self.records().values()), {None})
        held = self.parked_resume(world.reported(), committed=False)
        held["run_agent"].assert_not_called()

class ParkedFixRefusalTest(unittest.TestCase, world._FixReportMixin):
    """The replies this road publishes nothing for, and what each leaves."""

    def test_a_resume_with_no_report_stays_parked(self) -> None:
        # The reply produced a second commit and no report of either, so this
        # resume is held exactly as the round before it was: nothing pushed, the
        # round unspent, and the issue still on `fixing` for a reply that reports
        # the work the branch is carrying.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix("done -- see the diff")
        world.replied(self)

        mocks = self.parked_resume("done again", **_drift_world.RETRY_OVER_STRANDED)

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            (_handover(self), self.pinned()[PARK_REASON]),
            ((0, True), _report_delivery.UNDELIVERABLE_REPORT),
        )
        self.assertEqual(self.pull_request.head.sha, world.PUBLISHED_HEAD)
        self.assertNotIn((ISSUE, LABEL_VALIDATING), self.github.label_history)

    def test_the_human_route_re_reviews_a_report(self) -> None:
        # A report is a handover the next reviewer has to read, so on the
        # human-feedback route it takes the same fresh-review road a pushed fix
        # takes -- back to `validating` with the round reset, because the
        # approval that carried the issue to `in_review` was for the prior head.
        # The ordinary non-actionable acknowledgement is the separate road it
        # always was: no report, no round moved, and the pull request re-armed
        # for its ready ping.
        roads = (
            (world.reported(), (LABEL_VALIDATING, 0, 1)),
            (ACK_REPLY, (LABEL_IN_REVIEW, SPENT_ROUNDS, 0)),
        )
        for reply, expected in roads:
            with self.subTest(road=expected[0]):
                _seed_human_feedback(self)

                self.parked_resume(reply, committed=False)

                self.assertEqual(
                    (
                        self.github.label_history[-1][1],
                        _round(self),
                        len(self.published_reports()),
                    ),
                    expected,
                )
                self.assertIsNone(self.pinned()[PENDING_FIX_AT])
                self.assertFalse(self.pinned()[AWAITING_HUMAN])


def _handover(case) -> tuple:
    """The round a handover spent, and whether it left a human waiting."""
    return case.pinned()[REVIEW_ROUND], case.pinned()[AWAITING_HUMAN]


def _round(case) -> int:
    """The reviewer round this issue's pinned comment says it has spent."""
    return case.pinned()[REVIEW_ROUND]


def _withheld_then_reported(case) -> None:
    """A round that committed with no report, and the reply that reports it.

    The commit the first round left is still in the checkout and the pull
    request is still standing below it, so the reply's own publication is that
    commit going out for the first time.
    """
    case.seeded(ISSUE, PR, LABEL_VALIDATING)
    case.requested_fix("done -- see the diff")
    world.replied(case)
    pushed = case.parked_resume(world.reported(), **_drift_world.STRANDED)
    pushed[PUSH_BRANCH].assert_called_once()


def _seed_human_feedback(case) -> None:
    """A `fixing` issue the in_review route sent here, parked on a reply."""
    case.seeded(ISSUE, PR, LABEL_VALIDATING, review_round=SPENT_ROUNDS)
    world.parked(
        case,
        pending_fix_at=FEEDBACK_AT,
        pending_fix_issue_max_id=FEEDBACK_ID,
    )
    world.replied(case, "please look again")


if __name__ == "__main__":
    unittest.main()
