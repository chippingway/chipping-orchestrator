# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round's report, and the process that ended before it was handed on.

The round writes its report durably ahead of the size gate and the relabel to
`validating` comes last of all, so a process dying anywhere past that write
leaves the same shape: `workflow:fixing` still on the issue, nobody being
waited for, the reply that round answered still unread because a reporting
round's readers ride the report, and a report nothing has handed on. The next
tick FINISHES that round rather than repeating it -- the scan behind it would
read the reply as fresh feedback and resume a developer, charging another run
and writing a second report over the first.

Finishing it is whatever the round still owes and then the hand-back. A commit
the crash caught before the gate goes out the way every other one does,
spending the round frozen on the record; a candidate over the ceiling is held
for the adjudication; a delivery the crash caught unbound is re-proved against
the checkout and bound to a pull request read afresh; and a checkout that can
vouch for nothing holds the whole thing for a human, because "nothing was
stranded" is the same answer the probe gives a worktree that is gone. A round
whose report SETTLED before the process ended is finished on the mark that
settlement raised and on nothing weaker.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
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

# The seam a case reads to say whether this tick paid for a developer at all.
RUN_AGENT = "run_agent"

CURRENT = "current"

DELIVERED = "delivered"

# The reviewer-feedback comment the direct round bookmarks as its lone replay
# anchor, which a handover nothing confirmed may not drop.
REVIEWER_COMMENT_ID = 1_002

# What a branch nothing could place against its pull request is held under: the
# park that waits for a READING, which the next quiet poll takes again.
PARK_UNPROVED_BRANCH = "stranded_unproved"

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
        # The window past the settlement, and the one only this stage can
        # answer: the report is published, the write that settled it applied
        # the readers and the round the record froze, and the process ends
        # before the label moves. What is left is `workflow:fixing`, nobody
        # being waited for, and a round that is over -- which the scan would
        # read as an issue with nothing to do and bounce, or, with a reply
        # above it, resume a second developer over. Recognised instead, the
        # mark that settlement raised hands the issue to `validating` with no
        # developer run and no second report.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)
        answered = max(reply.id for reply in self.issue.comments)

        with crashes.dying_before_the_relabel(self):
            self.parked_resume(world.reported(), committed=False)

        self.assertEqual(
            (self.pinned()[AWAITING_HUMAN],
             self.pinned().get(PR_LAST_COMMENT_ID),
             _round(self),
             len(self.published_reports())),
            (False, answered, 1, 1),
        )
        handed = self.parked_resume(world.reported(), committed=False)

        handed[RUN_AGENT].assert_not_called()
        self.assertEqual(self.github.label_history[-1], (ISSUE, LABEL_VALIDATING))
        # The hand-back consumed the mark, so nothing publishes a second
        # report and no later round is handed back on this one's evidence.
        self.assertEqual(
            (len(self.published_reports()), _round(self)), (1, 1),
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

        handed[RUN_AGENT].assert_not_called()
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


    def test_a_crash_over_a_lost_checkout_retries(self) -> None:
        # The same window with the branch unprovable under it. The checkout
        # names a head the pull request is not standing on, so the binding
        # refuses; and nothing is stranded that anything could prove, which is
        # the answer that probe also gives a fetch that failed and a divergence
        # git would not count -- so no road here republishes the commit either.
        # The wait is announced rather than held in silence: nothing pushed,
        # nothing published, the record intact and the debt standing.
        #
        # Held under the READING it is waiting for rather than as a report
        # nothing can move, because the two ask opposite things of the next
        # poll. The report is owed a publication and the refusal is the whole
        # reason there is none, so the poll that takes the reading again
        # publishes the commit, binds the same report to it, and hands the
        # round back over the park -- where a report park would have waited
        # for a human no condition clearing could answer.
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

                self.assertEqual(
                    _held_over_the_reading(self, held),
                    (world.PUBLISHED_HEAD, 0, PARK_UNPROVED_BRANCH, False),
                )

                retried = self.parked_resume(
                    world.reported(), **_drift_world.STRANDED,
                )

                self.assertEqual(
                    _finished_by_the_retry(self, retried),
                    (1, (1, False), (ISSUE, LABEL_VALIDATING)),
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
        # The window between the round's publication and the report's binding:
        # the head the report describes is what the pull request carries, and
        # nothing has bound the report to it. Nothing of the handover was
        # durable, so the round is unspent, the anchor intact and the reply
        # still unread -- and the recovery ahead of the next scan re-proves the
        # checkout, binds the report to the pull request it reads afresh,
        # settles the pairs the record froze and hands the round back, without
        # a developer and without a second report.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.requested_fix(world.QUESTION_REPLY, committed=False)
        world.replied(self)
        answered = max(reply.id for reply in self.issue.comments)

        with crashes.dying_before_the_binding():
            self.parked_resume(world.reported(), committed=False)

        self.assertEqual(
            (_round(self), self.pinned().get(REVIEWER_ANCHOR),
             self.records()[DELIVERED] is None,
             len(self.published_reports())),
            (0, REVIEWER_COMMENT_ID, False, 0),
        )
        recovered = self.parked_resume(world.reported(), committed=False)

        recovered[RUN_AGENT].assert_not_called()
        self.assertEqual(self.github.label_history[-1], (ISSUE, LABEL_VALIDATING))
        self.assertEqual(
            (_round(self), len(self.published_reports()),
             self.pinned().get(PR_LAST_COMMENT_ID),
             self.pinned().get(REVIEWER_ANCHOR)),
            (1, 1, answered, None),
        )


def _held_over_the_reading(case, mocks) -> tuple:
    """What a tick that could not place the branch left the issue holding.

    The pull request where it was, no report on it, the park that waits for a
    reading, and the record still there for the poll that takes one -- with no
    push and no developer paid for in between.
    """
    mocks[PUSH_BRANCH].assert_not_called()
    mocks[RUN_AGENT].assert_not_called()
    return (
        case.pull_request.head.sha,
        len(case.published_reports()),
        case.pinned()[PARK_REASON],
        case.records()[DELIVERED] is None,
    )


def _finished_by_the_retry(case, mocks) -> tuple:
    """What the poll that finally took that reading finished, in one push.

    One report on the pull request, the round handed back with nobody waiting,
    and the label moved -- off the same record the held tick left, and with no
    second developer run behind it.
    """
    mocks[RUN_AGENT].assert_not_called()
    mocks[PUSH_BRANCH].assert_called_once()
    return (
        len(case.published_reports()),
        _handover(case),
        case.github.label_history[-1],
    )


def _handover(case) -> tuple:
    """The round a handover spent, and whether it left a human waiting."""
    return case.pinned()[REVIEW_ROUND], case.pinned()[AWAITING_HUMAN]


def _round(case) -> int:
    """The reviewer round this issue's pinned comment says it has spent."""
    return case.pinned()[REVIEW_ROUND]
