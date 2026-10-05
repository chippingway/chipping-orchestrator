# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close no read could tie to a cycle ends none until a pass under the claim can.

Another poller on this host may settle the cycle a polled close ended and start
a fresh one before this process holds the issue, so a close ties to a cycle
only by a record read with the issue still closed behind it, or one no other
poller held the issue since. A close tied to neither is kept, and a cycle
restarted meanwhile is spared on every dispatch mode; a hold that ended before
the poll -- a restarted poller's predecessor's -- costs the reading nothing.
"""
from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from orchestrator.workflow.engine import (
    dispatch_partition as _dispatch_partition,
    poll_models as _poll_models,
    poll_reading as _poll_reading,
    scheduled_dispatch as _scheduled_dispatch,
    stage_targets as _stage_targets,
)
from tests.support.fakes import FakeLabel
from tests.support.writer_claim_processes import HELD, OtherProcess, shared_namespace
from tests.support.writer_claims import claimable, held_elsewhere
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import (
    ClosedOwnerCase,
    RestartedAfter,
    RestartedBeforeTheRead,
    restarted_elsewhere,
    ticked_on,
    written,
)
from tests.workflow.engine.writer_claim_test_support import DISPATCH_MODES
from tests.workflow.fixtures import LABEL_IMPLEMENTING

_OWED = frozenset((_deferral.OWNER_NUMBER,))

# The handler the owner reaches on an ordinary label, and must not here.
_IMPLEMENTING_TARGET = _stage_targets._STAGE_HANDLER_TARGETS[LABEL_IMPLEMENTING]

# Where the poll's reading can go stale: after classification, on every mode;
# and after the partition wrote it down, on the two modes that partition.
_CLASSIFIED = (_poll_reading, "_classify_pollable_issue")
_PARTITIONED = (_dispatch_partition, "_partition_pollable_issues")
_STALE_READINGS = tuple(
    (mode, step) for mode in DISPATCH_MODES for step in (_CLASSIFIED, _PARTITIONED)
    if step is _CLASSIFIED or mode[2] or mode[1] > 1
)

# Each, with the restart's hold found first by the worker's claim or another thread's.
_FOUND_BETWEEN = (False, True)
_RESTARTS = tuple((*reading, found) for reading in _STALE_READINGS for found in _FOUND_BETWEEN)

# Each mode, with the contender's record read refused and taken behind a restart.
_CONTENDED_READS = tuple((mode, unread) for mode in DISPATCH_MODES for unread in (True, False))

# The poller a restarted one comes up after: it holds the issue's claim and exits.
_PREDECESSOR = """
import sys

from orchestrator.scheduler import writer_claims

with writer_claims.issue_writer(int(sys.argv[1]), int(sys.argv[2])) as held:
    print("held" if held else "refused", flush=True)
"""


class ContendedUnconfirmedTest(ClosedOwnerCase, unittest.TestCase):
    """A close read while another poller holds the closed umbrella owner."""

    def test_an_unconfirmed_close_spares_a_restart(self) -> None:
        # The record unreadable, or restarted before it was read: the close is
        # kept tied to no cycle, and the retry lets it go.
        for mode, unread in _CONTENDED_READS:
            with self.subTest(mode=mode[0], unread=unread):
                self._held_while_read(mode, unread=unread)
                self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED, "the close is kept")
                if unread:
                    restarted_elsewhere(self.github)
                before = written(self.github)

                _ticked_in(self, mode)

                self._assert_restarted_cycle_spared(before)

    def test_an_unread_close_ends_a_closed_cycle(self) -> None:
        # What keeping it buys: a pass under the claim finding it closed ends it.
        for mode in DISPATCH_MODES:
            with self.subTest(mode=mode[0]):
                self._held_while_read(mode, unread=True)

                _ticked_in(self, mode)

                self.assertTrue(self._cancelled(), "a close standing under the claim ends the cycle")
                self.stage.assert_not_called()

    def _held_while_read(self, mode: tuple, *, unread: bool) -> None:
        """One tick over the fresh owner while another poller holds it.

        The contender's record read is refused where `unread` says so, and
        otherwise taken behind a restart the holder makes first.
        """
        self._seeded_owner()
        reading = Mock(side_effect=ConnectionError("unreachable")) if unread else RestartedBeforeTheRead(self.github)
        with (
            held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER),
            patch.object(self.github, "read_pinned_state", reading),
        ):
            _ticked_in(self, mode)


class PolledUnconfirmedTest(ClosedOwnerCase, unittest.TestCase):
    """A close the poll carries to its worker, on an owner wearing an ordinary label."""

    def test_a_polled_close_spares_a_later_restart(self) -> None:
        # Another poller restarts the cycle before this process's worker holds
        # the issue: no reading marks the fresh cycle, whichever claim of this
        # process found the restart's hold first.
        for mode, step, found in _RESTARTS:
            with self.subTest(mode=mode[0], restarted_after=step[1], found_between=found):
                restarted, stand_in = self._ticked_past_a_restart(mode, step, found=found)

                self.assertGreater(restarted.cycle_id, _deferral.CYCLE_ID)
                self.assertFalse(restarted.cancelled, "the fresh cycle is not ended by the old close")
                self.assertEqual(self._generation(), restarted, "nor by the pass that settles the reading")
                self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset(), "the reading is let go")
                stand_in.assert_not_called()

    def test_a_reopen_alone_still_ends_the_cycle(self) -> None:
        # The same reopen with no other poller in it, on an issue this host has
        # written before: the cycle the close ended is ended, and no handler run.
        for mode, step in _STALE_READINGS:
            with self.subTest(mode=mode[0], reopened_after=step[1]):
                self._seeded_owner()
                self.assertTrue(claimable(self.github.repo_id, _deferral.OWNER_NUMBER))
                self.github.get_issue(_deferral.OWNER_NUMBER).labels = [FakeLabel(LABEL_IMPLEMENTING)]
                stand_in = Mock()

                reopening = _ReopenedAfter(self, getattr(*step))
                with patch.object(*step, reopening), _intercepted(stand_in):
                    _ticked_in(self, mode)

                self.assertTrue(self._cancelled(), "the cycle the close ended is ended")
                stand_in.assert_not_called()

    def _ticked_past_a_restart(self, mode: tuple, step: tuple, *, found: bool) -> tuple:
        """Two ticks over the owner, restarted elsewhere once `step` of the first returns.

        Answers the cycle the restart started, as the first tick left it, and
        the handler an `implementing` owner reaches.
        """
        self._seeded_owner()
        self.github.get_issue(_deferral.OWNER_NUMBER).labels = [FakeLabel(LABEL_IMPLEMENTING)]
        stand_in = Mock()
        restarting = RestartedAfter(self.github, getattr(*step), found=found)

        with patch.object(*step, restarting), _intercepted(stand_in):
            _ticked_in(self, mode)
            restarted = self._generation()
            _ticked_in(self, mode)

        self.assertEqual(restarting.found_by, [True] if found else [], "the claim between is granted")
        return restarted, stand_in


class QueuedFamilyRestartTest(ClosedOwnerCase, unittest.TestCase):
    """A family drain queued before a contended close was kept, reaching the owner only after its restart."""

    def test_the_old_close_spares_the_restarted_cycle(self) -> None:
        self._seeded_owner()
        with held_elsewhere(self.github.repo_id, _deferral.OWNER_NUMBER):
            _ticked_in(self, DISPATCH_MODES[0])
        self.assertEqual(self._observed(_deferral.REPO_SLUG), _OWED, "the contender keeps the close")
        restarted_elsewhere(self.github)
        before = written(self.github)
        owner, name = _deferral.UMBRELLA_TARGET

        with patch.object(importlib.import_module(owner), name, self.stage):
            _scheduled_dispatch._drain_scheduler_family_bucket(
                self.github, self._spec(), self._scheduler(),
                _poll_models._PollablePartition([_deferral.OWNER_NUMBER], [None], [], set()),
            )

        self._assert_restarted_cycle_spared(before)


class RestartedPollerTest(ClosedOwnerCase, unittest.TestCase):
    """A poller restarted over the namespace its predecessor -- a real process -- signed and left."""

    def setUp(self) -> None:
        super().setUp()
        self.root = shared_namespace(self)

    def test_a_predecessors_hold_spares_the_reading(self) -> None:
        # The predecessor's hold ended before this poll read the close, so the
        # reopen ends the cycle as a lone poller's does.
        for mode, step in _STALE_READINGS:
            with self.subTest(mode=mode[0], reopened_after=step[1]):
                self._seeded_owner()
                self.github.get_issue(_deferral.OWNER_NUMBER).labels = [FakeLabel(LABEL_IMPLEMENTING)]
                self._held_before_the_restart()
                stand_in = Mock()

                reopening = _ReopenedAfter(self, getattr(*step))
                with patch.object(*step, reopening), _intercepted(stand_in):
                    _ticked_in(self, mode)

                self.assertTrue(self._cancelled(), "the cycle the close ended is ended")
                stand_in.assert_not_called()

    def _held_before_the_restart(self) -> None:
        """The predecessor takes the owner's claim, lets go, and exits."""
        predecessor = OtherProcess(self.root, _PREDECESSOR, self.github.repo_id, _deferral.OWNER_NUMBER)
        self.addCleanup(predecessor.close)
        self.assertEqual(predecessor.said(), HELD)
        self.assertEqual(predecessor.exited(), 0)


class _ReopenedAfter:
    """One step of the poll that, once it returns, finds the owner reopened."""

    def __init__(self, case: ClosedOwnerCase, step) -> None:
        self._case = case
        self._step = step

    def __call__(self, *asked):
        """Take the step, then reopen the owner."""
        answered = self._step(*asked)
        self._case._reopened()
        return answered


def _ticked_in(case: ClosedOwnerCase, mode: tuple) -> None:
    """One tick over the closed owner, through the dispatch mode `mode` names."""
    ticked_on(case, mode[1], scheduled=mode[2])


def _intercepted(stand_in: Mock):
    """Stand `stand_in` in for the handler an `implementing` owner reaches."""
    owner, name = _IMPLEMENTING_TARGET
    return patch.object(importlib.import_module(owner), name, stand_in)


if __name__ == "__main__":
    unittest.main()
