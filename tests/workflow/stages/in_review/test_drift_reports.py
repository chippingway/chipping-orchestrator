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
itself left. A publication such a hand-back still owes lands on `validating`
without spending a round: the fresh budget is what the edit that produced it
has already bought.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow import drift_reports as world
from tests.workflow.fixtures import LABEL_IN_REVIEW, LABEL_VALIDATING

ISSUE = 1_795

PR = 17_950

PUSH_BRANCH = "_push_branch"

REVIEW_ROUND = "review_round"

RUN_AGENT = "run_agent"

PARK_REASON = "park_reason"

# What a reviewer that ran says: no verdict, so it parks and nothing else runs.
REVIEW_REPLY = "Looked it over."

READY_PING = "is ready for review/merge"

# The reply that records no report at all, and the marker that is then the
# only thing saying this issue owes `validating` a label move.
ACK_REPLY = "ACK: the pushed commit already covers the edit."

HANDOFF_PENDING = "in_review_handoff_pending"

# The rounds a nearly spent review budget has left, which an edit to the
# requirements must not hand the next reviewer.
SPENT_ROUNDS = 2

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

    def test_a_failed_push_keeps_report_and_label(self) -> None:
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW)

        self.drift(world.reported(), push_branch=False)

        self.assertEqual(self.records()["delivered"].report, world.REPORT_TEXT)
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
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, **READY_TO_PING)
        self.drift(world.reported(), push_branch=False)

        self._assert_handed_back()
        self.drift(REVIEW_REPLY, committed=False)
        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)

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
        self.assertIsNotNone(self.records()["delivered"])

        self._assert_handed_back()
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

        self._assert_handed_back()
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
                self.assertIsNotNone(self.records()["delivered"])

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

        self._assert_handed_back()
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
        self._assert_handed_back()
        self.assertIsNone(self.pinned()[HANDOFF_PENDING])

    def _assert_handed_back(self) -> None:
        """One `in_review` tick: back to `validating`, no ping, nothing run."""
        mocks = self.drift(REVIEW_REPLY, committed=False)
        mocks[RUN_AGENT].assert_not_called()
        self.assertFalse(any(
            READY_PING in body for _, body in self.github.posted_comments
        ))
        self.assertEqual(
            (self.github.label_history[-1:], self.pinned()[REVIEW_ROUND]),
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
