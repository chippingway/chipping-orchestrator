# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite's final writes landing with their answers lost while the requirements its run rests on move.

Every finish held to the dormant settled-evidence policy and handed over
directly (`settled_finish_support`): issue #7's run settled and proved ready,
and the record of the `base_rebased` event, the checkpoint, or the retirement
landing with its answer lost while the issue is edited, then put back. The
proof behind the write reads the edit: the record's or checkpoint's
bookkeeping is taken in, or the attempt the retirement took put back, and
the run invalidated over it -- or, with no room, recorded by blanking the
base tip, or, the attempt no longer fitting, by the mark naming the run's
receipt in its handoff's place -- a pinned-comment read lost once losing
nothing. The next finish, room made, retires the run whole and routes the
head with everything said once; with nothing edited the run stays current,
and a successor or a replacement attempt another road wrote meanwhile is
kept as it wrote it, the run retired over the comment as it stands.
"""
from __future__ import annotations

import unittest
from functools import partial
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.workflow.engine import (
    rewrite_finish_readiness as _readiness,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a base that moved twice."

_HANDOFF = "verification_evidence_handoff"

# The readiness proof, read before any case stands in for it.
_SETTLED_WORD = _readiness.settled_word


class _Loss(NamedTuple):
    """Which final write lands with its answer lost, and how.

    `window` picks the write, `edited` has the issue edited while it is sent,
    `fills` the comment filled to its limit as the relabel is made, `crowds`
    it filled right behind the write instead, and `lost_read` the
    pinned-comment read behind the proof that fails once -- the invalidation's
    (1) or the putting back's (2) -- where any does.
    """

    name: str
    window: handoff.Boundary = handoff.BEFORE_THE_RETIREMENT
    edited: bool = True
    fills: bool = False
    crowds: bool = False
    lost_read: int = 0

    @property
    def stands(self) -> bool:
        """Whether the attempt stands behind the unconfirmed finish: put back behind a retirement only where it fits."""
        return (self.edited and not self.crowds) or self.window is not handoff.BEFORE_THE_RETIREMENT

    @property
    def blanked(self) -> bool:
        """Whether the attempt's base tip reads blank behind it: movement with no room, or the attempt retired."""
        return self.fills or not self.stands


_LOSSES = (
    _Loss("nothing moved behind the retirement", edited=False),
    _Loss("the issue edited behind the retirement"),
    _Loss("the issue edited behind the retirement, the comment full", fills=True),
    _Loss("the issue edited behind the retirement, the comment filled behind it", crowds=True),
    _Loss("the issue edited behind the retirement, the invalidation's read lost", lost_read=1),
    _Loss("the issue edited behind the retirement, the putting back's read lost", lost_read=2),
    _Loss("nothing moved behind the checkpoint", handoff.BEFORE_THE_CHECKPOINT, edited=False),
    _Loss("the issue edited behind the checkpoint", handoff.BEFORE_THE_CHECKPOINT),
    _Loss("the issue edited behind the event's record", handoff.BEFORE_THE_EVENT_RECORD),
)


class _LostAnswer:
    """The final write `loss` picks landing with its answer lost, the issue edited while it is sent where `loss` is.

    The `loss.lost_read`-th pinned-comment read behind the proof that follows
    it fails once, and `then`, where given, is made right ahead of that proof.
    """

    def __init__(self, case: settled.SettledRunCase, loss: _Loss, then=None) -> None:
        self._case = case
        self._loss = loss
        self._body = _EDITED_BODY if loss.edited else case.issue.body
        self._then = then
        self._reads = -1
        self.settled = None

    def edits(self, live, issue, state, *, over: dict):
        """`live`, the client's pinned edit, the write `loss` picks among its calls sent with its answer lost."""
        if not self._loss.window.kills(issue, state, over=over):
            return live(issue, state, over=over)
        self.settled = readings.pinned_records(self._case)[1]
        self._case.issue.body = self._body
        with patch.object(self._case.gh.pinned_failures, "lost", {git_support.ISSUE}):
            return live(issue, state, over=over)

    def proves(self, *args):
        """The readiness proof, the comment reads behind it counted once the write was sent."""
        if self.settled is not None and self._then is not None:
            self._then()
            self._then = None
        word = _SETTLED_WORD(*args)
        if self.settled is not None:
            self._reads = 0
        return word

    def reads(self, live, *args, **kwargs):
        """`live`, the client's pinned-comment read, the `lost`-th behind the proof failing once."""
        if self._reads >= 0:
            self._reads += 1
            if self._reads == self._loss.lost_read:
                raise RuntimeError("the pinned comment would not read")
        return live(*args, **kwargs)


def _pins_a_replacement(case: settled.SettledRunCase, head: str) -> None:
    """Pin an attempt of a later rebase, anchored on `head`, as that rebase would."""
    state = case.gh.read_pinned_state(case.issue)
    state.set(readings.KEY_PENDING_PUSH, head)
    case.gh.write_pinned_state(case.issue, state)


def _assert_superseded(case: settled.SettledRunCase, run) -> None:
    """A successor another road settled current, and `run` superseded into history under it as that road left it."""
    current, retired = readings.pinned_records(case)[1:]
    case.assertNotEqual(current.receipt, run.receipt)
    case.assertEqual(retired[-1], (run.receipt, "superseded"))


class LostAnswerTest(settled.SettledRunCase, unittest.TestCase):
    """Movement read behind a final write nobody confirmed outlives it until a later finish retires the run whole."""

    def test_the_movement_outlives_the_write(self) -> None:
        # The first finish ends unconfirmed: the run invalidated over the
        # attempt as the write left it or put back, or -- the comment full --
        # current beside that attempt's base tip blanked, or current where
        # nothing moved. With the issue put back and room made, the finish
        # handed over again routes the head, or makes nothing behind a
        # retirement nothing moved under.
        for loss in _LOSSES:
            with self.subTest(loss=loss.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                lost = self._finishes_losing(head, loss)
                self._assert_left(loss, lost.settled)
                if loss.fills or loss.crowds:
                    finish_moves.makes_room(self)

                again = self.finishes(head, FinishRoad.RECOVERY)

                self.assertEqual(again, FinishOutcome.ROUTED if loss.stands else FinishOutcome.UNFINISHABLE)
                self._assert_routed_once(head, lost.settled, loss.edited)

    def test_a_successor_is_kept(self) -> None:
        # Another road settles a newer run of the head right behind the
        # retirement, and the issue was edited while it was sent: the run
        # read moving is no longer the comment's current evidence, so nothing
        # is put back or invalidated, and the finish handed over again finds
        # no attempt and leaves the comment exactly as it is.
        head = self.lands_a_reviewed_rebase()
        newer = partial(settled.records_a_newer_run, self, settles=True)
        lost = self._finishes_losing(head, _LOSSES[1], then=newer)
        pinned = readings.pinned(self)

        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)

        self.assertEqual(readings.pinned(self), pinned)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], None)
        _assert_superseded(self, lost.settled)

    def test_a_replacement_is_kept(self) -> None:
        # A later rebase pins an attempt of its own right behind the
        # retirement, the issue edited while it was sent: the run read moving
        # is invalidated whole over the comment as it stands, that attempt
        # kept, and the finish handed over again leaves the comment as it is.
        head = self.lands_a_reviewed_rebase()
        pins = partial(_pins_a_replacement, self, head)
        lost = self._finishes_losing(head, _LOSSES[1], then=pins)
        pinned = readings.pinned(self)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], head)
        retired = (*git_support.invalidated(self), (lost.settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))

        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)

        self.assertEqual(readings.pinned(self), pinned)

    def test_a_successor_behind_a_checkpoint_is_kept(self) -> None:
        # Another road settles a newer run of the head right behind a
        # checkpoint that landed with its answer lost, the issue edited while
        # it was sent: nothing is invalidated under the successor, and the
        # finish handed over again routes the head with it current.
        head = self.lands_a_reviewed_rebase()
        newer = partial(settled.records_a_newer_run, self, settles=True)
        lost = self._finishes_losing(head, _LOSSES[6], then=newer)
        _assert_superseded(self, lost.settled)

        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.ROUTED)

        _assert_superseded(self, lost.settled)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def _finishes_losing(self, head: str, loss: _Loss, then=None) -> _LostAnswer:
        """Publish `head`'s finish with the write `loss` picks lost as it has it, then put the issue back; the loss."""
        written = self.issue.body
        if loss.crowds:
            then = partial(finish_moves.fills_the_comment, self)
        lost = _LostAnswer(self, loss, then)
        relabel = self.gh.set_workflow_label
        if loss.fills:
            relabel = _RacesPastTheCall(relabel, 1, partial(finish_moves.fills_the_comment, self))
        with (
            patch.object(self.gh, "edit_pinned_state", partial(lost.edits, self.gh.edit_pinned_state)),
            patch.object(self.gh, "read_pinned_state", partial(lost.reads, self.gh.read_pinned_state)),
            patch.object(self.gh, "set_workflow_label", relabel),
            patch.object(_readiness, "settled_word", lost.proves),
        ):
            self.assertEqual(self.finishes(head), FinishOutcome.UNCONFIRMED)
        self.issue.body = written
        return lost

    def _assert_left(self, loss: _Loss, run) -> None:
        """What the unconfirmed finish left: the attempt standing as `loss` has it, and the run kept where unproved."""
        pinned = readings.pinned(self)
        current = readings.pinned_records(self)[1]
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor if loss.stands else None)
        kept = loss.fills or loss.crowds or not loss.edited
        self.assertEqual(getattr(current, "receipt", None), run.receipt if kept else None)
        self.assertEqual(pinned[readings.KEY_REWRITE_BASE] is None, loss.blanked)
        marked = {"moved": run.receipt}
        self.assertEqual(pinned.get(_HANDOFF) == marked, loss.crowds)

    def _assert_routed_once(self, head: str, run, edited: bool) -> None:
        """`head` announced and relabelled once, its attempt retired, `run` invalidated whole where `edited`."""
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, ([head], 1))
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))
        if not edited:
            self.assertEqual(readings.pinned_records(self)[1].receipt, run.receipt)
            return
        retired = (*git_support.invalidated(self), (run.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (run.revision, run.binding))


if __name__ == "__main__":
    unittest.main()
