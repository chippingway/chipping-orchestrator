# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite's retirement that lands with its answer lost while the requirements its run rests on move.

The real-git finish case (`rewrite_verification_recovery_support`), every
finish held to the dormant settled-evidence policy (`settled_finish_support`)
and handed over directly: issue #7's rebased head reviewed, its run settled
under the anchor and proved ready, the head announced and relabelled, and the
retirement behind the relabel landing with its answer lost. The issue is
edited while that retirement is sent, and put back before the finish is handed
over again.

The proof behind the retirement reads the edit, so the run is no decision any
route may carry. The attempt is put back where the retirement took it and the
run invalidated over it -- or, the comment filled to its limit as the relabel
was made, the movement recorded by blanking that attempt's base tip -- and a
pinned-comment read lost once behind the proof, at the invalidation or at the
putting back, loses nothing. The attempt standing again brings the next finish
back: with room made it retires the run whole, its revision and binding kept,
and routes the head with nothing current and no second notice, `base_rebased`
event, or relabel. With nothing edited the run stays current, and the next
finish finds no attempt and makes nothing; a successor another road settled
behind the retirement is kept as that road wrote it, with nothing put back or
invalidated. The run is made once, nothing is pushed, and no developer is
launched.
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

# The readiness proof, read before any case stands in for it.
_SETTLED_WORD = _readiness.settled_word


class _Loss(NamedTuple):
    """How the retirement's lost answer goes.

    `edited` has the issue edited while the retirement is sent, `fills` the
    comment filled to its limit as the relabel is made, and `lost_read` the
    pinned-comment read behind the proof that fails once -- the invalidation's
    (1) or the putting back's (2) -- where any does.
    """

    name: str
    edited: bool = True
    fills: bool = False
    lost_read: int = 0


_LOSSES = (
    _Loss("nothing moved", edited=False),
    _Loss("the issue edited"),
    _Loss("the issue edited, the comment full", fills=True),
    _Loss("the issue edited, the invalidation's read lost", lost_read=1),
    _Loss("the issue edited, the putting back's read lost", lost_read=2),
)


class _LostRetirement:
    """The retirement landing with its answer lost, `body` written as the issue's while it is sent.

    The `lost`-th pinned-comment read behind the proof that follows it fails
    once, and `then`, where given, is made right ahead of that proof.
    """

    def __init__(self, case: settled.SettledRunCase, body: str, lost: int, then=None) -> None:
        self._case = case
        self._body = body
        self._lost = lost
        self._then = then
        self._reads = -1
        self.settled = None

    def edits(self, live, issue, state, *, over: dict):
        """`live`, the client's pinned edit, the retirement among its calls sent with its answer lost."""
        if not handoff.BEFORE_THE_RETIREMENT.kills(issue, state, over=over):
            return live(issue, state, over=over)
        self.settled = readings.pinned_records(self._case)[1]
        self._case.issue.body = self._body
        with patch.object(self._case.gh.pinned_failures, "lost", {git_support.ISSUE}):
            return live(issue, state, over=over)

    def proves(self, *args):
        """The readiness proof, the comment reads behind it counted once the retirement was sent."""
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
            if self._reads == self._lost:
                raise RuntimeError("the pinned comment would not read")
        return live(*args, **kwargs)


class LostRetirementTest(settled.SettledRunCase, unittest.TestCase):
    """Movement read behind a retirement nobody confirmed outlives it until a later finish retires the run whole."""

    def test_the_movement_outlives_the_retirement(self) -> None:
        # The first finish ends unconfirmed: the run invalidated over the
        # attempt put back, or -- the comment full -- current beside that
        # attempt's base tip blanked, or current with the attempt retired
        # where nothing moved. With the issue put back and room made, the
        # finish handed over again routes over the movement or makes nothing.
        for loss in _LOSSES:
            with self.subTest(loss=loss.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                lost = self._finishes_losing(head, loss)
                self._assert_left(loss, lost.settled)
                if loss.fills:
                    finish_moves.makes_room(self)

                again = self.finishes(head, FinishRoad.RECOVERY)

                self.assertEqual(again, FinishOutcome.ROUTED if loss.edited else FinishOutcome.UNFINISHABLE)
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
        self._assert_superseded(lost.settled)

    def _finishes_losing(self, head: str, loss: _Loss, then=None) -> _LostRetirement:
        """Publish `head`'s finish with its retirement lost as `loss` has it, then put the issue back; the loss."""
        written = self.issue.body
        lost = _LostRetirement(self, _EDITED_BODY if loss.edited else written, loss.lost_read, then)
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
        """What the unconfirmed finish left: the attempt put back where the issue moved, the run as `loss` has it."""
        pinned = readings.pinned(self)
        current = readings.pinned_records(self)[1]
        standing = self.anchor if loss.edited else None
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], standing)
        kept = loss.fills or not loss.edited
        self.assertEqual(getattr(current, "receipt", None), run.receipt if kept else None)
        blanked = loss.fills or not loss.edited
        self.assertEqual(pinned[readings.KEY_REWRITE_BASE] is None, blanked)

    def _assert_superseded(self, run) -> None:
        """A successor another road settled current, and `run` superseded into history under it as that road left it."""
        current, retired = readings.pinned_records(self)[1:]
        self.assertNotEqual(current.receipt, run.receipt)
        self.assertEqual(retired[-1], (run.receipt, "superseded"))

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
