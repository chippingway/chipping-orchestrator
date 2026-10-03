# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A split's child whose seed is not the one its receipt owes it is held, and one whose seed is runs.

No dispatcher asks the hold yet, so it is driven directly against one child
this orchestrator opened carrying a receipt. A seed is whole when it links
exactly the receipt's parent and carries exactly the lineage the receipt owes
-- none on a child owed none -- and a pointer only at that split's snapshot,
or none once the child's own guard dropped it.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.decomposition import split_receipts as _split_receipts, split_seeds as _split_seeds
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.stages.decomposition import replacement_lineage_support as _support

KEY_PARENT_NUMBER = "parent_number"
KEY_AWAITING_HUMAN = "awaiting_human"

PARK_HOLD = "replacement_lineage_unproved"

PARK_EVENT = "park_awaiting_human"

CHILD = 500

ATTEMPT = "0123456789abcdef"

_FOREIGN_REF = "refs/orchestrator/late-split/issue-4/cycle-2/gen-1"

# The receipts this split stamps on a child owed the root's lineage, and on one owed none.
_OWED_STAMP = _split_receipts.receipt(_support.PARENT, ATTEMPT, 0, _support.ROOT_LINEAGE)

_UNOWED_STAMP = _split_receipts.receipt(_support.PARENT, ATTEMPT, 0, None)

# Another split's receipt, quoted ahead of the stamp where a slice copied that child's body.
_QUOTED_RECEIPT = "<!--orchestrator-split-child:issue=990:attempt=fedcba9876543210:index=0:lineage=41-1-3-1-->"

_WHOLE = _support.seeded(_support.ROOT_REPLACEMENT)

_REF = "late_ancestry_snapshot_ref"

_SHA = "late_ancestry_snapshot_sha"

# Seeds a child owed the root's lineage is held on: never landed, linked by no
# issue number or another, the group gone, partial, or rewritten, pointed at a
# snapshot that split never preserved, or carrying half a pointer.
_LAPSED = MappingProxyType({
    "never seeded": {},
    "a link and no lineage": _support.seeded(),
    "the parent as a float": {**_WHOLE, KEY_PARENT_NUMBER: float(_support.PARENT)},
    "the parent as a string": {**_WHOLE, KEY_PARENT_NUMBER: str(_support.PARENT)},
    "a boolean link": {**_WHOLE, KEY_PARENT_NUMBER: True},
    "another parent": {**_WHOLE, KEY_PARENT_NUMBER: 999},
    "part of the group": {key: kept for key, kept in _WHOLE.items() if key != "late_ancestry_cycle_id"},
    "its depth rewritten": {**_WHOLE, "late_ancestry_depth": 0},
    "a field its reader would drop": {**_WHOLE, "late_ancestry_generation": "first"},
    "a foreign pointer": {**_WHOLE, _REF: _FOREIGN_REF},
    "a ref without its commit": {key: kept for key, kept in _WHOLE.items() if key != _SHA},
    "a commit without its ref": {key: kept for key, kept in _WHOLE.items() if key != _REF},
})

# Seeds that run: the whole one, the lineage with the pointer its guard dropped
# once the ref went, and -- on an ordinary split's child -- the link alone.
_RUNNABLE = MappingProxyType({
    "a whole seed": (_OWED_STAMP, _WHOLE),
    "a pointer retired after release": (
        _OWED_STAMP, _support.seeded(_support.ROOT_REPLACEMENT.without_snapshot()),
    ),
    "an ordinary child under a quoted receipt": (f"{_QUOTED_RECEIPT}\n\n{_UNOWED_STAMP}", _support.seeded()),
})


class _ChildCase(unittest.TestCase):
    """One child this orchestrator opened carrying a receipt, unless a case names another body or author."""

    def setUp(self, receipt: str | None = None, author: str | None = None) -> None:
        stamp = receipt or _OWED_STAMP
        self.github = FakeGitHubClient()
        opened_by = author or self.github._bot_login
        self.child = make_issue(CHILD, body=f"the slice\n\n{stamp}", author=opened_by)
        self.github.add_issue(self.child)

    def _holds(self, label, state: PinnedState) -> bool:
        return _split_seeds.holds_unseeded(self.github, self.child, label, state)

    def _parks(self) -> list:
        """What every park on the child was filed under."""
        return [
            event.get("reason") for event in self.github.recorded_events
            if event.get("event") == PARK_EVENT and event.get("issue") == CHILD
        ]


class UnseededChildTest(_ChildCase):
    """A lapsed seed is held under a park said once; an unreadable one is held with nothing written."""

    def test_a_lapsed_seed_is_held_once(self) -> None:
        for shape, carried in _LAPSED.items():
            with self.subTest(shape=shape):
                self.setUp()
                state = PinnedState(data=dict(carried))
                held = [self._holds(WorkflowLabel.READY, state) for _ in range(2)]

                self.assertEqual(held, [True, True])
                self.assertTrue(state.get(KEY_AWAITING_HUMAN))
                self.assertEqual(self._parks(), [PARK_HOLD])
                self.assertEqual(len(self.github.posted_comments), 1)

    def test_an_unreadable_comment_is_held_untouched(self) -> None:
        # The park's write would replace the comment with the empty payload
        # standing in for it, so the hold writes and says nothing, every tick.
        self.github.seed_state(CHILD, **_WHOLE)
        recorded = self.github.read_pinned_state(self.child)
        state = PinnedState(comment_id=recorded.comment_id, parsed=False)

        held = [self._holds(WorkflowLabel.READY, state) for _ in range(2)]

        self.assertEqual(held, [True, True])
        self.assertEqual(self.github.write_state_calls, 0)
        self.assertEqual(self.github.pinned_data(CHILD), _WHOLE)
        self.assertEqual(state.data, {})
        self.assertEqual(len(self.github.posted_comments), 0)
        self.assertEqual(self._parks(), [])

    def test_any_lineage_on_a_child_owed_none_is_held(self) -> None:
        self.setUp(_UNOWED_STAMP)

        self.assertTrue(self._holds(None, PinnedState(data=_WHOLE)))
        self.assertEqual(self._parks(), [PARK_HOLD])


class RunnableChildTest(_ChildCase):
    """A whole seed, and an issue that is no split's child, run with nothing held or written."""

    def test_a_whole_seed_runs(self) -> None:
        for shape, (receipt, carried) in _RUNNABLE.items():
            with self.subTest(shape=shape):
                self.setUp(receipt)
                state = PinnedState(data=dict(carried))

                self.assertFalse(self._holds(WorkflowLabel.DECOMPOSING, state))
                self.assertEqual(state.data, carried)
                self.assertEqual(self._parks(), [])

    def test_no_split_child_is_held(self) -> None:
        # A terminal, a body a human wrote the receipt into, and one carrying none.
        for shape, label, author, receipt in (
            ("done", WorkflowLabel.DONE, None, None),
            ("rejected", WorkflowLabel.REJECTED, None, None),
            ("a copied receipt", WorkflowLabel.READY, "geserdugarov", None),
            ("no receipt", WorkflowLabel.READY, None, "Parent: #41"),
        ):
            with self.subTest(shape=shape):
                self.setUp(receipt, author)

                self.assertFalse(self._holds(label, PinnedState()))
                self.assertEqual(self._parks(), [])


if __name__ == "__main__":
    unittest.main()
