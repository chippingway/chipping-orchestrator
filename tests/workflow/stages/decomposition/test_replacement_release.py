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
    split_receipts as _split_receipts,
    split_seeds as _split_seeds,
    umbrella as _umbrella,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.decomposition import (
    replacement_lineage_support as _support,
    replacement_split_support as _split,
)

# A ref no split of this lineage made, which a hand edit can name.
_FOREIGN_REF = "refs/orchestrator/late-split/issue-4/cycle-2/gen-1"

# The ledger key the parent's snapshot entries are pinned under.
_RESOURCES = "late_resources"

# A key of the ancestry group standing with none of the rest.
_STRAY_ANCESTRY_KEY = "late_ancestry_depth"

_PARKED_ONCE = (_replacement_lineage.PARK_LINEAGE_UNPROVED,)

# The parent's number as JSON can spell it and no writer here does: equal to
# the issue number in Python, and no issue number at all.
_FLOAT_LINK = ((_split.KEY_PARENT_NUMBER, float(_support.PARENT)),)


@dataclass(frozen=True)
class _Change:
    """What changed between the split and the poll that would release its two dependent children.

    The defaults change nothing, on a parent whose own split holds the
    snapshot: its snapshot entry `retained`, the dependent on its consumer
    ledger, and the dependents' pinned records and bodies as the split wrote
    them. `ordinary` splits an issue no late split charged instead. Every
    other change is made to the later dependent alone: `stripped` are keys
    taken off its pinned record, `added` are keys put on it over whatever it
    carries, `bare` leaves its body only the
    slice it was declared with, `named` is a ref added to its body, and
    `restamped` rewrites the receipt in its body to owe the other lineage.
    """

    ordinary: bool = False
    entry_state: str = "retained"
    kept: bool = True
    stripped: tuple[str, ...] = ()
    added: tuple[tuple[str, object], ...] = ()
    bare: bool = False
    named: str = ""
    restamped: bool = False


# Each change, beside the label both dependents end on and the parks the parent
# takes over two polls. Only the record and the children as the split left them
# vouch for a release, and every child the poll would release is asked first.
_CHANGES = MappingProxyType({
    "nothing": (_Change(), WorkflowLabel.READY, ()),
    "a snapshot entry no longer proved": (_Change(entry_state="pending"), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "a snapshot reclaimed": (_Change(entry_state="reconciled"), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "the dependent off the consumer ledger": (_Change(kept=False), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "the dependent's late ancestry taken off": (
        _Change(stripped=tuple(_lineage.LATE_ANCESTRY_KEYS)), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "the dependent's parent link taken off": (
        _Change(stripped=(_split.KEY_PARENT_NUMBER,)), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "the dependent's parent link rewritten as a float": (
        _Change(added=_FLOAT_LINK), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "the dependent's parent link rewritten as null": (
        _Change(added=((_split.KEY_PARENT_NUMBER, None),)), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    # What the text is held to is naming no ref the split cannot keep: a
    # protected child told nothing about its ref is still one it keeps.
    "the reuse instructions taken out of the dependent's body": (_Change(bare=True), WorkflowLabel.READY, ()),
    "another issue's snapshot named in the dependent's body": (
        _Change(named=_FOREIGN_REF), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "nothing, under an ordinary split": (_Change(ordinary=True), WorkflowLabel.READY, ()),
    # The receipt is what the dependent's own dispatch holds its seed to, so
    # one owing a lineage the split does not owe it would be released here and
    # held there -- whichever way round the two disagree.
    "the dependent's receipt rewritten to owe no lineage": (
        _Change(restamped=True), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
    "an ordinary split's dependent's receipt rewritten to owe one": (
        _Change(ordinary=True, restamped=True), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
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
    "the only child": (_split.ONE_REPLACEMENT_MANIFEST, 0),
    "the second of two independent children": (_split.REPLACEMENT_MANIFEST, 1),
})


def _reject(github, child) -> None:
    github.set_workflow_label(child, WorkflowLabel.REJECTED, guarded=False)


def _close(_github, child) -> None:
    child.closed = True


def _restamp(github, child, index: int = 0) -> None:
    """Rewrite the receipt in the child's body to owe the other lineage: none where it owed one, else one."""
    attempt = github.pinned_data(_support.PARENT)["split_attempt"]
    owed = _split_seeds.owed_by(child.body)
    stamped = _split_receipts.receipt(_support.PARENT, attempt, index, owed)
    restamped = _split_receipts.receipt(
        _support.PARENT, attempt, index, None if owed.is_present else _support.ROOT_LINEAGE,
    )
    child.body = child.body.replace(stamped, restamped)


# What a human can do to the first child while the split is still creating the
# second, beside the label that child is left on and the park its parent takes:
# reject it, close it, or rewrite the receipt its own dispatch is held to.
_ACTED_ON = MappingProxyType({
    "rejected": (_reject, WorkflowLabel.REJECTED, "child_rejected"),
    "closed short of a terminal": (_close, WorkflowLabel.BLOCKED, "child_manually_closed"),
    "its receipt rewritten to owe no lineage": (_restamp, WorkflowLabel.BLOCKED, _PARKED_ONCE[0]),
})


class _ActsOnFirstSeed:
    """A client on which a human acts on the first child right behind the write that seeds it."""

    def __init__(self, client, act) -> None:
        self._client = client
        self._wrote = client.write_pinned_state
        self._act = act
        self._acted = False

    def __call__(self, issue, state):
        written = self._wrote(issue, state)
        if issue.number != _support.PARENT and not self._acted:
            self._acted = True
            self._act(self._client, issue)
        return written


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
        for shape, (manifest, spared) in _SAME_TICK_LAPSES.items():
            with self.subTest(shape=shape):
                labels, parked = self._released_same_tick(manifest, _SeedsWithoutAncestry, spared)

                self.assertEqual((set(labels), parked), ({WorkflowLabel.BLOCKED}, _PARKED_ONCE))

    def test_a_same_tick_release_reads_every_label(self) -> None:
        # The release reads each child afresh -- its label, and the receipt
        # in its body -- and takes the parent poll's park for one a human acted
        # on, so neither child is relabelled -- not the one acted on, and not
        # its sibling.
        for shape, (act, left_on, parked) in _ACTED_ON.items():
            with self.subTest(shape=shape):
                released = self._released_same_tick(_split.REPLACEMENT_MANIFEST, _ActsOnFirstSeed, act)

                self.assertEqual(released, ([left_on, WorkflowLabel.BLOCKED], (parked,)))

    def test_only_a_vouched_dependent_is_released(self) -> None:
        # Two dependents become releasable on the same later poll, and only
        # the later of them is changed: one that lapses holds its sibling too,
        # since the poll asks every child it would release before the first.
        for shape, (change, label, parked) in _CHANGES.items():
            with self.subTest(shape=shape):
                released = self._released_after(change)

                self.assertEqual(released, (frozenset((label,)), parked))

    def _released_same_tick(self, manifest: str, seeding, how) -> tuple:
        """The label each child ends the split's tick on, in creation order, and the parent's parks.

        Every pinned write the split makes goes through `seeding(client, how)`.
        """
        github, issue = _split.late_parent(_support.own_split())
        with patch.object(github, "write_pinned_state", seeding(github, how)):
            _split.redecompose(github, issue, manifest)
        children = map(github.get_issue, _split.replacements(github))
        labels = [github.workflow_label(child) for child in children]
        return labels, tuple(_split.parks(github))

    def _released_after(self, change: _Change) -> tuple:
        """The labels the two dependent replacements end on, and the parent's parks, after two dependency polls.

        The split lands with the snapshot held and all three replacements
        pointed at it, the first one then finishes, and `change` is made before
        the polls that would release the other two together.
        """
        github, issue = _split.late_parent(None if change.ordinary else _support.own_split())
        _split.redecompose(github, issue, _split.FANNED_MANIFEST)
        first, *dependents = _split.replacements(github)
        github.set_workflow_label(github.get_issue(first), WorkflowLabel.DONE, guarded=False)
        self._change_parent(github, change, dependents[-1])
        self._change_dependent(github, change, dependents[-1])
        for _ in range(2):
            _split.redecompose(github, issue, tick=_umbrella._handle_umbrella)
        return (
            frozenset(github.workflow_label(github.get_issue(number)) for number in dependents),
            tuple(_split.parks(github)),
        )

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
        consumers = [number for number in _split.consumers(github) if number not in dropped]
        github.seed_state(_support.PARENT, **{**pinned, _RESOURCES: restated, _split.KEY_CONSUMERS: consumers})

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
        if change.restamped:
            _restamp(github, created, index=_split.replacements(github).index(dependent))


if __name__ == "__main__":
    unittest.main()
