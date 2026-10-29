# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commit a finished squash owes its relabel over, and what is no commit."""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    handoffs as _late_handoffs,
    keys as _late_keys,
    state as _late_state,
)
from tests.workflow.late_split.generation_test_support import (
    CANDIDATE_SHA,
    SHA_LENGTH,
    measured_generation,
)

# How short an abbreviation has to be to still look like a commit: git prints
# one at this width, and it is not an id this domain ever recorded.
ABBREVIATED = 12

_HANDOFF = _late_handoffs.LATE_COLLAPSE_HANDOFF

# Every value the record can carry and not name a commit: an abbreviation, a
# number, prose, an empty string, and the field simply not being there.
_UNUSABLE = (
    None,
    "",
    CANDIDATE_SHA[:ABBREVIATED],
    CANDIDATE_SHA.upper(),
    "the commit it published",
    1,
)


def _settled() -> PinnedState:
    """A pinned comment carrying the handoff one finished squash left."""
    state = PinnedState(state_data={})
    _late_handoffs.record_settled_handoff(state, CANDIDATE_SHA)
    return state


class SettledHandoffTest(unittest.TestCase):
    """What is left once the rewrite itself is over.

    The push landed and the notice went out, so nothing about the rewrite is
    outstanding -- but the relabel behind it is a second call, and an issue
    left on `validating` with nothing on the comment is one the next tick runs
    a second reviewer on, over a branch already published.
    """

    def test_the_commit_it_was_made_over_reads_back(self) -> None:
        self.assertEqual(
            _late_handoffs.read_settled_handoff(_settled()), CANDIDATE_SHA,
        )

    def test_a_comment_owing_no_move_reads_empty(self) -> None:
        self.assertEqual(
            _late_handoffs.read_settled_handoff(PinnedState(state_data={})), "",
        )

    def test_the_move_that_landed_ends_it(self) -> None:
        state = _settled()
        state.set("branch", "topic")

        _late_handoffs.clear_settled_handoff(state)

        self.assertNotIn(_HANDOFF, state.state_data)
        self.assertEqual(state.get("branch"), "topic")

    def test_a_longer_object_id_is_still_a_commit(self) -> None:
        # git writes SHA-1 and SHA-256 object ids, and this domain records
        # whichever the repository uses.
        state = PinnedState(state_data={})
        wide = "f" * (SHA_LENGTH + 24)

        _late_handoffs.record_settled_handoff(state, wide)

        self.assertEqual(_late_handoffs.read_settled_handoff(state), wide)


class UnusableHandoffTest(unittest.TestCase):
    """A value no commit could equal buys a relabel nobody can check.

    What the record is spent on is a comparison against the head the pull
    request stands on, and on an issue with no pull request to read there is
    nothing else between such a value and a label moved past the reviewer.
    """

    def test_a_value_that_is_not_a_commit_reads_empty(self) -> None:
        for unusable in _UNUSABLE:
            with self.subTest(unusable=unusable):
                state = PinnedState(state_data={_HANDOFF: unusable})

                self.assertEqual(
                    _late_handoffs.read_settled_handoff(state), "",
                )

    def test_a_value_that_is_no_commit_is_not_written(self) -> None:
        # Dropped rather than refused: the write is taken past the push and
        # past the notice, where there is nothing left to call off, so the most
        # it may cost is the reviewer round the record would have saved.
        for unusable in _UNUSABLE:
            with self.subTest(unusable=unusable):
                state = PinnedState(state_data={})

                _late_handoffs.record_settled_handoff(state, unusable)

                self.assertNotIn(_HANDOFF, state.state_data)


class HandoffOutlivesTheGenerationTest(unittest.TestCase):
    """The record survives the write that ends the generation beside it.

    A squash is measured under a generation the gate retires the moment it
    approves the commit, so a record cleared with one would be gone before the
    label it exists to move ever moved.
    """

    def test_clearing_late_mode_leaves_it_standing(self) -> None:
        state = _settled()
        _late_state.write_late_generation(state, measured_generation())

        _late_state.clear_late_generation(state)

        self.assertEqual(
            _late_handoffs.read_settled_handoff(state), CANDIDATE_SHA,
        )

    def test_the_key_is_not_the_generations_own(self) -> None:
        self.assertNotIn(_HANDOFF, _late_keys.LATE_STATE_KEYS)


class HandoffFieldSpellingTest(unittest.TestCase):
    """The wire string live issues would carry."""

    def test_the_key_is_spelled_once(self) -> None:
        self.assertEqual(_HANDOFF, "late_collapse_handoff_sha")


if __name__ == "__main__":
    unittest.main()
