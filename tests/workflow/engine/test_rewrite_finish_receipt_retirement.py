# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence read moving, retired under its own receipt however the attempt or the comment moved since.

The retirement case (`receipt_retirement_support`): issue #7's run settled
under the anchor, each retirement primitive asked directly over a finish held
to the dormant settled-evidence policy while another road or another finish of
the landing moves the attempt or the comment. An announcement another finish
put on the attempt is taken in and the invalidation made over it, retried once
over the comment read afresh where it landed under the first write; a route or
another attempt that took the attempt has the same receipt retired as the
comment stands, that attempt kept; a successor settled under another receipt
is never written over. Behind the phase's own invalidation the comment is read
afresh, so a newer transaction or another attempt another road wrote right
behind that write holds the route, laid over the finish's state, and the run
put back current there is retired again, where a blank of the base tip or this
landing's own announcement does not hold it; where nothing has room, the
movement is recorded as
`test_rewrite_finish_recorded_movement` covers. A routed head with nothing
current is held to a base its attempt can prove, the base the tick counted
where its tip is blank or missing. A readable
revision spent past the run -- the floor, or the one minted under a readable
pending record -- outranks it beside a pending record too, which still holds,
also where the phase holds over that pending record's proof itself; a
continuation abandons a newer transaction before the run is proved, so it
never holds over it.
A finish the policy does not hold refuses every one of these moves, reading
the comment no more often than it always has. Nothing runs, posts, launches,
relabels, or charges.
"""
from __future__ import annotations

import contextlib
import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.workflow.engine import (
    rewrite_finish_marks as _marks,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_settled as _settled,
    rewrite_finish_settlement as _settlement_step,
    rewrite_finish_unconfirmed as _unconfirmed,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    receipt_retirement_support as retirement,
    rewrite_captured_test_support as settled_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
    verification_evidence_test_support as support,
)
from tests.workflow.interleaving import _RacesPastTheCall, _RacesPastTheStep

_HANDOFF = _records.EVIDENCE_HANDOFF

_HELD = FinishOutcome.HELD

# A record another road writes beside the evidence, which nothing here owns.
_UNKNOWN = "another_roads_record"

# Whether another finish's announcement lands just behind the invalidation's
# first reading of the comment rather than ahead of it, and whether the finish
# asking is held to the dormant policy.
_ANNOUNCED = (
    (False, True),
    (False, False),
    (True, True),
    (True, False),
)

# What took the attempt off the comment: another finish's route, or another
# road's attempt, its anchor a head or a JSON object or list no head is.
_TAKEN = (
    ("routed", retirement.routes),
    ("replaced", retirement.replaces),
    ("replaced by an object", partial(retirement.replaces, written={"sha": settled_support.REBASED})),
    ("replaced by a list", partial(retirement.replaces, written=[settled_support.REBASED])),
)

# What refuses the first write of an invalidation for a finish the policy does
# not hold, how many times it reads the comment -- once afresh, never again,
# then whatever the tick's own copy's write reads -- and whether it landed: the
# comment full, its movement recorded on the tick's copy instead, or the
# comment unread once, the tick's copy taking the invalidation.
_UNSELECTED = (
    ("the comment full", lambda case: contextlib.nullcontext(moves.fills_the_comment(case)), (4, False)),
    (
        "the comment unread once",
        lambda case: patch.object(case.gh, "read_pinned_state", settled_support.FailsOnce(case.gh.read_pinned_state)),
        (2, True),
    ),
)

# The pending record, which the phase lays over its state as the comment carries it.
_PENDING = _records.PENDING_EVIDENCE

# What another road writes right behind the phase's invalidation of the run,
# before that invalidation returns -- handed the case and the comment as it
# read before the run moved -- what the phase answers once it reads the
# comment afresh, and whether the finish's state then carries the attempt as
# the comment does: a newer transaction of the head, or another attempt in
# place of the one the finish read, holds the route, laid over that state, and
# so does the run put back current with the records it was bound to, which is
# retired again; a blank of the base tip records movement rather than another
# attempt, and this landing's own announcement is taken in, so the route goes
# on beside either.
_BEHIND_THE_INVALIDATION = (
    ("a newer transaction", lambda case, kept: settled_moves.records_a_newer_one(case), _HELD, True),
    ("another attempt", lambda case, kept: retirement.replaces(case), _HELD, True),
    ("the run put back", lambda case, kept: case.puts_back(kept), _HELD, True),
    (
        "a blank base tip",
        lambda case, kept: settled_moves.writes_over(case, readings.KEY_REWRITE_BASE, None),
        None,
        False,
    ),
    ("its own announcement", lambda case, kept: retirement.announces(case), None, True),
)

# How the attempt records the base tip its replay was made onto, how the base
# the tick counted the head against reads now, and what the policy answers.
_BASES = (
    ("blank", _BaseStanding.STANDING, None),
    ("blank", _BaseStanding.MOVED, _HELD),
    ("missing", _BaseStanding.MOVED, _HELD),
    ("recorded", _BaseStanding.MOVED, _HELD),
)


def _drops_one_first(case, floor: object = None) -> object:
    """Record a newer transaction and drop it with no history entry, then record another; the one pending.

    `floor`, where given, is what the revision floor is left spelled as behind
    them -- one nobody can read, so only the pending record says what was spent.
    """
    settled_moves.records_a_newer_one(case)
    settled_moves.writes_over(case, _records.PENDING_EVIDENCE, None)
    pending = settled_moves.records_a_newer_one(case)
    if floor is not None:
        settled_moves.writes_over(case, readings.KEY_REVISION_FLOOR, floor)
    return pending


def _raises_the_floor_past(case) -> object:
    """Record a newer transaction, then raise the revision floor past it, as another road spending one would; it."""
    pending = settled_moves.records_a_newer_one(case)
    settled_moves.writes_over(case, readings.KEY_REVISION_FLOOR, pending.revision + 1)
    return pending


# A base advanced past the landed head again, as the tick counted it.
_ADVANCED = _BranchDivergence(tip=support.SQUASHED_SHA, behind=1, readable=True)

# A transaction dropped before the one pending, the floor then left unreadable.
_BESIDE_AN_UNREADABLE_FLOOR = partial(_drops_one_first, floor="unreadable")


def _resolves_behind(case, writes, answer):
    """The phase over a dormant finish answering `answer`, `writes` made right behind its invalidation; the finish.

    The review moved first, so the phase's readiness proof invalidates the run;
    `writes` is handed the comment as it read before that.
    """
    finish = case.dormant()
    kept = case.pinned()
    settled_moves.reviews_again(case)
    racing = _RacesPastTheStep(_readiness.invalidates, partial(writes, case, kept))
    with patch.object(_readiness, "invalidates", racing):
        case.assertEqual(case.asks(_settlement_step.resolves, finish), answer)
    return finish


def _assert_read_behind(case, finish, takes_the_attempt: bool) -> None:
    """The run invalidated whole and nothing run; `finish`'s state carrying the pending record the comment does.

    And the attempt as the comment carries it, where `takes_the_attempt`.
    """
    history = _settlement.read_evidence_history(case.gh.read_pinned_state(case.issue))
    invalidated = _records.HistoricalEvidence.of(case.settled, _records.Retirement.INVALIDATED)
    case.assertEqual(history[-1], invalidated)
    case.assertIsNone(case.records()[1])
    case.assert_untouched()
    pinned = case.pinned()
    case.assertEqual(finish.state.get(_PENDING), pinned.get(_PENDING))
    attempts = (readings.attempt(finish.state.data), readings.attempt(pinned))
    case.assertEqual(attempts[0] == attempts[1], takes_the_attempt)


class ReconciledRetirementTest(retirement.RetirementCase, unittest.TestCase):
    """Movement under the run is retired over the attempt as reconciled, or as the comment stands; never twice."""

    def test_an_announcement_is_taken_in(self) -> None:
        # Another finish of the landing announced the head before the
        # invalidation read the comment, or just behind that read, refusing
        # its first write: the policy takes the mark and the event's record
        # in and invalidates the run over them, read afresh once more. A
        # finish the policy does not hold reads another attempt and refuses.
        for behind_the_read, held in _ANNOUNCED:
            with self.subTest(behind_the_read=behind_the_read, held=held):
                self.setUp()
                finish = self.dormant() if held else self.landed()
                settled_moves.reviews_again(self)

                with self._announcing(behind_the_read):
                    invalidated = self.asks(_readiness.invalidates, finish, self.settled)

                self.assertEqual(invalidated, held)
                self.assertEqual(self.pinned()[readings.KEY_ANNOUNCED], settled_support.REBASED)
                self.assert_untouched()
                if held:
                    self.assert_whole()
                else:
                    self.assertEqual(self.records(), self.kept())

    def test_it_is_retired_as_the_comment_stands(self) -> None:
        # Another finish's route retired the attempt, or another road pinned
        # its own -- however its anchor is spelled -- before the invalidation:
        # the route is held, but the run read moving is retired over the
        # comment as it stands, whatever attempt it carries kept as written.
        for name, takes in _TAKEN:
            with self.subTest(name):
                self.setUp()
                finish = self.dormant()
                settled_moves.reviews_again(self)
                takes(self)
                attempt = readings.attempt(self.pinned())

                self.assertFalse(self.asks(_readiness.invalidates, finish, self.settled))

                self.assert_whole()
                self.assert_untouched(attempt)

    def test_a_successor_is_kept(self) -> None:
        # Another road settled a newer run of the head under its own receipt:
        # no primitive retires, marks, or puts back anything under the run
        # that receipt superseded, and the comment stays exactly as written.
        finish = self.dormant()
        settled_moves.reviews_again(self)
        retirement.supersedes(self)
        written = self.pinned()
        self.artifacts_before += 1

        answers = (
            self.asks(_readiness.invalidates, finish, self.settled),
            self.asks(_marks.retires_as_it_stands, finish, self.settled.receipt),
            self.asks(_unconfirmed.stands_back, finish, self.settled),
        )
        self.asks(_marks.marks, finish, self.settled, "the run moved")

        self.assertEqual(answers, (False, False, False))
        self.assertEqual(self.pinned(), written)
        superseded = self.records()[2][-1]
        self.assertEqual(superseded, (self.settled.receipt, "superseded"))
        self.assert_untouched()

    def test_an_unselected_one_reads_as_before(self) -> None:
        # A finish the policy does not hold reads the comment once afresh and,
        # where that write does not land, falls back to the tick's own copy
        # with nothing read again: no announcement taken in, no retry.
        for name, refuses, answers in _UNSELECTED:
            with self.subTest(name):
                self.setUp()
                finish = self.landed()
                settled_moves.reviews_again(self)

                with refuses(self):
                    counted = self.calls_to("read_pinned_state", _readiness.invalidates, finish, self.settled)

                self.assertEqual((counted, self.records()[1] is None), answers)
                self.assert_untouched()

    def test_an_attempt_put_back_keeps_the_movement(self) -> None:
        # Another road pinned its own attempt and the review moved: the phase
        # reads the movement and finds that other attempt, and just as it
        # reads the comment again to retire the run as it stands, that road
        # puts the attempt and the review back. The movement already read
        # retires the run whole over the attempt put back: the phase holds
        # once, and the next goes on with nothing current.
        finish = self.dormant()
        written = self.pinned()
        settled_moves.reviews_again(self)
        retirement.replaces(self)
        restores = _RacesPastTheCall(_durable.durable_comment, 1, partial(self.puts_back, written))

        with patch.object(_durable, "durable_comment", restores):
            first = self.asks(_settlement_step.resolves, finish)
        again = self.asks(_settlement_step.resolves, self.dormant())

        self.assertEqual((first, again), (_HELD, None))
        self.assert_whole()
        self.assert_untouched(readings.attempt(written))

    def test_what_lands_behind_it_is_read(self) -> None:
        # The review moved, so the phase's readiness proof invalidates the run,
        # and right behind that write, before it returns, another road writes
        # the comment: the phase reads it afresh and lays what it carries over
        # the finish's state -- holding over a newer transaction or another
        # attempt, and over the run put back current with its review, which it
        # retires again, going on beside a blank base tip or this landing's
        # own announcement -- the run invalidated whole either way.
        for name, writes, answer, takes_the_attempt in _BEHIND_THE_INVALIDATION:
            with self.subTest(name):
                self.setUp()

                finish = _resolves_behind(self, writes, answer)

                _assert_read_behind(self, finish, takes_the_attempt)

    def _announcing(self, behind_the_read: bool):
        """Another finish's announcement, made now or just behind the next reading of the comment; its context."""
        if behind_the_read:
            return settled_moves.raced_past(self, "read_pinned_state", retirement.announces)
        return contextlib.nullcontext(retirement.announces(self))


class OutrankingTest(retirement.RetirementCase, unittest.TestCase):
    """A readable revision spent past the run outranks it beside a pending record, which still holds the route."""

    def test_a_pending_record_hides_no_outranking(self) -> None:
        # Beside the transaction now pending, another road spent a revision
        # past the run that no history entry keeps: one it recorded and
        # dropped first -- which the pending record's own revision still says
        # beside a floor nobody can read -- or the floor it raised past the
        # pending one's own.
        # That revision outranks the run, which is invalidated whole while
        # the pending record holds the route, kept as that road wrote it. A
        # newer transaction recorded right past the run outranks nothing.
        for spends, outranked in (
            (_drops_one_first, True),
            (_BESIDE_AN_UNREADABLE_FLOOR, True),
            (_raises_the_floor_past, True),
            (settled_moves.records_a_newer_one, False),
        ):
            with self.subTest(spent=spends):
                self.setUp()
                pending = spends(self)

                answered = self._proves_ready()

                kept = None if outranked else self.settled
                self.assertEqual(answered, (_HELD, (pending, kept)))
                self.assert_untouched()
                if outranked:
                    self._assert_retired_whole()

    def test_a_continuation_abandons_it_first(self) -> None:
        # The base advanced past the landed head again, and another road
        # recorded a newer transaction beside the run: the continuation
        # abandons it before the run is proved, so no phase holds over it,
        # and the revision it spent then outranks the run, invalidated whole;
        # every phase behind goes on with nothing current.
        newer = settled_moves.records_a_newer_one(self)
        self.world.base = _BaseStanding.DROPPED
        self.world.base_ref = _ADVANCED

        first = self.asks(_settlement_step.resolves, self._continued())
        again = self.asks(_settlement_step.resolves, self._continued())

        self.assertEqual((first, again), (None, None))
        self.assert_invalidated((newer.receipt, readings.ABANDONED))
        self.assert_untouched()

    def test_a_held_proof_hides_no_outranking(self) -> None:
        # Another road recorded a newer transaction beside the run and raised
        # the floor past both, and the branch will not fetch: every phase
        # holds over the transaction it cannot prove again, but the revision
        # spent past the run outranks it all the same, so the first phase
        # invalidates the run whole and the pending record stays as that
        # road wrote it.
        pending = _raises_the_floor_past(self)
        self.world.fetched = 1

        first = self.asks(_settlement_step.resolves, self.dormant())
        again = self.asks(_settlement_step.resolves, self.dormant())

        self.assertEqual((first, again), (_HELD, _HELD))
        self.assertEqual(self.records()[:2], (pending, None))
        self._assert_retired_whole()
        self.assert_untouched()

    def test_an_unselected_proof_reads_as_before(self) -> None:
        # Beside a pending record a finish the policy does not hold reads no
        # revision past the run at all -- dropped before it, beside a floor
        # nobody can read, or the floor raised past it -- and reads no mark
        # in the run's handoff place as movement: each holds its proof with
        # the run kept current, as the readiness proof always has.
        for spends in (
            _drops_one_first,
            _BESIDE_AN_UNREADABLE_FLOOR,
            _raises_the_floor_past,
            retirement.marks_the_run,
        ):
            with self.subTest(spent=spends):
                self.setUp()
                spends(self)

                held = self.asks(_readiness.stands_ready, self.landed(), self.settled)

                kept = self.records()[1]
                self.assertEqual((held, kept), (_HELD, self.settled))
                self.assert_untouched()

    def _continued(self):
        """The dormant finish of a landing the base advanced past again, as the tick counted it."""
        finish = self.dormant()
        candidate = finish.landed.candidate
        candidate = replace(candidate, checkout=replace(candidate.checkout, base=_ADVANCED))
        return replace(finish, landed=replace(finish.landed, candidate=candidate))

    def _proves_ready(self) -> tuple:
        """What the readiness proof over a dormant finish answers, and the pending and current records it leaves."""
        held = self.asks(_readiness.stands_ready, self.dormant(), self.settled)
        return held, self.records()[:2]

    def _assert_retired_whole(self) -> None:
        """The run invalidated into history whole, its revision, transcript, and provenance kept."""
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        invalidated = _records.HistoricalEvidence.of(self.settled, _records.Retirement.INVALIDATED)
        self.assertEqual(history[-1], invalidated)


class BaseProofTest(retirement.RetirementCase, unittest.TestCase):
    """A routed head with no evidence current is held to a base its attempt's record of the replay can prove."""

    def test_a_blank_or_missing_tip_holds_to_the_base(self) -> None:
        # Nothing is current for the head, and the attempt's base tip is
        # blank, missing as a legacy attempt leaves it, or recorded: the base
        # the tick counted the head against standing lets the route go on,
        # and one moved since holds it. A finish the policy does not hold
        # reads nothing.
        for recorded, base, answer in _BASES:
            with self.subTest(recorded=recorded, base=base.name):
                self.setUp()
                settled_moves.retires_it(self)
                self._records_the_tip(recorded)
                self.world.base = base

                proved = self.asks(_settled.stands_ready_if_settled, self.dormant(), or_the_base=True)
                unselected = self.asks(_settled.stands_ready_if_settled, self.landed(), or_the_base=True)

                self.assertEqual((proved, unselected), (answer, None))
                self.assert_untouched()

    def _records_the_tip(self, recorded: str) -> None:
        """Leave the attempt's base tip `recorded`: as the attempt pinned it, blank, or missing altogether."""
        pinned = self.pinned()
        if recorded != "recorded":
            pinned[readings.KEY_REWRITE_BASE] = None
        if recorded == "missing":
            pinned.pop(readings.KEY_REWRITE_BASE)
        self.puts_back(pinned)


if __name__ == "__main__":
    unittest.main()
