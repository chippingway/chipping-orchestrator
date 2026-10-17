# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another finish's settlement under the evidence phase's own writes, told by what moved beside it.

The retirement case (`receipt_retirement_support`) and the captured case
(`rewrite_captured_test_support.CapturedEvidenceCase`), the evidence phase
asked directly over the finish a later recovery holds.
A settlement another finish makes of a newer transaction just as the phase
lands the invalidation the configuration owes the settled run moves the
evidence records alone: that refusal is no movement under the newer
transaction, whose settlement stays current -- unless the comment that
write's strict edit read beside
the settlement records movement under it -- a later review, a blank of the
attempt's base tip, a mark in its handoff place, or a revision spent past it
-- put back or not, which invalidates it. A
settlement another finish makes of the captured run, with a later review
handed over just as the phase's own settlement edit reads the comment and
put back before that edit answers, moved the run's binding all the same: the
comment the edit read names it, and the settlement adopted is invalidated
whole despite the restoration -- as it is where another proof blanked the
attempt's base tip there to record movement, and that tip was put back, also
once the ledger entry the phase commits alone took the blank in, and where
that finish marked movement in the run's handoff place or spent a revision
past it on the floor, and the records its settlement left were put back:
the edit read only evidence records moving, but moving to movement recorded
under the run. A mark the phase's own adoption of its settlement reads, the
settlement's answer lost, is that movement too -- as is a later review, a
blank of the attempt's base tip, or a revision spent past the run that
adoption read beside the run still owed, the phase's own post never
confirmed and the run settled by another finish once that is put back --
and so is a mark the phase's
first reading of the comment saw -- or a later review or a revision spent
past the run, on the floor or shown by a history entry beside a floor nobody
can read, it saw while the run was still owed, put back before another
finish settled the run, or the pull request the answer read closed and then
reopened -- and a blank tip or a mark first recorded just as that ledger
entry takes the comment in. With that finish's
announcement of the landing in the review's place, the edit read only the
evidence records and the attempt's members moved, neither a record any
binding rests on, so the settlement adopted stays current. Nothing runs.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from types import MappingProxyType
from unittest.mock import DEFAULT, Mock, patch

from orchestrator.workflow.engine import (
    rewrite_finish_settlement as _settlement_step,
    rewrite_finish_writes as _writes,
    verification_comments as _verification_comments,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    receipt_retirement_support as retirement,
    rewrite_captured_test_support as captured_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
    settled_finish_support as settled,
    verification_evidence_test_support as support,
    verification_record_test_support as record_support,
)
from tests.workflow.interleaving import _RacesTheStep

# Why a record a newer settlement replaced as current retired, as history spells it.
_SUPERSEDED = _records.Retirement.SUPERSEDED.value

# The report and review records a later review moves, as the pinned comment spells them.
_REPORT_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# The attempt members another finish's announcement of the landing moves.
_ANNOUNCEMENT = (readings.KEY_ANNOUNCED, readings.KEY_ANNOUNCED_EVENT)

# Two of the moves another road makes beside a settlement of the run, as the
# cases name them: a later review handed over, and a revision spent past it.
_LATER_REVIEW = "a later review"
_SPENT_PAST = "a revision spent past"

# The client's strict edit of the pinned comment, which a case makes another finish's moves under.
_EDIT = "edit_pinned_state"

# The evidence handoff, in whose place a finish marks movement read under the run.
_HANDOFF = _records.EVIDENCE_HANDOFF

# The step that reads the issue and comment the phase's answer starts from.
_READS_AGAIN = "_reads_again"

# Where a move made ahead of a step keeps the pull request's state beside the records it moves.
_PULL_REQUEST = "pull request"

# The records a revision abandoned past the run is shown spent on: the
# history, and the floor left unreadable beside it.
_SPENT_RECORDS = (_records.EVIDENCE_HISTORY, readings.KEY_REVISION_FLOOR)

# The client's post of a verification artifact.
_POST = "_post_verification_artifact"

# The phase's own post of the run's artifact, raising before it lands, which
# the client answers UNCONFIRMED; every post behind it goes out.
_POST_UNCONFIRMED = lambda case: Mock(
    wraps=case.gh._post_verification_artifact, side_effect=[RuntimeError("the post was never confirmed"), DEFAULT],
)

# A human closing the run's pull request.
_CLOSES_THE_PULL_REQUEST = lambda case: setattr(case.pull_request, "state", "closed")


# What another finish writes beside its settlement of the run to record
# movement it read under it, and what it writes there: the attempt's base tip
# blanked, or the mark of that movement in the run's handoff place.
_RECORDS_MOVEMENT = MappingProxyType({
    "a base tip blanked": (readings.KEY_REWRITE_BASE, lambda case: None),
    "a movement mark": (_HANDOFF, lambda case: {"moved": case.captured.receipt}),
})

# The mark of that movement alone.
_MARKS = _RECORDS_MOVEMENT["a movement mark"]

# What another finish makes beside its settlement of the run just as the
# phase's settlement edit reads the comment, and the records that moves: a
# later review handed over, the attempt's base tip blanked to record movement
# read under the run, the mark of that movement in the run's handoff place, or
# a revision spent past the run on the floor.
_RESTORED = MappingProxyType({
    _LATER_REVIEW: (settled_moves.reviews_again, _REPORT_RECORDS),
    "a base tip blanked": (
        partial(settled_moves.writes_over, key=readings.KEY_REWRITE_BASE, written=None), (readings.KEY_REWRITE_BASE,),
    ),
    "a movement mark": (
        lambda case: settled_moves.writes_over(case, _HANDOFF, {"moved": case.captured.receipt}), (_HANDOFF,),
    ),
    _SPENT_PAST: (
        lambda case: settled_moves.writes_over(case, readings.KEY_REVISION_FLOOR, case.captured.revision + 1),
        (readings.KEY_REVISION_FLOOR,),
    ),
})


def _settles(case, pending) -> None:
    """Post `pending`'s artifact and settle it over the comment as it stands, as another finish would; once."""
    state = case.gh.read_pinned_state(case.issue)
    if _record_state.read_pending_evidence(state) != pending:
        return
    posted = case.gh.publish_verification_artifact(case.pull_request, pending.artifact)
    case.gh.write_pinned_state(case.issue, _settlement.settled_state(
        state, pending, posted.landed_id, finish_support.REVIEWING,
    ))


class _MovesUnderTheEdit:
    """The strict edit, its first call made just as another finish settles the run and makes `move` beside it.

    The records `keys` names are put back exactly as the settlement left them
    -- one missing then removed -- right behind that edit's own reading of
    the comment, so it answers over a comment that moved and leaves one that
    reads as the settlement left it before `move`; or, `behind_the_ledger`,
    only once the ledger entry the phase then commits alone has landed over
    the moved comment and taken it in. `settled` is the run as that
    settlement made it current.
    """

    def __init__(self, case, move, keys: tuple[str, ...], *, behind_the_ledger: bool = False) -> None:
        self._case = case
        self._move = move
        self._keys = keys
        self._edit = case.gh.edit_pinned_state
        self._walk = case.gh._pinned_comment
        self._behind_the_ledger = behind_the_ledger
        self._edits = 0
        self.kept: dict = {}
        self.settled = None

    def __call__(self, issue, state, **options):
        self._edits += 1
        if self._edits == 1:
            return self._moves_under(issue, state, **options)
        answered = self._edit(issue, state, **options)
        if self._behind_the_ledger and self._edits == 2:
            self._puts_back()
        return answered

    def left(self) -> dict:
        """The records `keys` names, as the comment carries them now."""
        pinned = readings.pinned(self._case)
        return {key: pinned[key] for key in self._keys if key in pinned}

    def _moves_under(self, issue, state, **options):
        """The settlement edit, the run settled and `move` made beside it just ahead of it."""
        _settles(self._case, self._case.captured)
        self.settled = self._case.records()[1]
        self.kept = self.left()
        self._move(self._case)
        if self._behind_the_ledger:
            return self._edit(issue, state, **options)
        with patch.object(self._case.gh, "_pinned_comment", self._walks):
            return self._edit(issue, state, **options)

    def _walks(self, *located):
        """The edit's walk to the comment, the records `keys` names put back right behind it."""
        found = self._walk(*located)
        self._puts_back()
        return found

    def _puts_back(self) -> None:
        """Put the records `keys` names back exactly as the settlement left them."""
        restored = self._case.gh.read_pinned_state(self._case.issue)
        for key in self._keys:
            restored.data.pop(key, None)
        for key, kept in self.kept.items():
            restored.set(key, kept)
        self._case.gh.write_pinned_state(self._case.issue, restored)


class _MovesAround:
    """A step, another finish settling the run -- where nobody has -- and recording `moved` just ahead of it; once.

    `moved` is the record another finish writes to record movement read
    under the run and what it writes there; that record is put back exactly
    as it read before right behind the step, so the step reads, or takes in,
    a comment carrying the movement and leaves one that reads as before it.
    `settled` is the run as it was current just ahead of the movement.
    """

    def __init__(self, case, step, moved: tuple) -> None:
        self._case = case
        self._step = step
        self._key = moved[0]
        self._written = moved[1]
        self._owed = True
        self.kept: dict = {}
        self.settled = None

    def __call__(self, *called, **options):
        if not self._owed:
            return self._step(*called, **options)
        self._owed = False
        _settles(self._case, self._case.captured)
        self.settled = self._case.records()[1]
        self.kept = self.left()
        settled_moves.writes_over(self._case, self._key, self._written(self._case))
        answered = self._step(*called, **options)
        settled_moves.writes_over(self._case, self._key, self.kept[self._key])
        return answered

    def left(self) -> dict:
        """The record `moved` names, as the comment carries it now."""
        return {self._key: readings.pinned(self._case)[self._key]}


class _MovedAhead:
    """A step's call number `nth`, `moved` made just ahead of it and the run settled by another finish behind it.

    `moved` is what another road makes -- a later review handed over, a
    revision spent past the run, the pull request closed -- and the records
    it moves, which are put back exactly as they read before right behind the
    step, the pull request reopened with them; another finish then settles
    the run over what was put back. So the step reads the run still owed with
    that movement under it, and every later reading finds that settlement
    over a world that reads as the run was bound to it. `settled` is the run
    as that settlement made it current, and `kept` what the move touched that
    the phase never writes itself -- every record it names but the history,
    which the phase's own retirements add to, and the pull request's state --
    as it read before the move (`left`).
    """

    def __init__(self, case, step, moved: tuple, nth: int = 1) -> None:
        self._case = case
        self._step = step
        self._move = moved[0]
        self._keys = moved[1]
        self._calls = nth
        self.kept: dict = {}
        self.settled = None

    def __call__(self, *called, **options):
        self._calls -= 1
        if self._calls:
            return self._step(*called, **options)
        before = self._reads()
        self.kept = self.left()
        self._move(self._case)
        answered = self._step(*called, **options)
        restored = self._case.gh.read_pinned_state(self._case.issue)
        for key in self._keys:
            restored.data.pop(key, None)
        self._case.pull_request.state = before.pop(_PULL_REQUEST)
        for key, recorded in before.items():
            restored.set(key, recorded)
        self._case.gh.write_pinned_state(self._case.issue, restored)
        _settles(self._case, self._case.captured)
        self.settled = self._case.records()[1]
        return answered

    def left(self) -> dict:
        """What the move touched that the phase never writes itself, as it stands now (`kept`)."""
        read = self._reads()
        read.pop(_records.EVIDENCE_HISTORY, None)
        return read

    def _reads(self) -> dict:
        """The records `moved` names, as the comment carries them now, and the pull request's state."""
        pinned = readings.pinned(self._case)
        left = {key: pinned[key] for key in self._keys if key in pinned}
        return {**left, _PULL_REQUEST: self._case.pull_request.state}


class _LosesTheFirstAnswer:
    """The strict edit, the answer to its first call lost once that edit landed."""

    def __init__(self, case) -> None:
        self._edit = case.gh.edit_pinned_state
        self._failures = case.gh.pinned_failures.lost
        self._owed = True

    def __call__(self, issue, state, **options):
        if self._owed:
            self._failures.add(issue.number)
        self._owed = False
        answered = self._edit(issue, state, **options)
        self._failures.discard(issue.number)
        return answered


# What the phase's answer read moved, the owner and name of the step that
# read it, and how that is made just ahead of it and put back right behind
# it: on the issue and comment the answer starts from, another finish's
# settlement of the run and the mark of movement it read under it, or -- the
# run still owed, and settled by another finish once they are put back -- a
# later review handed over or a revision spent past the run -- on the floor,
# or shown by a history entry beside a floor nobody can read; or the pull
# request the answer reads closed -- the second reading of it, behind the
# captured run's proof again -- reopened right behind that reading.
_ANSWER_READ = MappingProxyType({
    "a handoff marked": (_settlement_step, _READS_AGAIN, partial(_MovesAround, moved=_MARKS)),
    _LATER_REVIEW: (_settlement_step, _READS_AGAIN, partial(_MovedAhead, moved=_RESTORED[_LATER_REVIEW])),
    _SPENT_PAST: (
        _settlement_step, _READS_AGAIN, partial(_MovedAhead, moved=_RESTORED[_SPENT_PAST]),
    ),
    "a newer revision beside an unreadable floor": (
        _settlement_step, _READS_AGAIN, partial(_MovedAhead, moved=(settled.abandons_one_past, _SPENT_RECORDS)),
    ),
    "the pull request closed": (
        _proof._publication, "subject_verdict", partial(_MovedAhead, moved=(_CLOSES_THE_PULL_REQUEST, ()), nth=2),
    ),
})


# What the phase's adoption of a settlement read moved, put back right behind
# that reading: the client step that stops the phase's own answer short of
# settling the run and what stops it, and how the move is made around that
# reading. The phase's settlement edit lands with its answer lost and another
# finish marks movement in the run's handoff place; or the phase's post of
# the run's artifact is never confirmed, the run still owed as the adoption
# reads it, and a later review, a blank of the attempt's base tip, or a
# revision spent past the run is put back before another finish settles it.
_ADOPTION_READ = MappingProxyType({
    "a mark beside an edit whose answer was lost": (_EDIT, _LosesTheFirstAnswer, partial(_MovesAround, moved=_MARKS)),
    **{
        moved: (_POST, _POST_UNCONFIRMED, partial(_MovedAhead, moved=_RESTORED[moved]))
        for moved in (_LATER_REVIEW, "a base tip blanked", _SPENT_PAST)
    },
})


class EvidenceOnlyRefusalTest(retirement.RetirementCase, unittest.TestCase):
    """A refusal of the phase's own write over the evidence records alone moves nothing a binding rests on."""

    def test_the_newer_settlement_is_kept(self) -> None:
        # The configuration moved past the settled run, and a newer
        # transaction of the head is recorded under the configuration in
        # place now. Another finish settles it just as the phase lands the
        # invalidation the run is owed, refusing that write over the evidence
        # records alone: the newer settlement stays current, the run
        # superseded by it, and nothing runs.
        settled_moves.reconfigures(self)
        newer = self._records_under_the_new_configuration()
        finish = self.landed()
        lands = _RacesTheStep(_writes.lands, partial(_settles, self, newer))

        with patch.object(_writes, "lands", lands):
            self.assertEqual(self.asks(_settlement_step.resolves, finish), FinishOutcome.REFUSED)

        self._assert_current(newer)

    def test_what_the_write_read_is_movement(self) -> None:
        # As above, but beside that settlement
        # another road hands a later review over, blanks the attempt's base
        # tip, marks movement in the newer transaction's handoff place, or
        # spends a revision past it, just as the phase's invalidation write
        # reads the comment, and puts that back before the write answers: the
        # comment the write read records that movement under the newer
        # transaction, so the settlement adopted is invalidated whole despite
        # the restoration, with nothing run.
        for case, (move, keys) in _RESTORED.items():
            with self.subTest(case=case):
                self.setUp()
                settled_moves.reconfigures(self)
                self.captured = self._records_under_the_new_configuration()
                edits = _MovesUnderTheEdit(self, move, keys)

                with patch.object(self.gh, _EDIT, edits):
                    self.asks(_settlement_step.resolves, self.landed())

                history = self.records()[2]
                self.assertEqual(self.records()[:2], (None, None))
                self.assertEqual(history[-1], (self.captured.receipt, readings.INVALIDATED))
                self.assertEqual(edits.left(), edits.kept)
                self.assertEqual(self.verify.call_count, 0)

    def _assert_current(self, newer) -> None:
        """`newer` settled current, nothing pending, the run superseded by it, and nothing run."""
        pending, current, history = self.records()
        self.assertEqual((pending, current.receipt), (None, newer.receipt))
        self.assertEqual(history[-1], (self.settled.receipt, _SUPERSEDED))
        self.assertEqual(self.verify.call_count, 0)

    def _records_under_the_new_configuration(self):
        """Another road's newer transaction of the head, bound to the configuration in place now; it."""
        state = self.gh.read_pinned_state(self.issue)
        binding = replace(self.settled.binding, context_revision=_proof.configured_context_revision())
        newer = _record_state.mint_pending_evidence(state, support.ISSUE_NUMBER, binding, (record_support.ran(),))
        self.assertTrue(_record_state.record_pending_evidence(state, newer))
        self.gh.write_pinned_state(self.issue, state)
        return newer


class RestoredUnderTheEditTest(captured_support.CapturedEvidenceCase, unittest.TestCase):
    """Movement the phase's answer read is movement, however soon it was put back and whatever its state took in."""

    def test_restored_movement_retires_the_run(self) -> None:
        # Another finish settles the captured run and makes a move beside it
        # just as the phase's settlement edit reads the comment, and what it
        # moved is put back as the settlement left it before that edit
        # answers: the comment the edit read moved the run's binding, blanked
        # the attempt's base tip, marked the run's handoff, or spent a
        # revision past it -- each movement recorded under the run -- so the
        # settlement adopted is invalidated whole despite the restoration.
        for case, (move, keys) in _RESTORED.items():
            with self.subTest(case=case):
                self.setUp()
                edits = _MovesUnderTheEdit(self, move, keys)

                with patch.object(self.gh, _EDIT, edits):
                    self.asks(_settlement_step.resolves, self.landed())

                self._assert_retired(edits)

    def test_a_blank_the_ledger_took_in_is_movement(self) -> None:
        # Another finish settles the captured run and another proof blanks
        # the attempt's base tip just as the phase's settlement edit reads
        # the comment, and the ledger entry the phase then commits alone
        # takes that comment in -- the blank among it -- before the tip is
        # put back: the blank that edit read is movement whatever the
        # phase's state took in since, so the settlement adopted is
        # invalidated whole over the attempt as it stands.
        keys = (readings.KEY_REWRITE_BASE,)
        blanks = partial(settled_moves.writes_over, key=readings.KEY_REWRITE_BASE, written=None)
        edits = _MovesUnderTheEdit(self, blanks, keys, behind_the_ledger=True)

        with patch.object(self.gh, _EDIT, edits):
            self.asks(_settlement_step.resolves, self.landed())

        self._assert_retired(edits)

    def test_movement_the_ledger_took_in_is_movement(self) -> None:
        # Another finish settles the captured run just as the phase's
        # settlement edit reads the comment, and records movement read under
        # it -- the attempt's base tip blanked, or the mark in its handoff's
        # place -- just as the ledger entry the phase then commits alone
        # takes that comment in, put back right behind it: the comment the
        # phase took in records that movement, so the settlement adopted is
        # invalidated whole despite the restoration.
        for case, moved in _RECORDS_MOVEMENT.items():
            with self.subTest(case=case):
                self.setUp()
                settles = _RacesTheStep(self.gh.edit_pinned_state, partial(_settles, self, self.captured))
                takes_in = _MovesAround(self, _verification_comments.records_the_artifact, moved)

                with (
                    patch.object(self.gh, _EDIT, settles),
                    patch.object(_verification_comments, "records_the_artifact", takes_in),
                ):
                    self.asks(_settlement_step.resolves, self.landed())

                self._assert_retired(takes_in)

    def test_what_the_answer_read_is_movement(self) -> None:
        # Just as the phase first reads the issue and comment to answer the
        # captured run, another finish settles it and marks movement read
        # under it in its handoff's place -- or, the run still owed, a later
        # review is handed over or a revision spent past it, or the pull
        # request is closed as the answer reads it -- and what moved is put
        # back right behind that reading, another finish settling the run
        # over it: what the answer read is movement, so the settlement
        # adopted is invalidated whole despite the restoration.
        for case, (owner, step, around) in _ANSWER_READ.items():
            with self.subTest(case=case):
                self.setUp()
                reads = around(self, getattr(owner, step))

                with patch.object(owner, step, reads):
                    self.asks(_settlement_step.resolves, self.landed())

                self._assert_retired(reads)

    def test_what_the_adoption_read_is_movement(self) -> None:
        # The phase's settlement edit lands with its answer lost, and another
        # finish marks movement read under the run in its handoff's place just
        # as the phase reads that settlement back to adopt it -- or the
        # phase's post of the run's artifact is never confirmed, and a later
        # review, a blank of the attempt's base tip, or a revision spent past
        # the run stands on the comment as the adoption reads the run still
        # owed, put back before another finish settles it. What the adoption
        # read is movement, so the run is invalidated whole despite the
        # restoration.
        for case, (step, stops, around) in _ADOPTION_READ.items():
            with self.subTest(case=case):
                self.setUp()
                adopts = around(self, _durable.takes_in_a_settlement)

                with (
                    patch.object(self.gh, step, stops(self)),
                    patch.object(_durable, "takes_in_a_settlement", adopts),
                ):
                    self.asks(_settlement_step.resolves, self.landed())

                self._assert_retired(adopts)

    def test_a_restored_announcement_moves_nothing(self) -> None:
        # Another finish settles the captured run and announces the landing
        # just as the phase's settlement edit reads the comment, and the
        # announcement is put back before that edit answers: the comment it
        # read moved the evidence records and the attempt's announcement
        # members alone, which no binding rests on, so the settlement adopted
        # stays current as that finish made it, its run posted once and
        # nothing run, with the announcement as it was put back.
        edits = _MovesUnderTheEdit(self, retirement.announces, _ANNOUNCEMENT)

        with patch.object(self.gh, _EDIT, edits):
            self.asks(_settlement_step.resolves, self.landed())

        pending, current = self.records()[:2]
        self.assertEqual((pending, current.receipt), (None, self.captured.receipt))
        self.assertEqual(edits.left(), edits.kept)
        receipts = [found.receipt for found in support.posted_artifacts(self)]
        self.assertEqual(receipts.count(self.captured.receipt), 1)
        self.assertEqual(self.verify.call_count, 0)

    def _assert_retired(self, edits: _MovesUnderTheEdit | _MovesAround | _MovedAhead) -> None:
        """The settlement adopted invalidated whole, its provenance kept and its run posted once; `edits` put back.

        Its history entry is the run exactly as that settlement made it
        current -- receipt, revision, binding, transcript, verdict, and
        artifact -- and nothing ran, launched, or relabelled.
        """
        current, history = self.records()[1:]
        self.assertIsNone(current)
        self.assertEqual(history[-1], (self.captured.receipt, readings.INVALIDATED))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual(entry, _records.HistoricalEvidence.of(edits.settled, _records.Retirement.INVALIDATED))
        self.assertEqual(edits.left(), edits.kept)
        receipts = [found.receipt for found in support.posted_artifacts(self)]
        self.assertEqual(receipts.count(self.captured.receipt), 1)
        ran = (self.verify.call_count, self.developer.call_count, readings.relabels(self))
        self.assertEqual(ran, (0, 0, ()))


if __name__ == "__main__":
    unittest.main()
