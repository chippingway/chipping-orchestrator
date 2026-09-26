# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A developer report's whole life, walked across every interruption it survives.

The #1682 / PR #1697 sequence, end to end. The pull request carries the report
it was opened with when a human edits the requirements. The validating tick
resumes the developer on the edit, and the commit that run makes reaches the
pull request while the report written beside it does not: GitHub refused the
post, or took it and lost the response. A later tick finishes that publication
without the developer and only then spawns a reviewer, who is handed the new
report and asks for something only the report can answer. The developer answers
in words, on the commit the pull request already carries -- and that round is
cut short too: on its own accepted post, on the relabel that hands it back, or
on that relabel and then on the one the recovery hands it back with.
A fresh reviewer is handed that report and approves it, and the docs pass and
`in_review` follow as they always do.

Wherever the walk is interrupted, it ends in the same place. Each developer
result is one report revision on the pull request, no agent is spawned while a
report is still owed, every round and run is counted exactly once, and a human
comment that landed while the report-only round was out is read by nobody until
the approved pull request reaches `in_review`, which answers it once.
"""
from __future__ import annotations

import unittest

from tests.workflow import (
    drift_reports as _drift_world,
    published_reports as _published_reports,
    report_lifecycle as lifecycle,
)
from tests.workflow.fixtures import (
    LABEL_DOCUMENTING,
    LABEL_FIXING,
    LABEL_IN_REVIEW,
    LABEL_VALIDATING,
)

# Every pair of interruptions the walk is taken under: how the drift report's
# post goes unconfirmed, and where the report-only round is cut short.
INTERRUPTIONS = (
    (lifecycle.REFUSED, lifecycle.ACCEPTED),
    (lifecycle.REFUSED, lifecycle.RELABEL),
    (lifecycle.ACCEPTED, lifecycle.ACCEPTED),
    (lifecycle.ACCEPTED, lifecycle.RELABEL),
    (lifecycle.REFUSED, lifecycle.RELABELS),
    (lifecycle.ACCEPTED, lifecycle.RELABELS),
)

# The runs the walk pays for, in order, with the reviewer round each one found:
# the drift commit spends the first round and the report-only round the second,
# and nothing after the approval spends another.
PAID_FOR = (
    (lifecycle.DEVELOPER, 0),
    (lifecycle.REVIEWER, 1),
    (lifecycle.DEVELOPER, 1),
    (lifecycle.REVIEWER, 2),
    (lifecycle.DEVELOPER, 2),
    (lifecycle.DEVELOPER, 2),
)

ROUNDS_SPENT = 2

# One move into the fix round, one back, and the approved pull request's own
# road afterwards -- the moves an uninterrupted walk makes, each made once.
LABELS = (
    LABEL_FIXING,
    LABEL_VALIDATING,
    LABEL_DOCUMENTING,
    LABEL_IN_REVIEW,
    LABEL_FIXING,
    LABEL_IN_REVIEW,
)

# The revision the report-only round publishes, and the pinned records that
# name it once the walk is over.
LAST_REVISION = 3

CURRENT = "developer_report_current"

HANDOFF = "developer_report_handoff"

OUTSTANDING = ("developer_report_pending", "developer_report_delivery")


class ReportLifecycleTest(unittest.TestCase, lifecycle._ReportLifecycle):
    def test_every_interruption_ends_in_one_place(self) -> None:
        for drift, round_ in INTERRUPTIONS:
            with self.subTest(drift=drift, round=round_):
                self.walk(drift, round_)

                self._assert_one_revision_per_result()
                self._assert_reviewed_afresh()
                self._assert_counted_once()
                self._assert_feedback_kept()

    def _assert_one_revision_per_result(self) -> None:
        # The opening report, the drift resume's, and the report-only round's,
        # each on the pull request once. The later two are about the commit the
        # drift resume pushed and the requirements it was handed, and the last
        # is the one settled and handed off, with nothing left outstanding.
        self.assertEqual(
            [
                (report.report_revision, report.source_sha, report.text)
                for report in self.reports()
            ],
            [
                (1, _drift_world.PUBLISHED_HEAD, _published_reports.DELIVERED_REPORT),
                (2, _drift_world.FIXED_HEAD, lifecycle.DRIFT_REPORT),
                (LAST_REVISION, _drift_world.FIXED_HEAD, lifecycle.FINAL_REPORT),
            ],
        )
        self.assertEqual(
            {report.requirements_revision for report in self.reports()[1:]},
            {_drift_world.handed_revision(self.issue)},
        )
        pinned = self.pinned()
        self.assertEqual(
            (
                pinned[CURRENT]["revision"],
                pinned[HANDOFF]["revision"],
                *(pinned.get(record) for record in OUTSTANDING),
            ),
            (LAST_REVISION, LAST_REVISION, None, None),
        )

    def _assert_reviewed_afresh(self) -> None:
        # Each reviewer is handed the report current as it spawns, and the
        # approval covers the report-only round's revision on the unchanged
        # commit rather than riding the review of the one before it -- the
        # revision the returned reviewer's own write records as read.
        first, second = (
            spawn.prompt for spawn in self.spawns
            if spawn.role == lifecycle.REVIEWER
        )
        self.assertIn(f"> {lifecycle.DRIFT_REPORT}", first)
        self.assertIn(f"> {lifecycle.FINAL_REPORT}", second)
        self.assertNotIn(lifecycle.DRIFT_REPORT, second)
        pinned = self.pinned()
        self.assertEqual(
            (
                pinned["review_approved_subject"]["sha"],
                pinned["review_approved_subject"]["report_revision"],
                pinned["review_returned_subject"]["report_revision"],
            ),
            (_drift_world.FIXED_HEAD, LAST_REVISION, LAST_REVISION),
        )

    def _assert_counted_once(self) -> None:
        # No run was paid for twice or early: every spawn found nothing owed,
        # the round each found is the one its predecessors spent, the ledger
        # and the usage totals are exactly the staged runs, and the label made
        # each move once.
        self.assertEqual(
            [(spawn.role, spawn.review_round) for spawn in self.spawns],
            list(PAID_FOR),
        )
        self.assertFalse(any(spawn.owed for spawn in self.spawns))
        pinned = self.pinned()
        self.assertEqual(
            (
                pinned["review_round"],
                pinned["agent_runs_used"],
                pinned["issue_agent_runs"],
                pinned["issue_total_tokens"],
            ),
            (
                ROUNDS_SPENT,
                len(PAID_FOR),
                len(PAID_FOR),
                sum(lifecycle.tokens_of(spawn.backend) for spawn in self.spawns),
            ),
        )
        self.assertEqual(
            tuple(label for _, label in self.github.label_history), LABELS,
        )

    def _assert_feedback_kept(self) -> None:
        # The human's comment reaches exactly one agent -- the fixing round
        # `in_review` routed it to, last of all -- and the watermark moves past
        # it there and nowhere earlier.
        self.assertEqual(
            [
                position for position, spawn in enumerate(self.spawns)
                if lifecycle.LATER_FEEDBACK in spawn.prompt
            ],
            [len(PAID_FOR) - 1],
        )
        self.assertEqual(
            self.pinned()["pr_last_comment_id"], lifecycle.LATER_FEEDBACK_ID,
        )


if __name__ == "__main__":
    unittest.main()
