# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A split's child is released only while its split's lineage still vouches for it.

An ordinary split inside a late lineage proves its children's lineage and
snapshot before it creates them. It releases the ones with no dependency in
the same tick, and a dependency poll releases the rest later -- each off a
parent record and a child that may have changed since the proof. So every
release, the first included, asks the same decision again and holds the child
to what a recovery would hold it to; an ordinary split's children, owed no
lineage, are held to the same recognition. A child that no longer passes stays
`blocked`, and the parent parks once rather than on every poll that holds it.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.late_split import lineage as _lineage
from orchestrator.workflow.stages.decomposition import (
    replacement_lineage as _replacement_lineage,
    umbrella as _umbrella,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.decomposition import replacement_lineage_support as _support

# A ref no split of this lineage made, which a hand edit can name.
_FOREIGN_REF = "refs/orchestrator/late-split/issue-4/cycle-2/gen-1"

# The ledger key the parent's snapshot entries are pinned under.
_RESOURCES = "late_resources"

# A key of the ancestry group standing with none of the rest.
_STRAY_ANCESTRY_KEY = "late_ancestry_depth"

_PARKED_ONCE = (_replacement_lineage.PARK_LINEAGE_UNPROVED,)

# The parent's number as JSON can spell it and no writer here does: equal to
# the issue number in Python, and no issue number at all.
_FLOAT_LINK = ((_support.KEY_PARENT_NUMBER, float(_support.PARENT)),)


@dataclass(frozen=True)
class _Change:
    """What changed between the split and the poll that would release its dependent child.

    The defaults change nothing, on a parent whose own split holds the
    snapshot: its snapshot entry `retained`, the dependent on its consumer
    ledger, and the dependent's pinned record and body as the split wrote
    them. `ordinary` splits an issue no late split charged instead.
    `stripped` are keys taken off the dependent's pinned record, `added` are
    keys put on it over whatever it carries, `bare` leaves its body only the
    slice it was declared with, and `named` is a ref added to its body.
    """

    ordinary: bool = False
    entry_state: str = "retained"
    kept: bool = True
    stripped: tuple[str, ...] = ()
    added: tuple[tuple[str, object], ...] = ()
    bare: bool = False
    named: str = ""


# Each change, beside the label the dependent ends on and the parks the
# parent takes over two polls. Only the record and the child as the split left
# them vouch for a release.
_CHANGES = MappingProxyType({
    "nothing": (_Change(), WorkflowLabel.READY, ()),
    "a snapshot entry no longer proved": (_Change(entry_state="pending"), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "a snapshot reclaimed": (_Change(entry_state="reconciled"), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "the dependent off the consumer ledger": (_Change(kept=False), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "the dependent's late ancestry taken off": (
        _Change(stripped=tuple(_lineage.LATE_ANCESTRY_KEYS)), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "the dependent's parent link taken off": (
        _Change(stripped=(_support.KEY_PARENT_NUMBER,)), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "the dependent's parent link rewritten as a float": (
        _Change(added=_FLOAT_LINK), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "the dependent's parent link rewritten as null": (
        _Change(added=((_support.KEY_PARENT_NUMBER, None),)), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    # What the text is held to is naming no ref the split cannot keep: a
    # protected child told nothing about its ref is still one it keeps.
    "the reuse instructions taken out of the dependent's body": (_Change(bare=True), WorkflowLabel.READY, ()),
    "another issue's snapshot named in the dependent's body": (
        _Change(named=_FOREIGN_REF), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "nothing, under an ordinary split": (_Change(ordinary=True), WorkflowLabel.READY, ()),
    "a stray ancestry key on an ordinary split's dependent": (
        _Change(ordinary=True, added=((_STRAY_ANCESTRY_KEY, 1),)), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "an ordinary split's dependent linked by a float": (
        _Change(ordinary=True, added=_FLOAT_LINK), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
})


# Splits whose children all start with the split, each beside how many of
# its first seeds land whole: the only child's lapses, or the second of two
# independent children's does while the first's stands.
_SAME_TICK_LAPSES = MappingProxyType({
    "the only child": (_support.ONE_REPLACEMENT_MANIFEST, 0),
    "the second of two independent children": (_support.REPLACEMENT_MANIFEST, 1),
})


class _SeedsWithoutAncestry:
    """A client whose child seeds land without the late ancestry group, past the first `spared`.

    What the tick that created a child reads back in front of releasing it,
    where anything had taken that group off in between.
    """

    def __init__(self, client, spared: int) -> None:
        self._wrote = client.write_pinned_state
        self._spared = spared

    def __call__(self, issue, state):
        if issue.number != _support.PARENT:
            self._spared -= 1
            if self._spared < 0:
                for key in _lineage.LATE_ANCESTRY_KEYS:
                    state.data.pop(key, None)
        return self._wrote(issue, state)


class DeferredReleaseTest(unittest.TestCase):
    """A child is started only as its split's lineage and its own record stand at the release."""

    def test_a_same_tick_release_checks_every_seed(self) -> None:
        # The split releases its children with no dependency in the tick that
        # created them; a seed read back without its lineage there is held
        # exactly as a later poll would hold it -- and every child the walk
        # would release is asked first, so none starts in front of it.
        for shape, lapse in _SAME_TICK_LAPSES.items():
            with self.subTest(shape=shape):
                released = self._released_same_tick(*lapse)

                self.assertEqual(released, ({WorkflowLabel.BLOCKED}, _PARKED_ONCE))

    def test_only_a_vouched_dependent_is_released(self) -> None:
        for shape, (change, *expected) in _CHANGES.items():
            with self.subTest(shape=shape):
                released = self._released_after(change)

                self.assertEqual(released, tuple(expected))

    def _released_same_tick(self, manifest: str, spared: int) -> tuple:
        """Every label the split's children end its tick on, and the parent's parks, past `spared` whole seeds."""
        github, issue = _support.late_parent(_support.own_split())
        with patch.object(github, "write_pinned_state", _SeedsWithoutAncestry(github, spared)):
            _support.redecompose(github, issue, manifest)
        children = map(github.get_issue, _support.replacements(github))
        labels = {github.workflow_label(child) for child in children}
        return labels, tuple(_support.parks(github))

    def _released_after(self, change: _Change) -> tuple:
        """Where the dependent replacement and the parent's parks stand after two dependency polls.

        The split lands with the snapshot held and both replacements pointed
        at it, the first one then finishes, and `change` is made before the
        polls that would release the second.
        """
        github, issue = _support.late_parent(None if change.ordinary else _support.own_split())
        _support.redecompose(github, issue, _support.DEPENDENT_MANIFEST)
        first, second = _support.replacements(github)
        github.set_workflow_label(github.get_issue(first), WorkflowLabel.DONE, guarded=False)
        self._change_parent(github, change, second)
        self._change_dependent(github, change, second)
        for _ in range(2):
            _support.redecompose(github, issue, tick=_umbrella._handle_umbrella)
        parked = tuple(_support.parks(github))
        return github.workflow_label(github.get_issue(second)), parked

    def _change_parent(self, github, change: _Change, dependent: int) -> None:
        """Put the parent's own snapshot entry at the change's state, and its dependent off the ledger unless kept."""
        if (change.entry_state, change.kept) == (_Change.entry_state, _Change.kept):
            return
        pinned = github.pinned_data(_support.PARENT)
        restated = [
            {**entry, "state": change.entry_state} if entry.get("target") == _support.SNAPSHOT_REF else entry
            for entry in pinned[_RESOURCES]
        ]
        dropped = () if change.kept else (dependent,)
        consumers = [number for number in _support.consumers(github) if number not in dropped]
        github.seed_state(_support.PARENT, **{**pinned, _RESOURCES: restated, _support.KEY_CONSUMERS: consumers})

    def _change_dependent(self, github, change: _Change, dependent: int) -> None:
        """Take keys off the dependent's pinned record, put keys on it, and bare its body or name a ref in it."""
        kept = {
            key: carried
            for key, carried in github.pinned_data(dependent).items()
            if key not in change.stripped
        }
        github.seed_state(dependent, **{**kept, **dict(change.added)})
        created = github.get_issue(dependent)
        if change.bare:
            created.body = created.body.split("\n\n", 1)[0]
        if change.named:
            created.body = f"{created.body}\n\nsee also {change.named}"


if __name__ == "__main__":
    unittest.main()
