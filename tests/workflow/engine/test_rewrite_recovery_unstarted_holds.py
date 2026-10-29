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

The clear is a write of its own, and only one that landed lets the tick go on.
Refused, or landed with its answer lost, it holds that refresh with nothing
rebased or pushed, and the next refresh -- reading the comment afresh, the
attempt standing or already cleared -- rebases and pushes once. An attempt the
comment came to record otherwise behind the refresh's reading, by no write of
the recovery's, stops the clear: that record stands as it is, and nothing is
rebased, pushed, or relabelled behind it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

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
)
from tests.workflow.interleaving import _RacesPastTheCall

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

_WATERMARK = "last_action_comment_id"

_PARK = "auto_base_rebase_dirty"

_REPORT_PENDING = "developer_report_pending"

# The records a recovery's clear leaves holding the branch, each spelled as
# the owner that spends it reads it.
_HOLDS = (_REPORT_PENDING, "read_only_baseline_sha", "late_collapse_head")

# How the clear's write goes wrong on the first refresh, as the client names
# it, beside whether it landed: refused outright, or landed with its answer lost.
_UNLANDED_CLEARS = (("refused", False), ("lost", True))

# The anchor the comment comes to carry behind the refresh's reading.
_MOVED_ANCHOR = "0dd0a5c4" * 5


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


def _spends(case: support.VerificationRecoveryCase, hold: str) -> None:
    """Take `hold` off the comment, ending its freeze as its owner's spend does."""
    state = case.gh.read_pinned_state(case.issue)
    state.state_data.pop(hold)
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


class UnstartedClearCheckpointTest(support.VerificationRecoveryCase, unittest.TestCase):
    """An unstarted attempt's clear lets the rebase go on only once it landed, and stops where the attempt moved."""

    def setUp(self) -> None:
        support.VerificationRecoveryCase.setUp(self)
        git_support.advances_the_base(self)
        state = self.gh.read_pinned_state(self.issue)
        state.state_data.update(
            finish_support.attempt_record(self.anchor, None, git_support.PR_NUMBER, git_support.REVIEWING),
        )
        self.gh.write_pinned_state(self.issue, state)

    def test_the_next_refresh_rebases(self) -> None:
        # The clear was refused, or landed with its answer lost: that refresh
        # rebases and pushes nothing. The next refresh reads the comment
        # afresh -- the attempt still standing, or already cleared -- and
        # rebases and pushes once.
        for failure, lands in _UNLANDED_CLEARS:
            with self.subTest(failure=failure):
                standing = self._clears_failing(failure)

                self.assertEqual(standing, None if lands else self.anchor)
                self._assert_unmoved()
                self.recovers()
                self.assertNotEqual(git_support.remote_head(self), self.anchor)
                self.assertEqual(_moved(self), (1, readings.ROUTED))

    def test_a_moved_attempt_stops_the_clear(self) -> None:
        # Behind the refresh's reading the comment comes to carry another
        # anchor, by no write of the recovery's -- an invariant failure under
        # the issue writer claim. The clear refuses rather than put the
        # reading back: the moved record stands as it is, and nothing is
        # rebased, pushed, or relabelled behind it.
        moves = _RacesPastTheCall(self.gh.read_pinned_state, 1, self._moves_the_anchor)

        with (
            patch.object(self.gh, "read_pinned_state", moves),
            self.assertLogs("orchestrator.base_sync", "WARNING") as logged,
        ):
            self.recovers()
            self.assertIn("clearing its attempt", "\n".join(logged.output))

        self.assertEqual(readings.pinned(self).get(readings.KEY_PENDING_PUSH), _MOVED_ANCHOR)
        self._assert_unmoved()

    def _clears_failing(self, failure: str) -> str | None:
        """Refresh a fresh case once, the clear's write answered with the client's `failure`; the anchor left."""
        self.setUp()
        failing = getattr(self.gh.pinned_failures, failure)
        failing.add(self.issue.number)
        self.recovers()
        failing.discard(self.issue.number)
        return readings.pinned(self).get(readings.KEY_PENDING_PUSH)

    def _assert_unmoved(self) -> None:
        """Nothing rebased, pushed, or relabelled: the pull request's branch still on the anchor."""
        self.assertEqual(git_support.remote_head(self), self.anchor)
        self.assertEqual(_moved(self), (0, ()))

    def _moves_the_anchor(self) -> None:
        """Repoint the anchor on the pinned comment, by no write of the recovery's."""
        moved = self.gh.read_pinned_state(self.issue)
        moved.set(readings.KEY_PENDING_PUSH, _MOVED_ANCHOR)
        self.gh.write_pinned_state(self.issue, moved)


if __name__ == "__main__":
    unittest.main()
