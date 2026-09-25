# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reviewer handed a developer report, and the stages that act on its verdict.

The fix-loop world, seen from the reviewer's side: report-only rounds put report
after report on the head the pull request already carries, a reviewer is handed
whichever the pull request carries when it spawns, and an approval travels on
through the final-docs hop to the ready ping. What a case varies is which
report is current, what happened to it on the thread, and which authors the
deployment trusts.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow import fix_reports as _fix_world
from tests.workflow.fixtures import LABEL_IN_REVIEW, _agent

RUN_AGENT = "run_agent"

FIRST_REPORT = "Covers the requested change; `uv run pytest tests` passes."

SECOND_REPORT = "Says how the suite was run, as the reviewer asked, on the same commit."

# What a human leaves in place of the first report when they edit its comment.
EDITED_REPORT = "A different account of the work."

# The records the reviewer and the approval leave on the pinned comment.
REVIEWED = "review_subject"

APPROVED = "review_approved_subject"

READY_PING = "ready for review/merge"

# Where the review refusals below leave the issue: held for a human, with the
# report recorded as owed so the reply is answered by a fresh one.
AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"


def prompt(mocks, call: int = 0) -> str:
    """The prompt one agent run of a tick was handed."""
    runs = mocks[RUN_AGENT].call_args_list
    return runs[call].args[1]


def restate(case, **fields) -> None:
    """Write `fields` onto the case's pinned comment as a hand edit would."""
    state = case.github.read_pinned_state(case.issue)
    for key, staged in fields.items():
        state.set(key, staged)
    case.github.write_pinned_state(case.issue, state)


def ready_pings(github) -> list[str]:
    """Every ready ping the issue thread has been sent."""
    return [body for _, body in github.posted_comments if READY_PING in body]


def edits_report(case) -> None:
    """Rewrite the words of the report recorded as current, in place."""
    landed = case.report_comment()
    landed.body = landed.body.replace(FIRST_REPORT, EDITED_REPORT)


def deletes_report(case) -> None:
    """Remove the comment the report recorded as current landed as."""
    case.pull_request.issue_comments.remove(case.report_comment())


def forgets_approval(case) -> None:
    """Leave the approval as one recorded before approvals named a subject."""
    state = case.github.read_pinned_state(case.issue)
    state.data.pop(APPROVED, None)
    case.github.write_pinned_state(case.issue, state)


class _ReviewedReports(_fix_world._FixReportMixin):
    """Report rounds, reviews, and the in_review tick behind an approval.

    `allowed` is the author allowlist every tick is taken under, so a case can
    name the one it means and change it between ticks.
    """

    allowed: tuple = ()

    def reported_round(self, text: str):
        """One validating tick whose reviewer asks for a report-only change."""
        return self.requested_fix(_fix_world.reported(text), committed=False)

    def report_comment(self):
        """The comment the report recorded as current landed as."""
        location = self.records()["current"].location
        return next(
            posted for posted in self.pull_request.issue_comments
            if posted.id == location.comment_id
        )

    def documented(self) -> None:
        """Finish the docs pass on the head the pull request carries.

        What the documenting stage leaves when its pass needed no change: the
        verdict stamped on that head, and the issue handed to `in_review`.
        """
        restate(
            self,
            docs_checked_sha=self.pull_request.head.sha,
            docs_verdict="no_change",
        )
        self.github.apply_foreign_label(self.issue, LABEL_IN_REVIEW)

    def in_review_tick(self):
        """One in_review tick, under this case's author policy."""
        with self._author_policy():
            return self.drift(_agent(), committed=False)

    def assert_refused(self, mocks, detail: str) -> None:
        """No reviewer ran, and the issue is parked for the report it lacks."""
        mocks[RUN_AGENT].assert_not_called()
        pinned = self.pinned()
        self.assertEqual(
            (
                pinned.get(AWAITING_HUMAN),
                pinned.get(PARK_REASON),
                pinned.get(_report_delivery.OWED_REPORT),
            ),
            (True, _report_delivery.UNDELIVERABLE_REPORT, True),
        )
        self.assertTrue(
            any(detail in body for _, body in self.github.posted_comments),
            detail,
        )

    def _author_policy(self):
        return patch.object(config, "ALLOWED_ISSUE_AUTHORS", self.allowed)
