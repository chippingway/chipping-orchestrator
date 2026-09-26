# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a verdict's return reads off the pinned comment, and what it keeps.

The state a validating tick holds was read before its reviewer ran, so a report
record another road moved meanwhile is on the comment and nowhere in hand. The
comment is read again when the verdict comes back: records that stand leave the
state alone, records that moved refuse the verdict and carry everything the
comment changed since the spawn onto the state -- beside what this tick staged
and never wrote -- and a comment that will not read or will not parse refuses
the verdict and carries nothing.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_records as _records
from orchestrator.workflow.stages.validating import review_coverage as _review_coverage

# The report the reviewer was handed, and the one that settled over it.
HANDED = MappingProxyType({"revision": 1})

SETTLED = MappingProxyType({"revision": 2})

# What the tick staged before the spawn and never wrote, and what the road
# that settled the later report wrote beside it.
STAGED = "review_subject"

STAGED_VALUE = "the subject handed over"

ALSO_SETTLED = "orchestrator_comment_ids"


def _returned(durable: PinnedState | Exception) -> tuple[bool, dict]:
    """Ask a verdict's return over `durable`; what it answered, and the state after.

    An exception is a read of the comment that failed.
    """
    spawned_over = {_records.CURRENT_REPORT: HANDED}
    state = PinnedState(state_data={**spawned_over, STAGED: STAGED_VALUE})
    github = MagicMock()
    github.read_pinned_state.side_effect = [durable]
    moved = _review_coverage._settled_while_it_ran(
        github, MagicMock(number=1), state, spawned_over,
    )
    return moved, state.data


class SettledWhileItRanTest(unittest.TestCase):
    """The report records on the comment, as the verdict comes back."""

    def test_records_that_stand_leave_the_state(self) -> None:
        durable = PinnedState(state_data={_records.CURRENT_REPORT: HANDED})

        self.assertEqual(
            _returned(durable),
            (False, {_records.CURRENT_REPORT: HANDED, STAGED: STAGED_VALUE}),
        )

    def test_a_later_settlement_is_carried(self) -> None:
        durable = PinnedState(state_data={
            _records.CURRENT_REPORT: SETTLED, ALSO_SETTLED: [1],
        })

        self.assertEqual(
            _returned(durable),
            (True, {
                _records.CURRENT_REPORT: SETTLED,
                ALSO_SETTLED: [1],
                STAGED: STAGED_VALUE,
            }),
        )

    def test_an_unread_comment_carries_nothing(self) -> None:
        # Neither a comment that will not parse nor a read that failed says
        # the records stand, and neither is a settlement to keep.
        for name, durable in (
            ("unparsed", PinnedState(parsed=False)),
            ("unread", ConnectionError("the request failed")),
        ):
            with self.subTest(name):
                self.assertEqual(
                    _returned(durable),
                    (True, {_records.CURRENT_REPORT: HANDED, STAGED: STAGED_VALUE}),
                )


if __name__ == "__main__":
    unittest.main()
