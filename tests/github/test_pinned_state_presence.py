# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a pinned comment carries a field, apart from what it holds.

The question a reader asking whether the record CLAIMS something has to
ask, and the one a value reading cannot answer for it: every fail-closed
reader in this repository turns a value nothing can act on into an absence,
so an issue that never wrote a field and one whose field a hand edit
truncated come back alike.
"""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState

_FIELD = "branch"
_WRITTEN = "orchestrator/issue-7"


class PinnedStateFieldPresenceTest(unittest.TestCase):
    """Whether the comment CARRIES a field, apart from what it holds.

    The question a reader asking whether the record claims something has to
    ask, and the one `get` cannot answer for it: a fail-closed reader turns a
    value nothing can act on into an absence, so an issue that never wrote a
    field and one whose field a hand edit truncated come back alike.
    """

    def test_a_field_that_was_written_is_carried(self) -> None:
        self.assertTrue(PinnedState(state_data={_FIELD: _WRITTEN}).carries(
            _FIELD,
        ))

    def test_a_field_nothing_wrote_is_not(self) -> None:
        self.assertFalse(PinnedState(state_data={}).carries(_FIELD))

    def test_a_value_that_reads_as_nothing_counts(self) -> None:
        # The payload is JSON, so a field can be present and `null` -- an
        # older binary writing a value this one reads as nothing, or a hand
        # edit. Asked as a value it would be indistinguishable from an issue
        # that never wrote the field, which is the gap this exists to close.
        for described, written in (
            ("null", None), ("empty", ""), ("truncated", _WRITTEN[:3]),
        ):
            with self.subTest(value=described):
                state = PinnedState(state_data={_FIELD: written})

                self.assertTrue(state.carries(_FIELD))


if __name__ == "__main__":
    unittest.main()
