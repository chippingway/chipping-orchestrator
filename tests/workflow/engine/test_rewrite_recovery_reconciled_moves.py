# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A dormant guarded recovery park keeping the movement its reconciliation read, and none an unrelated edit made.

The guarded recovery case (`guarded_recovery_support`): issue #7's rebased
head reviewed, its run settled under the anchor, and the finish killed before
its announcement, so the attempt stands. The recovery context read off the
comment is handed straight to the dormant guarded park
(`rewrite_recovery_parks.lands_a_park`), as a recovery road would.

Another road settles report 3 behind the park's notice, whose post then
raises, or right behind the park's own record, whose answer is lost -- and
settles a newer run bound to report 3 in the run's place, report 2 put back,
too -- or leaves the mark of movement under the run's receipt in the handoff's
place. The reconciliation behind that notice or record reads the comment, and
the records it read moving under the evidence there are put back right behind
that reading, before the proof behind it reads the comment again: the movement
that very reading recorded is kept for that proof, so the run, or that
successor on its own binding, is invalidated whole all the same. So is a
successor another road settles only right behind that reading, report 3 put
back right behind the proof's own next reading, which asks it of its own
binding rather than the run's alone -- or bound to requirements an edit of the
issue gave it and put back, which the issue that reading takes disproves. A field
nobody's binding rests on, written right under the park's strict edit, refuses
that edit and is no movement: the run stays current.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    rewrite_recovery_parks as _parks,
    verification_durable as _durable,
    verification_records as _records,
)
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_readings as readings,
    settled_finish_support as settled_support,
    verification_report_fixture as _report,
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# The park every case takes, and why.
_NOTICE = "The auto rebase needs a human."
_REASON = "auto_base_rebase_push_failed"

# A requirement another road adds to the issue, and takes back off, around a newer run it settles.
_ADDED_REQUIREMENT = "\nAlso cover a base that moved twice."

# A field nobody's binding rests on, and what another road writes into it.
_NOTE = "operator_note"
_NOTED = "independent update"


def _records_of(case) -> dict:
    """The report and review records `case`'s comment carries now."""
    pinned = readings.pinned(case)
    return {key: pinned.get(key) for key in _MOVED_RECORDS}


def _writes(case, records: dict) -> None:
    """Write `records` onto `case`'s comment as it stands."""
    state = case.gh.read_pinned_state(case.issue)
    for key, recorded in records.items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)


def _notes_under(case, live, issue, state, **options):
    """`live`, the client's strict edit, another road writing a field nobody's binding rests on right under a park's."""
    noted = case.pinned_fields(_NOTE)[0]
    if not noted and guarded.parking(issue, state, **options):
        _writes(case, {_NOTE: _NOTED})
    return live(issue, state, **options)


class _MovesBehindThePark:
    """Report 3 of `head` settled by another road at a park, put back right behind the reconciliation's reading.

    Settled behind the park's notice, whose post then raises (`raises`), or
    right behind the park's own record, whose answer is then lost (`loses`);
    `successor` settles a newer run bound to report 3 in the run's place as
    well, kept as `run`, and puts report 2 back; `marks`, the receipt of the
    run, has another finish leave the mark of movement under it in the
    handoff's place instead of any report. The reconciliation's reading of
    the comment (`reads`) has what it read moving written back right behind
    it -- report 2, report 3 under the successor, or the handoff the mark took
    the place of. A `late` road moves nothing as the notice's post raises:
    the client's first reading of the comment behind it (`reads_late`) -- the
    reconciliation's -- has it settle right behind, and the second, the
    proof's own, has report 3 put back right behind it instead.
    """

    def __init__(
        self,
        case,
        head: str,
        *,
        successor: bool = False,
        marks: str | None = None,
        late: bool = False,
    ) -> None:
        self._case = case
        self._head = head
        self._successor = successor
        self._marks = marks
        self._edit = case.gh.edit_pinned_state
        self._read = _durable.durable_comment
        self._comment = case.gh.read_pinned_state
        self._restores: dict | None = None
        self._restored = late
        self._late = late
        self._behind: int | None = None
        self.run = None

    def raises(self, *_posted, **_options):
        """The notice's post: report 3 settled -- or, `late`, nothing yet -- then a raise as GitHub not answering."""
        self._behind = 0
        if not self._late:
            self._settles()
        raise RuntimeError("GitHub did not answer the notice's post")

    def loses(self, issue, state, **options):
        """The client's strict edit: the park's record landed, report 3 settled behind it, and its answer lost."""
        if self._restores is not None or not guarded.parking(issue, state, **options):
            return self._edit(issue, state, **options)
        self._edit(issue, state, **options)
        self._settles()
        return PinnedEdit.UNCONFIRMED

    def reads(self, *read, **options):
        """The comment read afresh, the first time behind report 3 with what it read moving put back right behind."""
        durable = self._read(*read, **options)
        if self._restores is not None and not self._restored:
            self._restored = True
            _writes(self._case, self._restores)
        return durable

    def patching(self):
        """The comment read afresh through `reads`, which puts back what that reading read moving right behind it."""
        return patch.object(_durable, "durable_comment", self.reads)

    def reads_late(self, issue):
        """The client's reading of the comment, `late`: the move right behind the first behind the raise, as above."""
        durable = self._comment(issue)
        if not self._late or self._behind is None or self._behind > 1:
            return durable
        self._behind += 1
        with patch.object(self._case.gh, "read_pinned_state", self._comment):
            if self._behind == 1:
                self._settles()
            else:
                _writes(self._case, self._restores)
        return durable

    def _settles(self) -> None:
        """Settle report 3 -- and the successor bound to it, putting report 2 back -- or mark the run moved."""
        case = self._case
        if self._marks is not None:
            self._restores = {_records.EVIDENCE_HANDOFF: readings.pinned(case).get(_records.EVIDENCE_HANDOFF)}
            _writes(case, {_records.EVIDENCE_HANDOFF: {"moved": self._marks}})
            return
        earlier = _records_of(case)
        case.state = case.gh.read_pinned_state(case.issue)
        subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)
        self._restores = earlier
        if not self._successor:
            return
        binding = readings.pinned_records(case)[1].binding
        bound = replace(binding, target=replace(binding.target, subject=subject.recorded()))
        self.run = settled_support.records_a_newer_run(case, settles=True, binding=bound)
        self._restores = _records_of(case)
        _writes(case, earlier)


class _RequiresBehindThePark(_MovesBehindThePark):
    """`_MovesBehindThePark`, `late`, its newer run settled over an edit of the issue that is put back right behind.

    Right behind the reconciliation's reading another road edits the issue,
    settles report 3 and a newer run bound to the requirements that edit gave
    the issue, and puts the issue back: the newer run's own records hold, and
    only the issue every later reading takes beside them disproves it, with
    nothing to put back behind the proof's own reading.
    """

    def __init__(self, case, head: str) -> None:
        super().__init__(case, head, successor=True, late=True)

    def _settles(self) -> None:
        """Edit the issue, settle report 3 and the newer run bound to its requirements, and put the issue back."""
        case = self._case
        case.issue.body += _ADDED_REQUIREMENT
        case.state = case.gh.read_pinned_state(case.issue)
        subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)
        binding = readings.pinned_records(case)[1].binding
        publication = replace(binding.target.publication, requirements_revision=subject.requirements_revision)
        target = replace(binding.target, publication=publication, subject=subject.recorded())
        binding = replace(binding, target=target)
        self.run = settled_support.records_a_newer_run(case, settles=True, binding=binding)
        self._restores = {}
        case.issue.body = case.issue.body.removesuffix(_ADDED_REQUIREMENT)


class _FailsReadingFirst(_MovesBehindThePark):
    """`_MovesBehindThePark`, the reconciliation's first reading behind report 3 failing as a request GitHub refused.

    The reading behind it is the first that carries what moved, and has it
    put back right behind it.
    """

    def __init__(self, case, head: str, **options) -> None:
        super().__init__(case, head, **options)
        self._failed = False

    def reads(self, *read, **options):
        """The comment read afresh, the first time behind report 3 failing, every reading after as `reads` answers."""
        if self._restores is None or self._failed:
            return super().reads(*read, **options)
        self._failed = True
        with patch.object(self._case.gh, "read_pinned_state", side_effect=RuntimeError("GitHub refused the read")):
            return self._read(*read, **options)


# Each race behind a park's notice that raises: report 3 settled, a newer run
# settled bound to it, that run again where the reconciliation's first reading
# of the comment fails, or that run settled only right behind that reading --
# beside report 2, or bound to requirements an edit of the issue put back gave it.
_RAISED_NOTICES = (
    partial(_MovesBehindThePark),
    partial(_MovesBehindThePark, successor=True),
    partial(_FailsReadingFirst, successor=True),
    partial(_MovesBehindThePark, successor=True, late=True),
    partial(_RequiresBehindThePark),
)


class ReconciledMoveTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """What a dormant park's reconciliation read moving counts, and what an unrelated edit under it does not."""

    def test_a_raised_notice_keeps_the_move_it_read(self) -> None:
        # The notice's post raises behind report 3 -- or behind a newer run
        # settled bound to it, report 2 put back -- and what the
        # reconciliation's reading read moving is put back right behind it:
        # the run, or that successor, is invalidated whole with nothing parked
        # -- also where the reconciliation's first reading fails, the one
        # behind it reading the successor on its own binding, and where the
        # successor is settled only right behind the reconciliation's reading,
        # report 3 put back right behind the proof's own -- or bound to the
        # requirements an edit of the issue gave it, the edit put back, which
        # the issue every later reading takes beside it disproves.
        for mover in _RAISED_NOTICES:
            with self.subTest(moves=mover.func.__name__, **mover.keywords):
                self.setUp()
                head, run = self.settles_then_dies()
                moves = mover(self, head)
                context = guarded.recovery_context(self)
                with (
                    patch.object(self.gh, "comment", moves.raises),
                    patch.object(self.gh, "read_pinned_state", moves.reads_late),
                    moves.patching(),
                ):
                    self.assertRaises(RuntimeError, _parks.lands_a_park, context, _NOTICE, _REASON)

                self.assertFalse(self.pinned_fields(guarded.AWAITING)[0])
                if moves.run is None:
                    self.assert_invalidated(run)
                else:
                    self.assert_invalidated(moves.run, over=run)

    def test_a_raised_notice_keeps_the_mark_it_read(self) -> None:
        # The notice's post raises behind another finish's mark of movement
        # under the run's receipt in the handoff's place, and the handoff is
        # put back right behind the reconciliation's reading: the mark that
        # reading read is the movement it is, and the run is invalidated whole
        # with nothing parked.
        head, run = self.settles_then_dies()
        moves = _MovesBehindThePark(self, head, marks=run.receipt)
        context = guarded.recovery_context(self)
        with patch.object(self.gh, "comment", moves.raises), moves.patching():
            self.assertRaises(RuntimeError, _parks.lands_a_park, context, _NOTICE, _REASON)

        self.assertFalse(self.pinned_fields(guarded.AWAITING)[0])
        self.assert_invalidated(run)

    def test_a_lost_record_keeps_the_move_it_read(self) -> None:
        # The park's record lands with its answer lost, report 3 settled right
        # behind it, and report 2 is put back right behind the reconciliation's
        # reading: the run is invalidated whole beside the park.
        head, run = self.settles_then_dies()
        moves = _MovesBehindThePark(self, head)
        context = guarded.recovery_context(self)
        with patch.object(self.gh, "edit_pinned_state", moves.loses), moves.patching():
            _parks.lands_a_park(context, _NOTICE, _REASON)

        self.assertTrue(self.pinned_fields(guarded.AWAITING)[0])
        self.assert_invalidated(run)

    def test_an_unrelated_edit_is_no_move(self) -> None:
        # Another road writes a field nobody's binding rests on right under the
        # park's strict edit, which is refused over it: the run stays current
        # exactly as it settled, and nothing is parked.
        run = self.settles_then_dies()[1]
        context = guarded.recovery_context(self)
        with patch.object(self.gh, "edit_pinned_state", partial(_notes_under, self, self.gh.edit_pinned_state)):
            _parks.lands_a_park(context, _NOTICE, _REASON)

        self.assertEqual(readings.pinned_records(self)[1], run)
        self.assertEqual(self.pinned_fields(guarded.AWAITING, _NOTE), (None, _NOTED))
        self.assert_made_once()


if __name__ == "__main__":
    unittest.main()
