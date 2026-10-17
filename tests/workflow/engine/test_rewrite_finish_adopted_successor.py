# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A newer transaction another road records beside a settlement the evidence phase adopts, kept owed.

The captured case (`rewrite_captured_test_support.CapturedEvidenceCase`):
issue #7's run captured for the landed head, and the evidence phase asked
directly over the finish a later recovery holds. Another
finish settles the run while this one's answer reads the pull request, and a
later review is handed over under it, so the run's binding moved; as this
finish adopts that settlement -- as it invalidates the settlement it
adopted, or right behind that invalidation's write -- another road records a
newer transaction of the head bound to that review, its binding proved as it
is recorded. Only
the adopted settlement is invalidated over what the answer read, and the
route is held with the successor owed as recorded, for the next finish to
answer, the finish's own state carrying it. So is a continuation over a head
the base advanced past, whose abandonment of the run takes in its settlement
beside a successor that reads or one nobody can read, recorded ahead of that
abandonment or right behind its invalidation's write -- and so is another
road's attempt pinned right behind that write, laid over the finish's state,
whether the phase or a continuation made it. A settlement another
finish lands right behind the
answer's own retirement of the run -- a pull request read closed -- is read
back in that retirement's place and invalidated whole, held over a successor
recorded beside it; and a record the answer's retirement read moved, put back
before another finish settles the run, invalidates that settlement all the
same, whether the retirement read it on its own reading of the comment, its
commit's, or its strict edit's. A settlement landing right behind a
continuation's abandonment that did land is read back and invalidated whole
the same way, held over a successor beside it. Nothing runs, and the run is
posted once.
"""
from __future__ import annotations

import contextlib
import itertools
import unittest
from dataclasses import replace
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import (
    rewrite_finish_readiness as _readiness,
    rewrite_finish_settlement as _settlement_step,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_transaction as _transaction,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_captured_test_support as settled_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
    verification_evidence_test_support as support,
    verification_report_fixture as report,
)
from tests.workflow.interleaving import _RacesPastTheStep, _RacesTheStep

# A pending record nobody can read, as another road may leave one.
_UNREADABLE = "unreadable"

# The client's strict edit of the pinned comment.
_EDIT = "edit_pinned_state"

# The answer's own reading of the pull request: the second, behind the
# captured run's proof again.
_ANSWERS = 2

# The comment a handoff put back names the captured run's artifact at.
_HANDED_OVER = 1

# The records the retirement's reading reads moved, and the floor beside them,
# put back behind it: the report and review records a later review moves.
_RESTORED = (
    "developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject",
    readings.KEY_REVISION_FLOOR,
)

# Where the successor arrives behind the answer: ahead of the adoption that
# takes the comment in, as the settlement adopted is invalidated, or right
# behind that invalidation's write, before it returns -- the owner and name of
# that step, and the race that records it there.
_BEHIND_THE_INVALIDATION = "behind its invalidation"

# Another road's attempt pinned in place of the landing's, its anchor another head.
_REPLACES = partial(settled_moves.writes_over, key=readings.KEY_PENDING_PUSH, written=support.SQUASHED_SHA)
_ARRIVALS = MappingProxyType({
    "ahead of the adoption": (_durable, "takes_in_a_settlement", _RacesTheStep),
    "as it is invalidated": (_readiness, "invalidates", _RacesTheStep),
    _BEHIND_THE_INVALIDATION: (_readiness, "invalidates", _RacesPastTheStep),
})


def _fallen_behind(finish):
    """`finish` over a candidate that counted the base two commits past the landed head."""
    checkout = finish.landed.candidate.checkout
    checkout = replace(checkout, base=replace(checkout.base, behind=2))
    candidate = replace(finish.landed.candidate, checkout=checkout)
    return replace(finish, landed=replace(finish.landed, candidate=candidate))


class _SuccessorCase(settled_support.CapturedEvidenceCase):
    """Issue #7's captured run, settled by another finish, beside which another road records a successor."""

    def _settles_and_reviews(self) -> None:
        """Settle the run as another finish of the landing would (`_settles_elsewhere`), then review it again."""
        self._settles_elsewhere()
        self.rereads()
        self.reviewed = report.settles_report(self, 3, head=self.head)
        self.gh.write_pinned_state(self.issue, self.state)

    def _settles_elsewhere(self) -> None:
        """Post the captured run's artifact and settle it, as another finish of the landing would."""
        state = self.gh.read_pinned_state(self.issue)
        posted = self.gh.publish_verification_artifact(self.pull_request, self.captured.artifact)
        self.gh.write_pinned_state(self.issue, _settlement.settled_state(
            state, self.captured, posted.landed_id, finish_support.REVIEWING,
        ))

    def _records_beside(self, *, readable: bool) -> None:
        """Another road's newer transaction of the head beside the settlement, or one nobody can read; `written`."""
        if not readable:
            settled_moves.writes_over(self, _records.PENDING_EVIDENCE, _UNREADABLE)
            self.written = _UNREADABLE
            return
        state = self.gh.read_pinned_state(self.issue)
        commands = self.captured.commands
        newer = _record_state.mint_pending_evidence(state, support.ISSUE_NUMBER, self.captured.binding, commands)
        self.assertTrue(_record_state.record_pending_evidence(state, newer))
        self.gh.write_pinned_state(self.issue, state)
        self.written = readings.pinned(self)[_records.PENDING_EVIDENCE]

    def _records_a_successor(self) -> None:
        """Another road's newer transaction of the head, bound to that later review and proved, recorded once."""
        state = self.gh.read_pinned_state(self.issue)
        if _record_state.carries_pending_evidence(state):
            return
        target = replace(self.captured.binding.target, subject=self.reviewed.recorded())
        binding = replace(self.captured.binding, target=target)
        reading = _proof.ProofReading(self.gh, self.landed().spec, self.issue, state)
        self.assertTrue(_proof.binding_verdict(reading, binding).proved)
        commands = self.captured.commands
        self.successor = _record_state.mint_pending_evidence(state, support.ISSUE_NUMBER, binding, commands)
        self.assertTrue(_record_state.record_pending_evidence(state, self.successor))
        self.gh.write_pinned_state(self.issue, state)

    def _arrives(self, arrival: str, records):
        """The step `arrival` names (`_ARRIVALS`) patched to have another road `records` its successor there."""
        owner, step, race = _ARRIVALS[arrival]
        return patch.object(owner, step, race(getattr(owner, step), records))

    def _assert_owed(self, finish) -> None:
        """The run invalidated whole, `written` owed on the comment and in `finish`'s state, and nothing run."""
        self._assert_invalidated()
        self.assertEqual(readings.pinned(self)[_records.PENDING_EVIDENCE], self.written)
        self.assertEqual(finish.state.get(_records.PENDING_EVIDENCE), self.written)
        self.assertEqual(self.verify.call_count, 0)

    def _assert_invalidated(self) -> None:
        """The adopted run invalidated whole, its revision and binding kept, with nothing current."""
        current, history = self.records()[1:]
        self.assertIsNone(current)
        self.assertEqual(history[-1], (self.captured.receipt, readings.INVALIDATED))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual(entry.revision, self.captured.revision)
        self.assertEqual(entry.binding, self.captured.binding)


class AdoptedSuccessorTest(_SuccessorCase, unittest.TestCase):
    """The successor recorded beside an adopted settlement stays owed; only that settlement is invalidated."""

    def test_the_successor_is_kept(self) -> None:
        # The run is settled elsewhere and reviewed again under the answer's
        # second reading of the pull request, and the successor is recorded
        # just ahead of the adoption that takes the comment in -- as the
        # settlement adopted is invalidated, which lands over a comment
        # carrying it, or right behind that invalidation's write, which the
        # finish's state does not carry: the phase holds, the adopted run
        # invalidated whole and the successor pending -- on the comment and
        # in the finish's state -- neither published nor settled.
        for arrival in _ARRIVALS:
            with self.subTest(arrives=arrival):
                self.setUp()
                finish = self.landed()

                with (
                    settled_moves.raced_past(self, "get_pr", type(self)._settles_and_reviews, nth=2),
                    self._arrives(arrival, self._records_a_successor),
                ):
                    self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.HELD)

                self._assert_invalidated()
                self.assertEqual(self.records()[0], self.successor)
                self.assertEqual(_record_state.read_pending_evidence(finish.state), self.successor)
                receipts = [found.receipt for found in support.posted_artifacts(self)]
                self.assertEqual(receipts.count(self.captured.receipt), 1)
                self.assertEqual(self.verify.call_count, 0)

    def test_the_continuation_holds_over_it(self) -> None:
        # The base advanced past the head, and another finish settled the run
        # after this one read it captured, a newer transaction recorded beside
        # that settlement -- one that reads, or one nobody can read: the
        # continuation's abandonment takes that settlement in and invalidates
        # it whole, and the continuation holds with the successor owed as
        # recorded, its state carrying it, rather than going on past it.
        for readable in (True, False):
            with self.subTest(readable=readable):
                self.setUp()
                finish = _fallen_behind(self.landed())
                self._settles_elsewhere()
                self._records_beside(readable=readable)

                self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.HELD)

                self._assert_owed(finish)

    def test_one_behind_the_invalidation_holds_too(self) -> None:
        # As above, but the newer transaction -- one that reads, or one
        # nobody can read -- is recorded right behind the write invalidating
        # the settlement the abandonment took in, before that invalidation
        # returns, so the continuation's state does not carry it: the comment
        # read afresh once that write landed does, and the continuation holds
        # over it, owed as recorded and taken into its state.
        for readable in (True, False):
            with self.subTest(readable=readable):
                self.setUp()
                finish = _fallen_behind(self.landed())
                self._settles_elsewhere()

                with self._arrives(_BEHIND_THE_INVALIDATION, partial(self._records_beside, readable=readable)):
                    self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.HELD)

                self._assert_owed(finish)

    def test_another_attempt_behind_it_holds(self) -> None:
        # The run is settled elsewhere and reviewed again under the answer's
        # second reading of the pull request -- or, the base advanced past the
        # head, settled elsewhere ahead of the continuation's abandonment --
        # and right behind the write invalidating that settlement another
        # road pins its own attempt: the comment read afresh behind that write
        # carries it, so it is laid over the finish's state and the phase
        # holds rather than routing or continuing past it, the adopted run
        # invalidated whole.
        for continued in (False, True):
            with self.subTest(continuation=continued):
                self.setUp()
                finish = self.landed()
                if continued:
                    finish = _fallen_behind(finish)
                    self._settles_elsewhere()
                settles = contextlib.nullcontext() if continued else settled_moves.raced_past(
                    self, "get_pr", type(self)._settles_and_reviews, nth=2,
                )

                with settles, self._arrives(_BEHIND_THE_INVALIDATION, partial(_REPLACES, self)):
                    self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.HELD)

                self._assert_invalidated()
                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], support.SQUASHED_SHA)
                self.assertEqual(finish.state.get(readings.KEY_PENDING_PUSH), support.SQUASHED_SHA)
                self.assertEqual(self.verify.call_count, 0)


def _carries_its_revision(case) -> None:
    """Leave the evidence handoff naming `case`'s captured run beside its record, as a comment put back would."""
    state = case.gh.read_pinned_state(case.issue)
    settled_over = _settlement.settled_state(state, case.captured, _HANDED_OVER, finish_support.REVIEWING)
    settled_moves.writes_over(case, _records.EVIDENCE_HANDOFF, settled_over.get(_records.EVIDENCE_HANDOFF))


# Where the retirement reads a later review moved: the owner and name of the
# step it is made ahead of, and whether it is made under that step's strict
# edit instead -- the retirement's own reading of the comment, its commit's
# fresh reading, or the comment its strict edit reads.
_RETIREMENT_READS = MappingProxyType({
    "its reading": (_transaction, "_retires", False),
    "its commit's reading": (_durable, "lands_observing", False),
    "its strict edit": (_durable, "lands_observing", True),
})

# What the tick's reading carries that retires the captured run as the answer
# reads it: a floor nobody can read, which abandons it, or a handoff already
# naming its revision, which drops its record outright.
_RETIRES_IT = MappingProxyType({
    "a floor nobody can read": partial(
        settled_moves.writes_over, key=readings.KEY_REVISION_FLOOR, written=_UNREADABLE,
    ),
    "its revision already handed over": _carries_its_revision,
})


class _SettlesOverTheAbandonment:
    """The answer's reading of the pull request closed, and another finish's settlement landing over its retirement.

    The pull request is closed just as the answer reads it the second time --
    behind the captured run's proof again -- and reopened right behind that
    reading (`ends`). The retirement that reading earns lands through the
    strict edit (`edits`), and another finish's settlement of the run, whose
    own edit read the comment before that retirement landed, lands right
    behind it over the comment as that finish read it -- a successor recorded
    beside it where `successor` -- so both edits answered EDITED and the
    comment carries the settlement. `armed` lands it behind the first strict
    edit instead, whatever reading came before: a continuation's abandonment
    of the run among them.
    """

    def __init__(self, case: _SuccessorCase, *, successor: bool, armed: bool = False) -> None:
        self._case = case
        self._successor = successor
        self._read = _proof._publication.subject_verdict
        self._edit = case.gh.edit_pinned_state
        self._reads = 0
        self._armed = armed

    def ends(self, *called, **options):
        """The proof's reading of the pull request, the second one read closed."""
        self._reads += 1
        if self._reads != _ANSWERS:
            return self._read(*called, **options)
        self._case.pull_request.state = "closed"
        answered = self._read(*called, **options)
        self._case.pull_request.state = "open"
        self._armed = True
        return answered

    def edits(self, issue, state, **options):
        """The strict edit, another finish's settlement landing right behind the first one the closed reading earns."""
        if not self._armed:
            return self._edit(issue, state, **options)
        self._armed = False
        case = self._case
        before = case.gh.read_pinned_state(case.issue)
        answered = self._edit(issue, state, **options)
        posted = case.gh.publish_verification_artifact(case.pull_request, case.captured.artifact)
        settled_over = _settlement.settled_state(before, case.captured, posted.landed_id, finish_support.REVIEWING)
        case.gh.write_pinned_state(case.issue, settled_over)
        if self._successor:
            case._records_beside(readable=True)
        return answered


class _MovesUnderTheRetirement:
    """A retirement step, a later review handed over just ahead of it -- or of its strict edit -- put back behind it.

    Made once: right behind that step, the records `kept` names are put back
    as they read before and another finish settles the run over them
    (`RetiredUnderTheAnswerTest._puts_back_and_settles`).
    """

    def __init__(self, case: RetiredUnderTheAnswerTest, step, kept: dict, *, under_the_edit: bool) -> None:
        self._case = case
        self._step = step
        self._kept = kept
        self._under_the_edit = under_the_edit
        self._owed = True

    def __call__(self, *called, **options):
        if not self._owed:
            return self._step(*called, **options)
        self._owed = False
        moves = partial(settled_moves.reviews_again, self._case)
        if self._under_the_edit:
            edits = _RacesTheStep(self._case.gh.edit_pinned_state, moves)
            with patch.object(self._case.gh, _EDIT, edits):
                answered = self._step(*called, **options)
        else:
            moves()
            answered = self._step(*called, **options)
        self._case._puts_back_and_settles(self._kept)
        return answered


class RetiredUnderTheAnswerTest(_SuccessorCase, unittest.TestCase):
    """A settlement another finish made while the answer retired the run is adopted, and invalidated over movement."""

    def test_a_settlement_over_it_is_retired(self) -> None:
        # The answer reads the pull request closed and retires the run, and
        # another finish's settlement of the run -- read before that
        # retirement landed -- lands right behind it, a successor recorded
        # beside it or not: the phase reads that settlement back in place of
        # its own retirement and invalidates it whole over the end it read,
        # holding where the successor stands owed as recorded.
        for successor, answer in ((False, None), (True, FinishOutcome.HELD)):
            with self.subTest(successor=successor):
                self.setUp()
                races = _SettlesOverTheAbandonment(self, successor=successor)

                with (
                    patch.object(_proof._publication, "subject_verdict", races.ends),
                    patch.object(self.gh, _EDIT, races.edits),
                ):
                    resolved = self.asks(_settlement_step.resolves, self.landed())

                self.assertEqual(resolved, answer)
                self._assert_invalidated()
                if successor:
                    self.assertEqual(readings.pinned(self)[_records.PENDING_EVIDENCE], self.written)

    def test_a_settlement_behind_its_abandonment(self) -> None:
        # The base advanced past the head, and the continuation's abandonment
        # of the run lands -- but another finish's settlement of the run, made
        # over the comment read before that write, lands right behind it, a
        # successor recorded beside it or not: the continuation reads the
        # comment afresh behind its abandonment and invalidates that
        # settlement whole, going on where nothing else stands and holding
        # with the successor owed as recorded, its state carrying it.
        for successor, answer in ((False, None), (True, FinishOutcome.HELD)):
            with self.subTest(successor=successor):
                self.setUp()
                finish = _fallen_behind(self.landed())
                races = _SettlesOverTheAbandonment(self, successor=successor, armed=True)

                with patch.object(self.gh, _EDIT, races.edits):
                    self.assertEqual(self.asks(_settlement_step.resolves, finish), answer)

                self._assert_invalidated()
                pending = readings.pinned(self).get(_records.PENDING_EVIDENCE)
                self.assertEqual(pending is not None, successor)
                self.assertEqual(finish.state.get(_records.PENDING_EVIDENCE), pending)
                self.assertEqual(self.verify.call_count, 0)

    def test_a_move_the_retirement_read_is_movement(self) -> None:
        # The tick's reading retires the run as the answer reads it -- a
        # floor nobody can read abandons it, and a handoff already naming its
        # revision drops its record -- and a later review is handed over just
        # as that retirement reads the comment, as its commit reads it afresh,
        # or as its strict edit does, each of which refuses it; the review
        # and floor are put back right behind, and another finish settles the
        # run. The record that retirement read moved is movement, so the
        # settlement adopted is invalidated whole despite the restoration,
        # with nothing run.
        for case, read in itertools.product(_RETIRES_IT, _RETIREMENT_READS):
            with self.subTest(case=case, read=read):
                self.setUp()

                self._retires_under(case, read)

                self._assert_invalidated()
                self.assertEqual(self.verify.call_count, 0)

    def _retires_under(self, case: str, read: str) -> None:
        """The phase, the run retired as `case` has it and a later review read moved where `read` says, put back."""
        kept = {key: readings.pinned(self)[key] for key in _RESTORED}
        _RETIRES_IT[case](self)
        owner, step, under_the_edit = _RETIREMENT_READS[read]
        moves = _MovesUnderTheRetirement(self, getattr(owner, step), kept, under_the_edit=under_the_edit)
        with patch.object(owner, step, moves):
            self.asks(_settlement_step.resolves, self.landed())

    def _puts_back_and_settles(self, kept: dict) -> None:
        """Put `kept` back over the comment as it stands, then settle the run as another finish would."""
        state = self.gh.read_pinned_state(self.issue)
        for key, recorded in kept.items():
            state.set(key, recorded)
        self.gh.write_pinned_state(self.issue, state)
        self._settles_elsewhere()


if __name__ == "__main__":
    unittest.main()
