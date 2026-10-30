# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The holds a pending captured completion waits through.

An operator's `paused` or `backlog`, a dependency hold, the `ready`
decision that answers one, an issue a human unlabeled, and a spent run
ledger each keep the capture as it stands: nothing is handed on, retired,
released, re-baselined, or charged, and each stage that runs there runs as
it would with no capture -- a dependency hold beside an auto-rebase anchor
included, which the anchor's own hold answers while the base refresh keeps
the branch for the capture. A late revision is handed on over the live
adjudication it answers, and held over one nobody can read. The handoff a
capture is frozen over is in `test_frozen_handoff`.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.base_sync import refresh_selection as _refresh_selection
from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_records as _records,
    completion_recovery as _recovery,
    completion_recovery_models as _models,
    completion_routes as _routes,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import completion_dispatch_support as _dispatch, completion_recovery_support as _support
from tests.workflow.engine.completion_turn_support import Turn
from tests.workflow.fixtures import _TEST_SPEC

_NUMBER = _support.NUMBER
_IMPLEMENTING = str(WorkflowLabel.IMPLEMENTING)

# What a spent run ledger's park stands on, and the charges beside it.
_RUN_LIMIT_PARK = MappingProxyType({"awaiting_human": True, "park_reason": "agent_run_limit"})

_CHARGES = ("agent_runs_used", "issue_agent_runs")

# The holds a capture waits through, by the labels the issue wears, and whether a stage handler runs there.
_WAITS = (
    ((str(WorkflowLabel.BLOCKED),), True),
    ((str(WorkflowLabel.READY),), True),
    ((), False),
)

_PAUSED = Turn(labels=(_IMPLEMENTING, PAUSED_LABEL))

_PARKED = Turn(edits=_RUN_LIMIT_PARK)

_BLOCKED = Turn(labels=(str(WorkflowLabel.BLOCKED),))

# An auto-rebase anchor a hand edit left beside the capture, the park its own
# hold answers one carrying no terms with, and a human's reconciliation of both.
_ANCHOR = "pending_auto_base_rebase_push_sha"
_ANCHORED = MappingProxyType({_ANCHOR: _support.BEFORE})
_STRANDED = "auto_base_rebase_failed"
_RECONCILED = MappingProxyType(dict.fromkeys((_ANCHOR, "awaiting_human", "park_reason"), _support.DROPPED))

# A hand edit leaving that adjudication's ceiling as nothing its reader takes.
_UNREADABLE_MEASUREMENT = Turn(edits=MappingProxyType({"late_threshold": "unreadable"}))


def _revised_world() -> tuple[_support.CapturedWorld, _records.CompletionCapture]:
    """A world under a live late adjudication, its developer revision captured in that adjudication's cycle."""
    world = _support.CapturedWorld(WorkflowLabel.DECOMPOSING)
    world.hand_edit(**_support.ADJUDICATING)
    return world, world.captured(_support.road(_routes.CompletionRoute.LATE_REVISION, WorkflowLabel.DECOMPOSING))


class WaitingCaptureTest(unittest.TestCase):
    """A hold the capture waits through leaves it captured, and the stage runs as it would."""

    def test_a_dependency_hold_keeps_it(self) -> None:
        # The dependency walk and the ready decision run; an issue a human
        # unlabeled is left where they left it. None of them is handed the
        # capture, and nothing is written over it -- no release, no baseline.
        for labels, handled in _WAITS:
            with self.subTest(labels=labels):
                world = _support.CapturedWorld()
                world.captured()

                seen = _dispatch.observed(world, _dispatch.RoadOwner(), Turn(labels=labels))

                ran = (_NUMBER,) if handled else ()
                self.assertEqual((seen.ran, seen.handed), (ran, ()))
                self.assertTrue(seen.untouched)

    def test_an_anchor_beside_a_wait_keeps_it(self) -> None:
        # The capture waits through the dependency hold rather than being
        # retired for the anchor: the anchor's own hold answers it, on a
        # label the base refresh does not drive, with a park that leaves the
        # checkout where it stands, and holds the walk for that tick. Once a
        # human reconciles it, the walk runs; the capture is pending all
        # along, and the refresh keeps its branch on either side.
        world = _support.CapturedWorld()
        captured = world.captured()
        world.hand_edit(**_ANCHORED)

        held = _dispatch.observed(world, _dispatch.RoadOwner(), _BLOCKED)
        self.assertEqual((held.ran, held.handed), ((), ()))
        self.assertEqual(held.after["park_reason"], _STRANDED)
        self.assertTrue(self._branch_kept(world))
        world.hand_edit(**_RECONCILED)
        walked = _dispatch.observed(world, _dispatch.RoadOwner())

        self.assertEqual((walked.ran, walked.handed), ((_NUMBER,), ()))
        self.assertTrue(self._branch_kept(world))
        for seen in (held, walked):
            self.assertEqual(_support.read_capture(seen.after), captured)

    def test_an_operator_control_keeps_all_off(self) -> None:
        # Applied before the dispatch, nothing is read and nothing reached;
        # and on the one road a held issue is let through -- a close somebody
        # observed -- the recovery stands down without a reading.
        world = _support.CapturedWorld()
        world.captured()

        seen = _dispatch.observed(world, _dispatch.RoadOwner(), _PAUSED)

        self.assertEqual((seen.ran, seen.handed), ((), ()))
        self.assertTrue(seen.untouched)
        state = world.github.read_pinned_state(world.issue)
        with world.checkout(), patch.object(world.github, "get_issue", side_effect=AssertionError("read")):
            self.assertFalse(_recovery.capture_holds_the_tick(
                world.github, _TEST_SPEC, world.issue, WorkflowLabel.IMPLEMENTING, state,
            ))

    def test_a_run_limit_park_holds_first(self) -> None:
        # Recovering paid work buys no run: the spent ledger's hold is asked
        # first, and the park, the charges, and the capture all stand.
        world = _support.CapturedWorld()
        world.captured()

        seen = _dispatch.observed(world, _dispatch.RoadOwner(), _PARKED)

        self.assertEqual((seen.ran, seen.handed), ((), ()))
        self.assertEqual(seen.after[_support.FIELD], seen.before[_support.FIELD])
        parked = {key: seen.after[key] for key in _RUN_LIMIT_PARK}
        self.assertEqual(parked, dict(_RUN_LIMIT_PARK))
        charged = {seen.after[key] for key in _CHARGES}
        self.assertEqual(charged, {_support.RUNS_USED})

    def test_a_resolved_capture_leaves_the_stage(self) -> None:
        world = _support.CapturedWorld()
        captured = world.captured()
        state = world.github.read_pinned_state(world.issue)
        _checkpoint.retire(world.github, world.issue, state, captured.invocation, _records.RetirementReason.INVALIDATED)

        seen = _dispatch.observed(world, _dispatch.RoadOwner())

        self.assertEqual((seen.ran, seen.handed), ((_NUMBER,), ()))
        self.assertTrue(seen.untouched)

    def _branch_kept(self, world: _support.CapturedWorld) -> bool:
        """Whether the base refresh holds the world's branch still over its pinned comment as it reads now."""
        state = world.github.read_pinned_state(world.issue)
        return _refresh_selection._state_holds_the_branch(_NUMBER, state)


class LateRevisionTest(unittest.TestCase):
    """A late revision is handed on over the live adjudication it answers, and held over one nobody can read."""

    def test_a_live_adjudication_hands_it_on(self) -> None:
        world, captured = _revised_world()

        seen = _dispatch.observed(world, _dispatch.RoadOwner())

        self.assertEqual([admitted.capture for admitted in seen.handed], [captured])

    def test_an_unreadable_measurement_holds_it(self) -> None:
        # A measurement that will not read is no live adjudication to the
        # reader that asks, and no proof one ended either: the capture is
        # kept, with nothing written, handed on, or run.
        world, captured = _revised_world()

        seen = _dispatch.observed(world, _dispatch.RoadOwner(), _UNREADABLE_MEASUREMENT)

        held = seen.says(_models.Reason.PREREQUISITE_UNREAD, _models.Standing.UNCERTAIN)
        self.assertTrue(held, seen.said)
        self.assertEqual(_support.read_capture(seen.after), captured)
        self.assertEqual((seen.ran, seen.handed), ((), ()))
        self.assertTrue(seen.untouched)


if __name__ == "__main__":
    unittest.main()
