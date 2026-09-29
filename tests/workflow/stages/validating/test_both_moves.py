# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pinned field this tick and another road both moved, as a write laid over the comment keeps it.

Usage totals add up the runs each road folded in, the cost tags beside them
join, and a comment-id watermark keeps whichever reading went further. Any
other field -- and a value its writer never records, such as a hand-edited
total -- is one road's to say. What the comment held of a field kept both ways
reads back with this tick's own move taken out, so a later reading measured
against it keeps that move again; a watermark either road moved at all reads
back as the further one.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.validating import state as _state

# The cost tag both readings carried, and the one each road added.
_READ_TAG = "codex"

_OUR_TAG = "claude"

_THEIR_TAG = "agy"

# Each field both moved: what the comment held as they read it, this tick's
# value, and the other road's; what the write keeps, None where the field is
# one road's; and what the comment held of the value kept.
_BOTH_MOVED = (
    ("issue_total_tokens", (100, 120, 130), 150, 130),
    (
        "issue_cost_sources",
        ([_READ_TAG], [_OUR_TAG, _READ_TAG], [_THEIR_TAG, _READ_TAG]),
        [_THEIR_TAG, _OUR_TAG, _READ_TAG],
        [_THEIR_TAG, _READ_TAG],
    ),
    ("last_action_comment_id", (10, 30, 20), 30, 30),
    ("issue_total_tokens", (100, 120, "lots"), None, None),
    ("review_round", (0, 1, 2), None, None),
)


def _kept(field: str, moves: tuple) -> tuple:
    """What a write keeps of `field`, moved `moves` -- read, this tick's, the other road's -- and what the comment held.

    Both None where the field is one road's to say.
    """
    read, ours, theirs = moves
    state = PinnedState(comment_id=1, state_data={field: ours})
    if not _state._keeps_both_moves(state, field, {field: theirs}, {field: read}):
        return None, None
    kept = state.data[field]
    return kept, _state._as_the_comment_held(field, kept, {field: ours}, {field: read})


class BothMovesTest(unittest.TestCase):
    """Which fields keep both roads' moves, and what the comment held of one kept that way."""

    def test_moves_that_add_up_are_both_kept(self) -> None:
        for field, moves, kept, held in _BOTH_MOVED:
            with self.subTest(field, theirs=moves[-1]):
                self.assertEqual(_kept(field, moves), (kept, held))
