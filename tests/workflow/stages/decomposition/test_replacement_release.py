# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A dependent replacement is released only while its split's lineage still vouches for it.

An ordinary split inside a late lineage proves its children's lineage and
snapshot before it creates them, and starts only the ones with no dependency.
A dependent one is released by a dependency poll later, off a parent record and
a child that may both have changed since: so the same decision is asked again
in front of that release, and the child is held to what a recovery would hold
it to. A child that decision no longer vouches for stays `blocked`, and the
parent parks once rather than on every poll that holds it.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import MappingProxyType

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

_PARKED_ONCE = (_replacement_lineage.PARK_LINEAGE_UNPROVED,)


@dataclass(frozen=True)
class _Change:
    """What changed between the split and the poll that would release its dependent replacement.

    The defaults change nothing: the parent's own snapshot entry `retained`,
    the dependent on its consumer ledger, its seed whole, and its body as the
    split wrote it. `named` is a ref added to that body.
    """

    entry_state: str = "retained"
    kept: bool = True
    stripped: bool = False
    named: str = ""


# Each change, beside the label the dependent ends on and the parks the
# parent takes over two polls. Only the record and the child as the split left
# them vouch for a release.
_CHANGES = MappingProxyType({
    "nothing": (_Change(), WorkflowLabel.READY, ()),
    "a snapshot entry no longer proved": (_Change(entry_state="pending"), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "a snapshot reclaimed": (_Change(entry_state="reconciled"), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "the dependent off the consumer ledger": (_Change(kept=False), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "the dependent's late ancestry taken off": (_Change(stripped=True), WorkflowLabel.BLOCKED, _PARKED_ONCE),
    "another issue's snapshot named in the dependent's body": (
        _Change(named=_FOREIGN_REF), WorkflowLabel.BLOCKED, _PARKED_ONCE,
    ),
})


class DeferredReleaseTest(unittest.TestCase):
    """A dependency poll starts a replacement only as its lineage stands at that poll."""

    def test_only_a_vouched_dependent_is_released(self) -> None:
        for shape, (change, *expected) in _CHANGES.items():
            with self.subTest(shape=shape):
                released = self._released_after(change)

                self.assertEqual(released, tuple(expected))

    def _released_after(self, change: _Change) -> tuple:
        """Where the dependent replacement and the parent's parks stand after two dependency polls.

        The split lands with the snapshot held and both replacements pointed
        at it, the first one then finishes, and `change` is made before the
        polls that would release the second.
        """
        github, issue = _support.late_parent(_support.own_split())
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
        pinned = github.pinned_data(_support.PARENT)
        restated = [
            {**entry, "state": change.entry_state} if entry.get("target") == _support.SNAPSHOT_REF else entry
            for entry in pinned[_RESOURCES]
        ]
        dropped = () if change.kept else (dependent,)
        consumers = [number for number in _support.consumers(github) if number not in dropped]
        github.seed_state(_support.PARENT, **{**pinned, _RESOURCES: restated, _support.KEY_CONSUMERS: consumers})

    def _change_dependent(self, github, change: _Change, dependent: int) -> None:
        """Take the dependent's seed off, and name a ref in its body, where the change says so."""
        if change.stripped:
            kept = {
                key: carried
                for key, carried in github.pinned_data(dependent).items()
                if key not in _lineage.LATE_ANCESTRY_KEYS
            }
            github.seed_state(dependent, **kept)
        if change.named:
            created = github.get_issue(dependent)
            created.body = f"{created.body}\n\nsee also {change.named}"


if __name__ == "__main__":
    unittest.main()
