# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retiring evidence: only the record the comment holds, and only where the comment can carry it.

A retirement moves a record into the history index. Asked of a transaction the
comment does not record -- one minted and never recorded, or one a later record
has replaced -- it writes nothing: indexing the first would put a revision in
history that no floor covers, and retiring the second would drop the
transaction that IS recorded. A history entry is larger than the record it
replaces, so a retirement the comment could not carry is refused rather than
reported done, and the state is left as it was.

A retirement the reconciliation makes -- a transaction abandoned, a replay
already indexed dropped, a record nobody can read dropped -- is one guarded
commit staged on the pinned comment read afresh. Another road writing right
behind that reading or behind the commit's own is either kept -- every field no
retirement owns, as that road left it -- or refuses the commit with nothing
written: a bound record moved however the comment's JSON spells the move, the
transaction replaced or retired there first, the comment replaced, spoiled, or
filled past what the retirement needs. A commit nobody confirmed holds the
tick, and the next one retires the record once.
"""
from __future__ import annotations

import copy
import functools
import itertools
import json
import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    report_records as _report_records,
    review_subjects as _review_subjects,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    evidence_road_test_support as road,
    verification_evidence_test_support as evidence,
    verification_record_test_support as support,
)

# The filler a crowding case fills the rest of the comment with.
_FILLER = "filler"

# The reading a retirement is staged on -- the pinned comment read afresh --
# and the one its commit takes.
_STAGED_ON = 1
_COMMITTED_OVER = 2

_ABANDONED = _records.Retirement.ABANDONED

# Every bound record another road can move behind the reading a retirement is
# staged on: a developer report recorded, the review subject removed, an
# approval recorded or written `null` where none was, the pull request number
# spelled as a float, and the revision floor raised past the record.
_BOUND_MOVES = (
    road.Move(
        "a later report recorded", _report_records.PENDING_REPORT,
        lambda _case: {"receipt": f"issue-{support.ISSUE_NUMBER}-report-2"},
    ),
    road.Move("the review subject removed", _review_subjects.REVIEW_SUBJECT, lambda _case: road.GONE),
    road.Move("an approval recorded", _review_subjects.APPROVED_SUBJECT, lambda case: case.subject.recorded()),
    road.Move("an approval written null", _review_subjects.APPROVED_SUBJECT, lambda _case: None),
    road.Move("the pull request as a float", "pr_number", lambda _case: float(support.PR_NUMBER)),
    road.Move(
        "the floor raised", _records.REVISION_FLOOR,
        lambda case: case.state.get(_records.REVISION_FLOOR) + 1,
    ),
)

_LEVEL = "INFO"


def _issue() -> PinnedState:
    """The pinned comment of an issue with a pull request and no evidence yet."""
    return PinnedState(comment_id=1, state_data={"pr_number": support.PR_NUMBER})


class StoredRecordTest(unittest.TestCase):
    """Only the transaction the comment records is abandoned."""

    def test_an_unrecorded_mint_is_not_abandoned(self) -> None:
        # Indexed, its revision would sit in history above a floor that never
        # covered it, and every later mint would refuse. An issue recording
        # nothing has nothing to drop either.
        state = _issue()
        unrecorded = support.minted(state)

        for stale in (unrecorded, None):
            with self.subTest(named=stale is not None):
                self.assertFalse(_settlement.retire_pending_evidence(state, stale))
        self.assertEqual(state.data, _issue().data)
        self.assertEqual(support.minted(state).revision, unrecorded.revision)

    def test_a_replaced_transaction_is_not_abandoned(self) -> None:
        # Nor is a readable record dropped unnamed: dropping without an entry
        # is for a record nobody can read.
        state = _issue()
        replaced = support.recorded(state)
        standing = support.recorded(state)
        before = copy.deepcopy(state.data)

        for stale in (replaced, None):
            with self.subTest(named=stale is not None):
                self.assertFalse(_settlement.retire_pending_evidence(state, stale))
        self.assertEqual(state.data, before)

        self.assertTrue(_settlement.retire_pending_evidence(state, standing))
        self.assertIsNone(_record_state.read_pending_evidence(state))
        self.assertEqual(
            [(entry.receipt, entry.retired) for entry in _settlement.read_evidence_history(state)],
            [
                (replaced.receipt, _records.Retirement.ABANDONED),
                (standing.receipt, _records.Retirement.ABANDONED),
            ],
        )


class CommentLimitTest(unittest.TestCase):
    """A retirement fills the comment at most, and one past it writes nothing."""

    def test_an_invalidation_stops_at_the_comment(self) -> None:
        settled = _issue()
        support.settles(settled)

        self._stops_at_the_comment(settled, _settlement.retire_current_evidence)

    def test_an_abandonment_stops_at_the_comment(self) -> None:
        recorded = _issue()
        pending = support.recorded(recorded)

        self._stops_at_the_comment(
            recorded, functools.partial(_settlement.retire_pending_evidence, pending=pending),
        )

    def _stops_at_the_comment(self, base: PinnedState, retire) -> None:
        """`retire` over `base` crowded to fill the comment exactly, then one character past it."""
        probe = PinnedState(state_data=base.data | {_FILLER: ""})
        self.assertTrue(retire(probe))
        filling = "y" * (MAX_PINNED_BODY - len(pinned_state_body(probe.data)))
        fitting = PinnedState(state_data=base.data | {_FILLER: filling})
        past = PinnedState(state_data=base.data | {_FILLER: f"{filling}y"})
        before = copy.deepcopy(past.data)

        self.assertTrue(retire(fitting))
        self.assertEqual(len(pinned_state_body(fitting.data)), MAX_PINNED_BODY)
        self.assertFalse(retire(past))
        self.assertEqual(past.data, before)


def _history(state: PinnedState) -> list[tuple]:
    """Each retired record `state` indexes, by receipt and why it was retired, oldest first."""
    return [(entry.receipt, entry.retired) for entry in _settlement.read_evidence_history(state)]


class _OwedRetirement(evidence.VerificationEvidenceCase):
    """An issue owing evidence the reconciliation retires: each way it comes to, and the history that leaves."""

    def ends_the_pull_request(self) -> list[tuple]:
        """Owe evidence to a pull request that is over; abandoned, it is indexed once."""
        pending = self.record()
        self.pull_request.state = "closed"
        return [(pending.receipt, _ABANDONED)]

    def restores_an_indexed_record(self) -> list[tuple]:
        """Bring back a record a later one replaced and settled past; dropped, the history stays as it was."""
        stale = self.record()
        restored = self.gh.pinned_data(support.ISSUE_NUMBER)[_records.PENDING_EVIDENCE]
        self.record()
        self.reconcile()
        self.state.set(_records.PENDING_EVIDENCE, restored)
        self.gh.write_pinned_state(self.issue, self.state)
        return [(stale.receipt, _ABANDONED)]

    def damages_the_record(self) -> list[tuple]:
        """Owe a record nobody can read; dropped, it leaves no history."""
        self.state.set(_records.PENDING_EVIDENCE, {"receipt": f"issue-{support.ISSUE_NUMBER}-verification-1"})
        self.gh.write_pinned_state(self.issue, self.state)
        return []

    def persisted(self) -> PinnedState:
        """The pinned comment as it reads now."""
        return self.gh.read_pinned_state(self.issue)


# Every retirement the reconciliation commits: an abandonment, a replay
# already indexed dropped, and damage dropped.
_RETIREMENTS = (
    _OwedRetirement.ends_the_pull_request,
    _OwedRetirement.restores_an_indexed_record,
    _OwedRetirement.damages_the_record,
)


class GuardedRetirementTest(unittest.TestCase, _OwedRetirement):
    """A retirement lands over the comment as it stands, keeping what it does not own, or writes nothing."""

    def setUp(self) -> None:
        evidence.VerificationEvidenceCase.setUp(self)
        self.newer: list[_records.PendingEvidence] = []

    def test_another_roads_fields_are_kept(self) -> None:
        # Another road writes fields no retirement owns -- a usage total, a
        # watermark, a returned verdict, a comment of its own on the ledger, a
        # field no binary knows -- right behind the reading the retirement is
        # staged on, so the commit lays the retirement over them; or behind
        # the commit's own reading, so the edit finds the comment moved and
        # sends nothing, and the next tick retires the record. Either way it
        # goes once, every field reads as that road wrote it, nothing is
        # posted, and the tick's state reads -- and is synced with -- the
        # comment as the retirement left it.
        for retires, number in itertools.product(_RETIREMENTS, (_STAGED_ON, _COMMITTED_OVER)):
            with self.subTest(retires.__name__, number=number):
                self.setUp()
                history = retires(self)
                posted = self.artifacts()

                self.assertFalse(road.Behind(self, number, road.writes_bookkeeping).reconciles())
                if number == _COMMITTED_OVER:
                    self.assertTrue(_record_state.carries_pending_evidence(self.persisted()))
                    self.assertFalse(self.reconcile())

                persisted = self.persisted()
                self.assertEqual(
                    (_record_state.carries_pending_evidence(persisted), _history(persisted), self.artifacts()),
                    (False, history, posted),
                )
                self.assertEqual({**persisted.data, **road.INDEPENDENT}, persisted.data)
                self.assertIn(road.ANOTHER_ROADS_COMMENT, persisted.get(evidence.LEDGER))
                self.assertEqual(self.state.data, persisted.data)
                self.assertEqual(json.loads(self.state.synced), persisted.data)

    def test_a_moved_record_refuses_it(self) -> None:
        # Behind the reading the retirement is staged on, another road moves
        # a bound record -- however the comment's JSON spells the move. The
        # commit refuses with nothing written: the move is kept as that road
        # spelled it, and the transaction is still owed.
        for move in _BOUND_MOVES:
            with self.subTest(move.name):
                self.setUp()
                pending = self.record()
                self.pull_request.state = "closed"
                writes = self.gh.write_state_calls

                with self.assertLogs(evidence.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(road.Behind(self, _STAGED_ON, move.lands).reconciles())
                    self.assertIn(f"{move.record} moved since this tick read it", evidence.logged_refusal(logged))

                self.assertEqual(*move.spelled_on(self))
                self.assertEqual(
                    (
                        self.gh.write_state_calls - writes,
                        _record_state.read_pending_evidence(self.persisted()),
                        _history(self.persisted()),
                    ),
                    (1, pending, []),
                )

    def test_the_transaction_moved_meanwhile(self) -> None:
        # Behind the reading the retirement is staged on, another road
        # abandons the same transaction first, or records a newer one past
        # it. The commit refuses rather than index the transaction twice, or
        # erase the newer one and lower the floor under it: the history holds
        # the one entry that road wrote, and the newer record stands.
        for moves in (self.abandons_elsewhere, self.records_newer):
            with self.subTest(moves.__name__):
                self.setUp()
                pending = self.record()
                self.pull_request.state = "closed"

                with self.assertLogs(evidence.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(road.Behind(self, _STAGED_ON, moves).reconciles())
                    self.assertIn("moved since this tick read it", evidence.logged_refusal(logged))

                persisted = self.persisted()
                standing = _record_state.read_pending_evidence(persisted)
                self.assertEqual(standing, self.newer[0] if self.newer else None)
                self.assertEqual(
                    (persisted.get(_records.REVISION_FLOOR), _history(persisted)),
                    ((standing or pending).revision, [(pending.receipt, _ABANDONED)]),
                )

    def abandons_elsewhere(self, _case) -> None:
        """Another road abandoning the owed transaction over its own reading of the comment."""
        elsewhere = self.persisted()
        owed = _record_state.read_pending_evidence(elsewhere)
        self.assertTrue(_settlement.retire_pending_evidence(elsewhere, owed))
        self.gh.write_pinned_state(self.issue, elsewhere)

    def records_newer(self, _case) -> None:
        """Another road's transaction, recorded on its own reading of the comment."""
        self.newer.append(self.record(onto=self.persisted()))


class RefusedRetirementTest(unittest.TestCase, _OwedRetirement):
    """A retirement over a comment spoiled, filled, or never confirmed holds or writes nothing, and replays once."""

    def setUp(self) -> None:
        evidence.VerificationEvidenceCase.setUp(self)

    def test_a_spoiled_comment_holds_it(self) -> None:
        # Replaced by another comment carrying the same record, or edited into
        # something that does not parse, behind the reading the retirement is
        # staged on: the commit holds the tick and writes nothing. Over the
        # replacement the next tick abandons the record once; over a comment
        # that does not parse it finds nothing it may act on.
        for spoils, retired in ((road.repins, True), (road.unparses, False)):
            with self.subTest(spoils.__name__):
                self.setUp()
                history = self.ends_the_pull_request()
                writes = self.gh.write_state_calls

                with self.assertLogs(evidence.WORKFLOW_LOG, "WARNING"):
                    self.assertTrue(road.Behind(self, _STAGED_ON, spoils).reconciles())
                self.assertEqual(self.gh.write_state_calls, writes)

                self.assertFalse(self.reconcile())

                self.assertEqual(
                    (self.gh.write_state_calls - writes, _history(self.state)),
                    (int(retired), history if retired else []),
                )

    def test_a_comment_filled_under_it(self) -> None:
        # Another road fills the comment to its limit behind the reading the
        # retirement is staged on: the entry fit there, but the commit
        # measures it over the comment as it stands and refuses it, so nothing
        # past the limit is written and the record stays owed. Once the room
        # is back, the next tick abandons it once.
        history = self.ends_the_pull_request()
        pending = _record_state.read_pending_evidence(self.persisted())

        with self.assertLogs(evidence.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertFalse(road.Behind(self, _STAGED_ON, road.fills).reconciles())
            self.assertIn("no room for the write", evidence.logged_refusal(logged))

        filled = self.persisted()
        self.assertEqual(
            (len(pinned_state_body(filled.data)), _record_state.read_pending_evidence(filled)),
            (MAX_PINNED_BODY, pending),
        )
        filled.data.pop(road.FILLER)
        self.gh.write_pinned_state(self.issue, filled)

        self.assertFalse(self.reconcile())

        self.assertEqual(_history(self.state), history)

    def test_an_unconfirmed_retirement_replays_once(self) -> None:
        # The retirement's commit is accepted with its response lost, or
        # refused outright: the tick holds, since the comment may read either
        # way. The next tick finds the record gone and writes nothing, or
        # retires it then -- one history entry either way, nothing posted.
        for retires, failure in itertools.product(_RETIREMENTS, ("lost", "refused")):
            with self.subTest(retires.__name__, failure=failure):
                self.setUp()
                history = retires(self)
                posted = self.artifacts()
                self.holds_unconfirmed(failure)
                writes = self.gh.write_state_calls

                self.assertFalse(self.reconcile())

                self.assertEqual(
                    (
                        self.gh.write_state_calls - writes,
                        _record_state.carries_pending_evidence(self.state),
                        _history(self.state),
                        self.artifacts(),
                    ),
                    (int(failure == "refused"), False, history, posted),
                )

    def holds_unconfirmed(self, failure: str) -> None:
        """A tick whose retirement the pinned comment answers as `failure` names on `pinned_failures`: it holds."""
        failures = getattr(self.gh.pinned_failures, failure)
        failures.add(support.ISSUE_NUMBER)
        with self.assertLogs(evidence.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertTrue(self.reconcile())
            self.assertIn("never confirmed", evidence.logged_refusal(logged))
        failures.clear()

if __name__ == "__main__":
    unittest.main()
