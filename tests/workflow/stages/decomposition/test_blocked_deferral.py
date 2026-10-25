# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An edit made while a split's child waits on `workflow:blocked`, deferred to the entry to `ready` its release makes.

The family is the one a real split leaves: an umbrella over two slices, the
second waiting on the first. A decomposer splits an issue no late split
charged, or the root of a late lineage whose own split holds the snapshot both
slices are pointed at; a late split's own transaction splits an oversized
issue into slices on its register, pointed at the snapshot it preserves --
and, killed at a seed and resumed from its record, leaves the slice it seeds
then with no baseline. While the first slice is unfinished, every due poll
dispatches the umbrella and the waiting child as a tick dispatches them, and
an edit to the waiting child -- its title, its body, a trusted comment, or all
three across the polls -- moves nothing: no drift check hashes the child, its
baseline and the umbrella's manifest, graph, and late ledger stand as the
split wrote them, and nothing is told, split, relabelled, or run. Once the
first slice is done the umbrella releases the child, and its requirements are
compared on that entry to `ready`: changed ones, and a child its split's
recovery seeded with no baseline, edited or not, reach a decomposer before any
implementer, while a child that reads as its create answered it -- a comment
the hash filters included -- is implemented on that tick. A release a refused
sibling or a refused relabel holds back is made once, later. An operator's
hold on the child or on its umbrella outlasts edits and the prerequisite
alike, and the umbrella's own edit still takes its drift route.
"""
from __future__ import annotations

import itertools
import unittest
from unittest.mock import patch

from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow.stages.decomposition import (
    blocked_deferral_support as _support,
    ready_test_support as _ready,
    replacement_split_support as _split,
)

# Where the umbrella's record keeps whether it is parked for a human.
_AWAITING_HUMAN = "awaiting_human"

# What the polls held behind a refused sibling leave: neither child released,
# the refused record untouched, and no park on the umbrella.
_HELD_BEHIND_A_REFUSAL = ((), (), True, None)

# What the polls an operator's hold stands through leave: no agent run, nothing
# moved, and the waiting child hashed by none of them.
_HELD_THROUGH = (False, True, False)

# The waiting slice's journey once released into a decomposer that splits it:
# rerouted, then an umbrella over slices of its own, with only that decomposer
# run.
_SPLIT_AGAIN = ((WorkflowLabel.READY, WorkflowLabel.DECOMPOSING, WorkflowLabel.UMBRELLA), [0, 1])

# The splits whose slices are late: a late root's decomposer, and a late split's own transaction.
_LATE_SPLITS = (_support.LATE_ROOT, _support.LATE_SPLIT)

# Where a seeded record keeps the root of its late lineage and its depth below it.
_ROOT = "late_ancestry_root_issue"

_DEPTH = "late_ancestry_depth"


class DeferredEditTest(_support.DeferralCase, unittest.TestCase):
    """An edited child waits out its prerequisite untouched, and is decomposed once released."""

    def test_an_edit_waits_for_the_release(self) -> None:
        # A title, a body, a trusted comment, and all three across the polls:
        # nothing moves while the child waits, and once released it is
        # decomposed before anything implements it, the late ledger its
        # split wrote untouched throughout.
        for parent, edited in itertools.product(_support.SPLITS, _support.EDITS):
            with self.subTest(parent=parent, edited=edited):
                family = self.split(parent)
                owed = family.late_fields()

                self.waits_through(family, _support.EDITS[edited])

                self.assertEqual(self.released(family, *_support.DECOMPOSED_ANSWERS), _support.DECOMPOSED_FIRST)
                self.assertEqual(family.late_fields(), owed, "the late ledger is the split's")

    def test_an_unread_landing_is_implemented(self) -> None:
        # Nothing, or only what the hash leaves out, lands while the child
        # waits: released, it reads as its create answered it and is
        # implemented on its first tick, its baseline the one it was seeded
        # with.
        for parent, landed in itertools.product(_support.SPLITS, _support.UNREAD):
            with self.subTest(parent=parent, landed=landed):
                family = self.split(parent)
                seeded = family.baseline()

                self.waits_through(family, _support.UNREAD[landed])

                self.assertEqual(self.released(family, _support.IMPLEMENTER), _support.IMPLEMENTED)
                self.assertEqual(family.baseline(), seeded)

    def test_a_recovered_child_is_decomposed(self) -> None:
        # Its split's recovery seeded it with no baseline: edited while it
        # waits or not, nothing is recorded for it on the way, and released
        # it reaches a decomposer before any implementer, told why.
        for parent, landings in itertools.product(_support.SPLITS, ((), (_support.BODY,))):
            with self.subTest(parent=parent, edited=bool(landings)):
                family = self.split(parent, recovered=True)

                self.waits_through(family, landings)

                self.assertEqual(self.released(family, *_support.DECOMPOSED_ANSWERS), _support.DECOMPOSED_FIRST)
                self.assertEqual(_ready.notices(family.github, family.waiting.number), _support.TOLD_UNBASELINED)


class ReleaseBoundaryTest(_support.DeferralCase, unittest.TestCase):
    """The edited child's release across what holds it back: a refused sibling, and a relabel GitHub refuses."""

    def test_a_refused_release_is_made_once(self) -> None:
        # GitHub refuses the relabel that would release the edited child once
        # its prerequisite is done: that poll releases nothing, and the next
        # one releases it once, so it is decomposed once and implemented once.
        for parent in _support.SPLITS:
            with self.subTest(parent=parent):
                family = self.split(parent)
                refused = _support.RefusedOnce(family.github, family.waiting.number)
                self.waits_through(family, (_support.BODY,))
                family.finish_first()

                with patch.object(family.github, "set_workflow_label", refused), self.assertRaises(RuntimeError):
                    self.poll(family, family.umbrella)

                self.assertEqual(family.relabels(family.waiting.number), ())
                self.assertEqual(self.released(family, *_support.DECOMPOSED_ANSWERS), _support.DECOMPOSED_FIRST)

    def test_a_refused_sibling_holds_both(self) -> None:
        # The edited child's sibling carries a version this build does not
        # admit: once the first slice is done, neither is released, nothing
        # is written to the refused one, and nothing parks. Once its record
        # reads supported again, both are released once, and the edited one
        # is decomposed before anything implements it.
        for parent in _support.PARENTS:
            with self.subTest(parent=parent):
                family = self.split(parent, manifest=_split.FANNED_MANIFEST)
                sibling = family.github.created_child_issues[-1]
                supported = family.github.pinned_data(sibling.number)

                held = self._held_behind(family, sibling)
                family.github.seed_state(sibling.number, **supported)

                self.assertEqual(held, _HELD_BEHIND_A_REFUSAL)
                self.assertEqual(self.released(family, *_support.DECOMPOSED_ANSWERS), _support.DECOMPOSED_FIRST)
                self.assertEqual(family.relabels(sibling.number), (WorkflowLabel.READY,))

    def _held_behind(self, family: _support.Family, sibling) -> tuple:
        """Refuse the sibling's record, wait out an edit, finish the first slice, and poll all three; what that left.

        The relabels of the waiting child and of its sibling, whether the
        refused record was left exactly as it stood, and the umbrella's park.
        """
        recorded = {**family.github.pinned_data(sibling.number), _support.VERSION: _support.UNADMITTED_VERSION}
        family.github.seed_state(sibling.number, raw=True, **recorded)
        self.waits_through(family, (_support.BODY,))
        family.finish_first()
        with self.assertLogs(_support.WORKFLOW_LOG, level="WARNING"):
            self.poll(family, family.umbrella, family.waiting, sibling)
        self.assertFalse(family.waiting_hashed(), "no poll hashed the waiting child")
        return (
            family.relabels(family.waiting.number),
            family.relabels(sibling.number),
            family.github.pinned_data(sibling.number) == recorded,
            family.github.pinned_data(family.umbrella.number).get(_AWAITING_HUMAN),
        )


class HeldFamilyTest(_support.DeferralCase, unittest.TestCase):
    """An operator's hold on the waiting child or on its umbrella, through edits and the prerequisite finishing."""

    def test_a_hold_outlasts_both(self) -> None:
        # Held, the child is not released when its prerequisite finishes --
        # its own hold stops the umbrella's walk short of it, and the
        # umbrella's stops the walk altogether -- and nothing hashes, writes,
        # tells, or runs for it. Lifted, the next poll releases it, and its
        # edits are compared on that entry to `ready`.
        for parent, hold, held in itertools.product(_support.SPLITS, _support.HOLDS, _support.HELD):
            with self.subTest(parent=parent, hold=hold, held=held):
                family = self.split(parent)
                target = family.waiting if held == _support.HELD_CHILD else family.umbrella

                self.assertEqual(self._held_through(family, target, hold), _HELD_THROUGH)
                self.assertEqual(self.released(family, *_support.DECOMPOSED_ANSWERS), _support.DECOMPOSED_FIRST)

    def _held_through(self, family: _support.Family, target, hold: str) -> tuple:
        """Hold `target`, wait out two edits, finish the first slice, poll again, and lift the hold; what the hold saw.

        Whether any of those polls ran an agent, whether the family stood as
        it did, and whether any of them hashed the waiting child.
        """
        target.labels.append(FakeLabel(hold))
        self.waits_through(family, (_support.TITLE, _support.BODY))
        family.finish_first()
        before = family.standing()
        ran = [self.poll(family) for _ in range(_support.POLLS)]
        stood = (any(ran), family.standing() == before, family.waiting_hashed())
        target.labels = [label for label in target.labels if label.name != hold]
        return stood


class EditedUmbrellaTest(_support.DeferralCase, unittest.TestCase):
    """The umbrella over a waiting child, edited as the child is."""

    def test_the_umbrella_takes_its_drift_route(self) -> None:
        # The umbrella is no dependency hold: its own edit reroutes it to its
        # decomposer, orphaning both slices by name, and the late ledger its
        # split wrote stays whole. The waiting child is still asked nothing.
        for parent in _support.SPLITS:
            with self.subTest(parent=parent):
                family = self.split(parent)
                untouched = (family.late_fields(), family.github.pinned_data(family.waiting.number), ())
                _support.BODY(family.github, family.waiting)
                _support.BODY(family.github, family.umbrella)

                self.assertEqual(self.poll(family), 0)

                self.assertEqual(self._rerouted(family), (WorkflowLabel.DECOMPOSING, [], True))
                self.assertEqual(self._left(family), untouched)
                self.assertFalse(family.waiting_hashed())

    def _rerouted(self, family: _support.Family) -> tuple:
        """The umbrella's last label, the children it still tracks, and whether its notice orphans both by name."""
        notice = family.github.posted_comments[-1][1]
        named = all(
            f"#{child.number}" in notice
            for child in (family.first, family.waiting)
        )
        return (
            family.relabels(family.umbrella.number)[-1],
            family.github.pinned_data(family.umbrella.number)["children"],
            named and "ORPHANED" in notice,
        )

    def _left(self, family: _support.Family) -> tuple:
        """The umbrella's late fields, the waiting child's record, and its relabels."""
        return (
            family.late_fields(),
            family.github.pinned_data(family.waiting.number),
            family.relabels(family.waiting.number),
        )


class LateReplacementTest(_support.DeferralCase, unittest.TestCase):
    """A late slice, edited while it waits, released, and split into slices of its own."""

    def test_the_snapshot_stays_owed(self) -> None:
        # A replacement a late root's decomposer pointed at the snapshot, and
        # a slice on a late split's own register. The decomposition its
        # release earns replaces the slice's work with two children of its
        # own, born one level further down the same lineage. The root's ledger
        # is the one its split wrote -- the snapshot still held, the slice
        # still a consumer of it -- and the slice keeps the ancestry and
        # pointer it was seeded with, so the ref is kept for as long as the
        # slice is open.
        for parent in _LATE_SPLITS:
            with self.subTest(parent=parent):
                family = self.split(parent)
                owed = family.late_fields()
                seeded = _ancestry(family.github.pinned_data(family.waiting.number))

                self.assertEqual(self._split_again(family), _SPLIT_AGAIN)

                self.assertEqual(family.late_fields(), owed)
                self.assertIn(family.waiting.number, owed[_split.KEY_CONSUMERS])
                self.assertEqual(_ancestry(family.github.pinned_data(family.waiting.number)), seeded)
                born = (family.umbrella.number, family.waiting.number, seeded[_DEPTH] + 1)
                self.assertEqual(self._born(family), [born, born])

    def _split_again(self, family: _support.Family) -> tuple:
        """Edit the waiting slice through its blocked polls, release it into a splitting decomposer; its journey.

        The umbrella is polled once more behind it, with the slice open.
        """
        self.waits_through(family, (_support.BODY,))
        journey = self.released(family, _support.IMPLEMENTER, _support.SPLITTING)
        self.poll(family, family.umbrella)
        return journey

    def _born(self, family: _support.Family) -> list:
        """Each slice the waiting one was split into: the root it is born under, the parent it links to, its depth."""
        return [
            (record[_ROOT], record[_split.KEY_PARENT_NUMBER], record[_DEPTH])
            for record in map(family.github.pinned_data, _numbers(family.github.created_child_issues[2:]))
        ]


def _numbers(issues) -> list[int]:
    """The issue numbers of `issues`, in order."""
    return [issue.number for issue in issues]


def _ancestry(record: dict) -> dict:
    """The late ancestry group a pinned record carries."""
    return {key: kept for key, kept in record.items() if key.startswith("late_ancestry_")}


if __name__ == "__main__":
    unittest.main()
