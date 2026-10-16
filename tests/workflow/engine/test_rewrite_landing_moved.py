# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A recovery reading a landed rewrite's landing moved, and the run a finish captured or settled for it retired.

The captured case (`rewrite_captured_test_support`), with its attempt read back
the way the recovery reads it. A snapshot with both heads on the announced head
keeps the run for the landed road to finish, and so does one that read no head
off it -- a checkout or remote nobody read moves nothing; any snapshot reading
a head elsewhere abandons it before its road is taken, or answers that the road
must hold where no write could. A reset the git owner landed releases the
attempt and abandons the run in the park's one write, dropping it where the
comment has no room for its history; a reset that failed keeps both. Evidence a
finish settled for the announced head (`SettledEvidenceCase`) is invalidated
whole into history by any snapshot reading a head off it, kept by one that read
none, and holds the road where no write lands. Nothing is run, launched, or
routed.
"""
from __future__ import annotations

import subprocess
import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.git.base_sync import attempt_records as _attempt_records, persistence
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext, _AutoRebaseRecoverySnapshot
from orchestrator.workflow.engine import (
    rewrite_landing_moved as _landing_moved,
    rewrite_landing_retirement as _retirement,
)
from tests.workflow.engine import (
    rewrite_captured_test_support as captured_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_moves as moves,
    verification_evidence_test_support as support,
)
from tests.workflow.fixtures import _TEST_SPEC

REBASED = captured_support.REBASED

ANCHOR = support.TESTED_SHA

# The park a reset behind an unverifiable recovery takes.
_PARK_REASON = "auto_base_rebase_push_failed"

# Where the recovery reads the checkout and the remote, off the announced head.
_OFF_THE_LANDING = (
    ("an unmoved checkout back on the anchor", ANCHOR, ANCHOR),
    ("a remote rolled back off the checkout", REBASED, ANCHOR),
    ("a remote and a checkout agreeing on another head", support.SQUASHED_SHA, support.SQUASHED_SHA),
)

# Snapshots that read no head off the announced one: both on it, or a head
# nobody read -- the checkout's would not prove, or the remote's is not yet read.
_NO_HEAD_OFF_IT = (
    ("both heads on the landing", REBASED, REBASED),
    ("a checkout nobody could read beside the landed remote", "", REBASED),
    ("a landed checkout, the remote not yet read", REBASED, ""),
    ("neither head read", "", ""),
)

# Every snapshot a settled run is asked about, and whether it reads a head off the landing.
_SETTLED_SNAPSHOTS = (
    *((*read, True) for read in _OFF_THE_LANDING),
    *((*read, False) for read in _NO_HEAD_OFF_IT),
)

# A checkout whose head would not prove beside the landed remote, which the
# recovery answers by resetting it onto the anchor.
_UNREAD_CHECKOUT = _AutoRebaseRecoverySnapshot(branch=support.BRANCH, local_head="", remote_head=REBASED)

# A reset git answers with each exit status, over a comment with room for the
# run's history or filled to its limit, and the records and anchor it leaves.
_RESETS = (
    ("a landed reset", 0, moves.unmoved, lambda case: (case.abandoned(), None)),
    ("a landed reset with no room", 0, moves.fills_the_comment, lambda case: (captured_support.dropped(case), None)),
    ("a failed reset", 1, moves.unmoved, lambda case: (case.kept(), ANCHOR)),
)


def _snapshot(local: str, remote: str) -> _AutoRebaseRecoverySnapshot:
    return _AutoRebaseRecoverySnapshot(branch=support.BRANCH, local_head=local, remote_head=remote)


def _recovery(case) -> _AutoRebaseRecoveryContext:
    """The recovery context a later tick reads `case`'s standing attempt into."""
    state = case.gh.read_pinned_state(case.issue)
    return _AutoRebaseRecoveryContext(
        gh=case.gh,
        spec=_TEST_SPEC,
        issue=case.issue,
        state=state,
        worktree=case.world.path,
        pr_number=support.PR_NUMBER,
        label=str(finish_support.REVIEWING),
        pending_pre_rebase_sha=ANCHOR,
        pending_rewrite=_attempt_records._pending_rewrite(state),
    )


class LandingMovedTest(unittest.TestCase, captured_support.CapturedEvidenceCase):
    """The run captured for the announced head is abandoned before any road off the landing."""

    def setUp(self) -> None:
        captured_support.CapturedEvidenceCase.setUp(self)

    def test_no_head_read_off_the_landing_keeps_it(self) -> None:
        for read, local, remote in _NO_HEAD_OFF_IT:
            with self.subTest(read=read):
                unmoved = _snapshot(local, remote)

                self.assertTrue(self.asks(_landing_moved.abandons_off_the_landing, self.recovery(), unmoved))

                self.assert_dormant()

    def test_a_snapshot_off_the_landing_abandons(self) -> None:
        for read, local, remote in _OFF_THE_LANDING:
            with self.subTest(read=read):
                self.setUp()
                off_the_landing = _snapshot(local, remote)

                self.assertTrue(self.asks(_landing_moved.abandons_off_the_landing, self.recovery(), off_the_landing))

                self.assert_dormant(self.abandoned())

    def test_no_write_holds_the_road(self) -> None:
        self.gh.pinned_failures.refused.add(self.issue.number)
        unmoved = _snapshot(ANCHOR, ANCHOR)

        self.assertFalse(self.asks(_landing_moved.abandons_off_the_landing, self.recovery(), unmoved))

        self.assert_dormant()

    def test_a_reset_abandons_with_the_attempt(self) -> None:
        # The checkout's head would not read, which moves nothing the run is
        # bound to, so the run stands until the reset the recovery then takes
        # lands; a reset that failed leaves it standing beside the anchor.
        for reset, exit_code, fills, expected in _RESETS:
            with self.subTest(reset=reset):
                self.setUp()
                fills(self)
                self.assertTrue(self.asks(_landing_moved.abandons_off_the_landing, self.recovery(), _UNREAD_CHECKOUT))
                self.assert_dormant()

                self._resets(exit_code)

                self.assert_dormant(*expected(self))

    def recovery(self) -> _AutoRebaseRecoveryContext:
        """The recovery context a later tick reads the standing attempt into."""
        return _recovery(self)

    def _resets(self, exit_code: int) -> None:
        """The git owner's reset-and-park tail, its reset answered with `exit_code`, handed the recovery's answer.

        Under the world's readings, which a reset that did not land proves the
        run again over before its park keeps it.
        """
        recovery = self.recovery()
        answered = replace(recovery, settles_over_a_reset=partial(_retirement.retires_over_the_reset, recovery))
        reset = subprocess.CompletedProcess([], exit_code, "", "")
        with patch.object(commands, "_git_hardened", return_value=reset):
            self.asks(persistence._reset_clear_and_park, answered, ANCHOR, message="parked", reason=_PARK_REASON)


class SettledLandingMovedTest(unittest.TestCase, captured_support.SettledEvidenceCase):
    """Evidence a finish settled for the announced head is invalidated whole before any road off the landing."""

    def setUp(self) -> None:
        captured_support.SettledEvidenceCase.setUp(self)

    def test_a_snapshot_off_the_landing_invalidates(self) -> None:
        # Its revision, binding, and provenance kept in history, so putting
        # the landing back revives nothing; a snapshot that read no head off
        # it keeps it current.
        for read, local, remote, retires in _SETTLED_SNAPSHOTS:
            with self.subTest(read=read):
                self.setUp()
                snapshot = _snapshot(local, remote)

                self.assertTrue(self.asks(_landing_moved.abandons_off_the_landing, _recovery(self), snapshot))

                if retires:
                    self.assert_invalidated()
                else:
                    self.assert_dormant()

    def test_no_write_holds_the_road(self) -> None:
        # Neither the write over the comment read afresh nor the one over the
        # tick's own reading lands: the road holds with the evidence current.
        self.gh.pinned_failures.refused.add(self.issue.number)
        unmoved = _snapshot(ANCHOR, ANCHOR)

        self.assertFalse(self.asks(_landing_moved.abandons_off_the_landing, _recovery(self), unmoved))

        self.assert_dormant()


if __name__ == "__main__":
    unittest.main()
