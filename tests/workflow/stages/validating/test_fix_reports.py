# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the reviewer-requested fix round does with the report it writes.

The report is recorded before the size gate and the push and published once the
code is out -- or at once, on the head the pull request already carries, for a
round whose reviewer asked only for words. A report already on the pull request
is re-read and never posted twice. Either handover spends the round and hands
the issue back to `validating`, where the reviewer waits until the pull request
carries the report.

The refusals are the other half. A commit nobody described is published
nowhere, a run that did not finish is parked as the missing report it also is,
a report over loose work is refused on the tree, and a question, a timeout and
a shutdown keep the roads they always had.
"""

from __future__ import annotations

import unittest

from orchestrator import config
from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow import (
    drift_reports as _drift_world,
    fix_report_crashes as crashes,
    fix_reports as world,
)
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING, _agent

ISSUE = 1_794

PR = 17_940

RUN_AGENT = "run_agent"

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

REVIEW_ROUND = "review_round"

REVIEWER_ANCHOR = "pending_fix_reviewer_comment_id"

CURRENT = "current"

PENDING = "pending"

# The report a human published on the pull request themselves, which a round
# can verify instead of writing its own.
HUMAN_REPORT = "### Report\n\nRan the suite by hand; every check is green."

# The one file a checkout carrying loose work names, which is what refuses a
# report of that checkout before it is ever recorded.
LOOSE_PATH = "scratch.txt"

# The report the resume behind a requirements edit writes, which supersedes the
# one the fix round before it left owed. Spelled apart so a case can count each
# of the two on the pull request.
SUPERSEDING_REPORT = "Answers the edited criteria as well as the reviewer's."

# The two readers a fix round's issue-thread half answers to, which its report
# carries and the report superseding it has to carry on.
PR_LAST_COMMENT_ID = "pr_last_comment_id"

ISSUE_ACTION_ID = "last_action_comment_id"


class RequestedFixReportTest(unittest.TestCase, world._FixReportMixin):
    """The handovers a round the reviewer's own verdict opened can make."""

    def test_a_committed_fix_publishes_its_report(self) -> None:
        # The reviewer's feedback answered in code: the report the round wrote
        # -- the revision after the one the pull request was opened with --
        # reaches the pull request beside the commit and about it, the round is
        # spent, the replay anchor is dropped, and the issue goes back for the
        # reviewer to read both.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        mocks = self.requested_fix(world.reported())

        mocks[PUSH_BRANCH].assert_called_once()
        current = self.records()[CURRENT]
        self.assertEqual(
            (current.subject.pr_number, current.subject.source_sha,
             current.report_revision, len(self.published_reports())),
            (PR, world.FIXED_HEAD, 2, 1),
        )
        self.assertEqual(
            (*_handover(self), self.pinned().get(REVIEWER_ANCHOR)),
            (1, False, None),
        )
        self.assertIn((ISSUE, LABEL_VALIDATING), self.github.label_history)

    def test_a_report_alone_needs_no_commit(self) -> None:
        # The fix prompt asks a reviewer item naming report content to be
        # answered in the report and not in a commit, so a round that ends on
        # one publishes with nothing pushed: the report goes onto the head the
        # pull request already carries, and the round it spends is the round any
        # other handover spends, since the next reviewer reads it afresh.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        mocks = self.requested_fix(world.reported(), committed=False)

        mocks[PUSH_BRANCH].assert_not_called()
        current = self.records()[CURRENT]
        self.assertEqual(
            (current.subject.source_sha, len(self.published_reports())),
            (world.PUBLISHED_HEAD, 1),
        )
        self.assertEqual(_handover(self), (1, False))
        self.assertIn((ISSUE, LABEL_VALIDATING), self.github.label_history)

    def test_a_verified_report_is_never_reposted(self) -> None:
        # A report a human published is verified rather than written again: the
        # transaction re-reads that exact location, holds its text to the digest
        # the round named, and settles there with nothing posted -- so the pull
        # request carries one report rather than a duplicate of somebody's.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        published = world.published_report(self, HUMAN_REPORT)

        self.requested_fix(
            world.verified(PR, published.id, HUMAN_REPORT), committed=False,
        )

        current = self.records()[CURRENT]
        self.assertEqual(current.location.comment_id, published.id)
        self.assertEqual(
            [posted.body for posted in self.pull_request.issue_comments].count(
                HUMAN_REPORT,
            ),
            1,
        )
        self.assertEqual(_round(self), 1)

    def test_the_reviewer_waits_for_the_report(self) -> None:
        # The round hands the head back the moment its code is out, and the
        # report it recorded can still be outstanding -- here the remote reading
        # the transaction needs refuses. The reviewer is held on `validating`
        # for as long as that lasts rather than reading work whose report
        # nothing on the pull request carries, and the reconciliation behind it
        # is what releases them.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(
            world.reported(), fetched_branch_tip=world.PUBLISHED_HEAD,
        )
        self.assertIsNotNone(self.records()[PENDING])

        held = self.reviewed()
        self.reconcile()
        released = self.reviewed()

        held[RUN_AGENT].assert_not_called()
        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(released[RUN_AGENT].call_args[0][0], config.REVIEW_AGENT)
        # The round this handover cost was spent all the same, because what
        # spent it was a commit reaching the pull request rather than the report
        # -- durable in the write the size gate made beside its own receipt. It
        # is the road with NO code in it that charges nothing until the report
        # lands.
        self.assertEqual(_round(self), 1)


    def test_a_crash_before_the_push_publishes_first(self) -> None:
        # This round runs inline behind the label flip, so the window between
        # its report's write and the gate is one it leaves on `workflow:fixing`
        # with nobody waited for -- the same shape the parked resume leaves,
        # and answered by the same fixing tick. The commit the report describes
        # goes out through the gate before anything is handed on, because a
        # delivery bound to a head no publication carries is one `validating`
        # can only park.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        with crashes.dying_before_the_publication():
            self.requested_fix(world.reported())

        self.assertEqual(self.pull_request.head.sha, world.PUBLISHED_HEAD)
        # The next `fixing` tick, which is where both roads' window is
        # answered: this round left the label there with nobody waited for.
        handed = self.parked_resume(world.reported(), **_drift_world.STRANDED)

        handed[RUN_AGENT].assert_not_called()
        handed[PUSH_BRANCH].assert_called_once()
        self.reviewed()
        self.assertEqual(
            (self.pull_request.head.sha, len(self.published_reports()),
             _round(self)),
            (world.FIXED_HEAD, 1, 1),
        )

class RequestedFixRefusalTest(unittest.TestCase, world._FixReportMixin):
    """The rounds that publish nothing, and what each of them leaves."""

    def test_an_undescribed_commit_is_withheld(self) -> None:
        # A round that committed and handed over no report breaks the contract
        # every developer prompt teaches, and the reviewer behind it would be
        # handed work nothing accounts for with no session left to ask. So
        # nothing is pushed, the commit stays in the worktree, the round is
        # unspent, and the issue holds on `fixing` for the reply that reports.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        mocks = self.requested_fix("done -- see the diff")

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            (self.pinned()[AWAITING_HUMAN], self.pinned()[PARK_REASON]),
            (True, _report_delivery.UNDELIVERABLE_REPORT),
        )
        self.assertTrue(self.pinned()[_report_delivery.UNREPORTED_WORK])
        self.assertEqual(_round(self), 0)
        self.assertEqual(self.pull_request.head.sha, world.PUBLISHED_HEAD)
        self.assertNotIn((ISSUE, LABEL_VALIDATING), self.github.label_history)

    def test_an_unfinished_round_parks_for_a_report(self) -> None:
        # The engine exempts a run that did not COMPLETE from the report
        # contract, because the roads it serves publish nothing either way.
        # This road publishes, so a nonzero exit over committed work is parked
        # as the missing report it also is -- in this road's own words, since
        # the engine's speak for a developer that finished and declined.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        mocks = self.requested_fix(
            _agent(session_id=world.DEV_SESSION, last_message="died", exit_code=1),
        )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            self.pinned()[PARK_REASON], _report_delivery.UNDELIVERABLE_REPORT,
        )
        self.assertIn("did not finish", _park_notice(self))
        self.assertEqual(_round(self), 0)

    def test_a_report_over_loose_work_parks(self) -> None:
        # A report of a checkout carrying uncommitted work describes something
        # the pull request does not carry, and recorded anyway it could never
        # settle. So the round parks on the tree the way a commit would, with
        # nothing recorded but the debt -- which is what reads the reply to that
        # park as the answer to the report it still owes.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        self.requested_fix(
            world.reported(), committed=False, dirty_files=(LOOSE_PATH,),
        )

        self.assertEqual(set(self.records().values()), {None})
        self.assertTrue(self.pinned()[_report_delivery.OWED_REPORT])
        self.assertTrue(self.pinned()[AWAITING_HUMAN])
        self.assertEqual(len(self.published_reports()), 0)

    def test_a_report_needs_its_head_proved(self) -> None:
        # The road with no code in it publishes onto a head it does not push, so
        # that head is proved rather than assumed -- and "this run committed
        # nothing publishable" is the same answer the disposition gives a
        # checkout nobody could read, a fetch that failed, a divergence git
        # refused, a remote that moved, and a branch carrying a commit the pull
        # request has not got. None of them may be read as a report alone:
        # published over one, the report describes a head no reviewer will see.
        # Each parks with the debt recorded, the report unwritten, and the
        # commit under it left for the ordinary measurement.
        for described, unproved in world.UNPROVED_HEADS:
            with self.subTest(refusal=described):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)

                mocks = self.requested_fix(
                    world.reported(), committed=False, **unproved,
                )

                mocks[PUSH_BRANCH].assert_not_called()
                self.assertEqual(set(self.records().values()), {None})
                self.assertEqual(
                    (self.pinned()[AWAITING_HUMAN], _round(self)),
                    (True, 0),
                )
                self.assertTrue(self.pinned()[_report_delivery.OWED_REPORT])
                self.assertNotIn(
                    (ISSUE, LABEL_VALIDATING), self.github.label_history,
                )

    def test_every_other_outcome_keeps_its_road(self) -> None:
        # The roads a report does not change. A silent reply is still the
        # question this route has always read it as -- the reviewer asked for a
        # concrete change, so there is nothing to acknowledge. A timeout keeps
        # its own transient park, which the fixing handler retries without a
        # human. And a shutdown-killed round records nothing at all, so the next
        # tick simply runs the round again.
        rounds = (
            (world.QUESTION_REPLY, (True, None)),
            (_agent(session_id=world.DEV_SESSION, timed_out=True), (True, "agent_timeout")),
            (_agent(session_id=world.DEV_SESSION, interrupted=True), (False, None)),
        )
        for reply, expected in rounds:
            with self.subTest(park=expected):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)

                mocks = self.requested_fix(reply, committed=False)

                mocks[PUSH_BRANCH].assert_not_called()
                self.assertEqual(set(self.records().values()), {None})
                self.assertEqual(
                    (
                        bool(self.pinned().get(AWAITING_HUMAN)),
                        self.pinned().get(PARK_REASON),
                    ),
                    expected,
                )
                self.assertEqual(_round(self), 0)
                self.assertIn((ISSUE, LABEL_FIXING), self.github.label_history)
                self.assertNotIn((ISSUE, LABEL_VALIDATING), self.github.label_history)


class SupersededFixReportTest(unittest.TestCase, world._FixReportMixin):
    """A fix round's report replaced before it ever reached the pull request."""

    def test_drift_carries_what_it_supersedes(self) -> None:
        # A round whose reviewer asked only for words reports, and the human
        # edits the issue while that session is out -- so the transaction
        # refuses to publish against requirements the run never saw and is left
        # owed, with the round it lands on, the replay anchor it closes and the
        # reply it answered all frozen on it and NONE of them written. The
        # resume that edit earns writes the report that supersedes it. Both
        # roads that reach this window are the same window, so both are driven:
        # the direct round the reviewer's own verdict opened, and the resume on
        # the far side of a park.
        #
        # What the replacement owes is both handovers, because it replaces the
        # record that carried the first: published alone, it would leave a
        # round nobody spent, an anchor a `/orchestrator continue` would replay
        # stale reviewer feedback from, and the human's reply reading as fresh
        # feedback for a developer that already answered it.
        for parked, road in ((False, "direct"), (True, "parked")):
            with self.subTest(road=road):
                answered = self._owing_round(parked)

                self.drift(world.reported(SUPERSEDING_REPORT), committed=False)

                self.assertEqual(
                    (_handover(self), self.pinned().get(REVIEWER_ANCHOR),
                     self.pinned().get(PR_LAST_COMMENT_ID) >= answered),
                    ((1, False), None, True),
                )
                self.assertEqual(
                    (len(self.published_reports()),
                     len(self.published_reports(SUPERSEDING_REPORT))),
                    (0, 1),
                )

    def _owing_round(self, parked: bool) -> int:
        """A fix round holding a report it could not publish, and what it read.

        The reply the round answered, so a case can say the reader it froze
        moved. Zero on the direct road, whose input is the reviewer's own
        comment rather than a human's.
        """
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        edited = self.mid_run("edit", world.reported())
        if not parked:
            self.requested_fix(edited, committed=False)
            return 0
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)
        answered = max(reply.id for reply in self.issue.comments)
        self.parked_resume(edited, committed=False)
        return answered


def _handover(case) -> tuple:
    """The round a handover spent, and whether it left a human waiting."""
    return case.pinned()[REVIEW_ROUND], case.pinned()[AWAITING_HUMAN]


def _round(case) -> int:
    """The reviewer round this issue's pinned comment says it has spent."""
    return case.pinned()[REVIEW_ROUND]


def _park_notice(case) -> str:
    """What the park this round took said to the human."""
    return next(
        body for _, body in reversed(case.github.posted_comments)
        if config.HITL_MENTIONS in body
    )


if __name__ == "__main__":
    unittest.main()
