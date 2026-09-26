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
not parse carries nothing and says the tick is to write nothing. So does a
reading of another comment than the one the state was read from -- the pinned
comment replaced or gone -- whatever records it carries, since the tick's write
names the comment it read. Records are compared as the comment spells them, so
one written `null` where there was none, or a revision spelled `true` where it
was `1`, is a move.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_records as _records
from orchestrator.workflow.stages.validating import review_comment as _review_comment

# The revision of the report the reviewer was handed, and of the one that
# settled over it.
HANDED = 1

SETTLED = 2

# What the tick staged before the spawn and never wrote, and what the road
# that settled the later report wrote beside it.
STAGED = "review_subject"

STAGED_VALUE = "the subject handed over"

ALSO_SETTLED = "orchestrator_comment_ids"

# The pinned comment the tick read, and the one that replaced it since.
PINNED_ID = 5_579_000_001

REPLACEMENT_ID = 5_579_000_002


def _current(revision: object) -> dict:
    """The comment's report records, with the current report at `revision`."""
    return {_records.CURRENT_REPORT: {"revision": revision}}


def _pinned(state_data: dict, comment_id: int = PINNED_ID) -> PinnedState:
    """The pinned comment read afresh, carrying `state_data`."""
    return PinnedState(comment_id=comment_id, state_data=state_data)


def _in_hand() -> dict:
    """The state the tick holds: the handed report, and what it staged."""
    return {**_current(HANDED), STAGED: STAGED_VALUE}


# Every fresh reading that is not the comment the tick read: one that will not
# parse, a read that failed, the comment replaced -- with the handed records or
# a later settlement -- and the comment gone. None of them is ever written to.
NO_COMMENT_IN_HAND = (
    ("unparsed", PinnedState(parsed=False)),
    ("unread", ConnectionError("the request failed")),
    ("replaced, records unchanged", _pinned(_current(HANDED), REPLACEMENT_ID)),
    ("replaced, records moved", _pinned(_current(SETTLED), REPLACEMENT_ID)),
    ("gone", PinnedState()),
)


def _reading(durable: PinnedState | Exception) -> MagicMock:
    """A client whose one read of the pinned comment answers `durable`.

    An exception is a read of the comment that failed.
    """
    github = MagicMock()
    github.read_pinned_state.side_effect = [durable]
    return github


def _returned(
    durable: PinnedState | Exception,
) -> tuple[bool | None, dict, int | None]:
    """Ask a verdict's return over `durable`: its answer, and the state after.

    The state after is its data and the comment it names.
    """
    state = _pinned(_in_hand())
    stood = _review_comment._records_stand(
        _reading(durable), MagicMock(number=1), state, _current(HANDED),
    )
    return stood, state.data, state.comment_id


class RecordsStandTest(unittest.TestCase):
    """The report records on the comment, as the verdict comes back."""

    def test_records_that_stand_leave_the_state(self) -> None:
        self.assertEqual(
            _returned(_pinned(_current(HANDED))), (True, _in_hand(), PINNED_ID),
        )

    def test_a_later_settlement_is_carried(self) -> None:
        # Carried as the comment spells it -- a damaged record included, which
        # Python would call equal to the one handed over, so the comparison is
        # of the JSON the comment is written as -- and no write the run makes
        # puts the handed record back over it.
        for name, durable_data in (
            ("a later revision", {**_current(SETTLED), ALSO_SETTLED: [1]}),
            ("a record written null", {
                **_current(HANDED), _records.PENDING_REPORT: None,
            }),
            ("a revision spelled true", _current(True)),
        ):
            with self.subTest(name):
                stood, carried, comment_id = _returned(_pinned(durable_data))

                self.assertIs(stood, False)
                self.assertEqual(
                    json.dumps(carried, sort_keys=True),
                    json.dumps({**durable_data, STAGED: STAGED_VALUE}, sort_keys=True),
                )
                self.assertEqual(comment_id, PINNED_ID)

    def test_no_comment_in_hand_carries_nothing(self) -> None:
        # No reading of another comment than the one the tick read says the
        # records stand or is a settlement to keep: a write over a replaced
        # or deleted comment would pin a second one. Nothing is carried, the
        # state names the comment it did, and the answer writes nothing.
        for name, durable in NO_COMMENT_IN_HAND:
            with self.subTest(name):
                self.assertEqual(_returned(durable), (None, _in_hand(), PINNED_ID))


class ResolvedOverTest(unittest.TestCase):
    """The comment a subject resolved from the state in hand is bound to.

    A road about to act on an approval asks the same agreement of the state it
    holds, and is answered only whether the records are in hand. Neither
    carries anything onto that state: a comment that moved binds nothing.
    """

    def test_only_agreeing_records_bind(self) -> None:
        agreeing = _current(HANDED)
        for name, durable, bound in (
            ("agreeing", _pinned(agreeing), agreeing),
            ("settled since", _pinned(_current(SETTLED)), None),
            ("a record written null", _pinned({
                **agreeing, _records.PENDING_REPORT: None,
            }), None),
            ("a revision spelled true", _pinned(_current(True)), None),
        ):
            with self.subTest(name):
                self.assert_binds(durable, bound)

    def test_no_comment_in_hand_binds_nothing(self) -> None:
        # Whatever records a replaced comment carries, the tick's writes name
        # the comment it read.
        for name, durable in NO_COMMENT_IN_HAND:
            with self.subTest(name):
                self.assert_binds(durable, None)

    def assert_binds(self, durable: PinnedState | Exception, bound: dict | None) -> None:
        """Both bindings over `durable` answer `bound`, and leave the state alone."""
        state = _pinned(_in_hand())
        self.assertEqual(
            _review_comment._resolved_over(_reading(durable), MagicMock(number=1), state),
            bound,
        )
        self.assertIs(
            _review_comment._records_in_hand(
                _reading(durable), MagicMock(number=1), state, "ping",
            ),
            bound is not None,
        )
        self.assertEqual((state.data, state.comment_id), (_in_hand(), PINNED_ID))


if __name__ == "__main__":
    unittest.main()
