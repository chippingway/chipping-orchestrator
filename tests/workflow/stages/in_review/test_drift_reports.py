# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a requirements-drift resume on an approved pull request does with its report.

A commit answering the edit and a report alone both publish the report the
session wrote and send the issue back to `validating` with a fresh round, since
the approval that carried it here was earned against the old requirements. A
push that does not land keeps the report recorded, and the issue parked where
it is for that tick; the next one hands it to `validating` before anything here
can act on the stale approval, and so does a tick that died mid-way -- on the
report it owes, or, where the reply recorded none, on the marker the move
itself left. A resume that answered the edit with nothing at all -- a question
-- owes the same move, and the comment a human wrote while it was out is still
there for the road that answers it. A publication such a hand-back still owes
lands on `validating` without spending a round: the fresh budget is what the
edit that produced it has already bought. That holds however long it takes to
land -- a push retried after one that failed, and a publication a reply paying
none of the debt came before.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import report_delivery as _report_delivery
from orchestrator.workflow.stages.in_review import drift as _drift
from tests.workflow import drift_reports as world
from tests.workflow.fixtures import LABEL_IN_REVIEW, LABEL_VALIDATING, _agent

ISSUE = 1_795

PR = 17_950

PUSH_BRANCH = "_push_branch"

REVIEW_ROUND = "review_round"

RUN_AGENT = "run_agent"

DELIVERED = "delivered"

PARK_REASON = "park_reason"

# What a reviewer that ran says: no verdict, so it parks and nothing else runs.
REVIEW_REPLY = "Looked it over."

READY_PING = "is ready for review/merge"

# The reply that records no report at all, and the marker that is then the
# only thing saying this issue owes `validating` a label move.
ACK_REPLY = "ACK: the pushed commit already covers the edit."

# What a resume that answers the edit with nothing says, and the pinned key
# saying how far this stage has read the issue thread.
QUESTION_REPLY = "Should the new criterion replace the old one or sit beside it?"

PR_LAST_COMMENT_ID = "pr_last_comment_id"

HANDOFF_PENDING = "in_review_handoff_pending"

# The rounds a nearly spent review budget has left, which an edit to the
# requirements must not hand the next reviewer.
SPENT_ROUNDS = 2

# The two things a silent retry finds on the branch a killed resume left.
_NOTHING_TO_PUSH = "nothing to push"

_A_COMMIT_TO_PUSH = "a commit to push"

# The two roads out of `in_review` that move the label, by the tick they die on.
_DRIFT_TICK = "the drift tick"

_HAND_BACK = "the hand-back"

# The final-docs handoff the approval left on the head the edit landed on,
# which is all the ready ping asks of a mergeable pull request.
READY_TO_PING = MappingProxyType({
    "docs_checked_sha": world.PUBLISHED_HEAD,
    "docs_verdict": "updated",
})


class InReviewDriftReportTest(unittest.TestCase, world._DriftReportMixin):
    def test_a_reported_resume_goes_back_to_review(self) -> None:
        # With a commit or without one, the session's report reaches the pull
        # request about the head it now stands on, and the stale approval is
        # dropped on the way back to `validating`.
        for committed, head in (
            (True, world.FIXED_HEAD), (False, world.PUBLISHED_HEAD),
        ):
            with self.subTest(committed=committed):
                self.seeded(ISSUE, PR, LABEL_IN_REVIEW, review_round=2)
                handed = world.handed_revision(self.issue)

                mocks = self.drift(world.reported(), committed=committed)

                self.assertEqual(mocks[PUSH_BRANCH].called, committed)
                self.assertEqual(len(self.published_reports()), 1)
                subject = self.records()["current"].subject
                self.assertEqual(
                    (subject.source_sha, subject.requirements_revision),
                    (head, handed),
                )
                self.assertEqual(
                    (self.github.label_history, self.pinned()[REVIEW_ROUND]),
                    ([(ISSUE, LABEL_VALIDATING)], 0),
                )

    def test_a_failed_run_still_owes_the_move(self) -> None:
        # A run that exits nonzero records no report -- a failure is not a
        # developer declining to report -- but the commit it left is
        # published all the same, so the head the reviewer approved is gone.
        # The refreshed hash goes durable with that publication, so no later
        # tick re-detects the edit: if the move this issue owes is not
        # durable beside them, the approval stands over a head nobody read
        # and the ping calls it ready.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, **READY_TO_PING)

        with patch.object(
            _drift, "_relabels_for_review", side_effect=RuntimeError("died"),
        ), self.assertRaises(RuntimeError):
            self.drift(_agent(session_id=world.DEV_SESSION, exit_code=1))

        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)
        self.assertEqual(set(self.records().values()), {None})
        self.assertTrue(self.pinned()[HANDOFF_PENDING])
        _assert_handed_back(self)

    def test_a_death_mid_push_keeps_the_delivery_mark(self) -> None:
        # The report goes onto the comment before the push and the process
        # dies in the push, so the record is durable. The mark saying how far
        # this tick read has to be durable beside it: carried only after the
        # disposition, it dies with the tick, and everything this run was
        # handed -- the notice it posted, and any PR comment its prompt
        # quoted -- reads as unread the next time the issue is in review,
        # buying a `fixing` round for words the developer already answered.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, **READY_TO_PING)

        with self.assertRaises(RuntimeError):
            self.drift(world.reported(), push_branch=_dies)

        self.assertIsNotNone(self.records()[DELIVERED])
        self.assertGreaterEqual(
            self.pinned()[PR_LAST_COMMENT_ID],
            self.pull_request.issue_comments[-1].id,
        )

    def test_a_failed_push_keeps_report_and_label(self) -> None:
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW)

        self.drift(world.reported(), push_branch=False)

        self.assertEqual(self.records()[DELIVERED].report, world.REPORT_TEXT)
        self.assertEqual(self.published_reports(), [])
        self.assertEqual(self.github.label_history, [])


class InReviewReportDebtTest(unittest.TestCase, world._DriftReportMixin):
    """A report the drift tick recorded and did not settle, a tick or more later.

    Whatever stopped it -- a push that failed, or a process that died between
    the record and the relabel -- the next `in_review` tick hands the issue to
    `validating` before feedback, drift, or the ready ping: the approval this
    label stands on is stale, and only `validating` binds the report.
    """

    def test_a_failed_push_is_recovered_on_validating(self) -> None:
        # The push fails and the drift tick parks on `in_review`. The next
        # tick hands the issue on without pinging; `validating` retries the
        # push silently, then binds and settles the recorded report and only
        # then runs the reviewer -- one report, and no second developer run.
        # The retry lands the publication the edit already bought a fresh
        # budget for, so it spends none of it: counted there, a push that
        # failed once would leave its reviewer a round short of the same
        # push landing first time.
        self.seeded(
            ISSUE, PR, LABEL_IN_REVIEW,
            review_round=SPENT_ROUNDS, **READY_TO_PING,
        )
        self.drift(world.reported(), push_branch=False)

        _assert_handed_back(self)
        self.drift(REVIEW_REPLY, committed=False)
        self.assertEqual(
            (self.pull_request.head.sha, self.pinned()[REVIEW_ROUND]),
            (world.FIXED_HEAD, 0),
        )

        reviewed = self.drift(REVIEW_REPLY, committed=False)

        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(
            self.records()["current"].subject.source_sha, world.FIXED_HEAD,
        )
        self.assertEqual(reviewed[RUN_AGENT].call_args[0][0], config.REVIEW_AGENT)

    def test_a_death_before_the_push_pings_nobody(self) -> None:
        # The report is durable and the process dies before anything is
        # published. The pull request still stands on the approved head, but
        # the approval is stale: the next tick hands the issue on rather than
        # pinging, and `validating` refuses to bind the report to a head its
        # checkout is not on.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, **READY_TO_PING)
        with self.assertRaises(RuntimeError):
            self.drift(world.reported(), push_branch=_dies)
        self.assertIsNotNone(self.records()[DELIVERED])

        _assert_handed_back(self)
        held = self.drift(REVIEW_REPLY, head_shas=(world.FIXED_HEAD,))

        held[RUN_AGENT].assert_not_called()
        self.assertEqual(
            self.pinned().get(PARK_REASON), _report_delivery.UNDELIVERABLE_REPORT,
        )

    def test_a_death_before_the_relabel_is_reviewed(self) -> None:
        # The push landed and the process died before the relabel, with the
        # report recorded and unbound. The next tick hands the issue on, and
        # `validating` binds and settles the report before its reviewer runs.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, **READY_TO_PING)
        with patch.object(
            self.github, "set_workflow_label", side_effect=RuntimeError("died"),
        ), self.assertRaises(RuntimeError):
            self.drift(world.reported())
        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)

        _assert_handed_back(self)
        reviewed = self.drift(REVIEW_REPLY, committed=False)

        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(reviewed[RUN_AGENT].call_args[0][0], config.REVIEW_AGENT)

    def test_a_death_on_the_relabel_keeps_the_round(self) -> None:
        # The label moves last, behind the write that resets the round, so a
        # tick that dies the moment the relabel lands leaves the fresh budget
        # durable: the reviewer that runs on the other side of it reads the
        # rounds the edited requirements are owed rather than the one the
        # stale approval had left. Both roads out of here are asked.
        for path in (_DRIFT_TICK, _HAND_BACK):
            with self.subTest(dies_in=path):
                self.seeded(
                    ISSUE, PR, LABEL_IN_REVIEW,
                    review_round=SPENT_ROUNDS, **READY_TO_PING,
                )
                if path == _HAND_BACK:
                    self.drift(world.reported(), push_branch=False)

                with _RelabelsThenDies(self), self.assertRaises(RuntimeError):
                    self.drift(world.reported(), committed=path == _DRIFT_TICK)

                self.assertEqual(
                    (self.github.label_history[-1:], self.pinned()[REVIEW_ROUND]),
                    ([(ISSUE, LABEL_VALIDATING)], 0),
                )
                self.assertIsNotNone(self.records()[DELIVERED])

    def test_a_handed_back_debt_spends_no_round(self) -> None:
        # The resume committed and reported nothing, so nothing was published
        # and the debt is all that stands. The hand-back gives the edited
        # requirements a fresh budget, and the reply that finally brings the
        # report publishes that same commit on `validating` -- the
        # publication the edit earned the budget for, so it spends none of
        # it. Counted there, an edit answered a tick late would leave its
        # reviewer one round short of the edit answered at once.
        self.seeded(
            ISSUE, PR, LABEL_IN_REVIEW,
            review_round=SPENT_ROUNDS, **READY_TO_PING,
        )
        self.drift("fixed the criteria")

        _assert_handed_back(self)
        world.human_reply(self)
        self.drift(world.reported(), **world.STRANDED)
        self.reconcile()

        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(
            (self.pull_request.head.sha, self.pinned()[REVIEW_ROUND]),
            (world.FIXED_HEAD, 0),
        )
        # The budget the edit bought is spent by the reviewers that read it,
        # so the record of it ends with the debt rather than outliving it.
        self.assertIsNone(self.pinned()[_report_delivery.OWED_ROUND_RESET])

    def test_an_ack_keeps_the_owed_budget(self) -> None:
        # The first reply to that debt only says `ACK:`, which pays none of
        # it: the commit stays withheld for the report it owes, so the
        # publication the hand-back reset the budget for has still not
        # happened. Read as the end of the edit, the `ACK:` would drop the
        # record of that reset, and the reply that finally publishes would
        # spend a round the edit had already bought back.
        self.seeded(
            ISSUE, PR, LABEL_IN_REVIEW,
            review_round=SPENT_ROUNDS, **READY_TO_PING,
        )
        self.drift("fixed the criteria")
        # The hand-back is setup here; what asserts it is
        # `test_a_handed_back_debt_spends_no_round`.
        self.drift(REVIEW_REPLY, committed=False)
        world.human_reply(self)

        self.drift(ACK_REPLY, **world.STRANDED)[PUSH_BRANCH].assert_not_called()

        self.assertTrue(self.pinned()[_report_delivery.OWED_ROUND_RESET])
        _assert_the_report_publishes_free(self)

    def test_an_ack_whose_relabel_failed_is_remade(self) -> None:
        # An `ACK:` records no report, so a relabel that never lands leaves
        # nothing else on the comment to recognise the debt by -- no drift to
        # re-detect, and a ready ping one tick away on an approval the edit
        # made stale. The marker written beside the fresh round is what the
        # next tick reads, and it remakes the move before anything else runs.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, **READY_TO_PING)

        with patch.object(
            self.github, "set_workflow_label", side_effect=RuntimeError("died"),
        ), self.assertRaises(RuntimeError):
            self.drift(ACK_REPLY, committed=False)

        self.assertTrue(self.pinned()[HANDOFF_PENDING])
        self.assertEqual(set(self.records().values()), {None})
        _assert_handed_back(self)
        self.assertIsNone(self.pinned()[HANDOFF_PENDING])


class InReviewParkedDriftTest(unittest.TestCase, world._DriftReportMixin):
    """A drift resume that answered the edit with nothing, and the tick after.

    A question parks with no report recorded, so nothing the pinned comment
    carries would otherwise say this label owes a move -- and the approval it
    stands on was earned against requirements that are gone. The marker the
    park leaves is what sends the issue back before the feedback scan, the
    drift check, or the ready ping can act on it, and `validating` reads the
    answer as the rest of that resume.
    """

    def test_a_question_hands_the_approval_back(self) -> None:
        # The resume asked rather than answered, so the edit stands and the
        # approval is stale with nothing recorded to say so. The next tick
        # hands the issue on instead of pinging a mergeable head as ready,
        # and the answer is read on `validating` as the rest of the drift
        # resume: its report is published, on the budget the edit bought.
        self.seeded(
            ISSUE, PR, LABEL_IN_REVIEW,
            review_round=SPENT_ROUNDS, **READY_TO_PING,
        )

        self.drift(QUESTION_REPLY, committed=False)

        self.assertEqual(self.github.label_history, [])
        _assert_handed_back(self)
        world.human_reply(self, "replace the old criterion")
        self.drift(world.reported(), committed=False)

        self.assertEqual(len(self.published_reports()), 1)
        self.assertEqual(self.pinned()[REVIEW_ROUND], 0)

    def test_a_recovered_timeout_ends_the_owed_budget(self) -> None:
        # The resume was killed by its own timeout, so the edit is answered
        # with nothing and the hand-back gives the requirements a fresh
        # budget for whatever that park still owes. The silent retry on
        # `validating` is what answers it -- pushing the commit the kill left
        # behind, or reading the branch and finding none -- so the record of
        # that reset comes down with the park. Left standing, the next
        # unrelated publication this stage owes would spend nothing.
        for retry, options in (
            (_NOTHING_TO_PUSH, {
                "head_shas": (world.PUBLISHED_HEAD,), "committed": False,
            }),
            (_A_COMMIT_TO_PUSH, dict(world.STRANDED)),
        ):
            with self.subTest(retry=retry):
                self.seeded(
                    ISSUE, PR, LABEL_IN_REVIEW,
                    review_round=SPENT_ROUNDS, **READY_TO_PING,
                )
                self.drift(
                    _agent(session_id=world.DEV_SESSION, timed_out=True),
                    committed=False,
                )
                # Setup again: `InReviewReportDebtTest` is what asserts it.
                self.drift(REVIEW_REPLY, committed=False)

                self.drift(REVIEW_REPLY, **options)

                self.assertIsNone(
                    self.pinned()[_report_delivery.OWED_ROUND_RESET],
                )

    def test_a_comment_mid_run_outlives_the_park(self) -> None:
        # A human writes while the agent is out and the resume comes back
        # with a question. The park notice lands above that comment, so a
        # mark taken from the thread's tip would skip it for good. The
        # ratchet stops at what this tick actually read instead, and the
        # comment is still there for the resume that answers the park --
        # which is where the report the edit is owed finally comes from.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, **READY_TO_PING)

        self.drift(self.mid_run("comment", QUESTION_REPLY), committed=False)

        self.assertLess(
            self.pinned()[PR_LAST_COMMENT_ID], world.LATER_COMMENT_ID,
        )
        # Setup: `test_a_question_hands_the_approval_back` asserts the move.
        self.drift(REVIEW_REPLY, committed=False)
        answered = self.drift(world.reported(), committed=False)

        answered[RUN_AGENT].assert_called_once()
        self.assertEqual(len(self.published_reports()), 1)


def _assert_the_report_publishes_free(case) -> None:
    """The debt holds the review, and the report pays for it with no round."""
    case.drift(REVIEW_REPLY, head_shas=(world.FIXED_HEAD,))
    world.human_reply(case)
    case.drift(world.reported(), **world.STRANDED)
    case.reconcile()
    case.assertEqual(len(case.published_reports()), 1)
    case.assertEqual(
        (case.pull_request.head.sha, case.pinned()[REVIEW_ROUND]),
        (world.FIXED_HEAD, 0),
    )


def _assert_handed_back(case) -> None:
    """One `in_review` tick: back to `validating`, no ping, nothing run."""
    mocks = case.drift(REVIEW_REPLY, committed=False)
    mocks[RUN_AGENT].assert_not_called()
    case.assertFalse(any(
        READY_PING in body for _, body in case.github.posted_comments
    ))
    case.assertEqual(
        (case.github.label_history[-1:], case.pinned()[REVIEW_ROUND]),
        ([(ISSUE, LABEL_VALIDATING)], 0),
    )


class _RelabelsThenDies:
    """A relabel that lands, and a process that gets no further than that."""

    def __init__(self, case) -> None:
        self._case = case
        self._relabel = case.github.set_workflow_label
        self._patch = patch.object(
            case.github, "set_workflow_label", side_effect=self,
        )

    def __call__(self, *args, **kwargs):
        self._relabel(*args, **kwargs)
        raise RuntimeError("the process died on the relabel")

    def __enter__(self):
        return self._patch.__enter__()

    def __exit__(self, *closing):
        return self._patch.__exit__(*closing)


def _dies(*_args, **_kwargs):
    """A push the process never returns from."""
    raise RuntimeError("the process died before the push")
