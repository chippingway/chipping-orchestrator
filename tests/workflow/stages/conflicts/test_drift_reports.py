# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a body edit's resume mid-rebase does with the report it returns.

#2077 / PR #2087: the requirements change while the approved, documented pull
request is being rebased, and the resumed session rebases it and returns a
fresh report. That report is the one the pull request gets -- recorded before
the rewritten head is pushed, stamped with the requirements the resume was
handed and the road it came down, and settled before the reviewer is handed it
-- with no park, no human reply, and no second run to write it again. A report
with no commit goes onto the head the pull request already carries. A run that
committed and wrote none parks, and the reply to that park is the rest of the
same road, publishing the commit the first run left -- a rebase past the pull
request's head included -- under the report it writes, stamped with the
requirements that reply actually delivered; a bare `/orchestrator continue`
retrying that reply's timeout is a retry there too, never quoted as guidance.
Whatever window a process ends in between the record and its settlement, the
existing receipts carry the saved report to the pull request once, and a round
counted ahead of a relabel that never landed is not counted again.
"""
from __future__ import annotations

import contextlib
import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    prompt_notes as _prompt_notes,
    report_delivery as _report_delivery,
    report_publishing as _report_publishing,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import drift_reports as world, fix_report_crashes as crashes
from tests.workflow.stages.conflicts import drift_report_support as conflict

# What the reviewer behind a settled report says: no verdict, so it parks on
# its own side and nothing else runs.
REVIEW_REPLY = "Looked it over."

# A developer that finished, committed, and wrote no report at all; and one
# that answered the edit with a question.
UNREPORTED_REPLY = "rebased onto main and folded in the new criterion"

QUESTION_REPLY = "which of the two criteria did you mean?"

# Runs that answer the edit with nothing a report may stand for -- a question,
# and a report written with a command still running, over the head the run
# began on and over a commit it left -- with the park each takes.
EXECUTION_FAILED = "agent_execution_failed"

UNANSWERED_RUNS = (
    ("a question", QUESTION_REPLY, False, None),
    ("an unfinished report", conflict.UNFINISHED_REPORT, False, EXECUTION_FAILED),
    ("an unfinished report over a commit", conflict.UNFINISHED_REPORT, True, EXECUTION_FAILED),
)

# Two replies to a park that owes a report, longer between them than the
# excerpt a drift prompt is bounded to: an instruction, and background behind it.
EARLIER_REPLY = "Also cover the second criterion before anything else."

BACKGROUND = "background "

LONG_REPLY = BACKGROUND * (_prompt_context._EXCERPT_CHARS // len(BACKGROUND) + 1)

# A reply that only acknowledges the edit, writing no report of the commit.
ACK_REPLY = "ACK: the existing commits already cover the changed criteria"

# The command that retries a session the agent timeout killed.
CONTINUE = "/orchestrator continue"

# What a human rewrites the body to once the resume has parked, while the
# branch is still ahead of its remote.
LATER_BODY = world.LATER_BODY

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
PARK_REASON = "park_reason"
AWAITING_HUMAN = "awaiting_human"
CONFLICT_ROUND = "conflict_round"
REVIEW_ROUND = "review_round"
DRIFT_OPEN = "requirements_drift_open"
AGENT_RUNS_USED = "agent_runs_used"
USER_CONTENT_HASH = "user_content_hash"
REBASE_IN_PROGRESS = "rebase_in_progress"
DELIVERED = "delivered"
PENDING = "pending"
CURRENT = "current"
AGENT_TIMEOUT = "agent_timeout"
HANDED_CLAIM = "conflict_handed_sha"
LAST_ACTION = "last_action_comment_id"

# A counter that has spent every round the cap allows, and the park it takes.
MAX_CONFLICT_ROUNDS = "MAX_CONFLICT_ROUNDS"
AT_THE_CAP = 2
CONFLICT_CAP = "conflict_cap"
DIVERGED = "diverged_branch"

# What stands in front of a saved report once a crash has cut its binding
# short: the cap, and a park waiting on a human -- one a later tick took over
# a remote somebody moved, the branch since reconciled and nobody replying
# yet. Each with the park it leaves standing.
IN_FRONT = (
    ("the cap", MappingProxyType({}), CONFLICT_CAP),
    ("a reply wait", MappingProxyType({AWAITING_HUMAN: True, PARK_REASON: DIVERGED}), DIVERGED),
)

# What the dev answers a conflict the rebase onto a moved base left.
RESOLVER = "resolved the conflict in a.py"

# The head a rebase onto a base that moved leaves the recovered commit at, and
# the readings of the tick that makes it and of the one behind it.
REBASED_HEAD = "d0d0d0d0" * 5

ONTO_THE_NEW_BASE = MappingProxyType({
    world.HEAD_SHAS: (world.FIXED_HEAD, REBASED_HEAD),
    world.FETCHED_TIP: world.FIXED_HEAD,
    "candidate_commit": FrozenCommit(sha=REBASED_HEAD),
})

# The checkout once the recovered push has put the pull request on its commit.
ON_THE_PUSHED_HEAD = MappingProxyType({
    world.HEAD_SHAS: (world.FIXED_HEAD,),
    world.FETCHED_TIP: world.FIXED_HEAD,
})

ON_THE_REBASED_HEAD = MappingProxyType({
    world.HEAD_SHAS: (REBASED_HEAD,),
    world.FETCHED_TIP: REBASED_HEAD,
})

# The rewrite behind the recovery, and the run that answers it: none for a
# clean replay, and a developer resolving the file both sides changed.
REWRITES = (
    ("a clean rebase", conflict.REBASED_CLEANLY, []),
    ("a conflicted rebase", conflict.REBASED_INTO_CONFLICT, "resolved the conflict in a.py"),
)

FRESH_REPORT = "Reports the rebased head the conflict round left."

# A commit the checkout moved on to after a crash took the push of the one the
# saved report describes, and the two shapes a checkout can be found in off
# that candidate: moved on and still ahead of the remote, which looks like any
# other unpushed work, and put back on the head the push would have replaced.
MOVED_ON_HEAD = "e0e0e0e0" * 5

OFF_THE_CANDIDATE = (
    ("moved on ahead of the remote", MappingProxyType({
        world.HEAD_SHAS: (MOVED_ON_HEAD,),
        world.AHEAD_BEHIND: (1, 0),
        world.FETCHED_TIP: world.PUBLISHED_HEAD,
        "candidate_commit": FrozenCommit(sha=MOVED_ON_HEAD),
    })),
    ("put back on the published head", MappingProxyType({
        world.HEAD_SHAS: (world.PUBLISHED_HEAD,),
        world.FETCHED_TIP: world.PUBLISHED_HEAD,
    })),
)

SAVED_CANDIDATE = "conflict_resume_to_sha"

# Every way a checkout leaves the candidate a saved report describes, and
# whether that candidate's push had landed first, the relabel behind it lost.
KEPT_CANDIDATES = (
    *((shape, checkout, False) for shape, checkout in OFF_THE_CANDIDATE),
    ("moved on past its landed push", conflict.PAST_THE_PUSH, True),
)

# The ways a report alone is left unsettled: the process ending as its
# delivery is bound; the binding landing and the post behind it held for a
# later tick; and a run that left a head nothing could read, whose report is
# never recorded. Each with the records it leaves owed, and the head the
# conflict-resume record names.
AS_IT_IS_BOUND = "as it is bound"
ONCE_IT_IS_BOUND = "once it is bound"
OVER_AN_UNREAD_HEAD = "over a head nobody read"

REPORT_ALONE_UNSETTLED = (
    (AS_IT_IS_BOUND, (DELIVERED,), world.PUBLISHED_HEAD),
    (ONCE_IT_IS_BOUND, (PENDING,), world.PUBLISHED_HEAD),
    (OVER_AN_UNREAD_HEAD, (), None),
)

# How many resumes a developer session may take: room to spare, so the reply
# resumes it, and one, which the edit's own resume has already spent, so the
# reply rotates it out for a fresh spawn.
SESSION_LIMITS = ((False, 50), (True, 1))

# The same two for a retry behind a reply's timed-out run: room to spare, and
# two, which the edit's resume and that run have spent between them, so the
# retry rotates the session out for a fresh spawn.
RETRY_SESSION_LIMITS = ((False, 50), (True, 2))


def _assert_published_once(case, head: str, handed: str) -> None:
    """One report of `head` on the pull request, answering `handed`, and the one the approval covered as it was."""
    case.assertEqual(len(case.published_reports()), 1)
    current = case.records()[CURRENT]
    case.assertEqual(
        (current.subject.source_sha, current.subject.requirements_revision),
        (head, handed),
    )
    case.assertEqual(case.opening_report.subject.source_sha, world.PUBLISHED_HEAD)


def _assert_handed_to_review(case) -> None:
    """The round counted once, the reviewer's budget reset, and the label handed to `validating`."""
    pinned = case.pinned()
    case.assertEqual(case.github.label_history, [(conflict.ISSUE, WorkflowLabel.VALIDATING)])
    case.assertEqual((pinned[CONFLICT_ROUND], pinned[REVIEW_ROUND]), (1, 0))
    case.assertIsNone(pinned.get(PARK_REASON))


class ResolvingConflictDriftReportTest(
    unittest.TestCase, conflict._ConflictDriftReportMixin,
):
    """The report a body edit's resume returns mid-rebase, carried to the reviewer."""

    def test_a_rebased_resume_publishes_its_report(self) -> None:
        self.seeded_on_conflict()
        handed = self.handed()
        push = conflict.PushedAfterTheRecord(self)

        self.drift(world.reported(), push_branch=push)[PUSH_BRANCH].assert_called_once()

        self._assert_recorded_before(push, handed)
        _assert_published_once(self, world.FIXED_HEAD, handed)
        _assert_handed_to_review(self)

        reviewed = self.drift(REVIEW_REPLY, committed=False)

        self.assertIn(world.REPORT_TEXT, reviewed[RUN_AGENT].call_args.args[1])
        _assert_published_once(self, world.FIXED_HEAD, handed)
        self.assertEqual(self.pinned()[AGENT_RUNS_USED], 2)

    def test_a_report_alone_settles_on_the_pr_head(self) -> None:
        # The rebase is already on the pull request, so the session answers
        # the edit in words. Nothing is pushed and no round is spent; the issue
        # stays here as it would on an `ACK:`, and the next tick finds the
        # branch on its base and hands it on without another agent. The record
        # naming the head the report is about outlives the settlement, which
        # never retires a record some other report may still be held to.
        self.seeded_on_conflict()
        handed = self.handed()

        resumed = self.drift(world.reported(), committed=False)

        resumed[PUSH_BRANCH].assert_not_called()
        _assert_published_once(self, world.PUBLISHED_HEAD, handed)
        pinned = self.pinned()
        self.assertEqual(
            (pinned[CONFLICT_ROUND], pinned[REVIEW_ROUND], pinned.get(SAVED_CANDIDATE)),
            (0, 2, world.PUBLISHED_HEAD),
        )
        self.assertFalse(pinned.get(AWAITING_HUMAN))
        self.assertEqual(self.github.label_history, [])

        flipped = self.drift([], committed=False)

        flipped[RUN_AGENT].assert_not_called()
        self.assertEqual(self.github.label_history, [(conflict.ISSUE, WorkflowLabel.VALIDATING)])
        _assert_published_once(self, world.PUBLISHED_HEAD, handed)

    def test_an_unanswered_edit_parks_here(self) -> None:
        # A question answers the edit with nothing, and its reply is the rebase
        # loop's to read: no drift claim goes down for `validating` to read the
        # next unrelated park's reply by. Nor does a report written with a
        # command still running answer it: that run never finished, so it
        # parks as the execution failure it is, and nothing is recorded,
        # pushed, or published -- over the head it began on or a commit it left.
        for shape, run_agent, committed, reason in UNANSWERED_RUNS:
            with self.subTest(shape=shape):
                self.seeded_on_conflict()

                self.drift(run_agent, committed=committed)[PUSH_BRANCH].assert_not_called()

                pinned = self.pinned()
                self.assertEqual(
                    (pinned.get(PARK_REASON), pinned[AWAITING_HUMAN], pinned.get(DRIFT_OPEN)),
                    (reason, True, None),
                )
                self.assertEqual(set(self.records().values()), {None})
                self.assertEqual(self.published_reports(), [])

    def test_a_timeout_mid_rebase_is_retried(self) -> None:
        # The timeout kills the session with its rebase still mid-flight. That
        # reads first, as the resolution funnel reads it: a session failure,
        # parked as the timeout it is, which `/orchestrator continue` retries
        # -- not a rebase only a human can finish, which refuses the command.
        self.seeded_on_conflict()

        self.drift(conflict.TIMED_OUT, rebase_in_progress=True)[PUSH_BRANCH].assert_not_called()

        self.assertEqual(self.pinned()[PARK_REASON], AGENT_TIMEOUT)
        self.assertEqual(set(self.records().values()), {None})
        world.human_reply(self, CONTINUE)
        retried = self.drift(QUESTION_REPLY, committed=False)[RUN_AGENT]
        retried.assert_called_once()
        self.assertNotIn(CONTINUE, retried.call_args.args[1])

    def test_a_capped_report_alone_still_settles(self) -> None:
        # The counter has spent every round, and the session answers the edit
        # with a report and no commit; the process ends as that report is
        # bound. The ticks behind it settle the report before the cap parks
        # the issue or a human's park is waited on -- behind either, nothing
        # would ever settle it, and the base refresh stays frozen on its
        # records -- so it goes out once, nobody is launched, and the park in
        # front of it is the one left standing.
        for shape, parked, park in IN_FRONT:
            with self.subTest(shape=shape), patch.object(config, MAX_CONFLICT_ROUNDS, AT_THE_CAP):
                self.seeded_on_conflict(**{CONFLICT_ROUND: AT_THE_CAP})
                handed = self.handed()
                with self.dying_at_the_binding():
                    self.drift(world.reported(), committed=False)
                self.github.seed_state(conflict.ISSUE, **{**self.pinned(), **parked})

                for _ in range(2):
                    self.drift([], committed=False)[RUN_AGENT].assert_not_called()

                _assert_published_once(self, world.PUBLISHED_HEAD, handed)
                self.assertEqual(self.pinned()[PARK_REASON], park)

    def test_a_capped_recovery_waits_on_its_report(self) -> None:
        # At the cap, a crash took the push of a commit whose report was saved,
        # and the base has moved since. The recovered push publishes it and
        # lands behind the base; the cap is asked only once that report is
        # settled, so no park lands over a report still owed. The dispatch
        # reconciliation settles it, and the cap parks on the tick behind,
        # the report out once and the rebase never run.
        rebase = MagicMock(return_value=conflict.REBASED_CLEANLY)
        with patch.object(config, MAX_CONFLICT_ROUNDS, AT_THE_CAP):
            self.seeded_on_conflict(documented=False, **{CONFLICT_ROUND: AT_THE_CAP})
            with crashes.dying_before_the_publication():
                self.drift(world.reported())
            self.drift([], base=conflict.behind_its_base(rebase), **world.STRANDED)
            self.assertIsNone(self.pinned().get(PARK_REASON))
            self.reconcile()
            self.drift([], base=conflict.behind_its_base(rebase), **ON_THE_PUSHED_HEAD)

        rebase.assert_not_called()
        _assert_published_once(self, world.FIXED_HEAD, self.handed())
        self.assertEqual(self.pinned()[PARK_REASON], CONFLICT_CAP)

    def _assert_recorded_before(self, push, handed: str) -> None:
        """The report on the comment as the push went out, under this road and the revision it was handed."""
        recorded = push.delivered
        self.assertIsNotNone(recorded, "the report must be durable before the push")
        self.assertEqual(
            (recorded.route, recorded.requirements_revision, recorded.report),
            (WorkflowLabel.RESOLVING_CONFLICT, handed, world.REPORT_TEXT),
        )


class ResolvingConflictReportReplyTest(
    unittest.TestCase, conflict._ConflictDriftReportMixin,
):
    """The reply that finishes a body edit's resume parked for its report.

    A finished run that committed and wrote no report publishes nothing, and
    its notice says the pull request stands where it stood. The reply resumes
    the session as the rest of that road: the report it writes goes onto the
    comment ahead of the gate and the commit the first run left is published
    under it -- not pushed undescribed by the resolution road, with the report
    parked as a question. That holds over a commit one ahead of the pull
    request and over a rebase that went past it, where the reply commits
    nothing more, with no final-docs pass behind the head to vouch for it.
    """

    def test_an_unreported_commit_rides_the_reply(self) -> None:
        for shape, checkout in conflict.UNPUBLISHED:
            with self.subTest(shape=shape):
                self._parked_on_an_unreported_commit(replied=True)

                self.drift(world.reported(), **checkout)[PUSH_BRANCH].assert_called_once()

                pending = self.records()[PENDING]
                self.assertEqual(
                    (pending.subject.source_sha, pending.route, pending.subject.requirements_revision),
                    (world.FIXED_HEAD, WorkflowLabel.RESOLVING_CONFLICT, self.handed()),
                )
                # What the reply's run was handed is the new baseline, so no
                # drift check reads the reply as an edit and answers it again.
                self.assertEqual(self.pinned()[USER_CONTENT_HASH], self.handed())
                _assert_handed_to_review(self)
                self.reconcile()
                _assert_published_once(self, world.FIXED_HEAD, self.handed())

    def test_a_reply_delivers_the_edit_it_finds(self) -> None:
        # The body moves while the branch is ahead of its remote, so the reply
        # is answered before the edit's own resume can run. The reply's run is
        # resumed on the frozen drift prompt, which quotes the edited body and
        # every reply whole -- an instruction a long reply behind it would push
        # out of a bounded excerpt included -- and its report is stamped with
        # that record's revision, whether the session resumes or, rotated out,
        # a fresh spawn is re-grounded on the same frozen text. That revision
        # is then the baseline, and the replies are marked read by what that
        # record delivered, so nothing is left reading as an edit nobody
        # answered and nothing is marked read that was never handed over.
        for rotated, resumes in SESSION_LIMITS:
            with self.subTest(rotated=rotated), patch.object(config, "DEV_SESSION_MAX_RESUMES", resumes):
                self._parked_on_an_unreported_commit()
                world.edits(self, LATER_BODY)
                world.human_reply(self, EARLIER_REPLY)
                world.human_reply(self, LONG_REPLY)

                resumed = self.drift(world.reported(), **world.STRANDED)[RUN_AGENT].call_args

                self.assertEqual(
                    [
                        quoted in resumed.args[1]
                        for quoted in (LATER_BODY, EARLIER_REPLY, LONG_REPLY.strip())
                    ],
                    [True, True, True],
                )
                self.assertEqual(
                    self.pinned()[LAST_ACTION],
                    self.issue.comments[-1].id,
                )
                self.assertEqual(resumed.kwargs.get("resume_session_id") is None, rotated)
                stamped = self.records()[PENDING].subject.requirements_revision
                handed = self.handed()
                self.assertEqual((stamped, self.pinned()[USER_CONTENT_HASH]), (handed, handed))

    def test_a_timeout_retries_on_the_owed_report(self) -> None:
        # The reply's run times out with the report still owed, and a human
        # answers the timeout with a bare `/orchestrator continue`. That stays
        # the retry it is on every other park: the neutral retry prompt leads
        # the frozen drift prompt, and the command is out of that read --
        # neither quoted as the last thing a human said nor in the
        # conversation a rotated session's fresh spawn is re-grounded on. The
        # report the retry writes publishes the commit once, stamped with the
        # requirements the command never moved, and the command is consumed.
        for rotated, resumes in RETRY_SESSION_LIMITS:
            with self.subTest(rotated=rotated), patch.object(config, "DEV_SESSION_MAX_RESUMES", resumes):
                self._parked_on_an_unreported_commit(replied=True)
                self.drift(conflict.TIMED_OUT, **world.STRANDED)[PUSH_BRANCH].assert_not_called()
                world.human_reply(self, CONTINUE)

                retried = self.drift(world.reported(), **world.STRANDED)[RUN_AGENT].call_args

                self.assertIn(_prompt_notes._CONTINUE_RETRY_PROMPT, retried.args[1])
                self.assertNotIn(CONTINUE, retried.args[1])
                pinned = self.pinned()
                self.assertEqual(
                    (retried.kwargs.get("resume_session_id") is None, pinned[LAST_ACTION], pinned[USER_CONTENT_HASH]),
                    (rotated, self.issue.comments[-1].id, self.handed()),
                )
                _assert_handed_to_review(self)
                self.reconcile()
                _assert_published_once(self, world.FIXED_HEAD, self.handed())

    def test_an_ack_leaves_the_report_owed(self) -> None:
        # Nobody has replied at first: the park's own notice is this
        # orchestrator's, however far the watermark was carried, so tick after
        # tick launches nothing and charges nothing. The reply's run then only
        # acknowledges the edit. That answers the park without writing the
        # report the commit is owed, so the debt stands with the flags down --
        # and the commit is still ahead of the remote. No later tick publishes
        # it, counts the round, or launches anybody: the recovery parks again
        # for the report, and waits there for a human.
        self._parked_on_an_unreported_commit()
        charged = self.pinned()[AGENT_RUNS_USED]
        for _ in range(2):
            self.drift(world.reported(), **world.STRANDED)[RUN_AGENT].assert_not_called()
        world.human_reply(self)
        self.drift(ACK_REPLY, **world.STRANDED)[PUSH_BRANCH].assert_not_called()

        for _ in range(2):
            ticked = self.drift([], **world.STRANDED)
            ticked[PUSH_BRANCH].assert_not_called()
            ticked[RUN_AGENT].assert_not_called()

        # One charge across every tick: the reply's run.
        pinned = self.pinned()
        self.assertEqual(
            (pinned[PARK_REASON], pinned[CONFLICT_ROUND], pinned[AGENT_RUNS_USED]),
            (_report_delivery.UNDELIVERABLE_REPORT, 0, charged + 1),
        )
        self.assertEqual(set(self.records().values()), {None})
        self.assertEqual(self.github.label_history, [])

    def test_an_unfinished_rebase_records_nothing(self) -> None:
        # The reply's run returns with the rebase still mid-flight, whether or
        # not it moved the head. A branch not finished being written is none a
        # report may describe or a push may send, so the issue parks as the
        # resolution funnel parks such a run: no report recorded, nothing
        # pushed, no round counted, and the label where it was.
        for after in (world.FIXED_HEAD, REBASED_HEAD):
            with self.subTest(moved=after != world.FIXED_HEAD):
                self._parked_on_an_unreported_commit(replied=True)

                self.drift(
                    world.reported(), rebase_in_progress=True,
                    **{**world.STRANDED, world.HEAD_SHAS: (world.FIXED_HEAD, after)},
                )[PUSH_BRANCH].assert_not_called()

                pinned = self.pinned()
                self.assertEqual((pinned[PARK_REASON], pinned[CONFLICT_ROUND]), (REBASE_IN_PROGRESS, 0))
                self.assertEqual(set(self.records().values()), {None})
                self.assertEqual(self.github.label_history, [])

    def test_a_concurrent_push_keeps_the_lease(self) -> None:
        # Somebody pushes onto the pull request while the agent is out, a
        # commit the candidate still descends from. The publication stays
        # leased to the head its caller read before the run -- the one the
        # body edit's resume began at, or the one a reply found the pull
        # request on -- so the size gate refuses it rather than adopting the
        # newer head as the one the push replaces. The report stays recorded.
        for shape, entered, checkout in (
            ("a body edit's resume", self.seeded_on_conflict, MappingProxyType({})),
            ("a reply's resume", partial(self._parked_on_an_unreported_commit, replied=True), world.STRANDED),
        ):
            with self.subTest(shape=shape):
                entered()

                ran = self.drift(self.mid_run("push", world.reported()), **checkout)

                ran[PUSH_BRANCH].assert_not_called()
                self.assertEqual(self.pull_request.head.sha, world.CONCURRENT_HEAD)
                self.assertIsNotNone(self.records()[DELIVERED])
                self.assertEqual(
                    (self.published_reports(), self.github.label_history, self.pinned()[CONFLICT_ROUND]),
                    ([], [], 0),
                )

    def _parked_on_an_unreported_commit(self, *, replied: bool = False) -> str:
        """The body edit's resume parked for its commit's report, and a reply where `replied`; its baseline."""
        self.seeded_on_conflict(documented=False)
        self.drift(UNREPORTED_REPLY)[PUSH_BRANCH].assert_not_called()
        pinned = self.pinned()
        self.assertEqual(pinned[PARK_REASON], _report_delivery.UNDELIVERABLE_REPORT)
        self.assertIsNone(pinned.get(DRIFT_OPEN))
        self.assertIn(
            "the pull request still stands on the commit it already carried",
            self.github.posted_comments[-1][1],
        )
        if replied:
            world.human_reply(self)
        return pinned[USER_CONTENT_HASH]


class ResolvingConflictDriftReportRecoveryTest(
    unittest.TestCase, conflict._ConflictDriftReportMixin,
):
    """A process ending between the report this road recorded and its settlement.

    Whatever the window, the saved report is the one published: the existing
    receipts carry it to the pull request -- the recovered push, the settled
    round, the transaction's own -- and no tick publishes it twice, launches
    another developer, charges another run, or counts the round again.
    """

    def test_a_death_before_the_push_is_recovered(self) -> None:
        # The report is on the comment and the commit only in the checkout --
        # one ahead of the remote, or rebased past it with no final-docs pass
        # behind the head it would replace. The next tick pushes it, the
        # record written beside the report licensing the force-push over the
        # second, and the review hold binds and settles the saved report
        # before the reviewer runs.
        for shape, checkout in conflict.UNPUBLISHED:
            with self.subTest(shape=shape):
                self.seeded_on_conflict(documented=False)
                handed = self.handed()
                with crashes.dying_before_the_publication():
                    self.drift(world.reported())
                self.assertEqual(self.records()[DELIVERED].requirements_revision, handed)

                self.drift([], **checkout)[PUSH_BRANCH].assert_called_once()

                self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)
                self._assert_reviewed_once(handed)

    def test_a_death_past_the_push_settles_once(self) -> None:
        # Past the push: on the write that would make the round's count
        # durable, on the relabel the bound report is waiting behind, or on
        # the report's own post GitHub took and never answered. The round the
        # push's own write named is counted once, and reported by one audit
        # event, which goes out only once its count is down; the move a lost
        # relabel owed is made on the next tick without counting it again --
        # held, while nothing can prove the head it hands on, with nothing
        # pushed, launched, or counted; the transaction finishes off its
        # receipt without a second post.
        for window, crash, held in (
            ("the count write", self.dying_at_the_count, 0),
            ("the relabel", partial(crashes.dying_before_the_relabel, self), 0),
            ("the relabel, its head unproved", partial(crashes.dying_before_the_relabel, self), 2),
            ("the report post", self._loses_the_post, 0),
        ):
            with self.subTest(window=window):
                self.seeded_on_conflict()
                handed = self.handed()
                with crash():
                    self.drift(world.reported())
                self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)
                held_ticks = [
                    self.drift([], committed=False, **conflict.UNPROVED_HEAD)
                    for _ in range(held)
                ]
                self.assertEqual(
                    {ticked[name].call_count for ticked in held_ticks for name in (PUSH_BRANCH, RUN_AGENT)},
                    {0} if held else set(),
                )

                self.drift([], committed=False)[PUSH_BRANCH].assert_not_called()

                self._assert_reviewed_once(handed)

    def test_a_death_behind_the_relabel_is_counted(self) -> None:
        # The relabel lands and the process ends on the write behind it. The
        # round was made durable ahead of the move, so `validating` holds the
        # head with the round counted and the review budget reset, and its
        # report hold settles the saved report before the reviewer runs. The
        # claim the lost write left is retired there too, so a later conflict
        # over the same head -- a base that moved and no longer replays
        # cleanly, on an issue no park holds -- is rebased and resolved, not
        # handed straight back to review.
        self.seeded_on_conflict()
        handed = self.handed()

        with conflict.dying_behind_the_relabel(self):
            self.drift(world.reported())

        _assert_handed_to_review(self)
        self._assert_reviewed_once(handed)
        self.assertIsNone(self.pinned().get(HANDED_CLAIM))
        self.github.seed_state(conflict.ISSUE, **{**self.pinned(), AWAITING_HUMAN: False})
        self.github.apply_foreign_label(self.issue, WorkflowLabel.RESOLVING_CONFLICT)
        rebase = MagicMock(return_value=conflict.REBASED_INTO_CONFLICT)
        reopened = self.drift(RESOLVER, base=conflict.behind_its_base(rebase), committed=False)
        rebase.assert_called_once()
        reopened[RUN_AGENT].assert_called_once()

    def test_a_rewrite_waits_for_the_saved_report(self) -> None:
        # The base moved again before the recovery. The commit the crash left
        # is pushed, but the rebase behind it -- clean, or one the developer
        # resolves -- does not run while the report saved for that commit is
        # unsettled: settled after it, the report would be bound to the head
        # the rebase left and handed to the reviewer as its account. Settled
        # first, the rebased head is owed a fresh report, which `validating`
        # asks the developer for, naming the head the saved report is about.
        for shape, rebased, resolver in REWRITES:
            with self.subTest(shape=shape):
                prompt = self._rewritten_behind_the_recovery(rebased, resolver)

                self.assertIn(f"now stands on commit `{REBASED_HEAD}`", prompt)
                self.assertIn(f"describes `{world.FIXED_HEAD}`", prompt)

    def _rewritten_behind_the_recovery(self, rebased, resolver) -> str:
        """A crash before the push, its recovery behind a moved base, the rewrite; what `validating` asks next."""
        rebase = MagicMock(return_value=rebased)
        self.seeded_on_conflict(documented=False)
        handed = self.handed()
        with crashes.dying_before_the_publication():
            self.drift(world.reported())
        self.drift([], base=conflict.behind_its_base(rebase), **world.STRANDED)
        rebase.assert_not_called()
        self.reconcile()
        self.drift(resolver, base=conflict.behind_its_base(rebase), **ONTO_THE_NEW_BASE)
        rebase.assert_called_once()
        _assert_published_once(self, world.FIXED_HEAD, handed)
        refreshed = self.drift(world.reported(FRESH_REPORT), committed=False, **ON_THE_REBASED_HEAD)
        return refreshed[RUN_AGENT].call_args.args[1]

    @contextlib.contextmanager
    def _loses_the_post(self):
        """GitHub takes the report's post and the response never comes back."""
        self.github.report_failures.lost.add(conflict.PR)
        yield
        self.github.report_failures.lost.clear()

    def _assert_reviewed_once(self, handed: str) -> None:
        """The reconciliation, then a reviewer handed the one saved report, over one round reported once."""
        self.reconcile()
        reviewed = self.drift(REVIEW_REPLY, committed=False)

        self.assertIn(world.REPORT_TEXT, reviewed[RUN_AGENT].call_args.args[1])
        _assert_published_once(self, world.FIXED_HEAD, handed)
        rounds = [event for event in self.github.recorded_events if event["event"] == CONFLICT_ROUND]
        self.assertEqual([event[CONFLICT_ROUND] for event in rounds], [1])
        pinned = self.pinned()
        self.assertEqual(pinned[CONFLICT_ROUND], 1)
        self.assertEqual(pinned[AGENT_RUNS_USED], 2)
        self.assertIsNone(pinned.get(PARK_REASON))



class ResolvingConflictReportRefreshTest(
    unittest.TestCase, conflict._ConflictDriftReportMixin,
):
    """What may move past a report a crash left unsettled as it was bound.

    The base refresh a tick runs ahead of dispatch may not: a rebase it pushed
    would leave the report to be bound to a head it never described -- paying
    that head's debt and reaching the reviewer as its account. It holds still
    instead, the hold settles the report about the head it was written over,
    and only then may the refresh rewrite.

    A later change to the requirements may, and has to. The saved report is
    then an account of requirements the issue no longer has, which the
    reconciliation defers for good, so the edit's resume runs ahead of its
    settlement and the report that resume writes is the one published.
    """

    def test_the_refresh_waits_for_the_saved_report(self) -> None:
        self.seeded_on_conflict()
        handed = self.handed()
        with self.dying_at_the_binding():
            self.drift(world.reported())
        self.assertEqual(self.github.label_history, [(conflict.ISSUE, WorkflowLabel.VALIDATING)])
        self.assertIsNotNone(self.records()[DELIVERED])

        self.refreshes().assert_not_called()
        reviewed = self.drift(REVIEW_REPLY, committed=False)

        self.assertIn(world.REPORT_TEXT, reviewed[RUN_AGENT].call_args.args[1])
        _assert_published_once(self, world.FIXED_HEAD, handed)
        self.refreshes().assert_called_once()

    def test_an_edit_replaces_the_saved_report(self) -> None:
        # A report-only answer is saved and the process ends as it is bound;
        # then the requirements move again. Held in front of the edit, the
        # saved report would keep back the one resume that replaces it, tick
        # after tick. Answered first, the edit resumes the developer once, its
        # report is the one published, and the saved one never goes out.
        self.seeded_on_conflict()
        with self.dying_at_the_binding():
            self.drift(world.reported(), committed=False)
        world.edits(self, LATER_BODY)
        handed = self.handed()

        resumed = self.drift(world.reported(world.LATER_REPORT_TEXT), committed=False)

        resumed[RUN_AGENT].assert_called_once()
        current = self.records()[CURRENT].subject
        self.assertEqual((current.source_sha, current.requirements_revision), (world.PUBLISHED_HEAD, handed))
        self.assertEqual(len(self.published_reports(world.LATER_REPORT_TEXT)), 1)
        self.assertEqual(self.published_reports(), [])
        self.assertIsNone(self.pinned().get(PARK_REASON))


class ResolvingConflictSavedCandidateTest(
    unittest.TestCase, conflict._ConflictDriftReportMixin,
):
    """A saved report goes out with the commit it describes, or not at all.

    A body edit's resume recorded its report and died before its push, or past
    it on the relabel behind it, and the checkout is no longer on the commit
    that report describes -- or answered
    with a report alone left unsettled, and the checkout has gained a commit
    since. Neither the recovered push nor the binding ahead of a rebase may
    carry the report onto the head the checkout stands on now: the issue parks
    for the report that head is owed, the record naming the saved candidate
    stays, and the reply that answers the park publishes the branch as it
    stands under a report of it. A report whose run left a head nobody could
    read names no candidate, so it is never saved at all.
    """

    def test_a_saved_report_keeps_its_candidate(self) -> None:
        # A push that landed counted its round ahead of the relabel it lost,
        # and the tick that refuses the commit gained since counts nothing.
        for shape, checkout, pushed in KEPT_CANDIDATES:
            with self.subTest(shape=shape):
                rebase = self._parked_off_the_candidate(checkout, pushed=pushed)

                rebase.assert_not_called()
                pinned = self.pinned()
                self.assertEqual(
                    (pinned[PARK_REASON], pinned[SAVED_CANDIDATE], pinned[CONFLICT_ROUND]),
                    (_report_delivery.UNDELIVERABLE_REPORT, world.FIXED_HEAD, int(pushed)),
                )
                self.assertIsNotNone(self.records()[DELIVERED])
                self.assertEqual(self.github.label_history, [])

    def test_the_reply_reports_the_moved_head(self) -> None:
        moved_on = dict(OFF_THE_CANDIDATE)["moved on ahead of the remote"]
        self._parked_off_the_candidate(moved_on)
        world.human_reply(self)

        answered = self.drift(world.reported(world.LATER_REPORT_TEXT), **moved_on)

        answered[PUSH_BRANCH].assert_called_once()
        pending = self.records()[PENDING]
        self.assertEqual(
            (pending.subject.source_sha, pending.report),
            (MOVED_ON_HEAD, world.LATER_REPORT_TEXT),
        )
        self.assertEqual(self.published_reports(), [])

    def test_a_report_alone_replaces_the_candidate(self) -> None:
        # The checkout is back on the head the pull request carries, and the
        # reply's run reports it without a commit; the process ends as that
        # report is bound. The very write that saved this report names the
        # head it is about in place of the candidate the earlier report was
        # about, so the next tick settles the report it finds rather than
        # parking it as the account of a commit it never described.
        put_back = dict(OFF_THE_CANDIDATE)["put back on the published head"]
        self._parked_off_the_candidate(put_back)
        world.human_reply(self)
        with self.dying_at_the_binding():
            self.drift(world.reported(world.LATER_REPORT_TEXT), **put_back)
        self.assertEqual(self.pinned().get(SAVED_CANDIDATE), world.PUBLISHED_HEAD)

        recovered = self.drift([], **put_back)

        recovered[RUN_AGENT].assert_not_called()
        recovered[PUSH_BRANCH].assert_not_called()
        pinned = self.pinned()
        self.assertEqual(
            (pinned.get(PARK_REASON), pinned.get(SAVED_CANDIDATE)),
            (None, world.PUBLISHED_HEAD),
        )
        self.assertEqual(self.records()[CURRENT].subject.source_sha, world.PUBLISHED_HEAD)
        self.assertEqual(len(self.published_reports(world.LATER_REPORT_TEXT)), 1)

    def test_a_report_alone_keeps_its_head(self) -> None:
        # A report-only answer is left unsettled -- its binding cut short,
        # bound with the post not yet made, or never recorded because nothing
        # could read the head its run left -- and the checkout then gains a
        # commit nobody published. The report is held to the head it was
        # saved or bound over, or there is none to hold, so the recovered push
        # neither sends that commit under it nor moves the pull request off
        # the head it describes: the issue parks for a human, and later ticks
        # push, launch, charge, and count nothing. The reply to that park
        # publishes the commit once, under the report it writes, and the
        # first report never goes out.
        for unsettled in REPORT_ALONE_UNSETTLED:
            with self.subTest(window=unsettled[0]):
                self._parked_on_a_report_alone(*unsettled)
                world.human_reply(self)

                answered = self.drift(world.reported(world.LATER_REPORT_TEXT), **world.STRANDED)
                self.reconcile()

                answered[PUSH_BRANCH].assert_called_once()
                self.assertEqual(self.records()[CURRENT].subject.source_sha, world.FIXED_HEAD)
                self.assertEqual(len(self.published_reports(world.LATER_REPORT_TEXT)), 1)
                self.assertEqual(self.published_reports(), [])

    def test_an_ack_keeps_the_candidate(self) -> None:
        # An `ACK:` saves no report, so the record stays beside the earlier
        # report it is about, and the next tick parks that report again
        # rather than binding it to the head the checkout was put back on.
        put_back = dict(OFF_THE_CANDIDATE)["put back on the published head"]
        self._parked_off_the_candidate(put_back)
        world.human_reply(self)
        self.drift(ACK_REPLY, **put_back)

        self.drift([], **put_back)[RUN_AGENT].assert_not_called()

        pinned = self.pinned()
        self.assertEqual(
            (pinned[PARK_REASON], pinned[SAVED_CANDIDATE]),
            (_report_delivery.UNDELIVERABLE_REPORT, world.FIXED_HEAD),
        )
        self.assertEqual(self.published_reports(), [])

    def _parked_on_a_report_alone(self, window: str, owed: tuple, saved: str | None) -> None:
        """A report alone left unsettled `window`'s way, then two ticks over a commit gained since.

        Neither tick pushes, launches, charges, counts, or relabels anything,
        and the issue stands parked for its report with `owed` outstanding and
        `saved` the head the conflict-resume record names.
        """
        self.seeded_on_conflict()
        if window == OVER_AN_UNREAD_HEAD:
            self.drift(world.reported(), committed=False, **conflict.UNREAD_HEAD)
        else:
            cut_short = (
                patch.object(_report_publishing, "finishes", return_value=True)
                if window == ONCE_IT_IS_BOUND else self.dying_at_the_binding()
            )
            with cut_short:
                self.drift(world.reported(), committed=False)
        charged = self.pinned()[AGENT_RUNS_USED]
        for _ in range(2):
            ticked = self.drift([], **world.STRANDED)
            ticked[PUSH_BRANCH].assert_not_called()
            ticked[RUN_AGENT].assert_not_called()
        pinned = self.pinned()
        self.assertEqual(
            (pinned[PARK_REASON], pinned.get(SAVED_CANDIDATE), pinned[CONFLICT_ROUND], pinned[AGENT_RUNS_USED]),
            (_report_delivery.UNDELIVERABLE_REPORT, saved, 0, charged),
        )
        recorded = self.records()
        self.assertEqual(
            tuple(key for key in (DELIVERED, PENDING) if recorded[key]),
            owed,
        )
        self.assertEqual(self.github.label_history, [])

    def _parked_off_the_candidate(self, checkout, *, pushed: bool = False) -> MagicMock:
        """A crash before the push, or `pushed` on its relabel, then a tick off the candidate; the rebase seam."""
        rebase = MagicMock(return_value=conflict.REBASED_CLEANLY)
        self.seeded_on_conflict()
        crash = crashes.dying_before_the_relabel(self) if pushed else crashes.dying_before_the_publication()
        with crash:
            self.drift(world.reported())
        ticked = self.drift([], base=conflict.behind_its_base(rebase), **checkout)
        ticked[PUSH_BRANCH].assert_not_called()
        return rebase


if __name__ == "__main__":
    unittest.main()
