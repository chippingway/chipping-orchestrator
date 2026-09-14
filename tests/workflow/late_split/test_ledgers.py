# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An external obligation this binary cannot type is one it must not drop."""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import formats as _formats, state as _late_state
from orchestrator.workflow.late_split.obligations import LateResource, LateResourceKind
from tests.workflow.late_split import generation_test_support as _support

_RESOURCES_KEY = "late_resources"
_CONSUMERS_KEY = "late_consumers"
_CYCLE_KEY = "late_cycle_id"
_BRANCH_TARGET = "orchestrator/issue-7"
_KIND = "kind"
_TARGET = "target"
_STATE = "state"
_BRANCH = "branch"
_PENDING = "pending"

# A ledger holding one obligation this binary can act on and one it cannot.
_UNTYPED_RESOURCES = (
    ((_KIND, "starship"), (_TARGET, "x"), (_STATE, _PENDING)),
    ((_KIND, _BRANCH), (_TARGET, _BRANCH_TARGET), (_STATE, _PENDING)),
)


def _untyped_entries() -> list:
    """The ledger as JSON: one entry this binary types, one it cannot."""
    return [dict(entry) for entry in _UNTYPED_RESOURCES]


def _written_ledger() -> PinnedState:
    """A pinned comment holding a ledger this binary wrote itself."""
    state = PinnedState(comment_id=1, state_data={})
    _late_state.write_late_generation(state, _support.full_generation())
    return state


def _untyped_ledger() -> PinnedState:
    state_data = {
        _CYCLE_KEY: _support.CYCLE_ID, _RESOURCES_KEY: _untyped_entries(),
    }
    return PinnedState(comment_id=1, state_data=state_data)


# Each an entry this binary did not write: a state it cannot type, a field it
# never wrote, and a target that is not a usable identifier. Rewriting any of
# them from what was understood would change what the issue records it owes.
_UNRECOGNIZED_ENTRIES = (
    {_KIND: _BRANCH, _TARGET: _BRANCH_TARGET, _STATE: "gone"},
    {_KIND: _BRANCH, _TARGET: _BRANCH_TARGET, _STATE: _PENDING, "why": "x"},
    {_KIND: _BRANCH, _TARGET: _BRANCH_TARGET},
    {_KIND: _BRANCH, _TARGET: "", _STATE: _PENDING},
)


class UnrecognizedEntryTest(unittest.TestCase):
    """An entry this binary did not write comes back exactly as it was."""

    def test_an_unrecognized_shape_survives(self) -> None:
        for entry in _UNRECOGNIZED_ENTRIES:
            with self.subTest(entry=sorted(entry)):
                state = PinnedState(state_data={
                    _CYCLE_KEY: _support.CYCLE_ID, _RESOURCES_KEY: [dict(entry)],
                })
                self.assertTrue(_support.read_state(state).obligations.is_opaque)
                self.assertEqual(
                    _support.rewritten_state(state).data[_RESOURCES_KEY],
                    [entry],
                )

    def test_a_consumer_that_is_not_an_issue_holds(self) -> None:
        # Only a positive whole number is an issue a sweep can ask about, and
        # anything else leaves the ledger opaque rather than dropping it.
        for damaged in (0, -3, True, 2.5, "7"):
            with self.subTest(damaged=damaged):
                state = PinnedState(state_data={
                    _CYCLE_KEY: _support.CYCLE_ID,
                    _CONSUMERS_KEY: [21, damaged],
                })
                self.assertTrue(_support.read_state(state).obligations.is_opaque)
                self.assertEqual(
                    _support.rewritten_state(state).data[_CONSUMERS_KEY],
                    [21, damaged],
                )

    def test_an_uncorrelatable_record_still_owes(self) -> None:
        # The identity beside an obligation being damaged does not discharge
        # it: a write that cleared the ledger would leave a snapshot with
        # nothing on the issue to reclaim it by.
        state = PinnedState(state_data={
            _CYCLE_KEY: "two",
            _RESOURCES_KEY: [dict(_UNRECOGNIZED_ENTRIES[0])],
            _CONSUMERS_KEY: [21],
        })
        self.assertFalse(_support.read_state(state).is_present)
        rewritten = _support.rewritten_state(state).data
        self.assertEqual(rewritten[_RESOURCES_KEY], [_UNRECOGNIZED_ENTRIES[0]])
        self.assertEqual(rewritten[_CONSUMERS_KEY], [21])
        self.assertNotIn(_CYCLE_KEY, rewritten)


class OpaqueUpdateTest(unittest.TestCase):
    """A ledger that is written back verbatim takes no update in the meantime."""

    def test_a_resource_update_is_refused(self) -> None:
        # The write puts the verbatim copy back, so an update accepted here
        # would be returned to the caller and lost at the next persist.
        held = _support.read_state(_untyped_ledger())
        with self.assertRaises(_formats.InvalidLateValue):
            held.obligations.with_resource(
                LateResource(
                    kind=LateResourceKind.BRANCH, target=_BRANCH_TARGET,
                ),
            )

    def test_a_consumer_update_is_refused(self) -> None:
        state = PinnedState(state_data={
            _CYCLE_KEY: _support.CYCLE_ID, _CONSUMERS_KEY: "21,22",
        })
        with self.assertRaises(_formats.InvalidLateValue):
            _support.read_state(state).obligations.with_consumers((21,))

    def test_the_other_ledger_still_takes_one(self) -> None:
        # Only the ledger being written back verbatim is closed: an opaque
        # consumer list does not freeze the obligations beside it.
        state = PinnedState(state_data={
            _CYCLE_KEY: _support.CYCLE_ID, _CONSUMERS_KEY: "21,22",
        })
        recorded = _support.read_state(state).obligations.with_resource(
            LateResource(kind=LateResourceKind.BRANCH, target=_BRANCH_TARGET),
        )
        self.assertEqual(len(recorded.resources), 1)

    def test_a_readable_ledger_takes_updates(self) -> None:
        readable = _support.read_state(_written_ledger())
        self.assertEqual(len(readable.obligations.with_consumers((23,)).consumers), 3)


class OpaqueLedgerTest(unittest.TestCase):
    """An obligation this binary cannot type is still one the remote is owed."""

    def test_an_untypable_entry_survives_a_write(self) -> None:
        # The failure this prevents: a cleanup that looks complete because the
        # binary that rewrote the ledger only understood part of it.
        rewritten = _support.rewritten_state(_untyped_ledger())
        self.assertEqual(rewritten.data[_RESOURCES_KEY], _untyped_entries())

    def test_an_unreadable_consumer_ledger_is_kept(self) -> None:
        # Reading it empty would let a snapshot be reclaimed as though nobody
        # were waiting on it, which is the one thing the ledger prevents.
        for damaged in ("21,22", {"child": 21}, [21, "22"]):
            with self.subTest(damaged=damaged):
                state = PinnedState(state_data={
                    _CYCLE_KEY: _support.CYCLE_ID, _CONSUMERS_KEY: damaged,
                })
                self.assertTrue(_support.read_state(state).obligations.is_opaque)
                self.assertEqual(
                    _support.rewritten_state(state).data[_CONSUMERS_KEY], damaged,
                )

    def test_a_readable_ledger_is_not_opaque(self) -> None:
        written = PinnedState(comment_id=1, state_data={})
        _late_state.write_late_generation(written, _support.full_generation())
        self.assertFalse(_support.read_state(written).obligations.is_opaque)

    def test_an_opaque_ledger_round_trips_unchanged(self) -> None:
        state = _untyped_ledger()
        first = _support.read_state(state)
        self.assertEqual(
            _support.read_state(_support.rewritten_state(state)), first,
        )

    def test_an_untypable_entry_still_types_the_rest(self) -> None:
        read_back = _support.read_state(_untyped_ledger())
        self.assertEqual(
            read_back.obligations.resources,
            (LateResource(
                kind=LateResourceKind.BRANCH, target=_BRANCH_TARGET,
            ),),
        )
        self.assertTrue(read_back.obligations.is_opaque)


if __name__ == "__main__":
    unittest.main()
