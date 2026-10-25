# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A `paused` or `backlog` an operator applies while the `ready` decision runs stops it where it stands.

The dispatcher's own hold check is as old as the tick, so every effect the
decision makes is preceded by a fresh reading of the issue's labels: the
reset, the relabel either way, the notice, the pickup, the checkpoint that
consumes the thread, and the implementer's launch. Each case applies the hold
behind one of the decision's requests and reads back what the tick did --
and, where a reroute's notice was the effect held, the `decomposing` tick that
says it once the hold is lifted.
"""
from __future__ import annotations

import copy
import itertools
import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from tests.support.fakes import DEFAULT_BOT_LOGIN, FakeGitHubClient, FakeLabel
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import child_baseline_support as _baseline, ready_test_support as _support

# The two operator holds, applied while the decision runs.
_HOLDS = ("paused", "backlog")

# A comment of ours on the thread: no requirement, and one a checkpoint consumes.
_GENERATED = _baseline.Commented(DEFAULT_BOT_LOGIN, body=_support.GENERATED)

# A reroute already landed, its relabel owed, with the receipt its notice is
# said under.
_OWED_REROUTE = MappingProxyType({"orphans": [], "unbaselined": False, "receipt": "fedcba9876543210"})

# The requests a hold lands behind: the decision's reading of the thread, and
# a relabel.
_READ_THREAD = "comments_after"

_RELABEL = "set_workflow_label"

# The requests a reroute's retirement makes past its reading: the owed notice,
# and the commit that retires the marker.
_NOTICE = "comment"

_RETIREMENT = "edit_pinned_state"

# The pinned readings a handoff takes up to its read-back behind the landed
# checkpoint: the handler's own, the pickup's preparation, the checkpoint's
# commit, and the read-back itself.
_READS_TO_THE_READ_BACK = 4

_READ_PIN = "read_pinned_state"


class _HeldTicks(_support.ReadyTicks):
    """The ticks a hold is applied in the middle of."""

    def held_tick(self, gh: FakeGitHubClient, child, hold: str, request: str, calls: int = 1) -> tuple:
        """The `ready` tick, the operator's `hold` applied behind the `calls`th answer to `request`; what it left."""
        lands = _support.LandsAfter(gh, request, calls, partial(_labelled, hold))
        return self.interleaved_tick(gh, child, lands)

    def held_decomposing(self, gh: FakeGitHubClient, child, hold: str, request: str = _READ_THREAD) -> int:
        """The `decomposing` tick, the operator's `hold` applied behind its first `request`; the agents it ran."""
        lands = _support.LandsAfter(gh, request, 1, partial(_labelled, hold))
        with patch.object(gh, lands.request, lands):
            return self.decomposing_tick(gh, child)


class ReadyHoldTest(unittest.TestCase, _PatchedWorkflowMixin, _HeldTicks):
    """A hold applied while an unchanged issue is handed on stops the handoff where it stands."""

    def test_a_hold_stops_the_handoff(self) -> None:
        # Applied once the decision has read the thread: no pickup is posted,
        # nothing is consumed or written, nothing relabelled or launched -- for
        # an issue still owed its pickup and one already anchored alike, each
        # with a comment of ours on the thread a checkpoint would consume. The
        # tick after the hold comes off hands the issue on.
        for hold, anchored in itertools.product(_HOLDS, (None, 1)):
            with self.subTest(hold=hold, anchored=anchored):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh, pickup_comment_id=anchored)
                _GENERATED(gh, child)

                held = self.held_tick(gh, child, hold, _READ_THREAD)
                _labelled(hold, gh, child)

                self.assertEqual(held, (0, _support.UNMOVED))
                self.assertEqual(self.ready_tick(gh, child), 1)

    def test_a_late_hold_stops_the_relabel(self) -> None:
        # Applied while the checkpoint is written: the pickup and what it
        # consumed are recorded, and nothing is relabelled or launched until
        # the hold comes off, when the next tick hands the issue on without
        # announcing it again.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh)

                held = self.held_tick(gh, child, hold, "edit_pinned_state")
                _labelled(hold, gh, child)
                started = self.ready_tick(gh, child)

                self.assertEqual(held[0], 0)
                self.assertEqual(held[1][:2], ((), _support.SAID_PICKUP))
                self.assertIsNotNone(self.recorded(gh, _support.KEY_LAST_ACTION))
                self.assertEqual((started, _support.notices(gh)), (1, _support.SAID_PICKUP))

    def test_a_hold_at_the_last_read_consumes_nothing(self) -> None:
        # Applied while the thread is read the last time, behind the pickup:
        # the checkpoint that would consume that reading is never written, and
        # nothing is relabelled or launched.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh)

                held = self.held_tick(gh, child, hold, _READ_THREAD, calls=2)

                self.assertEqual(held, (0, ((), _support.SAID_PICKUP, 0)))
                self.assertIsNone(self.recorded(gh, _support.KEY_LAST_ACTION))

    def test_a_hold_at_the_relabel_launches_nothing(self) -> None:
        # Applied while the label moves to implementation, behind the landed
        # checkpoint: no implementer is launched.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh)

                held = self.held_tick(gh, child, hold, _RELABEL)

                self.assertEqual(held[0], 0)
                self.assertEqual(held[1][0], (_support.STARTED,))
                self.assertEqual(held[1][1], _support.SAID_PICKUP)

    def test_a_hold_at_the_read_back_relabels_nothing(self) -> None:
        # Applied on GitHub while the record is read back behind the landed
        # checkpoint, every fetch an issue snapshot of its own: the issue is
        # fetched again behind that read, so nothing is relabelled -- no relabel
        # made on labels read before the hold writes it away -- and no
        # implementer runs.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                gh = _Snapshots()
                child = _support.ready_child(gh)

                held = self.held_tick(gh, child, hold, _READ_PIN, calls=_READS_TO_THE_READ_BACK)

                remote = gh.get_issue(_support.CHILD)
                self.assertEqual(held[0], 0)
                self.assertEqual(held[1][0], ())
                self.assertIn(hold, [label.name for label in remote.labels])


class _Snapshots(FakeGitHubClient):
    """The in-memory client, every fetch of an issue a snapshot of its own, the way each real fetch is an object.

    A relabel is written through to the issue as GitHub holds it, off the
    labels of the snapshot it was made on.
    """

    def get_issue(self, number: int):
        """A snapshot of the issue as GitHub holds it now, with labels of its own."""
        fetched = copy.copy(super().get_issue(number))
        fetched.labels = list(fetched.labels)
        return fetched

    def set_workflow_label(self, issue, label, **options) -> None:
        """Relabel the snapshot, and write its labels through to the issue as GitHub holds it."""
        super().set_workflow_label(issue, label, **options)
        self._issues[issue.number].labels = list(issue.labels)


class ReadyRerouteHoldTest(unittest.TestCase, _PatchedWorkflowMixin, _HeldTicks):
    """A hold applied while a reroute is landed, relabelled, announced, or retired stops it where it stands."""

    def test_a_hold_stops_the_reroute(self) -> None:
        # A changed child, and one whose reroute already landed with its
        # relabel owed: a hold applied once the decision has read the thread
        # lands no reset, relabels nothing, and says nothing, and the marker a
        # landed reroute left stays for the tick after the hold comes off.
        for hold, owed in itertools.product(_HOLDS, (None, _OWED_REROUTE)):
            with self.subTest(hold=hold, owed=owed):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh, edited=True, ready_reroute=owed and dict(owed))

                held = self.held_tick(gh, child, hold, _READ_THREAD)

                self.assertEqual(held, (0, _support.UNMOVED))
                self.assertEqual(self.recorded(gh, _support.KEY_REROUTE), owed)

    def test_a_held_notice_is_said_by_decomposing(self) -> None:
        # Applied while the label moves to decomposition, behind the landed
        # reset: the notice waits, and the decomposing tick the hold coming off
        # lets run says it once ahead of retiring the marker and running the
        # decomposer.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh, edited=True)

                held = self.held_tick(gh, child, hold, _RELABEL)
                _labelled(hold, gh, child)
                decomposed = self.decomposing_tick(gh, child)

                self.assertEqual(held, (0, (_support.REROUTED, _support.SAID_NOTHING, 1)))
                self.assertEqual((decomposed, _support.notices(gh)), (1, _support.SAID_CHANGED))
                self.assertIsNone(self.recorded(gh, _support.KEY_REROUTE))

    def test_a_hold_at_retirement_keeps_the_marker(self) -> None:
        # A reroute that landed, relabelled, and said its notice; a hold applied
        # while the decomposing tick reads the thread holds the retirement
        # however settled the notice is: no decomposer runs and the marker
        # stays, until the tick after the hold comes off retires it and runs the
        # decomposer without saying the notice again.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh, edited=True)
                self.ready_tick(gh, child)

                self.assertEqual(self.held_decomposing(gh, child, hold), 0)
                self.assertEqual(self.reroute(gh), _support.CHANGED_REROUTE)
                _labelled(hold, gh, child)
                ran = self.decomposing_tick(gh, child)

                self.assertEqual((ran, _support.notices(gh)), (1, _support.SAID_CHANGED))
                self.assertIsNone(self.recorded(gh, _support.KEY_REROUTE))

    def test_a_hold_at_the_owed_notice_keeps_it(self) -> None:
        # A reroute that landed and relabelled with its notice still owed; a
        # hold applied while the decomposing tick says it holds the
        # retirement: the marker stays and no decomposer runs. The tick after
        # the hold comes off finds the notice by its receipt, retires the
        # marker, and runs the decomposer without saying it again.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh, ready_reroute=dict(_OWED_REROUTE))
                gh.set_workflow_label(child, _support.LABEL_DECOMPOSING, guarded=False)

                self.assertEqual(self.held_decomposing(gh, child, hold, _NOTICE), 0)
                self.assertEqual(self.recorded(gh, _support.KEY_REROUTE), _OWED_REROUTE)
                _labelled(hold, gh, child)
                ran = self.decomposing_tick(gh, child)

                self.assertEqual((ran, _support.notices(gh)), (1, _support.SAID_CHANGED))
                self.assertIsNone(self.recorded(gh, _support.KEY_REROUTE))

    def test_a_hold_at_retirement_launches_nothing(self) -> None:
        # A hold applied while the decomposing tick retires the marker: the
        # retirement stands, and no decomposer runs until the tick after the
        # hold comes off, which has nothing left to retire or say.
        for hold in _HOLDS:
            with self.subTest(hold=hold):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh, edited=True)
                self.ready_tick(gh, child)

                self.assertEqual(self.held_decomposing(gh, child, hold, _RETIREMENT), 0)
                self.assertIsNone(self.recorded(gh, _support.KEY_REROUTE))
                _labelled(hold, gh, child)
                ran = self.decomposing_tick(gh, child)

                self.assertEqual((ran, _support.notices(gh)), (1, _support.SAID_CHANGED))


def _labelled(hold: str, gh: FakeGitHubClient, issue) -> None:
    """Apply the operator's `hold` to the issue as GitHub holds it, or take it off where it stands there."""
    remote = gh._issues[issue.number]
    held = [label for label in remote.labels if label.name == hold]
    if held:
        remote.labels.remove(held[0])
        return
    remote.labels.append(FakeLabel(hold))


if __name__ == "__main__":
    unittest.main()
