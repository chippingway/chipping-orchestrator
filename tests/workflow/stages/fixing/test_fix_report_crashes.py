# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round's report, and the process that ended before it was handed on.

The round writes its report durably ahead of the size gate and the relabel to
`validating` comes after the push, so a process dying anywhere past that write
leaves the same shape: `workflow:fixing` still on the issue, nobody being
waited for, the reply that round answered still unread because a reporting
round's readers ride the report, and a report nothing has published. The next
tick FINISHES that round rather than repeating it -- the rescan behind it would
read the reply as fresh feedback and resume a developer, charging another run
and writing a second report over the first.

Finishing it is the publication the round may still owe and then the hand-back.
A commit the crash caught before the gate goes out the way every other one
does, spending the round frozen on the record; a candidate over the ceiling is
held for the adjudication; and a checkout that can vouch for nothing holds the
whole thing for a human, because "nothing was stranded" is the same answer the
probe gives a worktree that is gone. Only past all of that does `validating`
get the report, and only there is a delivery bound and settled.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow import (
    drift_reports as _drift_world,
    fix_report_crashes as crashes,
    fix_reports as world,
)
from tests.workflow.fixtures import LABEL_DECOMPOSING, LABEL_VALIDATING

ISSUE = 1_794

PR = 17_940

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

REVIEW_ROUND = "review_round"

REVIEWER_ANCHOR = "pending_fix_reviewer_comment_id"

PR_LAST_COMMENT_ID = "pr_last_comment_id"

CURRENT = "current"

DELIVERED = "delivered"

# The reviewer-feedback comment the direct round bookmarks as its lone replay
# anchor, which a handover nothing confirmed may not drop.
REVIEWER_COMMENT_ID = 1_002

# A ceiling one line below what the crashed round committed, for the recovery
# whose candidate the gate refuses to publish as one change.
_CEILING = "MAX_ADDED_LINES"

_ONE_LINE = 1

_TWO_LINES = 2

# What a checkout the crash left behind cannot say. Both readings that could
# have vouched for the branch refuse -- a fetch that never returned, and a
# divergence git would not count -- which is the shape an absent or unreadable
# worktree presents to every probe that asks about it.
_LOST_CHECKOUTS = (
    ("the fetch never returned", {"authed_fetch_result": world.REFUSED_FETCH}),
    ("the divergence would not read", {"branch_divergence_readable": False}),
)


class CrashedFixRoundTest(unittest.TestCase, world._FixReportMixin):
    """The tick that finds a report a round recorded and never handed on."""

    def test_a_crash_before_relabel_resumes_nobody(self) -> None:
        # The window the report's own write opens, and the one only this stage
        # can answer: the report is written durably ahead of the size gate, the
        # resume has cleared the park, and the process ends before the relabel.
        # What is left is `workflow:fixing`, nobody being waited for, the reply
        # that round answered still unread, and a delivered report nothing has
        # published -- which the rescan would read as fresh feedback and resume
        # the developer over, charging another run and writing a second report.
        # Recognised instead, the issue is handed to `validating` with no
        # developer run, and the report hold there settles the delivery and the
        # round it froze.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)
        answered = max(reply.id for reply in self.issue.comments)

        with crashes.dying_before_the_relabel(self):
            self.parked_resume(world.reported(), committed=False)

        self.assertEqual(
            (self.pinned()[AWAITING_HUMAN],
             self.pinned().get(PR_LAST_COMMENT_ID),
             self.records()[DELIVERED] is None),
            (False, 0, False),
        )
        handed = self.parked_resume(world.reported(), committed=False)

        handed["run_agent"].assert_not_called()
        self.assertEqual(self.github.label_history[-1], (ISSUE, LABEL_VALIDATING))
        self.reviewed()
        self.assertEqual(
            (len(self.published_reports()), _round(self),
             self.pinned().get(PR_LAST_COMMENT_ID)),
            (1, 1, answered),
        )


    def test_a_crash_before_the_push_publishes_first(self) -> None:
        # The earlier window, where the report is recorded and the commit it
        # describes is still in the checkout. Handed straight on from there,
        # `validating` would be asked to bind a report about work the pull
        # request has not got, and the only answer it has to that is a park.
        # So the candidate goes out the way every other one does -- through the
        # gate, leased to the head the pull request is standing on -- and the
        # hand-back follows the publication rather than replacing it.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)
        answered = max(reply.id for reply in self.issue.comments)

        with crashes.dying_before_the_publication():
            self.parked_resume(world.reported())

        handed = self.parked_resume(world.reported(), **_drift_world.STRANDED)

        handed["run_agent"].assert_not_called()
        handed[PUSH_BRANCH].assert_called_once()
        # The commit reached the pull request, so this handover's round was
        # spent by that push rather than by the settlement behind it, and
        # nobody is left waiting for a human.
        self.assertEqual(_handover(self), (1, False))
        self.reviewed()
        self.assertEqual(
            (self.records()[CURRENT].subject.source_sha,
             self.pinned().get(PR_LAST_COMMENT_ID)),
            (world.FIXED_HEAD, answered),
        )


    def test_a_crash_over_a_lost_checkout_holds(self) -> None:
        # The same window with the checkout gone under it. Nothing is stranded
        # that anything could prove, and "nothing stranded" is the answer this
        # probe also gives a worktree that vouches for nothing -- so read as a
        # clean hand-back the report would go to `validating`, whose binding
        # recreates a lost checkout from the remote, finds its head equal to
        # the receipt, and publishes the report of a commit that never passed
        # the gate against the head the pull request had all along. Held
        # instead: nothing pushed, nothing published, the record intact, and a
        # human asked.
        for refusal, lost in _LOST_CHECKOUTS:
            with self.subTest(checkout=refusal):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.requested_fix(world.QUESTION_REPLY, committed=False)
                world.replied(self)

                with crashes.dying_before_the_publication():
                    self.parked_resume(world.reported())

                held = self.parked_resume(
                    world.reported(), **{**_drift_world.STRANDED, **lost},
                )

                held[PUSH_BRANCH].assert_not_called()
                self.reviewed()
                self.assertEqual(
                    (self.pull_request.head.sha, len(self.published_reports()),
                     self.pinned()[PARK_REASON]),
                    (world.PUBLISHED_HEAD, 0,
                     _report_delivery.UNDELIVERABLE_REPORT),
                )


    def test_a_crash_the_gate_holds_hands_on_nothing(self) -> None:
        # The recovery publishes through the gate rather than around it, so a
        # candidate over the ceiling is held exactly as one a round pushed for
        # itself would be: the issue goes to the adjudication, and the
        # hand-back does not happen, because relabelling for a reviewer would
        # publish the very question the gate has just opened.
        # Seeded off the DIRECT round, because the window belongs to neither
        # road: what either leaves is `workflow:fixing` with a report written
        # and a commit nobody published, and this tick is what reads it.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        with crashes.dying_before_the_publication():
            self.requested_fix(world.reported())

        with patch.object(config, _CEILING, _ONE_LINE):
            held = self.parked_resume(
                world.reported(), added_lines=_TWO_LINES, **_drift_world.STRANDED,
            )

        held[PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            self.github.label_history[-1], (ISSUE, LABEL_DECOMPOSING),
        )


    def test_a_crash_before_binding_charges_nothing(self) -> None:
        # The window the relabel opens: the label is on `validating` and the
        # process dies before the report is bound. Nothing of the handover was
        # durable, so the round is unspent and the anchor intact -- and the
        # review hold on `validating` is what finishes the transaction, which
        # is where the round is finally spent.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)

        with crashes.dying_before_the_settlement():
            self.parked_resume(world.reported(), committed=False)

        self.assertEqual(
            (_round(self), self.pinned().get(REVIEWER_ANCHOR)),
            (0, REVIEWER_COMMENT_ID),
        )
        self.assertIsNotNone(self.records()[DELIVERED])
        self.reviewed()
        self.assertEqual(
            (_round(self), len(self.published_reports())),
            (1, 1),
        )


def _handover(case) -> tuple:
    """The round a handover spent, and whether it left a human waiting."""
    return case.pinned()[REVIEW_ROUND], case.pinned()[AWAITING_HUMAN]


def _round(case) -> int:
    """The reviewer round this issue's pinned comment says it has spent."""
    return case.pinned()[REVIEW_ROUND]
