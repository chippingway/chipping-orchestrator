# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The lineage an ordinary split's children are born into, inside a late lineage.

A genuine edit hands the ordinary decomposer an issue a late split made, or one
whose own late split it is replacing. The children it answers with are still
cut inside that lineage, so each is seeded one level below its parent under
the same root, and pointed at a snapshot only where the parent's own consumer
ledger keeps that ref for it. A lineage the record cannot prove creates
nothing and starts nothing, and a split a crash interrupted is repaired to the
same lineage before anything can start one of its children.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    lineage as _lineage,
    models as _late_models,
    obligations as _obligations,
)
from orchestrator.workflow.stages.decomposition import replacement_lineage as _replacement_lineage
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import _authorized_exemption
from tests.workflow.stages.decomposition import (
    late_crash_support as _crash,
    replacement_lineage_support as _support,
)

RUN_AGENT = "run_agent"

PARK_EVENT = "park_awaiting_human"

PARK_DECOMPOSITION_CRASH = "decomposition_crash"

# What a descendant that never split is cut from: two levels below the root,
# through an issue that is not the root.
_GRANDPARENT = 40

# A key of the ancestry group standing with none of the rest: a record that
# names no parent and cycle, so no lineage can be read off it.
_STRAY_ANCESTRY_KEY = "late_ancestry_depth"

# What every seed carries beside the lineage, and the group that lineage is.
_SEEDED_LINK = frozenset((_support.KEY_PARENT_NUMBER, _support.KEY_CREATED_AT))

_ANCESTRY_KEYS = frozenset(_lineage.LATE_ANCESTRY_KEYS)


@dataclass(frozen=True)
class _Lineage:
    """One parent's late record, and what its replacements are born with.

    `protected` says whether the parent's own ledger keeps a snapshot for
    them: it is what a pointer on the child and a consumer slot on the parent
    both follow from.
    """

    generation: _late_models.LateGeneration | None
    ancestry: _ancestry.LateAncestry | None
    born: _ancestry.LateAncestry
    protected: bool


def _born(root: int, depth: int, cycle: int = _support.CYCLE, *, pointer: bool) -> _ancestry.LateAncestry:
    """What a replacement of the parent is seeded with."""
    ancestry = _ancestry.LateAncestry(
        root_issue=root,
        lineage_depth=depth,
        parent_issue=_support.PARENT,
        cycle_id=cycle,
        generation=_support.GENERATION,
    )
    if not pointer:
        return ancestry
    return replace(
        ancestry, snapshot_ref=_support.SNAPSHOT_REF, snapshot_sha=_support.CANDIDATE_SHA, mirror_first=True,
    )


_ROOT_REPLACEMENT = _born(_support.PARENT, 1, pointer=True)

_ROOT_LINEAGE = _born(_support.PARENT, 1, pointer=False)

# Root and descendant replacements. The snapshot a descendant was itself cut
# from is its parent's ledger's to keep, so it is never handed down; the one a
# parent's own split holds is, while that ledger still holds it.
_LINEAGES = MappingProxyType({
    "a root that split": _Lineage(_support.own_split(), None, _ROOT_REPLACEMENT, protected=True),
    "a descendant that split": _Lineage(
        _support.own_split(root_issue=_support.ANCESTOR, lineage_depth=1),
        _support.cut_from_ancestor(),
        _born(_support.ANCESTOR, 2, pointer=True),
        protected=True,
    ),
    "a descendant that never split": _Lineage(
        None,
        _support.cut_from_ancestor(depth=2, parent=_GRANDPARENT),
        _born(_support.ANCESTOR, 3, _support.ANCESTOR_CYCLE, pointer=False),
        protected=False,
    ),
    "a root whose ref is gone": _Lineage(
        _support.own_split(_obligations.LateResourceState.RECONCILED), None, _ROOT_LINEAGE, protected=False,
    ),
})

# Parents whose children's lineage cannot be proved, as each is seeded.
_REFUSALS = MappingProxyType({
    "a parent already at the bound": MappingProxyType({
        "ancestry": _support.cut_from_ancestor(depth=_late_models.MAX_LINEAGE_DEPTH, parent=_GRANDPARENT),
    }),
    "an ancestry that names no parent": MappingProxyType({
        "generation": _support.own_split(), _STRAY_ANCESTRY_KEY: 1,
    }),
    "a child receipt with no ancestry": MappingProxyType({
        "body": "\n\n".join((
            _support.EDITED_BODY,
            _ancestry.child_marker(issue=_support.ANCESTOR, cycle=_support.ANCESTOR_CYCLE, generation=1, index=0),
        )),
    }),
})


class _DiesSeedingAChild:
    """A process that dies at the first write to a child's pinned comment.

    The parent's own writes land, which is what puts the child in `children`
    and on the consumer ledger: the crash is the one between that record and
    the seed.
    """

    def __init__(self, client) -> None:
        self._wrote = client.write_pinned_state

    def __call__(self, issue, state):
        if issue.number != _support.PARENT:
            raise KeyboardInterrupt("seed")
        return self._wrote(issue, state)


def _parks(github) -> list:
    """What every park on the parent was filed under."""
    return [
        record.get("reason")
        for record in github.recorded_events
        if record.get("event") == PARK_EVENT and record.get("issue") == _support.PARENT
    ]


class InheritedLineageTest(unittest.TestCase):
    """Replacements are born one level below their parent, never at depth 0."""

    def test_replacements_are_born_below_the_parent(self) -> None:
        for shape, lineage in _LINEAGES.items():
            with self.subTest(shape=shape):
                github, issue = _support.late_parent(lineage.generation, lineage.ancestry)
                recorded = _support.consumers(github)

                _support.redecompose(github, issue)

                self._assert_born(github, lineage, recorded)

    def test_a_seed_carries_nothing_of_the_gate(self) -> None:
        # The parent carries the whole bypass an operator granted a commit of
        # its own; what its children are seeded with is a parent link, a
        # stamp, and a lineage, written fresh.
        bypass = _authorized_exemption(_support.CANDIDATE_SHA, _support.BASE_SHA)
        github, issue = _support.late_parent(_support.own_split(), **bypass)

        _support.redecompose(github, issue)

        for number in _support.replacements(github):
            with self.subTest(child=number):
                seeded = set(github.pinned_data(number))
                self.assertEqual(seeded - _ANCESTRY_KEYS, _SEEDED_LINK)
                self.assertFalse(seeded & set(bypass))

    def _assert_born(self, github, lineage: _Lineage, recorded: list) -> None:
        """Every replacement is tracked, seeded with `lineage`, and protected by it."""
        created = _support.replacements(github)
        seeded = [_support.seeded_ancestry(github, number) for number in created]
        protected = sorted([*recorded, *created]) if lineage.protected else recorded
        self.assertEqual(len(created), _support.REPLACEMENT_COUNT)
        self.assertEqual(github.pinned_data(_support.PARENT)[_support.KEY_CHILDREN], created)
        self.assertEqual(github.workflow_label(github.get_issue(_support.PARENT)), WorkflowLabel.UMBRELLA)
        self.assertEqual(_support.consumers(github), protected)
        self.assertEqual(set(seeded), {lineage.born})


class UnprovedLineageTest(unittest.TestCase):
    """A lineage that cannot be proved parks the split before any child exists."""

    def test_nothing_is_created_or_started(self) -> None:
        for shape, seeded in _REFUSALS.items():
            with self.subTest(shape=shape):
                github, issue = _support.late_parent(**seeded)

                mocks = _support.redecompose(github, issue)

                mocks[RUN_AGENT].assert_called_once()
                self._assert_held(github)

    def _assert_held(self, github) -> None:
        """Nothing created or relabelled, and the park ahead of every marker.

        Ahead of the markers a recovery would read as a split, so the next
        answer is the decomposer's again.
        """
        pinned = github.pinned_data(_support.PARENT)
        self.assertEqual(github.created_child_issues, [])
        self.assertEqual(github.label_history, [])
        self.assertTrue(pinned[_support.KEY_AWAITING_HUMAN])
        self.assertNotIn(_support.KEY_EXPECTED, pinned)
        self.assertEqual(_parks(github), [_replacement_lineage.PARK_LINEAGE_UNPROVED])


class ReplacementCrashTest(unittest.TestCase):
    """A split a crash interrupted is repaired to its lineage before anything starts."""

    def setUp(self) -> None:
        github, issue = _support.late_parent(_support.own_split())
        self.github = github
        self.issue = issue

    def test_a_deferred_seed_is_repaired_first(self) -> None:
        child = self._die_seeding()

        mocks = _support.redecompose(self.github, self.issue)

        mocks[RUN_AGENT].assert_not_called()
        repaired = self.github.pinned_data(child)
        self.assertEqual(_support.replacements(self.github), [child])
        self.assertEqual(_support.seeded_ancestry(self.github, child), _ROOT_REPLACEMENT)
        self.assertEqual(repaired[_support.KEY_PARENT_NUMBER], _support.PARENT)
        # Finalized only once repaired; the walk that starts it comes later.
        self.assertEqual(self._labels(child), (WorkflowLabel.UMBRELLA, WorkflowLabel.BLOCKED))

    def test_an_unprotected_child_gets_no_pointer(self) -> None:
        # Recorded by a split that never put it on the ledger: the lineage is
        # still owed to it, and a pointer nothing keeps is not.
        child = self._die_seeding()
        unprotected = {**self.github.pinned_data(_support.PARENT), _support.KEY_CONSUMERS: [_support.ORIGINAL]}
        self.github.seed_state(_support.PARENT, **unprotected)

        _support.redecompose(self.github, self.issue)

        self.assertEqual(_support.seeded_ancestry(self.github, child), _ROOT_LINEAGE)
        self.assertEqual(_support.consumers(self.github), [_support.ORIGINAL])

    def test_an_unproved_lineage_is_not_finalized(self) -> None:
        # The record the split was proved on no longer proves it.
        child = self._die_seeding()
        damaged = {**self.github.pinned_data(_support.PARENT), _STRAY_ANCESTRY_KEY: 1}
        self.github.seed_state(_support.PARENT, **damaged)

        mocks = _support.redecompose(self.github, self.issue)

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(self.github.pinned_data(child), {})
        self.assertEqual(self._labels(child), (WorkflowLabel.DECOMPOSING, WorkflowLabel.BLOCKED))
        self.assertEqual(_parks(self.github), [_replacement_lineage.PARK_LINEAGE_UNPROVED])

    def test_an_unrecorded_child_is_never_started(self) -> None:
        # The crash before the parent record: the child exists, and nothing
        # on the parent names it -- not `children`, and not the ledger.
        with _crash.killed_after(self.github, "create_child_issue"), self.assertRaises(KeyboardInterrupt):
            _support.redecompose(self.github, self.issue, _support.ONE_REPLACEMENT_MANIFEST)
        orphan = _support.replacements(self.github)[0]

        mocks = _support.redecompose(self.github, self.issue)

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(_support.consumers(self.github), [_support.ORIGINAL])
        self.assertEqual(self.github.pinned_data(orphan), {})
        self.assertEqual(self._labels(orphan), (WorkflowLabel.DECOMPOSING, WorkflowLabel.BLOCKED))
        self.assertEqual(_parks(self.github), [PARK_DECOMPOSITION_CRASH])

    def _die_seeding(self) -> int:
        """Run the split into the crash between its parent record and its seed.

        Reports the child it left: recorded, protected, and seeded with
        nothing at all.
        """
        dying = patch.object(self.github, "write_pinned_state", _DiesSeedingAChild(self.github))
        with dying, self.assertRaises(KeyboardInterrupt):
            _support.redecompose(self.github, self.issue, _support.ONE_REPLACEMENT_MANIFEST)
        child = _support.replacements(self.github)[0]
        self.assertIn(child, _support.consumers(self.github))
        self.assertEqual(self.github.pinned_data(child), {})
        return child

    def _labels(self, child: int) -> tuple:
        """Where the parent and one of its children stand."""
        return (
            self.github.workflow_label(self.issue),
            self.github.workflow_label(self.github.get_issue(child)),
        )


if __name__ == "__main__":
    unittest.main()
