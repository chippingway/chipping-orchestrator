# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite continued over a further base advance while a refreshed report of its head is unsettled.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
reviewed head rebased onto a moved base and pushed, its run settled, and its
finish killed at a final handoff boundary (`rewrite_handoff_test_support`) --
or run through, the uninterrupted journey every boundary is held to. A
refresh of the head's report is then recorded, bound, and not yet settled,
and the base advances again.

The next tick's whole base refresh rebases nothing over that report: an
attempt still standing is retired unrouted, its head announced once, and the
refresh's selection, asked again once the anchor is down, holds the branch as
it holds the uninterrupted journey's. The dispatcher's report reconciliation
settles the report on the head it is about with nothing parked, and only the
tick behind it rebases onto the advanced base: one push, the pushed head
announced and routed, the run settled for the head it replaced no decision
about it, and no developer launched, wherever the first tail died.
"""
from __future__ import annotations

import unittest
from functools import partial

from orchestrator.workflow.engine import (
    report_record_state as _report_state,
    report_records as _report_records,
    report_settlement_state as _report_settlement,
    report_transaction as _report_transaction,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.implementing import late_publication_state as _publication_state
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

_PARK_REASON = "park_reason"

_UNINTERRUPTED = "uninterrupted"

# The tails that relabelled the landed head before the base advanced again: the
# uninterrupted one, and one killed behind its relabel.
_RELABELLED = frozenset((None, handoff.BEFORE_THE_RETIREMENT))


def _refreshes_the_report(case: support.CapturedRunCase, head: str) -> _report_records.PendingReport:
    """Record report 3 of `head` bound and unsettled, over the comment as it stands; that report.

    The code publication receipt names `head` over the head it replaced, as
    the push that put it on the pull request recorded it, so the report is one
    the reconciliation can deliver.
    """
    state = case.gh.read_pinned_state(case.issue)
    pending = _report_records.PendingReport(
        receipt="issue-7-report-3",
        subject=_report_settlement.read_current_report(state).subject,
        report_revision=3,
        mode=_report_records.ReportMode.PUBLISH,
        route=WorkflowLabel.VALIDATING,
        report="Refreshed the report of the rebased head.",
    )
    _publication_state._record_publication(state, head, case.anchor, git_support.PR_NUMBER)
    case.assertTrue(_report_state.record_pending_report(state, pending))
    case.gh.write_pinned_state(case.issue, state)
    return pending


def _reconciles(case: support.CapturedRunCase) -> tuple:
    """Run the dispatcher's report reconciliation; the report owed, the settled one's revision and head, any park."""
    label = case.gh.workflow_label(case.issue)
    state = case.gh.read_pinned_state(case.issue)
    _report_transaction._reconciles_pending_report(case.gh, case._spec, case.issue, label, state)
    state = case.gh.read_pinned_state(case.issue)
    current = _report_settlement.read_current_report(state)
    settled = (current.report_revision, current.subject.source_sha)
    return _report_state.read_pending_report(state), settled, state.get(_PARK_REASON)


class ReportInFlightContinuationTest(support.CapturedRunCase, unittest.TestCase):
    """A report recorded and unsettled holds the continuation's rebase until the reconciliation settles it."""

    def test_the_report_settles_before_the_rebase(self) -> None:
        for boundary in (None, *handoff.BOUNDARIES):
            named = _UNINTERRUPTED if boundary is None else boundary.name
            with self.subTest(boundary=named):
                self.setUp()
                head, run = self._lands_cut_short(boundary)
                settled = (_refreshes_the_report(self, head).report_revision, head)
                support.advances_the_base_again(self)

                self.recovers()
                self._assert_held(head)
                self.assertEqual(_reconciles(self), (None, settled, None))
                self.recovers()

                self._assert_routed(head, relabelled=boundary in _RELABELLED)
                self._assert_run_retired(head, run)

    def _lands_cut_short(self, boundary: handoff.Boundary | None) -> tuple:
        """Land and review a rebase, its finish killed at `boundary` or run through; the head, and its settled run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
        return head, readings.pinned_records(self)[1]

    def _said(self) -> tuple:
        """The head every `base_rebased` names, and how many landings the pull request was told of."""
        return support.announced(self), len(readings.notices(self))

    def _assert_held(self, head: str) -> None:
        """Nothing rebased over the report: the remote still on `head`, the attempt retired, `head` announced once."""
        held = (git_support.remote_head(self), readings.attempt(readings.pinned(self)))
        self.assertEqual(held, (head, readings.RETIRED))
        self.assertEqual(self._said(), ([head], 1))

    def _assert_routed(self, head: str, *, relabelled: bool) -> None:
        """`head` and the head the rebase behind the report pushed each announced once, that one routed and finished.

        Routed behind the relabel the first tail made where it `relabelled`
        `head`, the attempt retired and the round reset with nothing parked;
        one push, and no developer launched.
        """
        pushed = git_support.remote_head(self)
        self.assertEqual(self._said(), ([head, pushed], 2))
        self.assertEqual(readings.relabels(self), readings.ROUTED * (1 + relabelled))
        pinned = readings.pinned(self)
        self.assertEqual(readings.attempt(pinned), readings.RETIRED)
        reset = (pinned[readings.KEY_REVIEW_ROUND], pinned.get(_PARK_REASON))
        self.assertEqual(reset, (0, None))
        self.assertEqual((self.pushes.call_count, self.developer.call_count), (1, 0))

    def _assert_run_retired(self, head: str, run) -> None:
        """The `run` settled for `head` invalidated into history with its own tested head, and run once.

        Nothing is pending or current for the pushed head: its fresh reviewer
        owes its evidence.
        """
        retired = (*git_support.invalidated(self), (run.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        tested = history[-1].binding.tested_sha
        self.assertEqual((tested, self.runs()), (head, 1))


if __name__ == "__main__":
    unittest.main()
