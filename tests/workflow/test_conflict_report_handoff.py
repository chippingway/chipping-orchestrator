# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a rebasing resume returns, handed to the reviewer across every stage it crosses.

The #2077 / PR #2087 sequence, end to end through the dispatcher. The pull
request carries a settled report of the head the reviewer approves; the
approval squashes that head into another, the final docs pass runs on the
squash, and the issue reaches `in_review`. The base then moves under it with
real conflicts, so the pull request is handed to `workflow:resolving_conflict`,
and a human changes the requirements while it is there. The resumed session
rebases the squash onto the new base and returns a fresh report of the head it
leaves.

That report is the one the reviewer is handed next: recorded before the
rewritten head is pushed, stamped with the requirements the resume was given
and the road it came down, published once about the rewritten head, and settled
before any reviewer spawns. Nothing parks for a report nobody can deliver, no
human is asked to restart one, and no developer runs a second time to write the
report the first run already returned. The report the approval covered still
names the commit it was written about: neither the squash nor the rebase becomes
its source.

The same stage when the session answers the edit with a report and no commit,
and the process ends as that report is bound. At the conflict cap, the
dispatched ticks behind it settle the saved report before the cap parks the
issue, so it reaches the pull request once and nobody is launched to write it
again. Where the requirements move again first, the edit is answered ahead of
that settlement: the developer is resumed once, and its report is the one the
pull request gets. And where the binding landed and the post behind it did
not, a commit the checkout gains is never pushed over the head the bound report
is held to -- nor where nothing could read the head the run left, whose report
is never recorded, nor past a push whose relabel was lost before its report
was bound, nor once an older transaction settled beside a newer report of the
same head: the ticks behind it park once for a human and do nothing more.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.publication.models import _SquashOutcome
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_publishing as _report_publishing,
    report_records as _records,
)
from orchestrator.workflow.late_split import collapses as _collapses
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import (
    drift_reports as _drift_world,
    fix_report_crashes as _crashes,
    fix_reports as _fix_world,
    report_lifecycle as _lifecycle,
)
from tests.workflow.fixtures import _TEST_SPEC, LABEL_RESOLVING_CONFLICT, LABEL_VALIDATING, approved_on
from tests.workflow.stages.conflicts import drift_report_support as _conflict

# The head the reviewer approves, which the opening report is about; the one
# the approval squashes it into; and the one the resumed session rebases that
# squash onto -- the commit the size gate proves the checkout to.
APPROVED_HEAD = _drift_world.PUBLISHED_HEAD

SQUASHED_HEAD = "5c3a91b7" * 5

REBASED_HEAD = _drift_world.FIXED_HEAD

# What the approval's squash collapses, as its record names it.
COLLAPSED_BASE = "cc33dd44" * 5

COLLAPSED = 2

DOCS_UNCHANGED = "The documentation already describes it.\n\nDOCS: NO_CHANGE"

FRESH_REPORT = "Rebased onto the new base and answered the changed criteria; the suite passes."

PARK_EVENT = "park_awaiting_human"

# A counter that has spent every round the cap allows, and the park it takes.
AT_THE_CAP = 2

CONFLICT_CAP = "conflict_cap"

# How many developer runs the issue has been charged for.
RUNS_USED = "agent_runs_used"

# A newer report of the head an older, still outstanding one describes.
NEWER_REPORT = "A second account of the same head, over the same requirements."

# The report the developer writes once the requirements move past a saved one.
LATER_REPORT = _drift_world.LATER_REPORT_TEXT


class _SquashesTheApproval:
    """The approval's squash: its collapse recorded as the real one records it, and the squash published."""

    def __init__(self, case) -> None:
        self._case = case

    def __call__(self, gate, _branch, _pr_number) -> _SquashOutcome:
        _collapses.record_pending_collapse(
            gate.state, head=APPROVED_HEAD, base_sha=COLLAPSED_BASE, count=COLLAPSED,
        )
        self._case.pull_request.head.sha = SQUASHED_HEAD
        return _SquashOutcome(success=True, sha=SQUASHED_HEAD, count=COLLAPSED)


def _assert_recorded_before(case, push, handed: str) -> None:
    """The report on the comment as the push went out, under this road and the revision it was handed."""
    recorded = push.delivered
    case.assertEqual(
        (recorded.route, recorded.requirements_revision, recorded.report),
        (WorkflowLabel.RESOLVING_CONFLICT, handed, FRESH_REPORT),
    )

def _assert_published_once(case, handed: str) -> None:
    """One fresh report of the rebased head, and the approved report still naming its own commit."""
    case.assertEqual(len(case.published_reports(FRESH_REPORT)), 1)
    current = case.records()["current"]
    case.assertEqual(
        (current.subject.source_sha, current.subject.requirements_revision),
        (REBASED_HEAD, handed),
    )
    case.assertEqual(case.opening_report.subject.source_sha, APPROVED_HEAD)

def _assert_reviewed_without_a_park(case) -> None:
    """Every run paid for once, nothing owed at any spawn, and the fresh report reviewed and approved."""
    case.assertEqual(
        [(spawn.role, spawn.owed) for spawn in case.spawns],
        [
            (_lifecycle.REVIEWER, False),
            (_lifecycle.DEVELOPER, False),
            (_lifecycle.DEVELOPER, False),
            (_lifecycle.REVIEWER, False),
        ],
    )
    case.assertIn(FRESH_REPORT, case.spawns[-1].prompt)
    case.assertEqual(case.spawns[-1].review_round, 0)
    case.assertEqual(
        [event for event in case.github.recorded_events if event["event"] == PARK_EVENT],
        [],
    )
    case.assertEqual(
        [label for _, label in case.github.label_history][2:],
        [WorkflowLabel.VALIDATING, WorkflowLabel.DOCUMENTING],
    )
    pinned = case.pinned()
    case.assertEqual(
        (pinned["conflict_round"], pinned["docs_checked_sha"]),
        (1, SQUASHED_HEAD),
    )


def _assert_the_recovery_held(case, checkout=_drift_world.STRANDED) -> None:
    """Two dispatched ticks over a commit gained since, behind one park: nothing pushed, run, charged, or counted."""
    before, posted = case.pinned(), len(case.published_reports())
    ticks = [case.drift([], **checkout) for _ in range(2)]
    case.assertEqual(
        [(ticked["_push_branch"].call_count, ticked["run_agent"].call_count) for ticked in ticks],
        [(0, 0), (0, 0)],
    )
    pinned = case.pinned()
    case.assertEqual(
        (pinned["conflict_round"], pinned[RUNS_USED]),
        (before["conflict_round"], before[RUNS_USED]),
    )
    case.assertEqual(
        [event["reason"] for event in case.github.recorded_events if event["event"] == PARK_EVENT],
        [_report_delivery.UNDELIVERABLE_REPORT],
    )
    case.assertEqual(
        (case.github.label_history, len(case.published_reports())),
        ([], posted),
    )


class RebasedReportHandoffTest(unittest.TestCase, _fix_world._FixReportMixin):
    def setUp(self) -> None:
        self.enterContext(patch.object(config, "SQUASH_ON_APPROVAL", True))
        self.seeded(_conflict.ISSUE, _conflict.PR, LABEL_VALIDATING)
        self.spawns = []
        reviewer = partial(_lifecycle._Staged, self, _lifecycle.REVIEWER)
        developer = partial(_lifecycle._Staged, self, _lifecycle.DEVELOPER)
        self._runs = MagicMock(side_effect=_fix_world._Runs(
            reviewer(approved_on(APPROVED_HEAD)),
            developer(DOCS_UNCHANGED),
            developer(_drift_world.reported(FRESH_REPORT)),
            reviewer(approved_on(REBASED_HEAD)),
        ))

    def test_the_returned_report_reaches_review(self) -> None:
        self._approves_squashes_and_documents()
        push = self._rebases_under_changed_requirements()
        self._tick(committed=False)

        handed = _drift_world.handed_revision(self.issue)
        _assert_recorded_before(self, push, handed)
        _assert_published_once(self, handed)
        _assert_reviewed_without_a_park(self)

    def _rebases_under_changed_requirements(self) -> _conflict.PushedAfterTheRecord:
        """The base refresh's conflict handoff, the edit, and the resume that rebases and reports.

        The handoff is the label the refresh moves the pull request to when its
        rebase leaves conflicted files, which this hermetic tick cannot run.
        """
        self.github.apply_foreign_label(self.issue, LABEL_RESOLVING_CONFLICT)
        _drift_world.edits(self, _conflict.CHANGED_REQUIREMENTS)
        push = _conflict.PushedAfterTheRecord(self)
        self._tick(push_branch=push)
        return push

    def _approves_squashes_and_documents(self) -> None:
        """The approval and its squash, the carry's handoff, the docs pass, and `in_review`."""
        self._tick(committed=False, squash_result=_SquashesTheApproval(self))
        for _ in range(3):
            self._tick(committed=False)
        self.assertEqual(
            [label for _, label in self.github.label_history],
            [WorkflowLabel.DOCUMENTING, WorkflowLabel.IN_REVIEW],
        )

    def _tick(self, **run_options) -> None:
        """One whole dispatched tick, over whatever label the issue carries."""
        with _conflict.on_its_base():
            self._ticked(self._dispatched, self._runs, **run_options)

    def _dispatched(self, github, issue, *, run_agent, **run_options):
        return self._run(
            partial(
                _issue_processing._route_issue_to_handler,
                github, _TEST_SPEC, issue, github.workflow_label(issue),
            ),
            run_agent=run_agent,
            **run_options,
        )


class CappedReportAloneTest(unittest.TestCase, _conflict._ConflictDriftReportMixin):
    """A report-only answer whose settlement a crash cut short, recovered by the dispatcher.

    At the conflict cap, where the requirements move again before the saved
    report is settled, and where it was bound -- or its run's head could not be
    read, or its commit's push landed and the relabel did not, or an older
    transaction settled beside it -- and the checkout then gained a commit.
    """

    def test_the_saved_report_settles_before_the_cap(self) -> None:
        self.enterContext(patch.object(config, "MAX_CONFLICT_ROUNDS", AT_THE_CAP))
        self.seeded_on_conflict(conflict_round=AT_THE_CAP)
        handed = self.handed()
        with self.dying_at_the_binding():
            self.drift(_drift_world.reported(), committed=False)

        for _ in range(2):
            self.drift([], committed=False)["run_agent"].assert_not_called()

        self.assertEqual(len(self.published_reports()), 1)
        current = self.records()["current"].subject
        self.assertEqual((current.source_sha, current.requirements_revision), (APPROVED_HEAD, handed))
        self.assertEqual(
            [event["reason"] for event in self.github.recorded_events if event["event"] == PARK_EVENT],
            [CONFLICT_CAP],
        )

    def test_an_edit_replaces_the_saved_report(self) -> None:
        self.seeded_on_conflict()
        with self.dying_at_the_binding():
            self.drift(_drift_world.reported(), committed=False)
        _drift_world.edits(self, _drift_world.LATER_BODY)
        handed = self.handed()

        launches = [
            self.drift(_drift_world.reported(LATER_REPORT), committed=False)["run_agent"].call_count
            for _ in range(2)
        ]

        self.assertEqual(launches, [1, 0])
        self.assertEqual(len(self.published_reports(LATER_REPORT)), 1)
        self.assertEqual(self.published_reports(), [])
        current = self.records()["current"].subject
        self.assertEqual((current.source_sha, current.requirements_revision), (APPROVED_HEAD, handed))
        self.assertEqual(self.github.label_history, [(_conflict.ISSUE, WorkflowLabel.VALIDATING)])

    def test_a_bound_report_holds_the_recovery(self) -> None:
        self.seeded_on_conflict()
        with patch.object(_report_publishing, "finishes", return_value=True):
            self.drift(_drift_world.reported(), committed=False)

        _assert_the_recovery_held(self)

        self.assertEqual(self.records()["pending"].subject.source_sha, APPROVED_HEAD)

    def test_an_unread_head_holds_the_recovery(self) -> None:
        self.seeded_on_conflict()
        self.drift(_drift_world.reported(), committed=False, **_conflict.UNREAD_HEAD)

        _assert_the_recovery_held(self)

        self.assertEqual(set(self.records().values()), {None})

    def test_a_lost_relabel_holds_the_recovery(self) -> None:
        self.seeded_on_conflict()
        with _crashes.dying_before_the_relabel(self):
            self.drift(_drift_world.reported())

        _assert_the_recovery_held(self, _conflict.PAST_THE_PUSH)

        self.assertEqual(self.pinned()["conflict_resume_to_sha"], REBASED_HEAD)

    def test_an_older_settlement_keeps_the_record(self) -> None:
        # An older report-only transaction is still outstanding when a newer
        # report of the same head and requirements is saved beside it, and the
        # older one settles first. The record naming that head speaks for the
        # newer report too, so that settlement leaves it, and a commit the
        # checkout gains is refused rather than published with the newer
        # report bound to it.
        self.seeded_on_conflict()
        with patch.object(_report_publishing, "finishes", return_value=True):
            self.drift(_drift_world.reported(), committed=False)
        state = self.github.read_pinned_state(self.issue)
        _delivery_state.stage_delivered_report(state, _records.DeliveredReport(
            receipt=f"issue-{_conflict.ISSUE}-report-3", report_revision=3,
            mode=_records.ReportMode.PUBLISH, route=WorkflowLabel.RESOLVING_CONFLICT,
            requirements_revision=self.handed(), report=NEWER_REPORT,
        ))
        self.github.write_pinned_state(self.issue, state)
        self.reconcile()

        _assert_the_recovery_held(self)

        self.assertEqual(
            (self.records()["delivered"].report, self.pinned()["conflict_resume_to_sha"]),
            (NEWER_REPORT, APPROVED_HEAD),
        )
        self.assertEqual(
            (len(self.published_reports()), self.published_reports(NEWER_REPORT)),
            (1, []),
        )

    def _run_resolving_conflict(self, github, issue, *, run_agent, **run_options):
        """The tick the dispatcher runs, routing on the label the issue carries."""
        return self._run(
            partial(
                _issue_processing._route_issue_to_handler,
                github, _TEST_SPEC, issue, github.workflow_label(issue),
            ),
            run_agent=run_agent,
            **run_options,
        )


if __name__ == "__main__":
    unittest.main()
