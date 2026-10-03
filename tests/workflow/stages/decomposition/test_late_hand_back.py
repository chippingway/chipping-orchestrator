# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A late split's parent handed back to work of its own does it on a cycle of its own.

A genuine edit can re-decompose a late split's umbrella into a manifest that
keeps implementation for the parent. Once every child has resolved and what
the split owes the remote is settled, the split's cycle is retired in a write
of its own before the parent leaves `blocked`: the implementation it goes back
to is not that split's superseded candidate, and a later split of it is not
that split's register. A settlement that fails holds the parent for the next
poll, and a close latched in front of the retirement, or observed during it,
is the cycle's ending instead. With or without a cycle to retire, the split's
attempt is off the record before the label moves.
"""
from __future__ import annotations

import unittest
from contextlib import nullcontext
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import observations as _observations, retiring_cycles as _retiring_cycles
from orchestrator.workflow.stages.decomposition import blocked as _blocked
from tests.workflow.fixtures import _TEST_SPEC, _agent, _PatchedWorkflowMixin
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.decomposition import (
    late_cleanup_support as _support,
    late_run_support as _run_support,
    late_test_support as _late,
    replaced_manifest_support as _redecomposition,
)
from tests.workflow.stages.decomposition.late_seam_support import WorktreeSeed

# The parent's record of a live cycle, the one it retired, its ordinary
# split's attempt, its children, and the mark a cancellation leaves.
KEY_CYCLE = "late_cycle_id"

KEY_RETIRED_CYCLE = "late_retired_cycle_id"

KEY_SPLIT_ATTEMPT = "split_attempt"

KEY_CHILDREN = "children"

KEY_CANCELLED = "late_cancelled"

RUN_AGENT = "run_agent"

# A checkout the split's superseded candidate is nowhere in, which is all the
# parent's own implementation has once it is handed back.
GONE_CHECKOUT = Path("/nonexistent/orchestrator-handed-back-checkout")

# The slices a later split of the parent cuts.
LATER_SLICES = 2

# Where a close of the parent can land around its hand-back: latched before the
# walk reaches the retirement, or observed during the write that retires it.
LATCHED_BEFORE = "latched before the hand-back"

CLOSE_WINDOWS = (LATCHED_BEFORE, "observed during the retirement write")


class _LabelledWrites:
    """A client write that keeps every record it puts down beside the parent's label.

    `failing_under` is a label no write lands under: the pass dies there, after
    the label moved and before the record behind it did.
    """

    def __init__(self, client, failing_under: str | None = None) -> None:
        self._client = client
        self._wrote = client.write_pinned_state
        self._failing_under = failing_under
        self.seen: list[tuple[str | None, dict]] = []

    def __call__(self, issue, state):
        label = self._client.workflow_label(issue)
        if label == self._failing_under:
            raise RuntimeError("the pass died before its write landed")
        self.seen.append((label, dict(state.data)))
        return self._wrote(issue, state)

    def retirement(self) -> tuple[str | None, dict]:
        """The label the parent wore, and what it wrote, when its cycle first came off the record."""
        for label, recorded in self.seen:
            if recorded.get(KEY_CYCLE) is None:
                return label, recorded
        raise AssertionError("no write took the cycle off the parent's record")


class _LatchesDuringRetirement:
    """A client whose poll observes the parent's close while its cycle is being retired."""

    def __init__(self, client) -> None:
        self._wrote = client.write_pinned_state

    def __call__(self, issue, state):
        if _retiring_cycles.cycle_being_retired(_TEST_SPEC.slug, issue.number):
            _observations.observe_close(_TEST_SPEC.slug, issue.number)
        return self._wrote(issue, state)


class HandedBackParentTest(ObservedCloseCase, _PatchedWorkflowMixin, unittest.TestCase):
    """The split's cycle is retired before the parent goes back to its own work."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()

    def test_the_handed_back_parent_implements(self) -> None:
        # The cycle and the split's attempt go in a write the parent makes
        # while still `blocked`, keeping both ledgers and the cycle it retired;
        # the next tick is the implementation's own, so the developer runs and
        # nothing goes looking for the superseded candidate.
        seeded = _redecomposition.all_ended()
        writes = _LabelledWrites(seeded.github)
        with patch.object(seeded.github, "write_pinned_state", side_effect=writes):
            _redecomposition.walk(self, seeded, _blocked._handle_blocked)

        mocks = self._run(
            lambda: _blocked._handle_ready(seeded.github, _TEST_SPEC, seeded.parent),
            run_agent=_agent(),
            issue_checkout=GONE_CHECKOUT,
        )

        retired_under, retired = writes.retirement()
        self.assertEqual(retired_under, _support.LABEL_BLOCKED)
        self.assertEqual(retired.get(KEY_RETIRED_CYCLE), _support.CYCLE_ID)
        self.assertIsNone(retired.get(KEY_SPLIT_ATTEMPT))
        self.assertEqual(retired.get("late_consumers"), [_support.CHILD_NUMBER, _support.REPLACEMENT_CHILD])
        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        self.assertNotEqual(
            seeded.github.pinned_data(_support.PARENT_NUMBER).get("park_reason"), "late_measurement_failed",
        )

    def test_a_refused_delete_holds_for_retry(self) -> None:
        # Unsettled, the parent keeps `blocked` and its cycle; the next poll
        # that gets the delete through hands it back.
        seeded = _redecomposition.all_ended()
        github = seeded.github

        refused = _redecomposition.walk(
            self, seeded, _blocked._handle_blocked, _support.SnapshotOutcome.REFUSED,
        )
        self.assertEqual(github.workflow_label(seeded.parent), _support.LABEL_BLOCKED)
        self.assertEqual(_support.resource_states(github)[_support.SNAPSHOT_REF], _support.STATE_FAILED)
        self.assertEqual(github.pinned_data(_support.PARENT_NUMBER).get(KEY_CYCLE), _support.CYCLE_ID)
        retried = _redecomposition.walk(self, seeded, _blocked._handle_blocked)

        self.assertEqual(refused.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(retried.refs, [_support.SNAPSHOT_REF])
        self.assertEqual(_support.resource_states(github)[_support.SNAPSHOT_REF], _support.STATE_RECONCILED)
        self.assertEqual(github.workflow_label(seeded.parent), _support.LABEL_READY)

    def test_a_later_split_cuts_every_slice_afresh(self) -> None:
        # An oversized candidate of the parent's own, split: under the cycle
        # after the one retired, with a register of its own, so every slice
        # is a new child rather than one of the first split's closed ones.
        seeded = _redecomposition.handed_back(self)
        frozen = _redecomposition.oversized_candidate(seeded, GONE_CHECKOUT)
        earlier = len(seeded.github.created_child_issues)

        _run_support.adjudicate(
            seeded.github, seeded.parent, _run_support.agent_reply(_late.SPLIT_REPLY),
            worktree=WorktreeSeed(head=_late.OTHER_SHA), transact=True,
        )

        cut = [child.number for child in seeded.github.created_child_issues[earlier:]]
        self.assertEqual(frozen.cycle_id, _support.CYCLE_ID + 1)
        self.assertEqual(len(cut), LATER_SLICES)
        self.assertEqual(seeded.github.pinned_data(_support.PARENT_NUMBER)[KEY_CHILDREN], cut)

    def test_its_history_hands_on_again(self) -> None:
        # Re-decomposed by a later edit, the parent reaches a hand-off again
        # with the ledgers its retirement kept and no cycle beside them. What
        # they record was settled before that retirement, so neither hand-off
        # is held on it.
        for label, tick in _support.HAND_OFFS.items():
            with self.subTest(parent=label):
                seeded = _redecomposition.resplit(self, label)

                with self.assertNoLogs(_support.WORKFLOW_LOG, level="ERROR"):
                    _redecomposition.walk(self, seeded, tick)

                self.assertEqual(seeded.github.workflow_label(seeded.parent), _support.HANDED_ON[label])

    def test_a_close_ends_the_cycle_instead(self) -> None:
        # The parent stays `blocked` with the cycle back on its record,
        # cancelled, for the ending to run from.
        for when in CLOSE_WINDOWS:
            with self.subTest(when=when):
                self._fresh_process()
                seeded = _redecomposition.all_ended()

                with self._closing(seeded.github, when):
                    _redecomposition.walk(self, seeded, _blocked._handle_blocked)

                pinned = seeded.github.pinned_data(_support.PARENT_NUMBER)
                self.assertEqual(seeded.github.workflow_label(seeded.parent), _support.LABEL_BLOCKED)
                self.assertEqual(pinned.get(KEY_CYCLE), _support.CYCLE_ID)
                self.assertTrue(pinned.get(KEY_CANCELLED))

    def _closing(self, github, when: str):
        """Latch the parent's close before the walk, or inside the write that retires its cycle."""
        if when == LATCHED_BEFORE:
            self._latch_close(_TEST_SPEC.slug, _support.PARENT_NUMBER)
            return nullcontext()
        return patch.object(github, "write_pinned_state", side_effect=_LatchesDuringRetirement(github))


class AttemptBeforeFlipTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A parent with no cycle to retire drops its split's attempt while still `blocked`."""

    def test_the_attempt_clears_ahead_of_the_flip(self) -> None:
        # The flip sets `ready` before its own write, so a pass that dies
        # between the two still leaves no attempt on the record -- on a parent
        # no late split charged, and on one a hand-back left settled history on.
        parents = MappingProxyType({
            "never late": _never_late(),
            "retired history": _redecomposition.resplit(self, _support.LABEL_BLOCKED),
        })
        for shape, seeded in parents.items():
            with self.subTest(parent=shape):
                dying = patch.object(
                    seeded.github, "write_pinned_state",
                    side_effect=_LabelledWrites(seeded.github, failing_under=_support.LABEL_READY),
                )
                with dying, self.assertRaises(RuntimeError):
                    _redecomposition.walk(self, seeded, _blocked._handle_blocked)

                self.assertEqual(seeded.github.workflow_label(seeded.parent), _support.LABEL_READY)
                self.assertIsNone(seeded.github.pinned_data(_support.PARENT_NUMBER).get(KEY_SPLIT_ATTEMPT))


def _never_late() -> _support.SeededUmbrella:
    """A `blocked` parent no late split charged, its one child `done`, under a split attempt."""
    owner = _support.OwnerSeed(label=_support.LABEL_BLOCKED, recorded=False)
    seeded = _support.split_umbrella(None, owner=owner)
    seeded.github.seed_state(
        _support.PARENT_NUMBER, children=[_support.CHILD_NUMBER], split_attempt=_redecomposition.LATER_ATTEMPT,
    )
    return seeded


if __name__ == "__main__":
    unittest.main()
