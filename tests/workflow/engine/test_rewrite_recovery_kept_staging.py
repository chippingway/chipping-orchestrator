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
- Behind a refused park, its staging rides no write of the proof's; usage a
  proof write carried counts once -- its answer lost too, no later write of
  the proof sending it again -- and an equal increment another road wrote twice;
  a proof write whose answer was lost and that never landed leaves the usage
  and the gate's record to the writes behind it, still counted once.
- On a state alone (`KeepsTheStagingTest`): what the tick staged is staged
  again over its own reading, what the block staged or an edit carried is left.

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
from orchestrator.workflow.engine.rewrite_recovery_staging import keeps_the_staging
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_readings as readings,
    verification_report_fixture as _report,
)

# A record the gate staged before the hold is asked, as a gate holding over a reading of its own does.
_GATE = "late_gate_hold"

# How another road spells the gate's record its own way.
_ANOTHER_GATE = "another road's gate"

# A record the tick and the block a keeper guards both stage, and the base tip neither does, on a state alone.
_PENDING = "pending"

# A counter of the issue's usage the tick adds to, which a write carrying it must add once.
_USAGE = "issue_total_tokens"
_TIP = MappingProxyType({"tip": "onto"})

# The report and review records report 3 moves, as the pinned comment spells them.
_REPORTED = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# A field another road fills the comment to the limit with, and the reason a case's park gives.
_FILLER = "another_road_filler"
_REASON = "auto_base_rebase_push_failed"

# The park a case hands the dormant guarded park.
_PARKS = partial(_parks.lands_a_park, message="The auto rebase needs a human.", reason=_REASON)

# The roads staged usage is held down, and how much the comment's total gains on each: another road adding as much
# beside report 3, a checkout gone, and that checkout's reset record landing, or never sent, with its answer lost.
_CONCURRENT, _GONE, _LOST_ANSWER = "concurrent", "gone", "gone, the blank's answer lost"
_UNSENT = "gone, the blank never sent, its answer lost"
_USAGE_ROADS = (
    (_CONCURRENT, 10), (_GONE, 5),
    (_LOST_ANSWER, 5), (_UNSENT, 5),
)


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


def _loses_the_blank(lost: list, live, issue, staged, **options):
    """`live`, the pinned-comment edit, the first one blanking the base tip landed with its answer lost into `lost`."""
    answered = live(issue, staged, **options)
    tip = readings.KEY_REWRITE_BASE
    blanks = options["over"].get(tip) and not staged.get(tip)
    if blanks and answered is PinnedEdit.EDITED and not lost:
        lost.append(answered)
        return PinnedEdit.UNCONFIRMED
    return answered


def _drops_the_blank(lost: list, live, issue, staged, **options):
    """`live`, the pinned-comment edit, the first one blanking the base tip never sent, its answer lost into `lost`."""
    tip = readings.KEY_REWRITE_BASE
    blanks = options["over"].get(tip) and not staged.get(tip)
    if blanks and not lost:
        lost.append(None)
        return PinnedEdit.UNCONFIRMED
    return live(issue, staged, **options)


# How the lost-answer roads answer the reset record's blank.
_LOSES = MappingProxyType({_LOST_ANSWER: _loses_the_blank, _UNSENT: _drops_the_blank})


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
        # still adds the tick's own. Usage that rides the reset recorded over a checkout gone is added once --
        # that record's answer lost too, the retirement asked again behind it sending none of it a second time,
        # or sending all of it where that record never landed. The gate's record lands down every road.
        for road, added in _USAGE_ROADS:
            with self.subTest(road=road):
                self.setUp()
                counted, lost, head = self._holds_over_staged_usage(road)

                self.assertEqual(readings.pinned(self).get(_USAGE), counted + added)
                self.assertEqual(readings.pinned(self).get(_GATE), head)
                self.assertEqual(len(lost), int(road in {_LOST_ANSWER, _UNSENT}))

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
        lost: list = []
        losing = _LOSES.get(road)
        if losing is None:
            _parks.lands_a_hold(context)
        else:
            with patch.object(self.gh, "edit_pinned_state", partial(losing, lost, self.gh.edit_pinned_state)):
                _parks.lands_a_hold(context)
        return counted, lost, head

class KeepsTheStagingTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """The keeper on a tick's state alone: what it stages again behind its block, over which reading, and when not."""

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
            patch.object(self.gh, "edit_pinned_state", return_value=PinnedEdit.EDITED),
            keeps_the_staging(self._over(state)) as proving,
        ):
            carrying = _read({_USAGE: 5})
            proving.gh.edit_pinned_state(self.issue, carrying, over={_USAGE: 0})
            state.data = dict(landed)
            _commit.takes_in(state, landed)
            state.set(_PENDING, "the block's")

        self.assertEqual(state.data, {**landed, _PENDING: "the block's", _GATE: "head"})
        self.assertEqual(json.loads(state.synced), landed)

    def _over(self, state: PinnedState):
        """The recovery context of this case's issue, holding `state` as the tick's."""
        return replace(guarded.recovery_context(self), state=state)


if __name__ == "__main__":
    unittest.main()
