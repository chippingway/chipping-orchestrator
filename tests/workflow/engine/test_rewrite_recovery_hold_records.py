# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A guarded recovery hold, its settled run proved first and once more behind its own record.

The guarded recovery case (`guarded_recovery_support`): issue #7's rebased
head reviewed, its run settled under the anchor, and the finish killed before
its announcement, so the attempt stands. The next tick's recovery reads the landing standing with a transfer
permission still outstanding beside it, so the landed road receipts it through the permit-only leased no-op, and the
publication gate holds that no-op (`rewrite_landed_hold_support`): its hold is recorded through the guarded `HOLD`
(`rewrite_recovery_parks.lands_a_hold`), the run proved first, and only what the tick staged since its
reading lands, over the comment read afresh.
The transfer's machinery -- its progress, its permit, the gate's answer -- is stood in for; some cases hand the hold
or park a recovery context directly.

The issue edited under the run has it invalidated whole, putting the requirements back reviving nothing. A newer
transaction recorded while the gate answers survives the record with its revision
floor, and a newer run settled beside report 3 is proved on its own readings.
Behind the record the run is proved once more, so movement read at the record
stands however soon it is put back: report 3 settled there (landed, answer
lost, or refused, for room among the rest), or ahead of the fresh reading a
hold's or park's record is derived over, and the base tip blanked under its
strict edit, beside another finish's event record or not, or read blank or
repointed by the proof before a park. A newer run settled bound to report 3,
which that proof takes in, is no movement and stays current; where nothing
moved the run is kept current. The attempt stands behind every hold, the run
made once, and a later tick's poll routes the head over what the hold left.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import (
    owed_events as _owed_events,
    report_commits as _commits,
    rewrite_landing_records as _landing_records,
    rewrite_recovery_parks as _parks,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_landed_hold_support as gate,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled_support,
    verification_report_fixture as _report,
)

_EDITED_BODY = "Also cover a base that moved twice."

# How the history records evidence a newer transaction for its head settled over.
_SUPERSEDED = "superseded"

# The guarded commit, read before any case stands in for it, and its name on the class.
_LANDS = _commits.ReportCommit.lands
_LANDING = "lands"

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# How the hold's record goes once report 3 settled ahead of it -- landed, its
# answer lost, or refused -- or right under its strict edit, which is refused
# over it, and whether report 2 is put back right behind it.
_UNDER_THE_EDIT = "under the edit"

# The base tip, rather than report 3, moved under that edit: blanked as a
# reset is recorded, and put back right behind the edit's refusal.
_TIP_UNDER_THE_EDIT = "the tip under the edit"

# Report 3 settled ahead of the record's fresh reading, and report 2 put back
# right ahead of its strict edit, which is refused over the comment moved back.
_AHEAD_OF_THE_EDIT = "ahead of the edit"

# The tip blanked under that edit beside the record of the `base_rebased`
# event another finish of the landing is filing for the head, which advances
# this very attempt rather than replacing it; the tip alone is put back.
# That finish is this process's, so its event is noted owed as it notes it.
_TIP_BESIDE_THE_EVENT = "the tip beside the event record under the edit"

# The event that finish files.
_REBASED = "base_rebased"

# A record the tick staged since its reading, as a gate holding over a
# reading of its own does, so the hold's record has an edit to send -- one
# that fails as a case asks.
_STAGED_BY_THE_GATE = "late_gate_hold"

# Report 3 settled ahead of the record beside another road's own spelling of
# what the gate staged, so the record is refused as an owned-field conflict
# over the reading that carries report 3.
_CONFLICTS_WITH_THE_GATE = "a conflict with the gate's record"

# Report 3 settled ahead of the record beside another road's field filling the
# comment right to the limit, so the record is refused for room over the
# reading that carries report 3; that field is taken off with report 3.
_FILLS_THE_COMMENT = "the comment filled at the record"
_FILLER = "another_road_filler"

# A base tip the attempt never recorded, another road repointing the recorded one to it.
_ELSEWHERE = "0123456789abcdef0123456789abcdef01234567"

# The modes whose movement races the record's strict edit itself.
_AT_THE_EDIT = frozenset((_UNDER_THE_EDIT, _TIP_UNDER_THE_EDIT, _TIP_BESIDE_THE_EVENT, _AHEAD_OF_THE_EDIT))

# The guarded records a case races -- the hold's, and the park's -- and how a recovery context lands each.
_RECORDS = frozenset((_parks.HOLD, _parks.PARK))
_LANDED_BY = (
    ("hold", _parks.lands_a_hold),
    ("park", partial(
        _parks.lands_a_park, message="The auto rebase needs a human.", reason="auto_base_rebase_push_failed",
    )),
)

_AT_THE_RECORD = (
    ("", True),
    ("lost", True),
    ("refused", False),
    (_UNDER_THE_EDIT, True),
    (_TIP_UNDER_THE_EDIT, True),
    (_TIP_BESIDE_THE_EVENT, True),
    (_CONFLICTS_WITH_THE_GATE, True),
    (_FILLS_THE_COMMENT, True),
)


def _settles_a_successor(case, subject):
    """Settle a newer run bound to report `subject` over `case.state`, as another road would; now current."""
    earlier = _settlement.read_current_evidence(case.state)
    target = replace(earlier.binding.target, subject=subject.recorded())
    binding = replace(earlier.binding, target=target)
    pending = _record_state.mint_pending_evidence(case.state, case.issue.number, binding, case.source.commands)
    case.assertTrue(_record_state.record_pending_evidence(case.state, pending))
    artifact = case.gh.publish_verification_artifact(case.pull_request, pending.artifact)
    case.state = _settlement.settled_state(case.state, pending, artifact.landed_id, git_support.REVIEWING)
    return _settlement.read_current_evidence(case.state)


class _AroundTheHold:
    """The guarded commit, report 3 of `head` settled ahead of a hold's or park's record, which meets `failing`.

    "" lands it.

    `restores` puts report 2 back right behind the record; `successor` settles
    a newer run bound to report 3 beside it, kept as `successor`.
    """

    def __init__(self, case, head: str, failing: str = "", *, restores: bool = False, successor: bool = False) -> None:
        self._case = case
        self._head = head
        self._failing = failing
        self._restores = restores
        self._replaced: dict = {}
        self.successor = successor

    def __call__(self, commit, staged, write):
        if write not in _RECORDS or self._replaced:
            return _LANDS(commit, staged, write)
        case = self._case
        if self._failing:
            staged.set(_STAGED_BY_THE_GATE, self._head)
        if self._failing == _AHEAD_OF_THE_EDIT:
            self._settles()
        if self._failing in _AT_THE_EDIT:
            with patch.object(case.gh, "edit_pinned_state", partial(self._moves_under, case.gh.edit_pinned_state)):
                return _LANDS(commit, staged, write)
        self._settles()
        failures = getattr(case.gh.pinned_failures, self._failing, set())
        failures.add(case.issue.number)
        landed = _LANDS(commit, staged, write)
        failures.discard(case.issue.number)
        if self._restores:
            self.puts_back()
        return landed

    def puts_back(self) -> None:
        """Write the report and review records back as they stood before report 3 moved them, any filler taken off."""
        state = self._case.gh.read_pinned_state(self._case.issue)
        state.data.pop(_FILLER, None)
        for key, recorded in self._replaced.items():
            state.set(key, recorded)
        self._case.gh.write_pinned_state(self._case.issue, state)

    def _settles(self) -> None:
        """Settle report 3 -- and a newer run bound to it, where `successor` -- keeping what it moved."""
        case = self._case
        pinned = readings.pinned(case)
        self._replaced = {key: pinned.get(key) for key in _MOVED_RECORDS}
        case.state = case.gh.read_pinned_state(case.issue)
        subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        if self.successor:
            self.successor = _settles_a_successor(case, subject)
        if self._failing == _CONFLICTS_WITH_THE_GATE:
            case.state.set(_STAGED_BY_THE_GATE, "another road's gate")
        if self._failing == _FILLS_THE_COMMENT:
            case.state.set(_FILLER, "")
            room = MAX_PINNED_BODY - len(pinned_state_body(case.state.data))
            case.state.set(_FILLER, "x" * room)
        case.gh.write_pinned_state(case.issue, case.state)

    def _blanks(self) -> None:
        """Blank the base tip the attempt recorded its replay as made onto, keeping it to put back."""
        case = self._case
        durable = case.gh.read_pinned_state(case.issue)
        self._replaced = {readings.KEY_REWRITE_BASE: durable.get(readings.KEY_REWRITE_BASE)}
        durable.set(readings.KEY_REWRITE_BASE, None)
        if self._failing == _TIP_BESIDE_THE_EVENT:
            durable.set(readings.KEY_ANNOUNCED_EVENT, self._head)
            _owed_events.owes(case.gh, _REBASED, issue_number=case.issue.number, sha=self._head)
        case.gh.write_pinned_state(case.issue, durable)

    def _moves_under(self, live, issue, state, *, over: dict, **options):
        """`live`, the strict edit, with report 3 settled -- or the tip blanked -- under it and put back behind it.

        Report 3 settled ahead of the record's fresh reading is put back right
        ahead of the edit instead.
        """
        if self._failing == _AHEAD_OF_THE_EDIT:
            self.puts_back()
            return live(issue, state, over=over, **options)
        if self._failing in {_TIP_UNDER_THE_EDIT, _TIP_BESIDE_THE_EVENT}:
            self._blanks()
        else:
            self._settles()
        answered = live(issue, state, over=over, **options)
        self.puts_back()
        return answered


class _WritesAtTheHold:
    """The guarded commit as `around` answers it -- or as it always does -- `fields` written once at the hold's record.

    Another road writes them right behind the hold's record -- another finish
    of the landing recording its event on the attempt, say, advancing the
    attempt the proof behind that record invalidates over -- or, `ahead`,
    right ahead of it, so the record lands over them.
    """

    def __init__(self, case, fields: dict, *, around: _AroundTheHold | None = None, ahead: bool = False) -> None:
        self._case = case
        self._fields = fields
        self._around = around or _LANDS
        self._ahead = ahead
        self._written = False

    def __call__(self, commit, staged, write):
        holds = write is _parks.HOLD and not self._written
        if holds and self._ahead:
            self._writes()
        answered = self._around(commit, staged, write)
        if holds and not self._ahead:
            self._writes()
        return answered

    def _writes(self) -> None:
        """Write `fields` onto the comment as it stands, once."""
        self._written = True
        state = self._case.gh.read_pinned_state(self._case.issue)
        for key, recorded in self._fields.items():
            state.set(key, recorded)
        self._case.gh.write_pinned_state(self._case.issue, state)


def _assert_routed(case, head: str, current=None) -> None:
    """`head` announced once and routed, its attempt retired, `current` current with nothing pending; run once."""
    case.assert_recovered(head)
    case.assertEqual(readings.pinned_records(case)[:2], (None, current))
    case.assert_made_once()


class HoldRecordTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A recovery hold keeps the attempt, its settled run proved first and behind the record it lands."""

    def test_a_report_moved_at_the_record_is_read(self) -> None:
        # Report 3 settles behind the proof and ahead of the hold's record,
        # which lands it, loses its answer, or is refused -- for an owned
        # field another road spelled otherwise beside report 3 too, or for
        # room beside another road's field filling the comment -- or right
        # under its strict edit, refused over it; report 2 put back right behind a
        # record that carried report 3, or that edit, still leaves the run
        # moved -- and so does the base tip blanked right under that edit, beside
        # another finish's event record for the head or not, and put back behind
        # it. The run is invalidated whole with the attempt
        # kept, and the next poll routes the head with nothing current.
        for failing, restores in _AT_THE_RECORD:
            with self.subTest(record=failing or "landed"):
                self.setUp()
                head, settled = self.settles_then_dies()
                around = _AroundTheHold(self, head, failing, restores=restores)
                with patch.object(_commits.ReportCommit, _LANDING, side_effect=around, autospec=True):
                    gate.holds(self)

                self.assert_invalidated(settled)
                self._assert_held()
                around.puts_back()
                self.recovers()
                _assert_routed(self, head)

    def test_a_move_put_back_ahead_is_read(self) -> None:
        # Report 3 settles ahead of the fresh reading a hold's or a park's
        # record is derived over, and report 2 is put back right ahead of its
        # strict edit, which is refused over the comment moved back: what that
        # fresh reading read still invalidates the run whole, the attempt
        # kept unparked, and the next poll routes the head with nothing current.
        for name, lands in _LANDED_BY:
            with self.subTest(record=name):
                self.setUp()
                head, settled = self.settles_then_dies()
                around = _AroundTheHold(self, head, _AHEAD_OF_THE_EDIT)
                with patch.object(_commits.ReportCommit, _LANDING, side_effect=around, autospec=True):
                    lands(guarded.recovery_context(self))

                self.assert_invalidated(settled)
                self._assert_held()
                self.recovers()
                _assert_routed(self, head)

    def test_a_settled_successor_survives_the_hold(self) -> None:
        # Another road settles report 3 and a newer run bound to it ahead of
        # the hold's record, which takes both in: the newer run is proved on
        # its own readings rather than over report 2's move, kept current,
        # and routed with the head by the next poll.
        head = self.settles_then_dies()[0]
        around = _AroundTheHold(self, head, successor=True)
        with patch.object(_commits.ReportCommit, _LANDING, side_effect=around, autospec=True):
            gate.holds(self)

        self.assertEqual(readings.pinned_records(self)[1], around.successor)
        self._assert_held()
        self.recovers()
        _assert_routed(self, head, around.successor)

    def test_a_successor_moved_back_is_invalidated(self) -> None:
        # Another road settles report 3 and a newer run bound to it ahead of
        # the hold's record -- which lands it, loses its answer, or is refused
        # -- then puts report 2 back right behind it: the newer run is the
        # evidence the proof behind the record takes, on its own binding, and
        # is invalidated whole over report 2 rather than left current.
        for failing in ("", "lost", "refused"):
            with self.subTest(record=failing or "landed"):
                self.setUp()
                head = self.settles_then_dies()[0]
                around = _AroundTheHold(self, head, failing, restores=True, successor=True)
                with patch.object(_commits.ReportCommit, _LANDING, side_effect=around, autospec=True):
                    gate.holds(self)

                records = readings.pinned_records(self)
                retired = records[2][-1]
                self.assertIsNone(records[1])
                self.assertEqual(retired, (around.successor.receipt, readings.INVALIDATED))
                self._assert_held()

    def test_a_newer_run_survives_the_hold(self) -> None:
        # While the publication gate answers, another road records a newer
        # transaction for the head: the hold's record keeps it pending, with the
        # revision floor it raised, beside the settled run the proof kept;
        # the next poll settles it over that run and routes the head.
        head, settled = self.settles_then_dies()
        recorded: list = []
        with gate.holding(partial(gate.holds_beside_a_newer_run, self, recorded)):
            self.recovers()

        newer = recorded[0]
        self.assertEqual(readings.pinned_records(self)[:2], (newer, settled))
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], newer.revision)
        self._assert_held()
        self.recovers()

        settles = readings.pinned_records(self)
        _assert_routed(self, head, settles[1])
        self.assertEqual(settles[1].receipt, newer.receipt)
        self.assertEqual(settles[2][-1], (settled.receipt, _SUPERSEDED))

    def test_an_unmoved_run_is_kept(self) -> None:
        # Nothing moved: every hold keeps the run current exactly as it
        # settled, and the next poll routes the head with it.
        head, settled = self.settles_then_dies()
        gate.holds(self)
        gate.holds(self)

        self.assertEqual(readings.pinned_records(self)[:2], (None, settled))
        self._assert_held()
        self.recovers()

        _assert_routed(self, head, settled)

    def _assert_held(self) -> None:
        """The attempt standing on its anchor, unparked, with nothing announced, relabelled, or made again."""
        parked, anchor = self.pinned_fields(guarded.AWAITING, readings.KEY_PENDING_PUSH)
        self.assertEqual((bool(parked), anchor), (False, self.anchor))
        self.assertEqual(support.announced(self), [])
        self.assertEqual(readings.relabels(self), ())
        self.assert_made_once()



class HeldProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """The proof a hold or park takes, held to the settled-evidence policy as a finish is."""

    def test_a_moved_run_is_invalidated(self) -> None:
        # The issue is edited before a held poll: the run is invalidated whole with the attempt kept and nothing
        # parked; put back, a second held poll and the poll the gate lets through revive nothing, the head routed
        # once with nothing current.
        head, settled = self.settles_then_dies()
        for body in (_EDITED_BODY, self.issue.body):
            self.issue.body = body
            with gate.holding():
                self.recovers()

            self.assert_invalidated(settled)
            standing = self.pinned_fields(guarded.AWAITING, readings.KEY_PENDING_PUSH)
            self.assertEqual(standing, (None, self.anchor))
        self.recovers()
        _assert_routed(self, head)

    def test_marked_movement_is_retired(self) -> None:
        # An earlier finish left the mark of movement under the run's receipt
        # in the handoff's place: the proof a park asks before it keeps the
        # attempt, and the one the hold takes, read it as the movement it is
        # and invalidate the run whole, with the attempt kept.
        for name, proof in (("park", guarded.GuardedRecoveryCase.proves), ("hold", gate.holds)):
            with self.subTest(proof=name):
                self.setUp()
                settled = self.settles_then_dies()[1]
                state = self.gh.read_pinned_state(self.issue)
                state.set(_records.EVIDENCE_HANDOFF, {"moved": settled.receipt})
                self.gh.write_pinned_state(self.issue, state)

                proof(self)

                self.assert_invalidated(settled)
                self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH)[0], self.anchor)

    def test_a_tip_moved_under_the_proof_is_read(self) -> None:
        # The base tip the attempt recorded its replay as made onto reads
        # blank, or repointed, in the very reading the proof before a park
        # takes of the comment, and is put back right behind it: that reading
        # moves the run, so it is invalidated whole, with the attempt kept.
        for tip in (None, _ELSEWHERE):
            with self.subTest(tip="blank" if tip is None else "repointed"):
                self.setUp()
                settled = self.settles_then_dies()[1]
                context = guarded.recovery_context(self)
                moves = partial(self._moves_the_tip_under, self.gh.read_pinned_state, tip, [])
                with patch.object(self.gh, "read_pinned_state", moves):
                    _parks.proves_before_a_park(context)

                self.assert_invalidated(settled)
                self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH)[0], self.anchor)

    def test_an_adopted_successor_survives(self) -> None:
        # Another road settles report 3 and a newer run bound to it after the
        # tick read the comment, so the proof before the hold takes that newer
        # run in over the older report records the tick still holds: the hold's
        # record, landing over report 3, reads nothing moving under the newer
        # run, which stays current and is routed with the head by the next poll.
        head = self.settles_then_dies()[0]
        context = guarded.recovery_context(self)
        self.state = self.gh.read_pinned_state(self.issue)
        subject = _report.settles_report(self, 3, "Covered a base that moved twice as well.", head=head)
        successor = _settles_a_successor(self, subject)
        self.gh.write_pinned_state(self.issue, self.state)
        _parks.lands_a_hold(context)

        self.recovers()
        _assert_routed(self, head, successor)

    def test_an_announcement_keeps_the_hold_move(self) -> None:
        # Report 3 settles ahead of the hold's record and report 2 is put back
        # right behind it, and another finish of the landing records its
        # `base_rebased` event on the attempt right behind that record: the
        # movement the record read invalidates the run over the attempt as
        # that finish advanced it, so the next poll routes the head with
        # nothing current.
        head, settled = self.settles_then_dies()
        around = _AroundTheHold(self, head, restores=True)
        _owed_events.owes(self.gh, _REBASED, issue_number=self.issue.number, sha=head)
        announces = _WritesAtTheHold(self, {readings.KEY_ANNOUNCED_EVENT: head}, around=around)
        with patch.object(_commits.ReportCommit, _LANDING, side_effect=announces, autospec=True):
            gate.holds(self)

        self.assert_invalidated(settled)
        self.recovers()
        _assert_routed(self, head)

    def test_a_mark_leaves_another_receipt_intact(self) -> None:
        # The run stands settled beside a newer transaction another road
        # recorded for the head under the attempt's own receipt, and another
        # finish marks the run moved under the run's receipt right ahead of
        # the hold's record, which carries that mark: the run is invalidated
        # whole, and the transaction, intact under a receipt of its own, is
        # kept pending as recorded.
        run = self.settles_then_dies()[1]
        newer = settled_support.records_a_newer_run(self)
        state = self.gh.read_pinned_state(self.issue)
        self.assertTrue(_landing_records.records(state, newer))
        self.gh.write_pinned_state(self.issue, state)
        marks = _WritesAtTheHold(self, {_records.EVIDENCE_HANDOFF: {"moved": run.receipt}}, ahead=True)
        with patch.object(_commits.ReportCommit, _LANDING, side_effect=marks, autospec=True):
            gate.holds(self)

        self.assertEqual(readings.pinned_records(self)[:2], (newer, None))
        retired = readings.pinned_records(self)[2][-1]
        self.assertEqual(retired, (run.receipt, readings.INVALIDATED))

    def _moves_the_tip_under(self, live, tip: str | None, moved: list, issue):
        """`live`, the client's reading of the comment, the first taken with the base tip at `tip`, put back behind."""
        if moved:
            return live(issue)
        moved.append(tip)
        state = live(issue)
        recorded = state.get(readings.KEY_REWRITE_BASE)
        state.set(readings.KEY_REWRITE_BASE, tip)
        self.gh.write_pinned_state(issue, state)
        read = live(issue)
        state.set(readings.KEY_REWRITE_BASE, recorded)
        self.gh.write_pinned_state(issue, state)
        return read


if __name__ == "__main__":
    unittest.main()
