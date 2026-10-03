# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The receipt a split's child carries, and the adoption a recovery may make by it.

Each contract is driven directly here: the wire format, which receipt in a
body governs, and what a recovery short of its count records -- the next
slice's open child on its birth label, with its consumer slot, in one parent
write -- or names for a park. What a split and its recovery do with them is
`test_unrecorded_children`'s subject.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.workflow.late_split.ancestry import LateAncestry
from orchestrator.workflow.stages.decomposition import (
    models as _models,
    replacement_lineage as _replacement_lineage,
    split_receipts as _split_receipts,
    split_seeds as _split_seeds,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakeLabel, make_issue
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition import replacement_lineage_support as _support

KEY_CHILDREN = "children"
KEY_CONSUMERS = "late_consumers"
KEY_SPLIT_ATTEMPT = "split_attempt"

ATTEMPT = "0123456789abcdef"

# The wire receipts for slice 0 owed the root's lineage, and slice 2 owed none.
OWED_RECEIPT = f"<!--orchestrator-split-child:issue=41:attempt={ATTEMPT}:index=0:lineage=41-1-3-1-->"

UNOWED_RECEIPT = f"<!--orchestrator-split-child:issue=41:attempt={ATTEMPT}:index=2:lineage=none-->"

# A receipt another split stamped, quoted where a slice copied that child's body.
QUOTED_RECEIPT = "<!--orchestrator-split-child:issue=990:attempt=fedcba9876543210:index=0:lineage=none-->"

RECORDED_CHILD = 500

# An issue a human opened, carrying a receipt copied out of a child's body.
OUTSIDER = 990

_SLICE = "the declared slice"

KEY_BODY = "body"

KEY_DEPENDS_ON = "depends_on"

# A manifest whose second and third slices wait on the ones before them.
_MANIFEST = (
    {KEY_BODY: "a"},
    {KEY_BODY: "b", KEY_DEPENDS_ON: [0]},
    {KEY_BODY: "c", KEY_DEPENDS_ON: [0, 1]},
)

# Bodies whose receipt is no receipt: prose quoting the format, an attempt this
# binary never mints, a number edited out, and no text at all.
_NO_RECEIPT = (
    "see <!--orchestrator-split-child:issue=<parent>:attempt=<attempt>:index=<slice>:lineage=<owed>-->",
    OWED_RECEIPT.replace(ATTEMPT, "not-an-attempt"),
    OWED_RECEIPT.replace("41-1-3-1", "41--3-1"),
    None,
)

# Attempts on the parent no receipt is looked up by: another split's, one no
# binary mints, a number, and none at all -- what an older binary's split left.
_UNMATCHED_ATTEMPTS = MappingProxyType({
    "another split's attempt": "fedcba9876543210",
    "a hand-edited attempt": ATTEMPT.upper(),
    "a number": 123,
    "no attempt": None,
})


def _close(orphan) -> None:
    orphan.closed = True


def _relabel(orphan) -> None:
    orphan.labels = [FakeLabel(WorkflowLabel.READY)]


def _append_another(orphan) -> None:
    orphan.body = f"{orphan.body}\n\n{QUOTED_RECEIPT}"


def _cut_short(orphan) -> None:
    orphan.body = orphan.body.replace("lineage=none-->", "lineage=broken")


class ReceiptTest(unittest.TestCase):
    """What a split stamps, and which receipt a body is read by."""

    def test_the_wire_format(self) -> None:
        self.assertEqual(_split_receipts.receipt(_support.PARENT, ATTEMPT, 0, _support.ROOT_REPLACEMENT), OWED_RECEIPT)
        for unowed in (None, LateAncestry()):
            with self.subTest(owed=unowed):
                self.assertEqual(_split_receipts.receipt(_support.PARENT, ATTEMPT, 2, unowed), UNOWED_RECEIPT)
        minted = {_split_receipts.mint_attempt() for _ in range(2)}
        self.assertEqual(len(minted), 2)
        self.assertTrue(all(_split_receipts._ATTEMPT.fullmatch(attempt) for attempt in minted))

    def test_a_stamp_follows_the_slice(self) -> None:
        # Reuse instructions ride after the receipt, and only where told.
        manifest = [{"title": "t", KEY_BODY: _SLICE, KEY_DEPENDS_ON: [1]}]
        for lineage in (
            _support.decide(_support.record(_support.own_split())),
            _replacement_lineage.ReplacementLineage(),
        ):
            with self.subTest(pointed=lineage.snapshot is not None):
                stamp = _split_receipts.receipt(_support.PARENT, ATTEMPT, 0, lineage.ancestry)
                body = "\n\n".join(filter(None, (_SLICE, stamp, lineage.instructions)))
                stamped = _split_receipts.stamped(manifest, _support.PARENT, ATTEMPT, lineage)
                self.assertEqual(stamped, [{**manifest[0], KEY_BODY: body}])

    def test_the_last_whole_receipt_governs(self) -> None:
        for body, owed in (
            (f"{_SLICE}\n\n{OWED_RECEIPT}\n\nParent: #41", _support.ROOT_LINEAGE),
            (f"{QUOTED_RECEIPT}\n\n{OWED_RECEIPT}", _support.ROOT_LINEAGE),
            (f"{OWED_RECEIPT}\n\n{UNOWED_RECEIPT}", LateAncestry(parent_issue=_support.PARENT)),
            *((text, None) for text in _NO_RECEIPT),
        ):
            with self.subTest(body=body):
                self.assertEqual(_split_seeds.owed_by(body), owed)


class SplitPlanTest(unittest.TestCase):
    """A plan carries the lineage and attempt its receipts name, and its manifest's whole graph up front."""

    def test_the_declared_graph_precedes_any_child(self) -> None:
        # The graph a recovery holds an adopted slice to is the manifest's,
        # whole, while `record` only knows the slices created so far.
        lineage = _support.decide(_support.record(_support.own_split()))
        plan = _models._SplitPlan.start(list(_MANIFEST), is_umbrella=True)
        plan.record(1, RECORDED_CHILD, _MANIFEST[1])

        self.assertEqual(plan.lineage, _replacement_lineage.ReplacementLineage())
        self.assertEqual(plan.attempt, "")
        self.assertEqual(_models._SplitPlan.start([], False, lineage).lineage, lineage)
        declared = plan.declared_dependencies()
        self.assertEqual(declared, {"1": [0], "2": [0, 1]})
        self.assertEqual(plan.dep_graph, {"1": [0]})


class AdoptionTest(unittest.TestCase):
    """A parent short of its count records the next slice's child, or names why it cannot."""

    def setUp(self, generation=None, recorded: tuple = (), quoted: str = "") -> None:
        self.recorded = list(recorded)
        self.github = FakeGitHubClient([make_issue(_support.PARENT, body=_support.EDITED_BODY)])
        parent_state = _support.record(generation, **{KEY_SPLIT_ATTEMPT: ATTEMPT})
        self.github.seed_state(_support.PARENT, **parent_state.data)
        stamp = _split_receipts.receipt(_support.PARENT, ATTEMPT, len(recorded), None)
        self.orphan = self.github.create_child_issue(
            title="t",
            body=f"{quoted}{_SLICE}\n\n{stamp}",
            parent_number=_support.PARENT,
            labels=[WorkflowLabel.BLOCKED],
        )

    def test_the_next_slice_is_adopted(self) -> None:
        # Recorded -- and protected wherever the parent's lineage points its
        # children at a snapshot -- in one parent write, and seeded by nothing.
        # A receipt its slice quoted ahead of the stamp is no second claim.
        for generation, recorded, quoted in (
            (_support.own_split(), (), ""),
            (None, (RECORDED_CHILD,), ""),
            (_support.own_split(), (), f"{QUOTED_RECEIPT}\n\n"),
        ):
            with self.subTest(late=generation is not None, recorded=recorded, quoted=bool(quoted)):
                self.setUp(generation, recorded, quoted)
                adopted = [*recorded, self.orphan.number]
                protected = generation and sorted((_support.ORIGINAL, self.orphan.number))

                self.assertEqual(self._adopt(), (_split_receipts.Adoption(adopted), 1))
                self.assertEqual(self._ledgers(), (adopted, protected))
                self.assertEqual(self.github.pinned_data(self.orphan.number), {})

    def test_an_unmatched_receipt_is_not_found(self) -> None:
        # Another slice's child -- slice 10 is never slice 1 -- and a body a
        # human wrote the receipt into, beside every attempt nothing minted.
        self.setUp(recorded=(RECORDED_CHILD,))
        self.orphan.body = self.orphan.body.replace("index=1:", "index=10:")
        copied = _split_receipts.receipt(_support.PARENT, ATTEMPT, 1, None)
        self.github.add_issue(make_issue(OUTSIDER, body=copied))
        self._assert_untouched(None)
        for shape, attempt in _UNMATCHED_ATTEMPTS.items():
            with self.subTest(shape=shape):
                self.setUp()
                pinned = self.github.pinned_data(_support.PARENT)
                self.github.seed_state(_support.PARENT, **{**pinned, KEY_SPLIT_ATTEMPT: attempt})
                self._assert_untouched(None)

    def test_a_touched_or_unattributed_orphan_strands(self) -> None:
        # Closed, relabelled, ending on another split's receipt, or ending on
        # its own cut short -- found by the lookup, attributed by nothing.
        for act in (_close, _relabel, _append_another, _cut_short):
            with self.subTest(act=act.__name__):
                self.setUp(_support.own_split())
                act(self.orphan)
                number = self.orphan.number
                self._assert_untouched(f"issue #{number} carries the receipt for slice 0")

    def _adopt(self) -> tuple:
        """Ask the adoption off the parent's record; its answer and the pinned writes it took."""
        before = self.github.write_state_calls
        parent = self.github.get_issue(_support.PARENT)
        state = self.github.read_pinned_state(parent)
        adoption = _split_receipts.adopt_unrecorded(self.github, _TEST_SPEC, parent, state, self.recorded)
        return adoption, self.github.write_state_calls - before

    def _ledgers(self) -> tuple:
        """The children the parent records, and its consumer ledger."""
        pinned = self.github.pinned_data(_support.PARENT)
        return pinned[KEY_CHILDREN], pinned.get(KEY_CONSUMERS)

    def _assert_untouched(self, stranded: str | None) -> None:
        """Nothing adopted or written, and a park sentence carrying `stranded` exactly where one is named."""
        pinned = self.github.pinned_data(_support.PARENT)
        adoption, writes = self._adopt()

        said = adoption.stranded or ""
        self.assertEqual((adoption.children, writes), (self.recorded, 0))
        self.assertEqual(self.github.pinned_data(_support.PARENT), pinned)
        self.assertEqual(bool(said), stranded is not None)
        self.assertIn(stranded or "", said)


if __name__ == "__main__":
    unittest.main()
