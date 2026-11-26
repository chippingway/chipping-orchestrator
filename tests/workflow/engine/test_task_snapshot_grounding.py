# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an implementing conversation was handed, as a task snapshot of it is bound to.

A fresh conversation is handed its prompt's requirements: the road's own, or
what the road re-grounds a fresh one with. A resumed one is handed nothing
new, so it holds what the pinned record says it was grounded on -- while that
record still speaks for it: the same conversation, under the same baseline.
Another conversation, a baseline a road has since settled, or a record no
reading parses says nothing, and the road's own answers. The record is kept
only where the conversation was handed something other than the baseline.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import task_snapshot_grounding as _grounding

_BASELINE = "baseline-revision"
_EDITED = "edited-revision"
_ROAD = "road-revision"
_SESSION = "replacement-session"
_OTHER = "another-session"
_HASH = "user_content_hash"


def _state(**fields) -> PinnedState:
    return PinnedState(comment_id=1, state_data={_HASH: _BASELINE, **fields})


def _grounded(session: str = _SESSION, baseline: str = _BASELINE) -> dict:
    """The record of `session` grounded on the edit under `baseline`."""
    return {"session_id": session, "requirements": _EDITED, "baseline": baseline}


# Records that speak for the resumed conversation, and those that do not.
_SILENT_RECORDS = (
    ("another conversation", _grounded(_OTHER)),
    ("a settled baseline", _grounded(baseline=_ROAD)),
    ("a damaged record", "not a record"),
    ("a record without requirements", {"session_id": _SESSION, "baseline": _BASELINE}),
    ("no record", None),
)


class HandedTest(unittest.TestCase):
    """What each attempt's conversation was handed."""

    def test_a_fresh_conversation_has_its_prompts(self) -> None:
        state = _state(**{_grounding.GROUNDING: _grounded()})
        self.assertEqual(_grounding.handed(state, None, None, _ROAD), _ROAD)
        self.assertEqual(_grounding.handed(state, None, _EDITED, _ROAD), _EDITED)

    def test_a_resumed_one_keeps_its_grounding(self) -> None:
        state = _state(**{_grounding.GROUNDING: _grounded()})
        self.assertEqual(_grounding.handed(state, _SESSION, None, _ROAD), _EDITED)

    def test_a_stale_record_says_nothing(self) -> None:
        for name, record in _SILENT_RECORDS:
            with self.subTest(record=name):
                state = _state(**{_grounding.GROUNDING: record})
                self.assertEqual(_grounding.handed(state, _SESSION, _EDITED, _ROAD), _ROAD)


class RememberTest(unittest.TestCase):
    """The record staged beside an attempt's return."""

    def test_only_what_differs_is_kept(self) -> None:
        state = _state()
        _grounding.remember(state, _SESSION, _EDITED)
        self.assertEqual(state.get(_grounding.GROUNDING), _grounded())
        _grounding.remember(state, _OTHER, _BASELINE)
        self.assertIsNone(state.get(_grounding.GROUNDING))

    def test_nothing_is_staged_without_a_conversation(self) -> None:
        state = _state()
        _grounding.remember(state, None, _EDITED)
        self.assertFalse(state.carries(_grounding.GROUNDING))


if __name__ == "__main__":
    unittest.main()
