# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An auto rebase that pinned its anchor and never started, recovered beside a record the anchor set aside.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7
in review, the base moved, and an attempt standing on the comment that pinned
its anchor and terms and got no further -- the checkout still on the anchor.
It was made under a park this refresh left, released by the issue author's
reply. Beside it stands one record the refresh's selection holds an
unanchored branch for and sets aside beside an anchor: a developer report
recorded and unsettled, a stage's baseline, a squash's terms.

The recovery clears the attempt and lets the tick go on, and the selection
asked again holds the branch: nothing rebased or pushed, the park and the
reply left as they stood. Once the record's owner spends it, the next refresh
rebases, pushes once, and spends the reply.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.workflow.engine import (
    report_record_state as _report_state,
    report_records as _report_records,
    report_settlement_state as _report_settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
)

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

_WATERMARK = "last_action_comment_id"

_PARK = "auto_base_rebase_dirty"

_REPORT_PENDING = "developer_report_pending"

# The records a recovery's clear leaves holding the branch, each spelled as
# the owner that spends it reads it.
_HOLDS = (_REPORT_PENDING, "read_only_baseline_sha", "late_collapse_head")

# The branch transport's fetch, read before any case stands in for it.
_FETCH = branch_transport._authed_fetch


def _holds_beside_an_unstarted_attempt(case: support.VerificationRecoveryCase, hold: str) -> int:
    """Pin an attempt that never started, under a released park, with `hold` beside it; the reply's id."""
    state = case.gh.read_pinned_state(case.issue)
    unstarted = finish_support.attempt_record(case.anchor, None, git_support.PR_NUMBER, git_support.REVIEWING)
    for key, recorded in unstarted.items():
        state.set(key, recorded)
    state.set(_AWAITING_HUMAN, True)
    state.set(_PARK_REASON, _PARK)
    state.set(_WATERMARK, case.gh.latest_comment_id(case.issue))
    if hold == _REPORT_PENDING:
        case.assertTrue(_report_state.record_pending_report(state, _report_records.PendingReport(
            receipt="issue-7-report-2",
            subject=_report_settlement.read_current_report(state).subject,
            report_revision=2,
            mode=_report_records.ReportMode.PUBLISH,
            route=WorkflowLabel.VALIDATING,
            report="Refreshed the report of the anchor.",
        )))
    else:
        state.set(hold, case.anchor)
    case.gh.write_pinned_state(case.issue, state)
    reply = case.gh.comment(case.issue, "/orchestrator continue")
    reply.user.login = case.issue.user.login
    return reply.id


def _records_while_fetching(case, recorded: list, spec, ref: str, **options):
    """The branch's fetch, a newer transaction another road records behind its first answer, into `recorded`."""
    fetched = _FETCH(spec, ref, **options)
    if "issue-7" in ref and not recorded:
        recorded.append(settled.records_a_newer_run(case))
    return fetched


def _spends(case: support.VerificationRecoveryCase, hold: str) -> None:
    """Take `hold` off the comment, ending its freeze as its owner's spend does."""
    state = case.gh.read_pinned_state(case.issue)
    state.data.pop(hold)
    case.gh.write_pinned_state(case.issue, state)


def _parked(pinned: dict) -> tuple:
    """Whether a human is awaited, on which park, and the last reply the comment counts as read."""
    awaiting = bool(pinned.get(_AWAITING_HUMAN))
    return awaiting, pinned.get(_PARK_REASON), pinned.get(_WATERMARK)


def _moved(case: support.VerificationRecoveryCase) -> tuple:
    """How many pushes `case`'s refreshes made, and every relabel they made."""
    return case.pushes.call_count, readings.relabels(case)


class UnstartedRecoveryHoldsTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A record the anchor set aside holds the rebase behind an unstarted attempt's clear, and keeps its reply."""

    def test_the_hold_outlasts_the_clear(self) -> None:
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                self.setUp()
                git_support.advances_the_base(self)
                reply = _holds_beside_an_unstarted_attempt(self, hold)
                parked = _parked(readings.pinned(self))

                self.recovers()
                self._assert_held(hold, parked)

                _spends(self, hold)
                self.recovers()
                self._assert_rebased(reply)

    def test_a_newer_transaction_refuses_the_clear(self) -> None:
        # Another road records a transaction while the recovery fetches: the clear, guarded over the evidence records as
        # read, is refused, so that transaction and its revision floor stand, and the attempt is kept for the next tick.
        git_support.advances_the_base(self)
        _holds_beside_an_unstarted_attempt(self, _HOLDS[1])
        recorded: list = []
        with patch.object(branch_transport, "_authed_fetch", partial(_records_while_fetching, self, recorded)):
            self.recovers()

        pinned = readings.pinned(self)
        floor, anchored = pinned[readings.KEY_REVISION_FLOOR], pinned[readings.KEY_PENDING_PUSH]
        self.assertEqual(readings.records(pinned)[0], recorded[0])
        self.assertEqual((floor, anchored), (recorded[0].revision, self.anchor))

    def _assert_held(self, hold: str, parked: tuple) -> None:
        """The attempt cleared and nothing rebased or pushed: `hold` standing, and the park and reply as `parked`."""
        pinned = readings.pinned(self)
        self.assertEqual(readings.attempt(pinned), readings.RETIRED)
        self.assertIn(hold, pinned)
        heads = (git_support.remote_head(self), self._wt_head())
        self.assertEqual(heads, (self.anchor, self.anchor))
        self.assertEqual(_parked(pinned), parked)
        self.assertEqual(_moved(self), (0, ()))

    def _assert_rebased(self, reply: int) -> None:
        """The rebase behind the spent hold pushed once and routed, the park taken down and `reply` read."""
        self.assertNotEqual(git_support.remote_head(self), self.anchor)
        self.assertEqual(_parked(readings.pinned(self)), (False, None, reply))
        self.assertEqual(_moved(self), (1, readings.ROUTED))


if __name__ == "__main__":
    unittest.main()
