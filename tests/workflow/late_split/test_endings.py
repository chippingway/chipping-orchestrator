# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a cycle's ending records, and what the clear beside it may not take."""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    endings as _endings,
    keys as _late_keys,
    state as _late_state,
)
from tests.workflow.late_split import generation_test_support as _support

_LATER_CYCLE = _support.CYCLE_ID + 1

# Values a hand edit can leave in an identity field. None of them is a cycle,
# so none of them may read back as an ending anything is correlated to.
_NOT_AN_IDENTITY = (0, -1, "2", True, 2.0, None, [_support.CYCLE_ID])


class OutlivesTheClearTest(unittest.TestCase):
    """Both records survive the write that drops the generation's own group."""

    def test_a_clear_leaves_both_ending_records(self) -> None:
        # The whole reason these keys sit outside `LATE_STATE_KEYS`: each is
        # written so the generation CAN be cleared, and a clear that took one
        # would leave the receipt it answers for with nothing to be read
        # against.
        state = PinnedState(state_data={})
        _endings.record_retired_cycle(state, _support.CYCLE_ID)
        _endings.record_terminal(state, _support.CYCLE_ID, confirmed=True)

        _late_state.clear_late_generation(state)

        self.assertEqual(
            _endings.read_retired_cycle(state), _support.CYCLE_ID,
        )
        self.assertTrue(
            _endings.terminal_confirmed(state, _support.CYCLE_ID),
        )

    def test_no_ending_key_is_one_the_generation_owns(self) -> None:
        ending_keys = (
            _endings.LATE_RETIRED_CYCLE_ID,
            _endings.LATE_TERMINAL_CYCLE_ID,
            _endings.LATE_TERMINAL_CONFIRMED,
        )
        for key in ending_keys:
            with self.subTest(key=key):
                self.assertNotIn(key, _late_keys.LATE_STATE_KEYS)


class RetiredCycleTest(unittest.TestCase):
    """Which cycle a clear dropped, read back or not read back at all."""

    def test_a_recorded_cycle_reads_back(self) -> None:
        state = PinnedState(state_data={})
        _endings.record_retired_cycle(state, _support.CYCLE_ID)
        self.assertEqual(
            _endings.read_retired_cycle(state), _support.CYCLE_ID,
        )

    def test_a_damaged_cycle_is_no_retirement(self) -> None:
        for damaged in _NOT_AN_IDENTITY:
            with self.subTest(damaged=damaged):
                state = PinnedState(state_data={
                    _endings.LATE_RETIRED_CYCLE_ID: damaged,
                })
                self.assertIsNone(_endings.read_retired_cycle(state))

    def test_clearing_leaves_the_rest_alone(self) -> None:
        state = PinnedState(state_data={"branch": "orchestrator/issue-9"})
        _endings.record_retired_cycle(state, _support.CYCLE_ID)

        _endings.clear_retired_cycle(state)

        self.assertEqual(state.state_data, {"branch": "orchestrator/issue-9"})


class AppliedTerminalTest(unittest.TestCase):
    """Only this cycle's proved pair says a `rejected` landed."""

    def test_the_decision_alone_is_not_proof(self) -> None:
        # An attempt is not a terminal: a write GitHub refused leaves the
        # issue unlabeled for the reason it always was, and reading the
        # intent as proof would start a fresh cycle on a gesture nobody made.
        state = PinnedState(state_data={})
        _endings.record_terminal(state, _support.CYCLE_ID, confirmed=False)
        self.assertFalse(
            _endings.terminal_confirmed(state, _support.CYCLE_ID),
        )

    def test_an_unconfirmed_write_drops_a_proof(self) -> None:
        # The same field is reused by every cycle this issue ends, so a
        # confirmation left standing would authorize a restart over an
        # attempt that has not landed yet.
        state = PinnedState(state_data={})
        _endings.record_terminal(state, _support.CYCLE_ID, confirmed=True)

        _endings.record_terminal(state, _LATER_CYCLE, confirmed=False)

        self.assertNotIn(_endings.LATE_TERMINAL_CONFIRMED, state.state_data)

    def test_another_cycles_proof_is_not_this_one(self) -> None:
        state = PinnedState(state_data={})
        _endings.record_terminal(state, _support.CYCLE_ID, confirmed=True)
        self.assertFalse(_endings.terminal_confirmed(state, _LATER_CYCLE))

    def test_a_hand_edited_pair_is_not_proof(self) -> None:
        # Both halves are read through the domain's own readers: an identity
        # anybody could have typed, and a flag that is only the literal this
        # domain writes.
        damaged_pairs = (
            (_support.CYCLE_ID, "true"),
            (_support.CYCLE_ID, 1),
            (str(_support.CYCLE_ID), True),
        )
        for recorded, proved in damaged_pairs:
            with self.subTest(recorded=recorded, proved=proved):
                state = PinnedState(state_data={
                    _endings.LATE_TERMINAL_CYCLE_ID: recorded,
                    _endings.LATE_TERMINAL_CONFIRMED: proved,
                })
                self.assertFalse(
                    _endings.terminal_confirmed(state, _support.CYCLE_ID),
                )


if __name__ == "__main__":
    unittest.main()
