# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned comment a review is bound to, and what a verdict's return keeps.

The state a validating tick holds was read when the tick began, so a report
record another road moved since is on the comment and nowhere in hand. A
subject is bound only to a comment carrying the records it was resolved from.
The comment is read again when the verdict comes back: records that stand leave
the state alone, records that moved refuse the verdict and carry everything the
comment changed since the subject was resolved onto the state -- beside what
this tick staged and never wrote -- and a comment that will not read or will
not parse carries nothing and says the tick is to write nothing.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_records as _records
from orchestrator.workflow.stages.validating import review_comment as _review_comment

# The report the reviewer was handed, and the one that settled over it.
HANDED = MappingProxyType({"revision": 1})

SETTLED = MappingProxyType({"revision": 2})

# What the tick staged before the spawn and never wrote, and what the road
# that settled the later report wrote beside it.
STAGED = "review_subject"

STAGED_VALUE = "the subject handed over"

ALSO_SETTLED = "orchestrator_comment_ids"


def _reading(durable: PinnedState | Exception) -> MagicMock:
    """A client whose one read of the pinned comment answers `durable`.

    An exception is a read of the comment that failed.
    """
    github = MagicMock()
    github.read_pinned_state.side_effect = [durable]
    return github


def _returned(durable: PinnedState | Exception) -> tuple[bool | None, dict]:
    """Ask a verdict's return over `durable`; what it answered, and the state after."""
    resolved_over = {_records.CURRENT_REPORT: HANDED}
    state = PinnedState(state_data={**resolved_over, STAGED: STAGED_VALUE})
    github = _reading(durable)
    stood = _review_comment._records_stand(
        github, MagicMock(number=1), state, resolved_over,
    )
    return stood, state.data


class RecordsStandTest(unittest.TestCase):
    """The report records on the comment, as the verdict comes back."""

    def test_records_that_stand_leave_the_state(self) -> None:
        durable = PinnedState(state_data={_records.CURRENT_REPORT: HANDED})

        self.assertEqual(
            _returned(durable),
            (True, {_records.CURRENT_REPORT: HANDED, STAGED: STAGED_VALUE}),
        )

    def test_a_later_settlement_is_carried(self) -> None:
        durable = PinnedState(state_data={
            _records.CURRENT_REPORT: SETTLED, ALSO_SETTLED: [1],
        })

        self.assertEqual(
            _returned(durable),
            (False, {
                _records.CURRENT_REPORT: SETTLED,
                ALSO_SETTLED: [1],
                STAGED: STAGED_VALUE,
            }),
        )

    def test_an_unread_comment_carries_nothing(self) -> None:
        # Neither a comment that will not parse nor a read that failed says
        # the records stand, and neither is a settlement to keep: nothing is
        # carried, and the answer is the one that writes nothing.
        for name, durable in (
            ("unparsed", PinnedState(parsed=False)),
            ("unread", ConnectionError("the request failed")),
        ):
            with self.subTest(name):
                self.assertEqual(
                    _returned(durable),
                    (None, {_records.CURRENT_REPORT: HANDED, STAGED: STAGED_VALUE}),
                )


class ResolvedOverTest(unittest.TestCase):
    """The comment a subject resolved from the state in hand is bound to."""

    def test_only_agreeing_records_bind(self) -> None:
        state = PinnedState(state_data={_records.CURRENT_REPORT: HANDED, STAGED: STAGED_VALUE})
        agreeing = {_records.CURRENT_REPORT: HANDED}
        for name, durable, bound in (
            ("agreeing", PinnedState(state_data=agreeing), agreeing),
            ("settled since", PinnedState(state_data={_records.CURRENT_REPORT: SETTLED}), None),
            ("unparsed", PinnedState(parsed=False), None),
            ("unread", ConnectionError("the request failed"), None),
        ):
            with self.subTest(name):
                self.assertEqual(
                    _review_comment._resolved_over(_reading(durable), MagicMock(number=1), state),
                    bound,
                )


if __name__ == "__main__":
    unittest.main()
