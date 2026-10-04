# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick reads once an issue's writer claim is granted, after the poll read it.

Every dispatch path reads the issue again behind the claim: the handler is the
one the current label names, within the admission the poll gave it, and a close
the poll read is carried over that read rather than lost to it.
"""
from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    dispatch as _dispatch,
    scheduled_dispatch as _scheduled_dispatch,
    stage_targets as _stage_targets,
    tick as _tick,
)
from tests.support.fakes import make_issue
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine import refused_submit_support as _closed
from tests.workflow.engine.dispatch_scheduler_test_support import REPO_SLUG
from tests.workflow.engine.writer_claim_test_support import (
    DISPATCH_MODES,
    StandInHandler,
    WriterClaimDispatchCase,
)
from tests.workflow.fixtures import (
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    LABEL_IMPLEMENTING,
    LABEL_READY,
    LABEL_VALIDATING,
)
from tests.workflow.observation_support import ObservedCloseCase, read_now

# An issue another poller moves from `ready` to `validating`, and lets go of,
# between this tick's poll and its claim.
_ADVANCED = 13

# An issue that moves between the poll and its pass, and another issue's run
# holding the only slot the scheduler's caps leave.
_STALE = 14
_OCCUPIER = 15

# What the poll admitted that issue on -- its label and whether it was closed --
# and the label its pass reads: an `implementing` issue with no late cycle
# reopened, a `ready` one moved into family work, and a `blocked` child
# released out of a dependency walk.
_REOPENED_WORK = (LABEL_IMPLEMENTING, True, LABEL_IMPLEMENTING)
_FAMILY_WORK = (LABEL_READY, False, LABEL_DECOMPOSING)
_WALKED_OUT = (LABEL_BLOCKED, False, LABEL_READY)

# The first two, with each dispatch mode whose admission they outgrow: every
# mode's for the reopen, and the two running fan-out beside the family bucket.
_OUTGROWN = tuple(
    (admitted, mode)
    for admitted, modes in ((_REOPENED_WORK, DISPATCH_MODES), (_FAMILY_WORK, DISPATCH_MODES[1:]))
    for mode in modes
)


class AcquisitionGapTest(WriterClaimDispatchCase):
    """An issue another poller advanced before this tick's claim is routed as it reads now, not as polled."""

    def test_routed_by_the_label_it_reads_now(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.fresh_repository()
                self.github.add_issue(make_issue(_ADVANCED, label=LABEL_READY))
                polled = make_issue(_ADVANCED, label=LABEL_READY)
                with held_elsewhere(self.github.repo_id, _ADVANCED):
                    self.github.set_workflow_label(self.github.get_issue(_ADVANCED), LABEL_VALIDATING)
                stand_in = StandInHandler()

                with patch.object(self.github, "list_pollable_issues", return_value=[polled]):
                    self.ticked(stand_in, limit=limit, scheduled=scheduled, labels=(LABEL_READY, LABEL_VALIDATING))

                self.assertEqual(stand_in.ran_on, [(_ADVANCED, LABEL_VALIDATING)])
                self.assertEqual(
                    self.github.label_history, [(_ADVANCED, LABEL_VALIDATING)], "only the holder relabelled it",
                )


class StaleAdmissionTest(WriterClaimDispatchCase):
    """An issue whose pass reads it as work its admission did not cover.

    None is run on that admission; the next poll admits each as what it reads,
    under the caps and the family bucket.
    """

    def test_the_next_poll_admits_it(self) -> None:
        for admitted, (mode, limit, scheduled) in _OUTGROWN:
            with self.subTest(admitted=admitted, mode=mode):
                stand_in = StandInHandler()
                with self._admitted_stale(*admitted):
                    self.ticked(stand_in, limit=limit, scheduled=scheduled, labels=admitted[2:])

                self.assertEqual(stand_in.ran, [], "the stale admission runs no stage")

                self.ticked(stand_in, limit=limit, scheduled=scheduled, labels=admitted[2:])

                self.assertEqual(stand_in.ran, [_STALE], "the next poll runs it as what it reads")

    def test_saturated_caps_hold_it_back(self) -> None:
        for admitted in (_REOPENED_WORK, _WALKED_OUT):
            with self.subTest(admitted=admitted):
                scheduler = self._scheduler(global_cap=1, per_repo_cap=1)
                occupied = self._occupied(scheduler)
                stand_in = StandInHandler()
                with self._admitted_stale(*admitted):
                    self._ticked_on(scheduler, stand_in, admitted[2])
                self._ticked_on(scheduler, stand_in, admitted[2])

                self.assertEqual(stand_in.ran, [], "neither the exempt admission nor a capped submit runs it")

                occupied.set()
                self._wait_issue_idle(scheduler, _OCCUPIER)
                self._ticked_on(scheduler, stand_in, admitted[2])

                self.assertEqual(stand_in.ran, [_STALE])

    def _admitted_stale(self, polled: str, closed: bool, current: str):
        """A fresh repository whose issue reads `current`, listed as the poll read it."""
        self.fresh_repository()
        self.github.add_issue(make_issue(_STALE, label=current))
        listed = [make_issue(_STALE, label=polled, closed=closed)]
        return patch.object(self.github, "list_pollable_issues", return_value=listed)

    def _occupied(self, scheduler) -> threading.Event:
        """Another issue's run holding the scheduler's only slot until the event is set."""
        occupied = threading.Event()
        self.addCleanup(occupied.set)
        self.assertTrue(scheduler.submit(REPO_SLUG, _OCCUPIER, occupied.wait))
        return occupied

    def _ticked_on(self, scheduler, stand_in: StandInHandler, label: str) -> None:
        """One scheduled tick at a `parallel_limit` of 1, waited out on the issue and the family bucket."""
        with self._patched(stand_in, (label,)):
            _tick.tick(self.github, self._spec(parallel_limit=1), scheduler=scheduler)
            self._wait_issue_idle(scheduler, _STALE)
            self._wait_issue_idle(scheduler, _scheduled_dispatch._FAMILY_BUCKET_ISSUE)


class ClosedAcrossTheGapTest(ObservedCloseCase, unittest.TestCase):
    """A close the sequential poll read outlives a reopen or a failed read under the claim."""

    def setUp(self) -> None:
        self._fresh_process()
        self.github = _closed.closed_owner(live=True)
        self.polled = make_issue(_closed.OWNER_NUMBER, label=LABEL_IMPLEMENTING, closed=True)
        owner, name = _stage_targets._STAGE_HANDLER_TARGETS[LABEL_IMPLEMENTING]
        stage = patch(f"{owner}.{name}")
        self.stage = stage.start()
        self.addCleanup(stage.stop)

    def test_a_first_claim_unties_an_older_reading(self) -> None:
        # A first claim on this host cannot say who held the key before it, so
        # an older reading ties to nothing: the cycle stays live, no handler
        # runs, and the cleanup pass settles the reading.
        read_at = read_now()
        self.github.get_issue(_closed.OWNER_NUMBER).closed = False

        with self.assertLogs(_closed.WORKFLOW_LOG):
            _dispatch._process_polled_issue(self.github, _closed.SPEC, self.polled, read_at=read_at)

        owed = frozenset((_closed.OWNER_NUMBER,))
        self.assertFalse(self.github.pinned_data(_closed.OWNER_NUMBER).get(_closed.KEY_CANCELLED))
        self.stage.assert_not_called()
        self.assertEqual(self._observed(_closed.SPEC.slug), owed)

    def test_a_failed_read_keeps_the_reading(self) -> None:
        with (
            patch.object(self.github, "get_issue", side_effect=_closed.OUTAGE),
            self.assertRaises(ConnectionError),
        ):
            _dispatch._process_polled_issue(self.github, _closed.SPEC, self.polled, read_at=read_now())

        owed = frozenset((_closed.OWNER_NUMBER,))
        self.assertEqual(self._observed(_closed.SPEC.slug), owed)
        self.stage.assert_not_called()

if __name__ == "__main__":
    unittest.main()
