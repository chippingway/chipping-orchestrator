# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A child a crash left created and never recorded is found by its receipt before anything starts.

The crash is the one between a split's create and the parent write that would
record the child: the issue exists, and nothing on the parent names it -- not
`children`, and not the consumer ledger. Each child's body carries a receipt
naming its parent, the split's attempt, and its slice, so the recovery that
finds the register short records the child it can find, holds it to the
lineage like any other, and parks where it can find none it may take over.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.workflow.late_split import lineage as _lineage
from orchestrator.workflow.late_split.ancestry import LateAncestry
from orchestrator.workflow.stages.decomposition import split_receipts as _split_receipts, umbrella as _umbrella
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow.stages.decomposition import (
    late_crash_support as _crash,
    replacement_lineage_support as _support,
)

KEY_CHILDREN = "children"
KEY_PARENT_NUMBER = "parent_number"
# The parent's record of which split its children's receipts name.
KEY_SPLIT_ATTEMPT = "split_attempt"

PARK_DECOMPOSITION_CRASH = "decomposition_crash"

RUN_AGENT = "run_agent"

# An attempt some other split minted, in the shape every attempt has.
_OTHER_ATTEMPT = "0123456789abcdef"

# Attempts no receipt of the crashed split names: another split's, a value no
# split mints, and none at all -- what a split an older binary prepared left.
_UNMATCHED_ATTEMPTS = MappingProxyType({
    "another split's attempt": _OTHER_ATTEMPT,
    "a hand-edited attempt": "not-an-attempt",
    "no attempt": None,
})

# The parents a crash is recovered under, beside the ancestry the orphan is
# owed: the root of a late lineage holding the snapshot its own split
# preserved, whose child is pointed at it, and an issue no late split charged,
# whose child is owed none.
_PARENTS = MappingProxyType({
    "a late root": (_support.own_split(), _support.ROOT_REPLACEMENT),
    "an ordinary issue": (None, LateAncestry()),
})

# Where the parent and the orphan stand: the split finalized with the child
# not yet started, the child released, and the split left unfinalized.
_FINALIZED = (WorkflowLabel.UMBRELLA, WorkflowLabel.BLOCKED)
_RELEASED = (WorkflowLabel.UMBRELLA, WorkflowLabel.READY)
_UNFINALIZED = (WorkflowLabel.DECOMPOSING, WorkflowLabel.BLOCKED)

_CRASH_PARKED = (PARK_DECOMPOSITION_CRASH,)


def _seed(github, child: int) -> tuple:
    """The parent link and the ancestry one child's pinned comment records."""
    seeded = github.read_pinned_state(github.get_issue(child))
    return seeded.get(KEY_PARENT_NUMBER), _lineage.read_late_ancestry(seeded)


def _close(orphan) -> None:
    orphan.closed = True


def _relabel(orphan) -> None:
    orphan.labels = [FakeLabel(WorkflowLabel.READY)]


def _receipt_twice(orphan) -> None:
    orphan.body = f"{orphan.body}\n\n{_split_receipts.child_marker(_support.PARENT, _OTHER_ATTEMPT, 1)}"


# What makes an unrecorded child one a recovery may not take over: a human's
# close, a human's relabel, and a second receipt in its body.
_STRANDED = MappingProxyType({
    "closed": _close,
    "moved off its birth label": _relabel,
    "carrying a second receipt": _receipt_twice,
})


class _UnrecordedChildCase(unittest.TestCase):
    """A split interrupted between a create and its record, and the ticks that recover it."""

    def setUp(self, parent: str = "a late root") -> None:
        generation, owed = _PARENTS[parent]
        github, issue = _support.late_parent(generation)
        self.github = github
        self.issue = issue
        self.owed = owed

    def _die_recording(self, answer: str = _support.ONE_REPLACEMENT_MANIFEST, created: int = 1) -> int:
        """Run the split into the crash behind its `created`-th create, and report the child it opened."""
        dying = _crash.killed_after(self.github, "create_child_issue", after=created)
        with dying, self.assertRaises(KeyboardInterrupt):
            _support.redecompose(self.github, self.issue, answer)
        orphan = _support.replacements(self.github)[-1]
        self.assertNotIn(orphan, self._recorded())
        return orphan

    def _recover(self) -> None:
        """The next decomposing tick, which a recovery answers without the decomposer."""
        mocks = _support.redecompose(self.github, self.issue)
        mocks[RUN_AGENT].assert_not_called()

    def _recorded(self) -> list:
        return self.github.pinned_data(_support.PARENT).get(KEY_CHILDREN) or []

    def _register(self) -> tuple:
        """Every child the split opened, beside the ones the parent records."""
        return _support.replacements(self.github), self._recorded()

    def _labels(self, child: int) -> tuple:
        """Where the parent and one of its children stand."""
        return (
            self.github.workflow_label(self.issue),
            self.github.workflow_label(self.github.get_issue(child)),
        )

    def _parked(self, named: str) -> tuple:
        """The parks the parent took, and whether the notice it last posted says `named`."""
        notice = self.github.posted_comments[-1][1]
        return tuple(_support.parks(self.github)), named in notice


class AdoptionTest(_UnrecordedChildCase):
    """The child found by its receipt is recorded, then held to the recovery like any recorded child."""

    def test_the_last_child_is_adopted(self) -> None:
        # Recorded, protected where its split owes it the snapshot, and seeded
        # as the split would have seeded it -- with no second issue opened for
        # its slice -- then finalized, and released by the parent's next poll.
        for parent in _PARENTS:
            with self.subTest(parent=parent):
                self.setUp(parent)
                orphan = self._die_recording()

                self._recover()
                finalized = self._labels(orphan)
                _support.redecompose(self.github, self.issue, tick=_umbrella._handle_umbrella)

                protected = bool(self.owed.snapshot_ref)
                self.assertEqual(self._register(), ([orphan], [orphan]))
                self.assertEqual(orphan in _support.consumers(self.github), protected)
                self.assertEqual(_seed(self.github, orphan), (_support.PARENT, self.owed))
                self.assertEqual((finalized, self._labels(orphan)), (_FINALIZED, _RELEASED))
                self.assertEqual(_support.parks(self.github), [])

    def test_a_dying_recovery_is_retried(self) -> None:
        # The recovery's own record of the child lands and the process dies
        # behind it: the retry reads a complete register and protects, seeds,
        # and finalizes exactly as one uninterrupted recovery would.
        orphan = self._die_recording()
        dying = _crash.killed_after(self.github, "write_pinned_state")
        with dying, self.assertRaises(KeyboardInterrupt):
            self._recover()
        recorded = (self._recorded(), self.github.pinned_data(orphan))

        self._recover()

        self.assertEqual(recorded, ([orphan], {}))
        self.assertEqual(self._register(), (recorded[0], recorded[0]))
        self.assertCountEqual(_support.consumers(self.github), [_support.ORIGINAL, orphan])
        self.assertEqual(_seed(self.github, orphan), (_support.PARENT, self.owed))
        self.assertEqual(self._labels(orphan), _FINALIZED)

    def test_an_adopted_dependent_waits(self) -> None:
        # The crash lands on the second child, which waits on the first. The
        # graph was recorded before either existed, so the adopted child is
        # held until the first is done rather than released beside it.
        orphan = self._die_recording(_support.DEPENDENT_MANIFEST, created=2)

        self._recover()
        _support.redecompose(self.github, self.issue, tick=_umbrella._handle_umbrella)

        first = _support.replacements(self.github)[0]
        self.assertEqual(self._recorded(), [first, orphan])
        self.assertEqual(self._labels(first), _RELEASED)
        self.assertEqual(self._labels(orphan), _FINALIZED)


class StrandedTest(_UnrecordedChildCase):
    """Where no unrecorded child can be taken over, or the register stays short, the split parks."""

    def test_a_short_register_parks(self) -> None:
        # The crash lands on the first of two: adopting it leaves a slice
        # nobody created, and the manifest it was declared in is not kept, so
        # the split parks with the orphan recorded and opens nothing.
        orphan = self._die_recording(_support.REPLACEMENT_MANIFEST)

        self._recover()

        self.assertEqual(self._register(), ([orphan], [orphan]))
        self.assertEqual(self._labels(orphan), _UNFINALIZED)
        self.assertEqual(self._parked("1 of 2"), (_CRASH_PARKED, True))

    def test_a_touched_orphan_is_left(self) -> None:
        # A candidate a human acted on, or whose receipt is ambiguous, is
        # named in the park rather than adopted or created again.
        for shape, act in _STRANDED.items():
            with self.subTest(shape=shape):
                self.setUp()
                orphan = self._die_recording()
                act(self.github.get_issue(orphan))

                self._recover()

                self.assertEqual(self._register(), ([orphan], []))
                self.assertEqual(self.github.pinned_data(orphan), {})
                self.assertEqual(self._parked(f"#{orphan}"), (_CRASH_PARKED, True))

    def test_only_this_splits_receipt_counts(self) -> None:
        # Only the attempt this split minted names its receipts; any other
        # attempt on the parent finds nothing, and the split parks as before.
        for shape, attempt in _UNMATCHED_ATTEMPTS.items():
            with self.subTest(shape=shape):
                self.setUp()
                orphan = self._die_recording()
                pinned = self.github.pinned_data(_support.PARENT)
                self.github.seed_state(_support.PARENT, **{**pinned, KEY_SPLIT_ATTEMPT: attempt})

                self._recover()

                self.assertEqual(self._recorded(), [])
                self.assertEqual(self.github.pinned_data(orphan), {})
                self.assertEqual(self._parked("0 of 1"), (_CRASH_PARKED, True))


if __name__ == "__main__":
    unittest.main()
