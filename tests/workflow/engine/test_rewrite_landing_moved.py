# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A recovery reading a landed rewrite's landing moved, and the run a finish captured for it abandoned.

The captured case (`rewrite_captured_test_support`), with its attempt read back
the way the recovery reads it. A snapshot with both heads on the announced head
keeps the run for the landed road to finish, and so does one that read no head
off it -- a checkout or remote nobody read moves nothing; any snapshot reading
a head elsewhere abandons it before its road is taken, as the attempt's
checkpoint, or answers that the road must hold where that write was refused,
lost its answer, or met an attempt or evidence record moved by no write of the
recovery's, which stands as it is. A reset the git owner landed releases the
attempt and abandons the run in the park's one write, dropping it where the
comment has no room for its history; a reset that failed keeps both. What the
tick staged and had not written -- a gate's record, a run's usage -- rides the
abandonment's write once. Nothing is run, launched, or routed.
"""
from __future__ import annotations

import subprocess
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.git.base_sync import attempt_records as _attempt_records, persistence
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext, _AutoRebaseRecoverySnapshot
from orchestrator.workflow.engine import rewrite_landing_moved as _landing_moved, verification_records as _records
from tests.workflow.engine import (
    rewrite_captured_test_support as captured_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
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

# What a tick stages before the abandonment and writes only behind it: a run's
# usage over the total the comment carried, and a gate's record of its own.
KEY_TOKENS = "issue_total_tokens"

KEY_GATE_RECORD = "late_measurement_miss_count"

_READ_TOKENS = 100

_STAGED = MappingProxyType({KEY_TOKENS: 150, KEY_GATE_RECORD: 1})

# An anchor the comment comes to carry by no write of the recovery's.
_MOVED_ANCHOR = "0dd0a5c4" * 5

# How the abandonment's write fails to land, beside the evidence records and
# the anchor the comment then carries: refused, and landed with its answer
# lost, as the client names each; and over the evidence floor or the anchor
# the comment came to spell otherwise after the recovery read it.
_UNLANDED = (
    ("refused", "refused", captured_support.CapturedEvidenceCase.kept, ANCHOR),
    ("landed, its answer lost", "lost", captured_support.CapturedEvidenceCase.abandoned, ANCHOR),
    ("the evidence floor moved", (_records.REVISION_FLOOR, 99), captured_support.CapturedEvidenceCase.kept, ANCHOR),
    (
        "the anchor moved",
        (readings.KEY_PENDING_PUSH, _MOVED_ANCHOR),
        captured_support.CapturedEvidenceCase.kept,
        _MOVED_ANCHOR,
    ),
)

# An unmoved checkout back on the anchor, with the remote rolled back onto it.
_ON_THE_ANCHOR = _AutoRebaseRecoverySnapshot(branch=support.BRANCH, local_head=ANCHOR, remote_head=ANCHOR)

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


def _recovery(case: captured_support.CapturedEvidenceCase) -> _AutoRebaseRecoveryContext:
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


def _staged(record) -> dict:
    """What `record` carries of the fields a tick stages ahead of the abandonment."""
    return {key: record.get(key) for key in _STAGED}


class LandingMovedTest(unittest.TestCase, captured_support.CapturedEvidenceCase):
    """The run captured for the announced head is abandoned before any road off the landing."""

    def setUp(self) -> None:
        captured_support.CapturedEvidenceCase.setUp(self)

    def test_no_head_read_off_the_landing_keeps_it(self) -> None:
        for read, local, remote in _NO_HEAD_OFF_IT:
            with self.subTest(read=read):
                unmoved = _snapshot(local, remote)

                self.assertTrue(self.asks(_landing_moved.abandons_off_the_landing, _recovery(self), unmoved))

                self.assert_dormant()

    def test_a_snapshot_off_the_landing_abandons(self) -> None:
        for read, local, remote in _OFF_THE_LANDING:
            with self.subTest(read=read):
                self.setUp()
                off_the_landing = _snapshot(local, remote)

                self.assertTrue(self.asks(_landing_moved.abandons_off_the_landing, _recovery(self), off_the_landing))

                self.assert_dormant(self.abandoned())

    def test_an_unlanded_abandonment_holds_the_road(self) -> None:
        # The road may not go on behind an abandonment that did not land: one
        # refused, one whose answer was lost, and one over an attempt or
        # evidence record moved since the recovery read the comment, which is
        # left exactly as it stands. The tick's state is withheld from any
        # whole-state write behind it.
        for unlanded, breaks, records, anchor in _UNLANDED:
            with self.subTest(unlanded=unlanded):
                self.setUp()
                recovery = _recovery(self)
                self._breaks(breaks)

                self.assertFalse(self.asks(_landing_moved.abandons_off_the_landing, recovery, _ON_THE_ANCHOR))

                self.assert_dormant(records(self), anchor)
                self.assertTrue(recovery.state.withheld)

    def test_a_reset_abandons_with_the_attempt(self) -> None:
        # The checkout's head would not read, which moves nothing the run is
        # bound to, so the run stands until the reset the recovery then takes
        # lands; a reset that failed leaves it standing beside the anchor.
        for reset, exit_code, fills, expected in _RESETS:
            with self.subTest(reset=reset):
                self.setUp()
                fills(self)
                self.assertTrue(self.asks(_landing_moved.abandons_off_the_landing, _recovery(self), _UNREAD_CHECKOUT))
                self.assert_dormant()

                self._resets(exit_code)

                self.assert_dormant(*expected(self))

    def _breaks(self, how) -> None:
        """Fail the next pinned-comment edit as the client names `how`, or set the field `how` pairs on the comment."""
        if isinstance(how, str):
            getattr(self.gh.pinned_failures, how).add(self.issue.number)
            return
        moved = self.gh.read_pinned_state(self.issue)
        moved.set(*how)
        self.gh.write_pinned_state(self.issue, moved)

    def _resets(self, exit_code: int) -> None:
        """The git owner's reset-and-park tail, its reset answered with `exit_code`, handed the recovery's answer.

        Under the world's readings, which a reset that did not land proves the
        run again over before its park keeps it.
        """
        recovery = _recovery(self)
        answered = replace(recovery, settles_over_a_reset=lambda: _landing_moved.abandons_over_the_reset(recovery))
        reset = subprocess.CompletedProcess([], exit_code, "", "")
        with patch.object(commands, "_git_hardened", return_value=reset):
            self.asks(persistence._reset_clear_and_park, answered, ANCHOR, message="parked", reason=_PARK_REASON)


class StagingKeptTest(unittest.TestCase, captured_support.CapturedEvidenceCase):
    """What a tick staged ahead of an abandonment rides that abandonment's write, once."""

    def setUp(self) -> None:
        captured_support.CapturedEvidenceCase.setUp(self)
        state = self.gh.read_pinned_state(self.issue)
        state.set(KEY_TOKENS, _READ_TOKENS)
        self.gh.write_pinned_state(self.issue, state)

    def test_the_abandonment_carries_it_once(self) -> None:
        # The abandonment is the attempt's checkpoint over the reading the
        # tick last confirmed, so what the tick staged since rides it as the
        # tick's own, and the park behind it -- landing over that checkpoint --
        # counts the usage once.
        recovery = _recovery(self)
        recovery.state.data.update(_STAGED)

        self.assertTrue(self.asks(_landing_moved.abandons_off_the_landing, recovery, _ON_THE_ANCHOR))

        self.assert_dormant(self.abandoned())
        self.assertEqual(_staged(readings.pinned(self)), _STAGED)
        self.asks(
            persistence._park_auto_rebase_failure,
            recovery.gh, recovery.issue, recovery.state, message="parked", reason=_PARK_REASON,
        )
        self.assertEqual(_staged(readings.pinned(self)), _STAGED)
        self.assertTrue(readings.pinned(self).get("awaiting_human"))
        self.assert_dormant(self.abandoned())


if __name__ == "__main__":
    unittest.main()
