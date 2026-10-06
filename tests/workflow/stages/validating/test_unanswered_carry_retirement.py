# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Carried evidence that no longer answers, invalidated in `validating` over a comment other roads keep writing.

Each case settles a carry of a passing run onto the squashed head beside the
approval it was recorded for, with no approval claim naming it -- so it answers
for nothing -- and runs the route `validating` asks first, on a tick with no
squash outstanding. The invalidation is one guarded commit staged on the pinned
comment read afresh and held to every bound record and to the approval's claim
on the evidence: the carry goes into history and the approval it was carried
for is retired. Another road writing right behind that reading or behind the
commit's own either keeps every field it wrote that the invalidation does not
own, or -- moving the claim, the approval, the review subject, or the comment
itself -- holds the tick with nothing written, for the next to decide over what
the comment carries then -- the report debt the carry's review subject stands
only without among them. Retiring the approval frees the room the history
entry takes on a full comment; beside an approval of another subject, a comment
with no room for the entry is sent nothing, and one filled under the commit
holds the tick. A commit nobody confirmed holds it too, for the next to
invalidate the carry once.
"""
from __future__ import annotations

import itertools
import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    review_subjects as _review_subjects,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    collapse as _collapse,
    review_verdicts as _verdicts,
)
from tests.workflow.engine import evidence_road_test_support as road, verification_evidence_test_support as evidence
from tests.workflow.fixtures import _TEST_SPEC

# The tick's own reading, ahead of the route; the reading the invalidation is
# staged on; and the one its commit takes.
_TICK_READ = 0
_STAGED_ON = 1
_COMMITTED_OVER = 2

_INVALIDATED = _records.Retirement.INVALIDATED

_APPROVAL = _review_subjects.APPROVED_SUBJECT

_LEVEL = "INFO"


def _claim_on_the_carry(case) -> dict:
    """An approval claim naming exactly the carry current on `case`'s comment, under which it answers again."""
    current = _settlement.read_current_evidence(case.gh.read_pinned_state(case.issue))
    return _verdicts.EvidenceClaim(
        use=_verdicts.EvidenceUse.PUBLISHED,
        receipt=current.receipt,
        revision=current.revision,
        digest=current.content_revision,
        passed=True,
        covers=True,
    ).recorded()


# An approval another road records of another subject than the carry's.
_REPLACEMENT = road.Move(
    "a replacement approval", _APPROVAL,
    lambda case: {**case.subject.recorded(), "sha": evidence.REBASED_SHA},
)

def _cleared(_case) -> object:
    """What another road clearing a record moves it to: nothing at all."""
    return road.GONE


_CLAIMED = road.Move("the claim pointed at the carry", _approved_evidence.APPROVED_EVIDENCE, _claim_on_the_carry)

# The report debt a carry's review subject stands only without
# (`report_delivery.owes_a_report`): the debt an undeliverable park records,
# and that park's own reason.
_DEBTS = (
    road.Move("a report owed", _report_delivery.OWED_REPORT, lambda _case: True),
    road.Move("an undeliverable park", "park_reason", lambda _case: _report_delivery.UNDELIVERABLE_REPORT),
)

# Each move another road makes, whether the next tick still invalidates the
# carry over it, and the approval it leaves: the claim pointed at the carry,
# under which it answers again and keeps its approval; the claim written
# `null` where there was none, the review subject removed, or a report debt
# recorded, under which it still answers for nothing; and the approval
# replaced by one of another subject, which is not the carry's to retire.
_MOVES = (
    (_CLAIMED, False, lambda case: case.subject.recorded()),
    (road.Move("the claim written null", _approved_evidence.APPROVED_EVIDENCE, lambda _case: None), True, None),
    (road.Move("the review subject removed", _review_subjects.REVIEW_SUBJECT, lambda _case: road.GONE), True, None),
    *((debt, True, None) for debt in _DEBTS),
    (_REPLACEMENT, True, _REPLACEMENT.to),
)


class _SettledCarry(evidence.VerificationEvidenceCase):
    """A carry settled onto the squashed head beside the approval it was recorded for, with no claim naming it."""

    def setUp(self) -> None:
        evidence.VerificationEvidenceCase.setUp(self)
        self.state.set(_APPROVAL, self.subject.recorded())
        self.carry = self.record(self.binding().retargeted(evidence.SQUASHED_SHA))
        self.moves_the_head(evidence.SQUASHED_SHA)
        self.assertFalse(self.reconcile())

    def recovers(self, number: int = _TICK_READ, moves=None) -> bool:
        """What `validating`'s first route answers over the comment as it reads now, `moves` behind a reading.

        Behind the route's `number`-th pinned reading, or behind the tick's
        own reading, ahead of the route, for `_TICK_READ`.
        """
        tick = self.gh.read_pinned_state(self.issue)
        if moves is not None and number == _TICK_READ:
            moves(self)
        return road.Behind(self, number, moves).runs(
            _collapse._recovers_a_recorded_collapse, self.gh, _TEST_SPEC, self.issue, tick,
        )

    def standing(self) -> tuple:
        """The current evidence's receipt, the approval, and the history, as the comment reads now."""
        persisted = self.gh.read_pinned_state(self.issue)
        current = _settlement.read_current_evidence(persisted)
        return (
            None if current is None else current.receipt,
            persisted.get(_APPROVAL),
            [(entry.receipt, entry.retired) for entry in _settlement.read_evidence_history(persisted)],
        )

    def invalidated(self) -> tuple:
        """What `standing` reads once the carry is invalidated with its approval."""
        return None, None, [(self.carry.receipt, _INVALIDATED)]

    def kept(self, approval) -> tuple:
        """What `standing` reads while the carry stands beside `approval`."""
        return self.carry.receipt, approval, []


class UnansweredCarryTest(_SettledCarry, unittest.TestCase):
    """An unanswered carry is invalidated with its approval over the comment as it stands, or nothing is written."""

    def test_another_roads_fields_are_kept(self) -> None:
        # Behind the reading the invalidation is staged on, another road
        # writes fields it does not own, a returned verdict among them: the
        # commit lays the invalidation over them and the tick is spent on it.
        # Behind the commit's own reading, the edit finds the comment moved
        # and sends nothing, the tick held, and the next invalidates the
        # carry. Either way it goes once with its approval, and every field
        # reads as that road wrote it.
        for number in (_STAGED_ON, _COMMITTED_OVER):
            with self.subTest(number=number):
                self.setUp()

                self.assertTrue(self.recovers(number, road.writes_bookkeeping))
                if number == _COMMITTED_OVER:
                    self.assertEqual(self.standing(), self.kept(self.subject.recorded()))
                    self.assertTrue(self.recovers())

                self.assertEqual(self.standing(), self.invalidated())
                persisted = self.gh.pinned_data(evidence.ISSUE_NUMBER)
                self.assertEqual({**persisted, **road.INDEPENDENT}, persisted)

    def test_a_moved_record_holds_it(self) -> None:
        # Behind the reading the invalidation is staged on, another road moves
        # the approval's claim, the review subject, or the approval itself.
        # The commit refuses and holds the tick with nothing written over the
        # move. The next tick decides over what the comment carries then: a
        # claim naming the carry answers for it, so it stands with its
        # approval; a claim written `null` or the subject gone answers for
        # nothing, and a replaced approval leaves the carry unanswered too, so
        # it goes -- leaving any approval but its own.
        for move, invalidated, approval in _MOVES:
            with self.subTest(move.name):
                self.setUp()
                writes = self.gh.write_state_calls

                with self.assertLogs(evidence.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertTrue(self.recovers(_STAGED_ON, move.lands))
                    self.assertIn(f"{move.record} moved since this tick read it", evidence.logged_refusal(logged))
                self.assertEqual(self.gh.write_state_calls - writes, 1)
                self.assertEqual(*move.spelled_on(self))

                self.assertEqual(self.recovers(), invalidated)

                self.assertEqual(
                    self.standing()[:2],
                    (None if invalidated else self.carry.receipt, approval and approval(self)),
                )

    def test_a_cleared_report_debt_holds_it(self) -> None:
        # The approval's claim names the carry, and it answers for nothing only
        # because a developer report is owed -- the debt an undeliverable park
        # records, or that park's reason. Another road clears the debt behind
        # the tick's own reading or behind the reading the invalidation is
        # staged on: the carry answers again, so nothing is written and the
        # tick holds, and the next leaves the carry standing with its approval.
        for debt, number in itertools.product(_DEBTS, (_TICK_READ, _STAGED_ON)):
            with self.subTest(debt.name, number=number):
                self.setUp()
                _CLAIMED.lands(self)
                debt.lands(self)
                cleared = road.Move(debt.name, debt.record, _cleared)

                with self.assertLogs(evidence.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertTrue(self.recovers(number, cleared.lands))
                    self.assertIn(f"{debt.record} moved since this tick read it", evidence.logged_refusal(logged))

                self.assertFalse(self.recovers())
                self.assertEqual(self.standing(), self.kept(self.subject.recorded()))

    def test_a_spoiled_comment_holds_it(self) -> None:
        # Replaced by another comment carrying the same record, or edited into
        # something that does not parse, behind the reading the invalidation
        # is staged on: the tick holds and nothing is written.
        for spoils in (road.repins, road.unparses):
            with self.subTest(spoils.__name__):
                self.setUp()
                writes = self.gh.write_state_calls

                with self.assertLogs(evidence.WORKFLOW_LOG, "WARNING"):
                    self.assertTrue(self.recovers(_STAGED_ON, spoils))

                self.assertEqual(self.gh.write_state_calls, writes)


class RefusedInvalidationTest(_SettledCarry, unittest.TestCase):
    """An invalidation the comment has no room for, or nobody confirmed, writes nothing past it and replays once."""

    def test_a_full_comment_takes_it_whole(self) -> None:
        # Filled to its limit before the tick: retiring the carry's approval
        # frees the room its history entry takes, so both go in one commit.
        road.fills(self)

        self.assertTrue(self.recovers())

        self.assertEqual(self.standing(), self.invalidated())

    def test_no_room_beside_a_replacement_approval(self) -> None:
        # An approval of another subject stands in the carry's place, so
        # nothing the invalidation does shrinks the comment. Filled to its
        # limit before the tick, the carry's entry has no room: the record
        # stays, which every reader refuses, nothing is sent, and the tick
        # carries on -- as does the next, sending nothing either. Filled behind
        # the reading the invalidation is staged on, the entry fit there, but
        # the commit measures it over the comment as it stands and holds the
        # tick with nothing written past the limit.
        for filled_first in (True, False):
            with self.subTest(filled_first=filled_first):
                self.setUp()
                _REPLACEMENT.lands(self)
                if filled_first:
                    road.fills(self)
                writes = self.gh.write_state_calls

                behind = (_TICK_READ, None) if filled_first else (_STAGED_ON, road.fills)
                with self.assertLogs(evidence.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertEqual(self.recovers(*behind), not filled_first)
                    self.assertIn("no room", evidence.logged_refusal(logged))

                if filled_first:
                    self.assertFalse(self.recovers())
                self.assertEqual(self.standing(), self.kept(_REPLACEMENT.to(self)))
                self.assertEqual(self.gh.write_state_calls - writes, int(not filled_first))
                body = pinned_state_body(self.gh.pinned_data(evidence.ISSUE_NUMBER))
                self.assertEqual(len(body), MAX_PINNED_BODY)

    def test_an_unconfirmed_invalidation_replays_once(self) -> None:
        # The commit is accepted with its response lost, or refused outright:
        # the tick holds. The next finds the carry gone and carries on with
        # nothing written, or invalidates it then -- one history entry either
        # way, the approval retired.
        for failure in ("lost", "refused"):
            with self.subTest(failure):
                self.setUp()
                failures = getattr(self.gh.pinned_failures, failure)
                failures.add(evidence.ISSUE_NUMBER)
                with self.assertLogs(evidence.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertTrue(self.recovers())
                    self.assertIn("never confirmed", evidence.logged_refusal(logged))
                failures.clear()
                writes = self.gh.write_state_calls

                self.assertEqual(self.recovers(), failure == "refused")

                self.assertEqual(self.standing(), self.invalidated())
                self.assertEqual(self.gh.write_state_calls - writes, int(failure == "refused"))


if __name__ == "__main__":
    unittest.main()
