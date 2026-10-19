# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the tick staged before the proof a dormant recovery hold or park asks first, kept across that proof's writes.

The guarded recovery case (`guarded_recovery_support`): issue #7's run
settled and its finish killed before its announcement, the recovery context
read off the comment handed straight to the dormant guarded hold or park
(`rewrite_recovery_parks`), as a recovery road would.

- A gate's record of the hold, staged before the proof invalidates the run,
  still lands with the hold -- or is refused as a conflict where another road
  spelled it its own way -- and the tip the git owner stages back behind a
  reset git refused still lands with the park.
- Behind a refused park, its staging rides no write of the proof's. Ahead of
  the hold, the usage the tick staged rides none either and is added once
  behind the proof, beside an equal increment another road wrote, however the
  reset record's blank lost its answer -- landed, landed and written over by
  another road adding usage of its own, or never sent while another road
  blanks the tip -- and the gate's record, sent again behind a lost answer,
  still lands. So it is where the git owner asks the reset's record directly,
  that blank landing with its answer lost.
- On a state alone (`KeepsTheStagingTest`): what the tick staged is staged
  again over its own reading, what the block staged or an edit carried is
  left, and usage whose own write lost its answer is never sent twice. That
  write is the first the reset's record or the hold's proof makes, so an
  attempt pinned right ahead of it holds the reset, and the report moved and
  put back around it is read moving, the run invalidated whole.

Nothing is run again, pushed, or launched.
"""
from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from dataclasses import replace
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedEdit, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    rewrite_recovery_parks as _parks,
    verification_records as _records,
)
from orchestrator.workflow.engine.rewrite_recovery_staging import adds_the_totals, keeps_the_staging
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_evidence_test_support as fixtures,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    verification_report_fixture as _report,
)

# A record the gate staged before the hold is asked, as a gate holding over a reading of its own does.
_GATE = "late_gate_hold"

# How another road spells the gate's record its own way.
_ANOTHER_GATE = "another road's gate"

# A record the tick and the block a keeper guards both stage, and the base tip neither does, on a state alone.
_PENDING = "pending"

# A counter of the issue's usage the tick adds to, which a write carrying it must add once; and the strict edit.
_USAGE = "issue_total_tokens"
_EDITS = "edit_pinned_state"
_TIP = MappingProxyType({"tip": "onto"})

# The report and review records report 3 moves, as the pinned comment spells them.
_REPORTED = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# A field another road fills the comment to the limit with, and the reason a case's park gives.
_FILLER = "another_road_filler"
_REASON = "auto_base_rebase_push_failed"

# The park a case hands the dormant guarded park.
_PARKS = partial(_parks.lands_a_park, message="The auto rebase needs a human.", reason=_REASON)

# The roads staged usage is held down, and how much the comment's total gains on each: another road adding as much
# beside report 3, a checkout gone, and that checkout's reset record answered lost -- landed, landed and written over
# by another road adding 2 of its own, or never sent as another road blanks the tip and adds 2.
_CONCURRENT, _GONE, _LOST_ANSWER = "concurrent", "gone", "gone, the blank's answer lost"
_OVERWRITTEN = "gone, the blank landed with its answer lost, another road writing over it"
_UNSENT = "gone, the blank never sent, its answer lost, another road blanking the tip"
_RECORDED = "gone, the reset recorded directly, the blank's answer lost"
_USAGE_ROADS = (
    (_CONCURRENT, 10), (_GONE, 5),
    (_LOST_ANSWER, 5), (_OVERWRITTEN, 7), (_UNSENT, 7), (_RECORDED, 5),
)

# How each lost-answer road answers the reset record's blank: whether it is sent, and whether another road writes
# over the comment right then.
_LOSES = MappingProxyType({
    _LOST_ANSWER: (True, False),
    _OVERWRITTEN: (True, True),
    _UNSENT: (False, True),
    _RECORDED: (True, False),
})


def _read(carried: Mapping, *, synced: bool = True) -> PinnedState:
    """A tick's state over a comment carrying `carried`, synced with it where `synced`, as a tick reads one."""
    state = PinnedState(comment_id=1, state_data=dict(carried), parsed=True)
    if synced:
        _commit.takes_in(state, dict(carried))
    return state


def _settles_report_three(case, head: str, beside: dict) -> None:
    """Have another road settle report 3 for `head` over the comment as it stands, `beside` written with it."""
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=head)
    for field, written in beside.items():
        case.state.set(field, written)
    case.gh.write_pinned_state(case.issue, case.state)


def _answers_lost(live, issue, staged, **options) -> PinnedEdit:
    """`live`, the pinned-comment edit, sent as it is and answered lost."""
    live(issue, staged, **options)
    return PinnedEdit.UNCONFIRMED


class _LosesTheBlank:
    """The pinned-comment edit, its first one blanking the base tip answered lost as `answers` says, into `lost`.

    `answers` is whether that edit is sent, landing, and whether another road then writes over what the comment
    carries: the comment the edit was decided on, with 2 more of usage than the total standing there, and its base
    tip blanked where the edit was never sent -- so nothing of the edit left standing says whether it landed. None
    answers every edit as it is.
    """

    def __init__(self, live, answers: tuple[bool, bool] | None) -> None:
        self._live = live
        self._answers = answers
        self.lost: list = []

    def __call__(self, issue, staged, **options):
        """Answer the edit; the first blanking the tip answered lost, another road writing over it where asked."""
        over = options["over"]
        tip = readings.KEY_REWRITE_BASE
        blanks = over.get(tip) and not staged.get(tip)
        if self._answers is None or self.lost or not blanks:
            return self._live(issue, staged, **options)
        sends = self._answers[0]
        answered = self._live(issue, staged, **options) if sends else None
        self.lost.append(answered)
        if self._answers[1]:
            self._rewrites(issue, staged, over)
        return PinnedEdit.UNCONFIRMED

    def _rewrites(self, issue, staged, over: dict) -> None:
        """Write `over` back over the comment as it stands, as another road would, 2 more of usage beside its total.

        Its base tip as `over` records it where the lost edit landed and blanked it, and blanked where it never did.
        """
        tip = readings.KEY_REWRITE_BASE
        landed = self._answers[0]
        standing = staged.data if landed else over
        rewritten = {**over, _USAGE: (standing.get(_USAGE) or 0) + 2}
        rewritten[tip] = over.get(tip) if landed else None
        self._live(issue, PinnedState(comment_id=staged.comment_id, state_data=rewritten), over=standing)


class _RefusesThePark:
    """The park's strict edit refused over report 3, put back behind it -- `gone`, the checkout, removed beside it.

    Without a checkout gone, the second and third readings behind that edit go unanswered.
    """

    def __init__(self, case, head: str, gone) -> None:
        self._case = case
        self._head = head
        self._gone = gone
        self._read = case.gh.read_pinned_state
        self._edit = case.gh.edit_pinned_state
        self._fails: list | None = None

    def reads(self, issue):
        """The comment, read, unless it is one of the readings left unanswered."""
        if self._fails and self._fails.pop(0):
            raise RuntimeError("GitHub did not answer the pinned comment's read")
        return self._read(issue)

    def edits(self, issue, staged, **options):
        """The strict edit; the park's own refused over report 3 settled right ahead of it and put back behind."""
        if self._fails is not None or not guarded.parking(issue, staged, **options):
            return self._edit(issue, staged, **options)
        self._fails = []
        earlier = {key: readings.pinned(self._case).get(key) for key in _REPORTED}
        _settles_report_three(self._case, self._head, {})
        if self._gone is not None:
            self._gone.rename(self._gone.parent / "checkout-away")
        edited = self._edit(issue, staged, **options)
        restored = self._read(issue)
        for key, recorded in earlier.items():
            restored.set(key, recorded)
        self._case.gh.write_pinned_state(issue, restored)
        self._fails = [] if self._gone else [False, True, True]
        return edited


class KeptStagingTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """What the tick staged before the proof a hold or park asks first survives every write that proof lands."""

    def test_a_gate_record_survives_the_proof(self) -> None:
        # Report 3 settles before the hold, so its proof invalidates the run in a write of its own: the
        # hold's record still lands the gate's record staged before it, the attempt kept.
        head, settled = self.settles_then_dies()
        context = guarded.recovery_context(self)
        context.state.set(_GATE, head)
        _settles_report_three(self, head, {})
        _parks.lands_a_hold(context)

        self.assertEqual(readings.pinned(self).get(_GATE), head)
        self.assert_invalidated(settled)
        self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH)[0], self.anchor)

    def test_a_gate_record_moved_meanwhile_is_refused(self) -> None:
        # Another road spells the gate's record its own way beside report 3: the hold's record, staged
        # over the comment the tick read, is refused as a conflict rather than written over it.
        head, settled = self.settles_then_dies()
        context = guarded.recovery_context(self)
        context.state.set(_GATE, head)
        _settles_report_three(self, head, {_GATE: _ANOTHER_GATE})
        _parks.lands_a_hold(context)

        self.assertEqual(readings.pinned(self).get(_GATE), _ANOTHER_GATE)
        self.assert_invalidated(settled)
        self.assertTrue(context.state.withheld)

    def test_a_tip_staged_back_survives_the_proof(self) -> None:
        # The reset is recorded, git refuses it and the tip is staged back, and report 3 settles: the
        # proof before the park invalidates the run in a write of its own, and the park lands the tip back.
        head, settled = self.settles_then_dies()
        context = guarded.recovery_context(self)
        tip = context.state.get(readings.KEY_REWRITE_BASE)
        self.assertTrue(_parks.records_the_reset(context))
        context.state.set(readings.KEY_REWRITE_BASE, tip)
        _settles_report_three(self, head, {})
        self.assertTrue(_parks.proves_before_a_park(context))
        _PARKS(context)

        self.assertEqual(readings.pinned(self).get(readings.KEY_REWRITE_BASE), tip)
        self.assert_invalidated(settled)

    def test_a_refused_park_stays_off_the_proof(self) -> None:
        # The park's strict edit is refused over another road's write, and the proof behind it writes -- an
        # invalidation over the tick's own copy, or the reset over a checkout gone: none carries the park.
        for gone in (False, True):
            with self.subTest(checkout_gone=gone):
                self.setUp()
                head = self.settles_then_dies()[0]
                races = _RefusesThePark(self, head, self._wt if gone else None)
                context = guarded.recovery_context(self)
                with patch.multiple(self.gh, read_pinned_state=races.reads, edit_pinned_state=races.edits):
                    _PARKS(context)

                proved = readings.KEY_REWRITE_BASE if gone else _records.CURRENT_EVIDENCE
                self.assertEqual(self.pinned_fields(guarded.AWAITING, "park_reason"), (None, None))
                self.assertIsNone(readings.pinned(self).get(proved))
                self.assertFalse(context.state.get(guarded.AWAITING))

    def test_a_park_refused_for_room_stays_staged(self) -> None:
        # The comment, unmoved, is too full for the park's record, and the proof behind it writes nothing:
        # the tick keeps the park's bookkeeping, holding its handlers awaiting a human.
        self.settles_then_dies()
        state = self.gh.read_pinned_state(self.issue)
        state.set(_FILLER, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(state.data))
        state.set(_FILLER, "x" * room)
        self.gh.write_pinned_state(self.issue, state)
        context = guarded.recovery_context(self)
        _PARKS(context)

        self.assertTrue(context.state.get(guarded.AWAITING))
        self.assertEqual(context.state.get("park_reason"), _REASON)

    def test_staged_usage_is_counted_once(self) -> None:
        # Another road adds as much usage beside report 3, the proof's invalidation landing over it: the hold
        # still adds the tick's own. Over a checkout gone the usage rides none of the proof's writes, so however
        # the reset record's blank lost its answer -- landed, written over by another road adding 2, or never sent
        # as another road blanks the tip and adds 2 -- it is added once behind the proof beside what that road
        # added. The gate's record, sent again behind a lost answer, lands down every road -- the git owner's own
        # ask of the reset's record among them.
        for road, added in _USAGE_ROADS:
            with self.subTest(road=road):
                self.setUp()
                counted, lost, head = self._holds_over_staged_usage(road)

                self.assertEqual(readings.pinned(self).get(_USAGE), counted + added)
                self.assertEqual(readings.pinned(self).get(_GATE), head)
                self.assertEqual(len(lost), int(road in _LOSES))

    def _holds_over_staged_usage(self, road: str) -> tuple[int, list, str]:
        """Stage 5 of usage and the gate's record on the tick's state and hold over it down `road`; the usage before,
        the answers lost, and the head."""
        head = self.settles_then_dies()[0]
        context = guarded.recovery_context(self)
        counted = context.state.get(_USAGE) or 0
        context.state.set(_USAGE, counted + 5)
        context.state.set(_GATE, head)
        if road == _CONCURRENT:
            _settles_report_three(self, head, {_USAGE: counted + 5})
        else:
            self._wt.rename(self._wt.parent / "checkout-away")
        losing = _LosesTheBlank(self.gh.edit_pinned_state, _LOSES.get(road))
        with patch.object(self.gh, _EDITS, losing):
            (_parks.records_the_reset if road == _RECORDED else _parks.lands_a_hold)(context)
        return counted, losing.lost, head

class KeepsTheStagingTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """The keeper on a tick's state: what it stages again behind its block, over which reading, and its totals."""

    def test_the_staging_is_kept(self) -> None:
        # The tick stages a gate record, a pending record, and usage. In the block an edit through the
        # keeper's client lands the usage, a write lays its comment over the state whole, and the block
        # stages the pending record itself: the gate record is staged again over the tick's reading, the
        # pending record keeps the block's staging, and the carried usage is not added again.
        state = _read({_PENDING: "first", _USAGE: 0, **_TIP})
        state.set(_GATE, "head")
        state.set(_PENDING, "the tick's")
        state.set(_USAGE, 5)
        landed = {_PENDING: "another road's", _USAGE: 8, **_TIP}
        with (
            patch.object(self.gh, _EDITS, return_value=PinnedEdit.EDITED),
            keeps_the_staging(self._over(state)) as proving,
        ):
            carrying = _read({_USAGE: 5})
            proving.gh.edit_pinned_state(self.issue, carrying, over={_USAGE: 0})
            state.data = dict(landed)
            _commit.takes_in(state, landed)
            state.set(_PENDING, "the block's")

        self.assertEqual(state.data, {**landed, _PENDING: "the block's", _GATE: "head"})
        self.assertEqual(json.loads(state.synced), landed)

    def test_lost_totals_are_sent_once(self) -> None:
        # The tick stages usage alone, taken off the state for the block, whose first write lands it in a write of
        # its own whose answer is lost: taken in as sent, the tick's state withheld, so the hold recorded behind adds
        # none of it again.
        counted, context = self._stages_usage()[1:]
        with (
            patch.object(self.gh, _EDITS, partial(_answers_lost, self.gh.edit_pinned_state)),
            keeps_the_staging(context) as keeping,
        ):
            self.assertEqual(context.state.get(_USAGE) or 0, counted)
            adds_the_totals(keeping, {})
        self.assertTrue(context.state.withheld)
        self.assertTrue(_parks.lands_a_hold(context))

        self.assertEqual(readings.pinned(self).get(_USAGE), counted + 5)

    def test_a_replacement_under_the_totals_holds(self) -> None:
        # Another road pins a fresh attempt right ahead of the write landing the staged usage, the reset record's
        # first: the record reads that attempt behind it and holds the reset, the tick's state withheld, so nothing
        # written for the attempt it recovers lands over the one standing.
        head, _, context = self._stages_usage()
        replacement = fixtures.attempt_record(head, head, git_support.PR_NUMBER, git_support.REVIEWING, head)
        self._raced = ({**dict.fromkeys(readings.ATTEMPT_KEYS), **replacement}, False)
        with patch.object(self.gh, _EDITS, partial(self._races_the_totals, self.gh.edit_pinned_state)):
            self.assertFalse(_parks.records_the_reset(context))

        self.assertTrue(context.state.withheld)
        self.assertEqual(self.pinned_fields(*replacement), tuple(replacement.values()))

    def test_movement_under_the_totals_is_proved(self) -> None:
        # The report moves right ahead of the write landing the staged usage, the hold proof's first, and is put
        # back right behind it: that write read the run moving, so the proof invalidates it whole, and the hold's
        # record lands the usage that write did not.
        counted, context = self._stages_usage()[1:]
        settled = readings.pinned_records(self)[1]
        report = self.pinned_fields(_REPORTED[0])[0]
        moved = {**report, "revision": report["revision"] + 1}
        self._raced = ({_REPORTED[0]: moved}, True)
        with patch.object(self.gh, _EDITS, partial(self._races_the_totals, self.gh.edit_pinned_state)):
            self.assertTrue(_parks.lands_a_hold(context))

        self.assert_invalidated(settled)
        self.assertEqual(self.pinned_fields(_USAGE), (counted + 5,))

    def _stages_usage(self) -> tuple:
        """Settle the run and kill its finish, then stage 5 of usage on a context read off the comment; the head, the
        usage before, and that context."""
        head = self.settles_then_dies()[0]
        context = self._over(self.gh.read_pinned_state(self.issue))
        counted = context.state.get(_USAGE) or 0
        context.state.set(_USAGE, counted + 5)
        return head, counted, context

    def _races_the_totals(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit; the first moving the usage total sent behind `_raced`'s fields, written
        over the comment as another road would, and put back right behind it where `_raced` asks."""
        fields, puts_back = self._raced
        spends = staged.get(_USAGE) != options["over"].get(_USAGE)
        if not (fields and spends):
            return live(issue, staged, **options)
        self._raced = ({}, False)
        before = self.gh.read_pinned_state(issue)
        self.gh.write_pinned_state(
            issue, PinnedState(comment_id=before.comment_id, state_data={**before.data, **fields}),
        )
        answered = live(issue, staged, **options)
        if puts_back:
            self.gh.write_pinned_state(issue, before)
        return answered

    def _over(self, state: PinnedState):
        """The recovery context of this case's issue, holding `state` as the tick's."""
        return replace(guarded.recovery_context(self), state=state)


if __name__ == "__main__":
    unittest.main()
