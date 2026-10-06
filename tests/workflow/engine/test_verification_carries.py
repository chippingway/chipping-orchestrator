# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A refused carry abandoned into history, with the approval it was recorded for.

Only the transaction the comment records is abandoned, and only a carry -- a
run on another commit than the head it answers for -- takes the approval with
it: its subject written null, and only while that approval is the one the
carry was recorded for, spelled exactly as the carry recorded it, so a
replacement another road put in its place, or a respelling, stands. A run on
the head it answers for is abandoned alone, and a
transaction the comment does not record is left as it stands. Over the
comment read afresh, a transaction another road recorded meanwhile is never
written away, and a comment filled to its limit still takes the approval's
retirement, which only shrinks it.

The abandonment is one guarded commit staged on that fresh reading -- ahead of
the post, or at the settlement whose binding a push refused, where it records
the artifact's ledger entry too. Another road writing right behind that reading
or behind the commit's own either keeps every field it wrote that the
abandonment does not own -- a returned verdict, a usage total, a comment on the
ledger -- or, moving the approval, the transaction, or the comment itself,
refuses the commit with nothing written and the carry owed. At the settlement,
an approval another road moved earlier still -- behind the preparation ahead of
the post, or while the proof is taken -- refuses what the tick decided over
rather than the carry: nothing is abandoned and only the artifact's ledger
entry is committed, for the next tick's proof to abandon the carry over the
approval as that road wrote it. So does a report debt -- the one an
undeliverable park records, or its reason -- another road records or pays
under the proof: whether the carry's review subject stands is read off it, so
nothing is abandoned or settled over the move, and the next tick decides over
the comment as it reads then. A commit nobody confirmed holds the tick, and
the next abandons the carry once, with one artifact on the pull request.
"""
from __future__ import annotations

import itertools
import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_record_state as _report_record_state,
    review_subjects as _review_subjects,
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import evidence_road_test_support as road, verification_evidence_test_support as support

# A field another road fills the pinned comment to its limit with.
FILLER = "filler"

# The tick's own reading, ahead of the reconciliation; the reading an
# abandonment ahead of the post is staged on, and the one its commit takes;
# and a settling tick's readings: the preparation ahead of the post, the
# reading the proof is taken over, the one behind it a refused settlement
# stages its abandonment on, and the one that commit takes.
_TICK_READ = 0
_STAGED_ON = 1
_COMMITTED_OVER = 2
_SETTLEMENT_PREPARED = 1
_SETTLEMENT_PROVED_OVER = 2
_SETTLEMENT_STAGED_ON = 3
_SETTLEMENT_COMMITTED_OVER = 4

_ABANDONED = _records.Retirement.ABANDONED

_LEVEL = "INFO"

# An approval of another subject than the one the carry was recorded for, and
# the carry's own approval with its pull request spelled as a float.
_REPLACEMENT = road.Move(
    "a replacement approval", _review_subjects.APPROVED_SUBJECT,
    lambda case: {**case.subject.recorded(), "sha": support.REBASED_SHA},
)

_RESPELLED = road.Move(
    "the approval respelled", _review_subjects.APPROVED_SUBJECT,
    lambda case: {**case.subject.recorded(), "pr": float(support.PR_NUMBER)},
)


# The report debt a carry's review subject stands only without
# (`report_delivery.owes_a_report`): the debt an undeliverable park records,
# and that park's own reason -- each as another road records it, and as one
# pays it.
_DEBTS = (
    (
        road.Move("a report owed", _report_delivery.OWED_REPORT, lambda _case: True),
        road.Move("the owed report paid", _report_delivery.OWED_REPORT, lambda _case: road.GONE),
    ),
    (
        road.Move("an undeliverable park", "park_reason", lambda _case: _report_delivery.UNDELIVERABLE_REPORT),
        road.Move("the park answered", "park_reason", lambda _case: road.GONE),
    ),
)


def _history(state) -> list[tuple]:
    """Each retired record `state` indexes, by receipt and why it was retired, oldest first."""
    return [(entry.receipt, entry.retired) for entry in _settlement.read_evidence_history(state)]


def _persisted(case):
    """`case`'s pinned comment as it reads now."""
    return case.gh.read_pinned_state(case.issue)


def _owed_carry(case) -> _records.PendingEvidence:
    """A carry onto the squashed head, recorded beside the approval it was recorded for."""
    case.state.set(_review_subjects.APPROVED_SUBJECT, case.subject.recorded())
    return case.record(case.binding().retargeted(support.SQUASHED_SHA))


class CarryAbandonmentTest(unittest.TestCase, support.VerificationEvidenceCase):
    """What abandoning a transaction leaves of it and of the approval beside it."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.state.set(_review_subjects.APPROVED_SUBJECT, self.subject.recorded())
        self.gh.write_pinned_state(self.issue, self.state)

    def test_a_carry_takes_its_approval(self) -> None:
        for name, carried, approval in (
            ("a carry", True, None),
            ("a run on its own head", False, self.subject.recorded()),
        ):
            with self.subTest(name):
                self.setUp()
                binding = self.binding().retargeted(support.SQUASHED_SHA) if carried else self.binding()
                pending = self.record(binding)

                self.assertTrue(_carries.abandons(self.state, pending))

                self.assertEqual(
                    (
                        _record_state.read_pending_evidence(self.state),
                        [entry.retired for entry in _settlement.read_evidence_history(self.state)],
                        self.state.get(_review_subjects.APPROVED_SUBJECT),
                    ),
                    (None, [_records.Retirement.ABANDONED], approval),
                )

    def test_only_the_recorded_transaction_goes(self) -> None:
        # Minted and never recorded, or recorded on the comment after this
        # tick read it: the comment is not this transaction's to abandon, and
        # neither it nor the approval is touched.
        carry = self.binding().retargeted(support.SQUASHED_SHA)
        unrecorded = _record_state.mint_pending_evidence(self.state, support.ISSUE_NUMBER, carry, ())
        self.assertFalse(_carries.abandons(self.state, unrecorded))

        tick = self.gh.read_pinned_state(self.issue)
        pending = self.record(carry, onto=tick)
        self.record(onto=self.gh.read_pinned_state(self.issue))

        self.assertFalse(_carries.abandons_afresh(self.gh, self.issue, tick, pending))
        self.assertEqual(
            self.gh.read_pinned_state(self.issue).get(_review_subjects.APPROVED_SUBJECT),
            self.subject.recorded(),
        )

    def test_a_replacement_approval_stands(self) -> None:
        # Another road put an approval of another subject in place of the one
        # the carry was recorded for: the carry is abandoned, the replacement
        # left as it stands.
        replacement = {**self.subject.recorded(), "sha": support.REBASED_SHA}
        pending = self.record(self.binding().retargeted(support.SQUASHED_SHA))
        self.state.set(_review_subjects.APPROVED_SUBJECT, replacement)

        self.assertTrue(_carries.abandons(self.state, pending))

        self.assertEqual(self.state.get(_review_subjects.APPROVED_SUBJECT), replacement)

    def test_a_full_comment_still_retires_it(self) -> None:
        # Filled to its limit by another road: the approval's retirement only
        # shrinks the comment, so it is written over the comment read afresh,
        # and what it frees takes the carry's entry too.
        pending = self.record(self.binding().retargeted(support.SQUASHED_SHA))
        self.state.set(FILLER, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(self.state.data))
        self.state.set(FILLER, "y" * room)
        self.gh.write_pinned_state(self.issue, self.state)

        self.assertFalse(_carries.abandons_afresh(self.gh, self.issue, self.state, pending))

        written = self.gh.read_pinned_state(self.issue)
        self.assertEqual(
            (
                written.get(_review_subjects.APPROVED_SUBJECT),
                _record_state.read_pending_evidence(written),
                _report_record_state.fits_the_comment(written.data),
            ),
            (None, None, True),
        )


class GuardedAbandonmentTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A refused carry abandoned ahead of the post lands over the comment as it stands, or writes nothing."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.carry = _owed_carry(self)

    def test_another_roads_fields_are_kept(self) -> None:
        # Behind the reading the abandonment is staged on, another road writes
        # fields it does not own, a returned verdict among them: the commit
        # lays the abandonment over them. Behind the commit's own reading, the
        # edit finds the comment moved and sends nothing, and the next tick's
        # proof refuses the carry and abandons it then. Either way it goes once
        # with its approval, and every field reads as that road wrote it.
        for number in (_STAGED_ON, _COMMITTED_OVER):
            with self.subTest(number=number):
                self.setUp()

                self.assertFalse(self.abandons_behind(number, road.writes_bookkeeping))
                if number == _COMMITTED_OVER:
                    self.assertEqual(_record_state.read_pending_evidence(_persisted(self)), self.carry)
                    self.assertFalse(self.reconcile())

                persisted = _persisted(self)
                self.assertEqual(
                    (
                        _record_state.read_pending_evidence(persisted),
                        _history(persisted),
                        persisted.get(_review_subjects.APPROVED_SUBJECT),
                    ),
                    (None, [(self.carry.receipt, _ABANDONED)], None),
                )
                self.assertEqual({**persisted.data, **road.INDEPENDENT}, persisted.data)
                self.assertIn(road.ANOTHER_ROADS_COMMENT, persisted.get(support.LEDGER))

    def test_a_moved_approval_refuses_it(self) -> None:
        # Behind the reading the abandonment is staged on, another road puts
        # an approval of another subject in place of the carry's, or spells
        # the carry's own approval with its pull request as a float. The
        # commit refuses with nothing written: the approval reads as that road
        # wrote it, and the carry is still owed.
        for move in (_REPLACEMENT, _RESPELLED):
            with self.subTest(move.name):
                self.setUp()
                writes = self.gh.write_state_calls

                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(self.abandons_behind(_STAGED_ON, move.lands))
                    self.assertIn("review_approved_subject moved", support.logged_refusal(logged))

                self.assertEqual(*move.spelled_on(self))
                self.assertEqual(
                    (self.gh.write_state_calls - writes, _record_state.read_pending_evidence(_persisted(self))),
                    (1, self.carry),
                )

    def test_an_unconfirmed_abandonment_replays_once(self) -> None:
        # The commit is accepted with its response lost, or refused outright:
        # the tick holds. The next tick finds nothing owed, or its proof
        # refuses the carry and abandons it then -- with its approval, one
        # history entry either way, and nothing posted.
        for failure in ("lost", "refused"):
            with self.subTest(failure):
                self.setUp()
                failures = getattr(self.gh.pinned_failures, failure)
                failures.add(support.ISSUE_NUMBER)
                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertTrue(_carries.abandons_afresh(
                        self.gh, self.issue, _persisted(self), self.carry,
                    ))
                    self.assertIn("never confirmed", support.logged_refusal(logged))
                failures.clear()

                self.assertFalse(self.reconcile())

                self.assertEqual(
                    (
                        _record_state.read_pending_evidence(self.state),
                        _history(self.state),
                        self.state.get(_review_subjects.APPROVED_SUBJECT),
                        self.artifacts(),
                    ),
                    (None, [(self.carry.receipt, _ABANDONED)], None, []),
                )

    def abandons_behind(self, number: int, moves) -> bool:
        """Abandon the carry over this tick's reading, `moves` landing behind the `number`-th reading it takes."""
        tick = self.gh.read_pinned_state(self.issue)
        return road.Behind(self, number, moves).runs(
            _carries.abandons_afresh, self.gh, self.issue, tick, self.carry,
        )


class RefusedSettlementTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A carry whose settlement a push refused is abandoned with its artifact's entry over the comment as it stands."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.carry = _owed_carry(self)
        self.moves_the_head(support.SQUASHED_SHA)
        self.posts = self.gh._post_verification_artifact

    def test_another_roads_fields_are_kept(self) -> None:
        # Behind the reading the settlement's abandonment is staged on,
        # another road writes fields it does not own and a comment of its own
        # onto the ledger: the commit lays the abandonment and the artifact's
        # entry over them. Behind the commit's own reading, the edit finds the
        # comment moved and sends nothing; the artifact's entry is committed
        # alone, and the next tick's proof refuses the carry and abandons it.
        # Either way it goes once with its approval, one artifact is on the
        # pull request and on the ledger beside that road's comment, and
        # every field reads as that road wrote it.
        for number in (_SETTLEMENT_STAGED_ON, _SETTLEMENT_COMMITTED_OVER):
            with self.subTest(number=number):
                self.setUp()

                self.assertFalse(self.refused_behind(number, road.writes_bookkeeping))
                if number == _SETTLEMENT_COMMITTED_OVER:
                    self.assertEqual(_record_state.read_pending_evidence(_persisted(self)), self.carry)
                    self.assertFalse(self.reconcile())

                persisted = _persisted(self)
                self.assertEqual(
                    (
                        _record_state.read_pending_evidence(persisted),
                        _history(persisted),
                        persisted.get(_review_subjects.APPROVED_SUBJECT),
                        self.artifacts(),
                    ),
                    (None, [(self.carry.receipt, _ABANDONED)], None, [self.carry.artifact]),
                )
                self.assertEqual({**persisted.data, **road.INDEPENDENT}, persisted.data)
                self.assertLessEqual(
                    {road.ANOTHER_ROADS_COMMENT, self.pull_request.issue_comments[-1].id},
                    set(persisted.get(support.LEDGER)),
                )

    def test_a_moved_approval_refuses_it(self) -> None:
        # Another road puts an approval of another subject in place of the
        # carry's, or respells the carry's own, behind the preparation ahead
        # of the post, behind the reading the proof is taken over, or behind
        # the reading the abandonment is staged on. However early, the move
        # refuses what the tick decided over rather than the carry's binding:
        # the carry stays owed and only the artifact's ledger entry is
        # committed. The next tick's proof refuses the carry and abandons it,
        # leaving the approval as that road wrote it, with no second artifact.
        windows = (_SETTLEMENT_PREPARED, _SETTLEMENT_PROVED_OVER, _SETTLEMENT_STAGED_ON)
        for move, number in itertools.product((_REPLACEMENT, _RESPELLED), windows):
            with self.subTest(move.name, number=number):
                self.setUp()
                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(self.refused_behind(number, move.lands))
                    self.assertIn("review_approved_subject moved", support.logged_refusal(logged))
                persisted = _persisted(self)
                self.assertEqual(_record_state.read_pending_evidence(persisted), self.carry)
                self.assertIn(
                    self.pull_request.issue_comments[-1].id, persisted.get(support.LEDGER),
                )

                self.assertFalse(self.reconcile())

                self.assertEqual(*move.spelled_on(self))
                self.assertEqual(
                    (_record_state.read_pending_evidence(self.state), _history(self.state), self.artifacts()),
                    (None, [(self.carry.receipt, _ABANDONED)], [self.carry.artifact]),
                )

    def test_a_spoiled_comment_holds_it(self) -> None:
        # Replaced by another comment carrying the same record, or edited into
        # something that does not parse, behind the reading the settlement's
        # abandonment is staged on: the tick holds and nothing is written.
        for spoils in (road.repins, road.unparses):
            with self.subTest(spoils.__name__):
                self.setUp()
                writes = self.gh.write_state_calls

                with self.assertLogs(support.WORKFLOW_LOG, "WARNING"):
                    self.assertTrue(self.refused_behind(_SETTLEMENT_STAGED_ON, spoils))

                self.assertEqual(self.gh.write_state_calls, writes)

    def test_an_unconfirmed_abandonment_replays_once(self) -> None:
        # The settlement's abandonment is accepted with its response lost, or
        # refused outright: the tick holds. The next tick finds nothing owed,
        # or its proof refuses the carry and abandons it then -- one artifact
        # and one history entry either way, the approval retired.
        for failure in ("lost", "refused"):
            with self.subTest(failure):
                self.setUp()
                failures = getattr(self.gh.pinned_failures, failure)
                failures.add(support.ISSUE_NUMBER)
                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged, patch.object(
                    self.gh, "_post_verification_artifact", self.posts_then_pushes,
                ):
                    self.assertTrue(self.reconcile())
                    self.assertIn("never confirmed", support.logged_refusal(logged))
                failures.clear()

                self.assertFalse(self.reconcile())

                self.assertEqual(
                    (
                        _record_state.read_pending_evidence(self.state),
                        _history(self.state),
                        self.state.get(_review_subjects.APPROVED_SUBJECT),
                        self.artifacts(),
                    ),
                    (None, [(self.carry.receipt, _ABANDONED)], None, [self.carry.artifact]),
                )

    def refused_behind(self, number: int, moves) -> bool:
        """A tick whose post a push follows, `moves` landing behind the `number`-th pinned reading it takes."""
        with patch.object(self.gh, "_post_verification_artifact", self.posts_then_pushes):
            return road.Behind(self, number, moves).reconciles()

    def posts_then_pushes(self, pull_request, body: str):
        """Land the artifact, then push the pull request past the head the carry answers for."""
        landed = self.posts(pull_request, body)
        self.moves_the_head(support.REBASED_SHA)
        return landed


class ReportDebtTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A report debt another road moves under a carry's proof abandons nothing and settles nothing."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.carry = _owed_carry(self)
        self.moves_the_head(support.SQUASHED_SHA)

    def test_a_debt_paid_abandons_nothing(self) -> None:
        # The carry's proof refuses it only because a developer report is
        # owed -- the debt an undeliverable park records, or that park's
        # reason. Another road pays the debt behind the tick's own reading, or
        # behind the reading the abandonment is staged on: the refusal the
        # tick would abandon the carry over no longer stands, so nothing is
        # written and the carry stays owed with its approval. The next tick
        # publishes it and settles it once.
        for (owes, pays), number in itertools.product(_DEBTS, (_TICK_READ, _STAGED_ON)):
            with self.subTest(owes.name, number=number):
                self.setUp()
                owes.lands(self)
                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(self.reconciles_behind(number, pays.lands))
                    self.assertIn(
                        f"{owes.record} moved since this tick read it", support.logged_refusal(logged),
                    )
                self.assertEqual(self.standing(), self.owed())

                self.assertFalse(self.reconcile())

                self.assertEqual(_settlement.read_current_evidence(self.state).receipt, self.carry.receipt)
                self.assertEqual(self.artifacts(), [self.carry.artifact])

    def test_a_debt_recorded_under_the_settlement(self) -> None:
        # The carry proves, and another road records a report debt behind the
        # preparation ahead of its post, or while the settlement's proof is
        # taken. A record the proof reads moved under it, so the carry is
        # neither settled nor abandoned: it stays owed beside its approval,
        # and its artifact is recorded as ours. Once the debt is paid, the next
        # tick settles the one artifact.
        for (owes, pays), number in itertools.product(_DEBTS, (_SETTLEMENT_PREPARED, _SETTLEMENT_PROVED_OVER)):
            with self.subTest(owes.name, number=number):
                self.setUp()
                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(self.reconciles_behind(number, owes.lands))
                    self.assertIn(
                        f"{owes.record} moved since this tick read it", support.logged_refusal(logged),
                    )
                self.assertEqual(self.standing(), self.owed(self.carry.artifact))

                pays.lands(self)
                self.assertFalse(self.reconcile())

                self.assertEqual(_settlement.read_current_evidence(self.state).receipt, self.carry.receipt)
                self.assertEqual(self.artifacts(), [self.carry.artifact])

    def reconciles_behind(self, number: int, moves) -> bool:
        """One tick, `moves` behind its `number`-th pinned reading, or behind the tick's own for `_TICK_READ`."""
        tick = self.gh.read_pinned_state(self.issue)
        if number == _TICK_READ:
            moves(self)
        return road.Behind(self, number, moves).runs(self.reconcile, tick)

    def standing(self) -> tuple:
        """The transaction owed, the approval, the history, the artifacts, and whether the ledger records each."""
        persisted = self.gh.read_pinned_state(self.issue)
        posted = {comment.id for comment in self.pull_request.issue_comments}
        ledger = set(persisted.get(support.LEDGER) or ())
        return (
            _record_state.read_pending_evidence(persisted),
            persisted.get(_review_subjects.APPROVED_SUBJECT),
            _history(persisted),
            self.artifacts(),
            posted <= ledger,
        )

    def owed(self, *artifacts) -> tuple:
        """What `standing` reads while the carry is owed beside its approval, `artifacts` posted and recorded."""
        return self.carry, self.subject.recorded(), [], list(artifacts), True


if __name__ == "__main__":
    unittest.main()
