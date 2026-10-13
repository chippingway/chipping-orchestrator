# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite's settled run proved over the leased no-op a publication gate holds, ahead of the hold's write.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. The next tick's recovery reads the landing standing
with a transfer permission still outstanding beside it, so the landed road
receipts it through the permit-only leased no-op, and the publication gate
holds that no-op: the attempt is kept for a later tick, and the run is proved
again first (`rewrite_landing_retirement.retires_unproved`). The transfer's
own machinery -- how far it got, its permit, and the gate's answer -- is stood
in for; what is read back is the run, the attempt, and what the issue was told.

Where the issue was edited under the run, the run is invalidated into history
whole, its revision and binding kept, and putting the requirements back
before another held poll, or before the poll the gate lets through, revives
nothing: the head is routed with nothing current. Where nothing moved, the
run is kept current exactly as settled, poll after poll, and routed with it.
Either way the attempt stands while the gate holds, nothing is parked,
announced, or relabelled until the route, and the run is made once, with
nothing pushed or launched.

The hold's own record lands over the comment read afresh, never written whole:
a newer transaction another road records for the head while the gate answers
is kept pending with the revision floor it raised, and the poll the gate lets
through settles it over the run and routes the head.
"""
from __future__ import annotations

import contextlib
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import transfer_permits as _transfer_permits, transfers as _transfers
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.engine.rewrite_retry_permits_support import gated

_EDITED_BODY = "Also cover a base that moved twice."

# How the history records evidence a newer transaction for its head settled over.
_SUPERSEDED = "superseded"

# What the gate answered the permit-only no-op: held, with nothing pushed.
_HELD = _late_push._PushedCandidate(held=True)


@contextlib.contextmanager
def _gate_holds(publishes=None):
    """A transfer permission outstanding beside the landing, its permit granted, and the gate holding its no-op.

    `publishes` stands in for the gated publication where the gate's answer
    has to be made over something, `gated(_HELD)` otherwise.
    """
    with (
        patch.object(_transfers, "_carried_by", return_value=_Handoff.OUTSTANDING),
        patch.object(_transfer_permits, "_permits_the_publication", return_value=True),
        patch.object(_late_push, "_publishes", publishes or gated(_HELD)),
    ):
        yield


def _holds_beside_a_newer_run(case, recorded: list, *_called, **_options):
    """The gate's answer, held once another road recorded a newer transaction beside the run, kept in `recorded`."""
    recorded.append(guarded.records_a_newer_run(case))
    return _HELD


class GateHoldProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A gate holding the leased no-op keeps the attempt, its settled run proved first."""

    def test_a_moved_run_is_invalidated(self) -> None:
        # The issue is edited before the held poll: the run is invalidated
        # whole with the attempt kept; put back, a second held poll and the
        # poll the gate lets through revive nothing, the head routed once
        # with nothing current.
        head, settled = self.settles_then_dies()
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        with _gate_holds():
            self.recovers()
            self.assert_invalidated(settled)
            self._assert_held()
            self.issue.body = written
            self.recovers()

        self.assert_invalidated(settled)
        self._assert_held()
        self.recovers()

        self._assert_routed(head, current=None)
        retired = readings.pinned_records(self)[2]
        self.assertEqual(retired[-1], (settled.receipt, readings.INVALIDATED))

    def test_a_newer_run_survives_the_hold(self) -> None:
        # Another road records a newer transaction for the head while the gate
        # answers: the hold's record keeps it pending, with the revision floor
        # it raised, beside the settled run the proof held over it; the poll
        # the gate lets through settles it over that run and routes the head.
        head, settled = self.settles_then_dies()
        recorded: list = []
        with _gate_holds(partial(_holds_beside_a_newer_run, self, recorded)):
            self.recovers()

        newer = recorded[0]
        self.assertEqual(readings.pinned_records(self)[:2], (newer, settled))
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], newer.revision)
        self._assert_held()
        self.recovers()

        settles = readings.pinned_records(self)
        self._assert_routed(head, current=settles[1])
        self.assertEqual(settles[1].receipt, newer.receipt)
        self.assertEqual(settles[2][-1], (settled.receipt, _SUPERSEDED))

    def test_an_unmoved_run_is_kept(self) -> None:
        # Nothing moved: every held poll keeps the run current exactly as it
        # settled, and the poll the gate lets through routes the head with it.
        head, settled = self.settles_then_dies()
        with _gate_holds():
            self.recovers()
            self.recovers()

        self.assertEqual(readings.pinned_records(self)[:2], (None, settled))
        self._assert_held()
        self.recovers()

        self._assert_routed(head, current=settled)

    def _assert_held(self) -> None:
        """The attempt standing on its anchor, unparked, with nothing announced, relabelled, or made again."""
        parked, anchor = self.pinned_fields(guarded.AWAITING, readings.KEY_PENDING_PUSH)
        self.assertEqual((bool(parked), anchor), (False, self.anchor))
        self.assertEqual(support.announced(self), [])
        self.assertEqual(readings.relabels(self), ())
        self.assert_made_once()

    def _assert_routed(self, head: str, current) -> None:
        """`head` announced and routed once with `current` the evidence current, the attempt retired, run once."""
        announced = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(announced, ([head], 1))
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        self.assertEqual(readings.pinned_records(self)[1], current)
        self.assert_made_once()


if __name__ == "__main__":
    unittest.main()
