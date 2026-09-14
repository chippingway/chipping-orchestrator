# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two-phase restart marker: what it mints, keeps, and refuses to believe."""
from __future__ import annotations

import dataclasses
import unittest

from orchestrator.workflow.late_split import formats as _formats, restart as _restart
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.obligations import LateResourceState
from tests.workflow.late_split import generation_test_support as _support

_IMPLEMENTING = "workflow:implementing"
_CYCLE_KEY = "restart_cycle_id"
_TARGET_KEY = "restart_target"
_PREDECESSOR_KEY = "restart_predecessor"
_REFUSED = _formats.InvalidLateValue
_UNRECONCILED = (
    LateResourceState.PENDING,
    LateResourceState.RETAINED,
    LateResourceState.FAILED,
)


def _owing(recorded_state) -> LateGeneration:
    """A cancelled generation whose one obligation is in `recorded_state`."""
    generation = _support.full_generation()
    return dataclasses.replace(
        generation,
        obligations=generation.obligations.with_resource(
            dataclasses.replace(_support.SNAPSHOT, resource_state=recorded_state),
        ),
    )


def _settled() -> LateGeneration:
    """The same generation with every obligation reconciled."""
    return _owing(LateResourceState.RECONCILED)


class BeginRestartTest(unittest.TestCase):
    """A restart mints one cycle, and resumes the one a crash left behind."""

    def test_a_restart_names_the_cycle_it_intends(self) -> None:
        started = _restart.begin_restart(
            _support.measured_generation(cancelled=True), target=_IMPLEMENTING,
        )
        self.assertTrue(started.restart_pending)
        self.assertEqual(started.restart_target, _IMPLEMENTING)
        self.assertEqual(started.restart_cycle_id, _support.CYCLE_ID + 1)
        self.assertEqual(started.restart_predecessor, _support.CYCLE_ID)

    def test_re_entering_keeps_the_pending_cycle(self) -> None:
        # The crash case: a tick that persisted the marker and died before the
        # label write must resume that cycle, not mint a second one.
        started = _restart.begin_restart(
            _support.measured_generation(), target=_support.DECOMPOSING,
        )
        self.assertEqual(
            _restart.begin_restart(started, target=_IMPLEMENTING), started,
        )

    def test_a_target_no_restart_may_apply_is_refused(self) -> None:
        # Writing it would put a label nobody chose into the pinned comment
        # for a later tick to obey.
        for target in ("workflow:done", "banana", None, _support.CANDIDATE_SHA):
            with self.subTest(target=target), self.assertRaises(_REFUSED):
                _restart.begin_restart(
                    _support.measured_generation(), target=target,
                )

    def test_a_standing_marker_checks_the_target(self) -> None:
        # The argument is a bug whether or not a restart is already in
        # flight, and returning the marker before looking at it would let one
        # through unexamined.
        started = _restart.begin_restart(
            _support.measured_generation(), target=_support.DECOMPOSING,
        )
        with self.assertRaises(_REFUSED):
            _restart.begin_restart(started, target="workflow:done")

    def test_an_unbelievable_marker_is_re_minted(self) -> None:
        # Every way a marker can fail to be one this domain wrote: a cycle
        # that does not follow the current one -- backward, repeated, absent,
        # or a number no audit record has a line for -- a predecessor that is
        # not the cycle being restarted from, and a target no restart may
        # apply. Resuming any of them fabricates a lineage.
        damaged = (
            {_CYCLE_KEY: _support.CYCLE_ID},
            {_CYCLE_KEY: _support.CYCLE_ID - 1},
            {_CYCLE_KEY: None},
            {_CYCLE_KEY: 99},
            {_PREDECESSOR_KEY: 500},
            {_PREDECESSOR_KEY: None},
            {_PREDECESSOR_KEY: _support.CYCLE_ID - 1},
            {_TARGET_KEY: "workflow:done"},
        )
        for fields in damaged:
            with self.subTest(fields=sorted(fields)):
                marker = {
                    "restart_pending": True,
                    _TARGET_KEY: _support.DECOMPOSING,
                    _CYCLE_KEY: _support.CYCLE_ID + 1,
                    _PREDECESSOR_KEY: _support.CYCLE_ID,
                }
                marked = _support.measured_generation(**{**marker, **fields})
                remade = _restart.begin_restart(
                    marked, target=_support.DECOMPOSING,
                )
                self.assertEqual(
                    remade.restart_cycle_id, _support.CYCLE_ID + 1,
                )
                self.assertEqual(remade.restart_target, _support.DECOMPOSING)
                self.assertEqual(
                    remade.restart_predecessor, _support.CYCLE_ID,
                )


class RetireRestartTest(unittest.TestCase):
    """Retiring the marker projects a fresh cycle with a forward identity."""

    def test_retiring_projects_a_fresh_cycle(self) -> None:
        # The fresh cycle is a root with room to split -- not a lineage at the
        # depth the cancelled one reached, and not one whose depth is unknown.
        started = _restart.begin_restart(
            _settled().cancel(_support.CANCELLED_AT),
            target=_support.DECOMPOSING,
        )
        restarted = _restart.retire_restart(started)
        self.assertEqual(
            restarted,
            LateGeneration(
                cycle_id=started.restart_cycle_id,
                root_issue=_support.ROOT_ISSUE,
                current_issue=_support.CURRENT_ISSUE,
                lineage_depth=0,
                restart_predecessor=started.restart_predecessor,
            ),
        )
        self.assertTrue(restarted.may_split)

    def test_a_cycle_that_is_not_the_next_is_refused(self) -> None:
        # A marker naming a cycle at, behind, or well past the one it succeeds
        # would hand the fresh attempt a number an audit record never issued.
        for pending in (_support.CYCLE_ID, _support.CYCLE_ID - 1, 0, None, 2.5, 99):
            with self.subTest(pending=pending):
                marked = self._marked(restart_cycle_id=pending)
                self.assertEqual(
                    _restart.retire_restart(marked).cycle_id,
                    _support.CYCLE_ID + 1,
                )

    def test_a_mismatched_predecessor_is_not_trusted(self) -> None:
        # The ancestry half of the same rule: a predecessor that is not the
        # cycle being retired from is a link nothing wrote, and carrying it
        # forward would join the fresh cycle to an attempt that never ran.
        for predecessor in (500, None, _support.CYCLE_ID - 1, True):
            with self.subTest(predecessor=predecessor):
                marked = self._marked(restart_predecessor=predecessor)
                restarted = _restart.retire_restart(marked)
                self.assertEqual(restarted.cycle_id, _support.CYCLE_ID + 1)
                self.assertEqual(
                    restarted.restart_predecessor, _support.CYCLE_ID,
                )

    def test_an_unreconciled_obligation_refuses(self) -> None:
        # The projection keeps no ledger, so retiring over an obligation that
        # has not settled would discharge it by forgetting it -- leaving the
        # remote holding a ref or a branch no later tick could reclaim.
        for owed in _UNRECONCILED:
            with self.subTest(owed=str(owed)):
                owing = _owing(owed)
                self.assertFalse(_restart.obligations_settled(owing))
                with self.assertRaises(_REFUSED):
                    _restart.retire_restart(owing)

    def test_an_opaque_ledger_refuses(self) -> None:
        # What it could not type it also cannot see the state of.
        for held in ("opaque_resources", "opaque_consumers"):
            with self.subTest(ledger=held):
                settled = _settled()
                opaque = dataclasses.replace(
                    settled,
                    obligations=dataclasses.replace(settled.obligations, **{held: "[1]"}),
                )
                self.assertFalse(_restart.obligations_settled(opaque))
                with self.assertRaises(_REFUSED):
                    _restart.retire_restart(opaque)

    def test_a_discharged_ledger_retires(self) -> None:
        settled = _settled()
        self.assertTrue(_restart.obligations_settled(settled))
        self.assertEqual(
            _restart.retire_restart(settled).cycle_id, _support.CYCLE_ID + 1,
        )

    def _marked(self, **damaged) -> LateGeneration:
        """A pending marker, believable but for what a case damages."""
        marker = {
            "restart_pending": True,
            "restart_target": _support.DECOMPOSING,
            "restart_cycle_id": _support.CYCLE_ID + 1,
            "restart_predecessor": _support.CYCLE_ID,
        }
        return dataclasses.replace(
            _support.measured_generation(), **{**marker, **damaged},
        )


if __name__ == "__main__":
    unittest.main()
