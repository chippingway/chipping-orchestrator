# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned comment a review is bound to, and what a verdict's return keeps.

The state a validating tick holds was read when the tick began, so a report
record another road moved since is on the comment and nowhere in hand. A
subject is bound only to a comment carrying the records it was resolved from,
and pointing the issue at the pull request it was resolved at. The comment is
read again when the verdict comes back, and everything it changed since the
subject was resolved is carried onto the state -- beside what this tick staged
and never wrote, which is the tick's own to say where the records stand --
while records that moved refuse the verdict. A comment that will not read or
will not parse carries nothing and says the tick is to write nothing. So does a
reading of another comment than the one the state was read from -- the pinned
comment replaced or gone -- whatever records it carries, since the tick's write
names the comment it read. Records are compared as the comment spells them, so
one written `null` where there was none, or a revision spelled `true` where it
was `1`, is a move. A persisted verdict's recheck watches the verdict and the
pull request the issue points at beside the report, and a road about to act
on an approval holds the review subjects and the approval's evidence claim
too.
"""
from __future__ import annotations

import itertools
import json
import unittest
from types import MappingProxyType
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

# The current verification evidence and the returned verdict, which only a
# persisted verdict's recheck watches beside the report.
EVIDENCE = "verification_evidence_current"

VERDICT = "review_returned_verdict"

# The pull request the issue points at, which a persisted verdict's recheck
# watches too, and another one it could be pointed at since.
PR_NUMBER = "pr_number"

# The approval's evidence claim and the subject it covers, which a road acting
# on that approval holds beside the report.
CLAIM = "review_approved_evidence"

APPROVED = "review_approved_subject"

OTHER_PR = 17_991

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


# The comment as a persisted verdict's recheck reads it -- the handed report
# records beside evidence settled since, the verdict cleared, or only fields no
# verdict stands on moved -- whether the recheck is a persisted verdict's or
# the return's own reading, and what it answers and leaves the state holding.
# Settled evidence is carried for the verdict's claim to be judged over, and
# is no move of the records by itself.
_HANDED_RECORDS = MappingProxyType(_current(HANDED))

_MOVED_EVIDENCE = MappingProxyType({**_HANDED_RECORDS, EVIDENCE: {"revision": SETTLED}})

_EVIDENCE_CARRIED = MappingProxyType({**_MOVED_EVIDENCE, STAGED: STAGED_VALUE})

_PERSISTED_RECHECKS = (
    ("evidence moved, the return's reading", _MOVED_EVIDENCE, False, (True, _EVIDENCE_CARRIED)),
    ("evidence moved", _MOVED_EVIDENCE, True, (True, _EVIDENCE_CARRIED)),
    ("the verdict cleared", {**_HANDED_RECORDS, VERDICT: None}, True, (False, {**_in_hand(), VERDICT: None})),
    (
        "the verdict replaced",
        {**_HANDED_RECORDS, VERDICT: {"round": 1}},
        True,
        (False, {**_in_hand(), VERDICT: {"round": 1}}),
    ),
    (
        "the issue repointed",
        {**_HANDED_RECORDS, PR_NUMBER: OTHER_PR},
        True,
        (False, {**_in_hand(), PR_NUMBER: OTHER_PR}),
    ),
    (
        "only other fields moved",
        {**_HANDED_RECORDS, ALSO_SETTLED: [1], STAGED: "another road's"},
        True,
        (True, {**_in_hand(), ALSO_SETTLED: [1]}),
    ),
)

# The comment's records as an approval reader read them: the handed report,
# and beside it an approval of that report and its evidence claim.
_APPROVED_RECORDS = MappingProxyType({**_HANDED_RECORDS, CLAIM: {"receipt": "r"}, APPROVED: {"sha": "a"}})


def _reading(durable: PinnedState | Exception) -> MagicMock:
    """A client whose one read of the pinned comment answers `durable`.

    An exception is a read of the comment that failed.
    """
    github = MagicMock()
    github.read_pinned_state.side_effect = [durable]
    return github


def _returned(
    durable: PinnedState | Exception, *, persisted: bool = False,
) -> tuple[bool | None, dict, int | None]:
    """Ask a verdict's return over `durable`, or a persisted verdict's recheck: its answer, and the state after.

    The state after is its data and the comment it names.
    """
    state = _pinned(_in_hand())
    reread = _review_comment._records_stand(
        _reading(durable), MagicMock(number=1), state, _current(HANDED), persisted=persisted,
    )
    return None if reread is None else reread.stood, state.data, state.comment_id


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

    def test_a_persisted_verdict_is_composed(self) -> None:
        # Held for a persisted verdict, the verdict itself and the pull request
        # are watched beside the report's records, and where they stand every
        # field another road changed since is carried too -- evidence
        # included, which the verdict's claim answers for -- save one this tick
        # changed as well, which its own write says. The return's own reading
        # carries what moved the same way.
        for name, durable_data, persisted, expected in _PERSISTED_RECHECKS:
            with self.subTest(name):
                returned = _returned(_pinned(durable_data), persisted=persisted)

                self.assertEqual(returned[:2], expected)

    def test_no_comment_in_hand_carries_nothing(self) -> None:
        # No reading of another comment than the one the tick read says the
        # records stand or is a settlement to keep: a write over a replaced
        # or deleted comment would pin a second one. Nothing is carried, the
        # state names the comment it did, and the answer writes nothing --
        # for the return's own reading and a persisted verdict's recheck alike.
        for (name, durable), persisted in itertools.product(NO_COMMENT_IN_HAND, (False, True)):
            with self.subTest(name, persisted=persisted):
                self.assertEqual(_returned(durable, persisted=persisted), (None, _in_hand(), PINNED_ID))


class ResolvedOverTest(unittest.TestCase):
    """The comment a subject resolved from the state in hand is bound to.

    Bound only where the comment carries the report records the state does and
    points the issue at the same pull request. A road about to act on an
    approval asks the same agreement of the state it holds -- which stages
    nothing, being about to write only what it read -- and of the review
    subjects and the approval's evidence claim beside them, and is answered
    only whether the records are in hand. Neither carries anything onto that
    state: a comment that moved binds nothing.
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
            ("the issue repointed", _pinned({**agreeing, PR_NUMBER: OTHER_PR}), None),
        ):
            with self.subTest(name):
                self.assert_binds(durable, bound)

    def test_no_comment_in_hand_binds_nothing(self) -> None:
        # Whatever records a replaced comment carries, the tick's writes name
        # the comment it read.
        for name, durable in NO_COMMENT_IN_HAND:
            with self.subTest(name):
                self.assert_binds(durable, None)

    def test_an_approval_reader_holds_its_records(self) -> None:
        # The approval's evidence claim removed or written null, or the review
        # subject it covers replaced, since the reader read the comment: the
        # records are not in hand, and the reader writes nothing back over them.
        for name, durable, in_hand in (
            ("agreeing", dict(_APPROVED_RECORDS), True),
            ("the claim removed", {**_HANDED_RECORDS, APPROVED: _APPROVED_RECORDS[APPROVED]}, False),
            ("the claim null", {**_APPROVED_RECORDS, CLAIM: None}, False),
            ("the approved subject replaced", {**_APPROVED_RECORDS, APPROVED: {"sha": "b"}}, False),
        ):
            with self.subTest(name):
                state = _pinned(dict(_APPROVED_RECORDS))

                held = _review_comment._records_in_hand(
                    _reading(_pinned(durable)), MagicMock(number=1), state, "ping",
                )

                self.assertEqual((held, state.data), (in_hand, dict(_APPROVED_RECORDS)))

    def assert_binds(self, durable: PinnedState | Exception, bound: dict | None) -> None:
        """Both bindings over `durable` answer `bound`, and leave the state alone.

        A subject is resolved over the state a reviewer round staged its launch
        on; an approval reader holds the comment as it read it, staging none.
        """
        state = _pinned(_in_hand())
        read = _pinned(dict(_HANDED_RECORDS))
        self.assertEqual(
            _review_comment._resolved_over(_reading(durable), MagicMock(number=1), state),
            bound,
        )
        self.assertIs(
            _review_comment._records_in_hand(
                _reading(durable), MagicMock(number=1), read, "ping",
            ),
            bound is not None,
        )
        self.assertEqual((state.data, state.comment_id), (_in_hand(), PINNED_ID))


if __name__ == "__main__":
    unittest.main()
