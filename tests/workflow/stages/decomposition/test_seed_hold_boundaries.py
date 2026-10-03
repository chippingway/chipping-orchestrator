# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the dispatcher's hold on a split child's seed meets the roads around it.

Each road is driven through the dispatcher a tick routes by: the child's own
adjudication, held all the same; its parent's recovery, which writes the seed
and lifts the park, so the child is released and implemented; and an
operator's restart of its own cycle, which keeps the seed.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.snapshots import mirrors as _snapshot_mirrors
from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.late_split import (
    endings as _endings,
    lineage as _lineage,
    obligations as _obligations,
    state as _late_state,
)
from orchestrator.workflow.stages.decomposition import late_relabel as _late_relabel, umbrella as _umbrella
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, KEY_PARENT_NUMBER, _manifest
from tests.workflow.stages.decomposition import (
    late_crash_support as _crash,
    late_restart_support as _restart,
    late_test_support as _late,
    replacement_lineage_support as _support,
    replacement_split_support as _split,
)

RUN_AGENT = "run_agent"

PARK_HOLD = "replacement_lineage_unproved"

# What the implementer of a released child answers with.
IMPLEMENTED_MESSAGE = "implemented"

# What the decomposer a restarted child reaches answers with: one change, so
# the tick ends on the answer rather than on a split of the child's own.
SINGLE_MANIFEST = _manifest('{"decision": "single", "rationale": "fits"}')

# The prefix every key of a child's late ancestry is pinned under.
_ANCESTRY_PREFIX = "late_ancestry_"

# A ref no split of this lineage made.
_FOREIGN_REF = "refs/orchestrator/late-split/issue-4/cycle-2/gen-1"

# Seeds a child under an adjudication of its own can be left with, each as the
# keys taken off it and the keys written over it: its lineage gone, its parent
# link naming another issue, and its pointer moved elsewhere or cut down to the
# ref alone.
_LAPSES = MappingProxyType({
    "its late ancestry taken off": (tuple(_lineage.LATE_ANCESTRY_KEYS), ()),
    "its parent link naming another issue": ((), ((KEY_PARENT_NUMBER, _support.ANCESTOR),)),
    "its pointer moved to another snapshot": ((), (("late_ancestry_snapshot_ref", _FOREIGN_REF),)),
    "its pointer's commit taken off": (("late_ancestry_snapshot_sha",), ()),
})

# What an unrecorded child carries when its parent next recovers the split:
# nothing at all, as the crash between its create and its record leaves it,
# or its parent link with its lineage taken off by hand.
_HELD_SEEDS = MappingProxyType({
    "never seeded": MappingProxyType({}),
    "linked, its lineage taken off": MappingProxyType({KEY_PARENT_NUMBER: _support.PARENT}),
})

# Splits whose child a restart is asked to keep the seed of, by the parent's
# own record: a lineage whose snapshot was released, so the child is owed the
# lineage and no pointer, and an issue no late split charged, which owes its
# child a parent link and nothing more.
_RESTARTED_SPLITS = MappingProxyType({
    "a lineage with no pointer": _support.own_split(_obligations.LateResourceState.RECONCILED),
    "a parent link alone": None,
})


def _routed(github, spec, issue) -> None:
    """Route one issue the way a tick does, every dispatch guard included."""
    _issue_processing._route_issue_to_handler(github, spec, issue, github.workflow_label(issue))


class _BoundaryCase(unittest.TestCase):
    """One split's parent and child on one client, and what the child's own ticks leave on it."""

    def _split_under(self, generation) -> None:
        """A one-child split of a parent whose own late record is `generation`, run whole."""
        github, parent = _split.late_parent(generation)
        _split.redecompose(github, parent, _split.ONE_REPLACEMENT_MANIFEST)
        self.github = github
        self.parent = parent
        self.child = github.created_child_issues[0]

    def _ticked(self, answer: str = IMPLEMENTED_MESSAGE) -> int:
        """Route the child's own next tick through every dispatch guard; how many agents it ran."""
        mocks = _split.redecompose(self.github, self.child, answer, tick=_routed)
        return mocks[RUN_AGENT].call_count

    def _parks(self) -> tuple:
        """What every park on the child was filed under."""
        parked = (_split.PARK_EVENT, self.child.number)
        return tuple(
            event.get("reason") for event in self.github.recorded_events
            if (event.get("event"), event.get("issue")) == parked
        )

    def _seed(self) -> dict:
        """The parent link and the late ancestry the child's pinned comment carries."""
        return {
            key: carried
            for key, carried in self.github.pinned_data(self.child.number).items()
            if key == KEY_PARENT_NUMBER or key.startswith(_ANCESTRY_PREFIX)
        }

    def _ancestry(self):
        """The late ancestry the child's pinned comment records, read the way every stage reads it."""
        return _lineage.read_late_ancestry(self.github.read_pinned_state(self.child))


class OwnAdjudicationTest(_BoundaryCase):
    """A child adjudicating a candidate of its own is held to its seed like any other road."""

    def test_its_lapsed_seed_spawns_nothing(self) -> None:
        # The live adjudication steps past every other stage's guard on
        # `workflow:decomposing`; the hold is asked ahead of it, so the late
        # decomposer is never spawned over a seed nobody vouches for.
        for shape, lapse in _LAPSES.items():
            with self.subTest(shape=shape):
                self._split_under(_support.own_split())
                self._adjudicated(lapse)

                spawned = [self._ticked() for _ in range(2)]

                self.assertEqual(spawned, [0, 0])
                self.assertEqual(self.github.workflow_label(self.child), WorkflowLabel.DECOMPOSING)
                self.assertEqual(self._parks(), (PARK_HOLD,))

    def _adjudicated(self, lapse: tuple) -> None:
        """Leave the child's seed lapsed, under a live adjudication of an oversized candidate of its own."""
        stripped, added = lapse
        pinned = self.github.read_pinned_state(self.child)
        for key in stripped:
            pinned.data.pop(key, None)
        pinned.data.update(added)
        _late_state.write_late_generation(pinned, _late.late_generation(current_issue=self.child.number))
        self.github.seed_state(self.child.number, **pinned.data)
        self.github.set_workflow_label(self.child, WorkflowLabel.DECOMPOSING, guarded=False)
        self.assertTrue(_late_relabel._adjudicating(self.github.read_pinned_state(self.child)))


class RecoveredChildTest(_BoundaryCase):
    """The recovery that writes a held child's seed lets it run."""

    def test_a_held_child_runs_once_recovered(self) -> None:
        # Held while its seed is short of what its receipt owes, the child is
        # adopted and seeded by its parent's recovery, which lifts the park in
        # the same write; the next poll releases it, and the tick after hands
        # it to its implementer, which runs.
        for shape, left in _HELD_SEEDS.items():
            with self.subTest(shape=shape):
                self._unrecorded(left)
                held = self._ticked()

                recovered = self._recovered()
                _split.redecompose(self.github, self.parent, tick=_umbrella._handle_umbrella)
                implemented = self._implemented()

                self.assertEqual(held, 0)
                self.assertEqual(recovered, (False, (PARK_HOLD,)))
                self.assertEqual(self._ancestry(), _support.ROOT_REPLACEMENT)
                self.assertEqual(implemented, 1)

    def _unrecorded(self, left) -> None:
        """A one-child split dead behind its create, the child it opened carrying `left`."""
        github, parent = _split.late_parent(_support.own_split())
        with _crash.killed_after(github, "create_child_issue"), self.assertRaises(KeyboardInterrupt):
            _split.redecompose(github, parent, _split.ONE_REPLACEMENT_MANIFEST)
        self.github = github
        self.parent = parent
        self.child = github.created_child_issues[0]
        github.seed_state(self.child.number, **left)

    def _recovered(self) -> tuple:
        """The parent's next decomposing tick; whether the child is still parked, and its parks so far."""
        _split.redecompose(self.github, self.parent)
        return self.github.pinned_data(self.child.number)[KEY_AWAITING_HUMAN], self._parks()

    def _implemented(self) -> int:
        """The released child's next tick; how many agents it ran.

        This host still holds the snapshot the child is pointed at, which is
        what its reuse guard asks before anything else.
        """
        with patch.object(_snapshot_mirrors, "local_snapshot_present", return_value=True):
            return self._ticked()


class RestartedChildTest(_BoundaryCase):
    """A restart of the child's own cancelled cycle keeps the seed its receipt names."""

    def test_a_restarted_child_runs(self) -> None:
        # The tick that restarts the cycle runs no handler; the one after hands
        # the child to the stage the restart put it on, with its seed intact.
        for shape, generation in _RESTARTED_SPLITS.items():
            with self.subTest(shape=shape):
                self._split_under(generation)
                seeded = self._seed()
                self._restartable()

                spawned = [self._ticked(SINGLE_MANIFEST) for _ in range(2)]

                self.assertEqual(spawned, [0, 1])
                self.assertEqual(self._seed(), seeded)
                self.assertNotIn(PARK_HOLD, self._parks())

    def test_a_restart_keeps_the_pointer(self) -> None:
        # Pointed at its parent's snapshot, the child keeps the pointer too: its
        # body still tells its implementer to reuse that ref, and the pointer is
        # what its reuse guard checks the ref by.
        self._split_under(_support.own_split())
        self._restartable()

        self._ticked()

        self.assertEqual(self._ancestry(), _support.ROOT_REPLACEMENT)
        self.assertEqual(self._seed()[KEY_PARENT_NUMBER], _support.PARENT)

    def _restartable(self) -> None:
        """Leave the child's own late cycle as an operator authorizing a restart finds it.

        A close cancelled it and the ending settled everything it took on; the
        issue was reopened and its `rejected` taken off.
        """
        pinned = self.github.read_pinned_state(self.child)
        cancelled = replace(_restart.CANCELLED, current_issue=self.child.number)
        _late_state.write_late_generation(pinned, cancelled)
        _endings.record_terminal(pinned, cancelled.cycle_id, confirmed=True)
        self.github.seed_state(self.child.number, **pinned.data)
        self.child.labels = []
        self.assertIsNone(self.github.workflow_label(self.child))


if __name__ == "__main__":
    unittest.main()
