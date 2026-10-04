# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close of a restarted cycle, read beside this process's own worker.

A poll read the owner closed while its record named cycle 4. Another poller on
this host then settled that cycle and an operator restarted it, and this
process's worker took the owner up on the fresh cycle. Whatever this process
still holds of the old close -- a reading no read can tie to the fresh cycle,
or the memo of the receipt it already posted for cycle 4 -- may not stand in
the way of the next close: the owner is closed again, which is a close of the
fresh cycle, and reopened, and the worker's barriers have to end that cycle
with it, and so does the process after a restart, from the thread.
"""
from __future__ import annotations

import contextlib
import unittest
from unittest.mock import Mock, patch

from orchestrator.scheduler import writer_claims
from orchestrator.workflow.engine import (
    dispatch_closure as _dispatch_closure,
    dispatch_partition as _dispatch_partition,
    poll_reading as _poll_reading,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.stages.decomposition import late_close_observation as _late_close_observation
from tests.support.fakes import FakeLabel, make_issue
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import (
    ClosedOwnerCase,
    RestartedAfter,
    restarted_elsewhere,
)
from tests.workflow.fixtures import LABEL_IMPLEMENTING
from tests.workflow.observation_support import read_now, receipt_for


class FreshCloseBesideAWorkerTest(ClosedOwnerCase, unittest.TestCase):
    """The second close ends the restarted cycle, however soon it is reopened."""

    def test_a_second_close_ends_the_fresh_cycle(self) -> None:
        # Reopened once the poll's own read behind the record has found it
        # closed, and reopened before that read: the second is a close only
        # the moment the poll read it at can tie to the fresh cycle.
        for reopened_early in (False, True):
            with self.subTest(reopened_before_the_read_behind_the_record=reopened_early):
                fresh = self._restarted_owner()

                ended = self._closed_again_beside_the_worker(reopened_early=reopened_early)

                self.assertTrue(_thread_says(self.github, fresh), "the thread says the fresh cycle's close")
                self.assertTrue(ended, "the worker's barrier ends the fresh cycle")
                self.assertTrue(self._generation().cancelled)

    def _restarted_owner(self) -> int:
        """The owner restarted elsewhere behind an old reading a poll kept beside the worker.

        Answers the fresh cycle's id.
        """
        self._seeded_owner()
        self.github.get_issue(_deferral.OWNER_NUMBER).labels = [FakeLabel(LABEL_IMPLEMENTING)]
        read_before = read_now()
        restarted_elsewhere(self.github)
        polled = make_issue(_deferral.OWNER_NUMBER, label=LABEL_IMPLEMENTING, closed=True)
        with writer_claims.issue_writer(self.github.repo_id, _deferral.OWNER_NUMBER) as held:
            self.assertTrue(held)
            _dispatch_closure._recorded_at_poll(self.github, self._spec(), polled, read_before)
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset((_deferral.OWNER_NUMBER,)))
        return self._generation().cycle_id

    def _closed_again_beside_the_worker(self, *, reopened_early: bool) -> bool:
        """Close and reopen the owner while this process's worker holds it.

        Answers whether that worker's cancellation barrier, asked once the
        owner is open again, ends the fresh cycle.
        """
        with _worker_holding(self) as scheduler:
            self._closed_again(scheduler, reopened_early=reopened_early)
            return self._barrier_ends()

    def _barrier_ends(self) -> bool:
        """Ask the barrier a worker's walk takes whether a latched close ends its cycle."""
        owner = self.github.get_issue(_deferral.OWNER_NUMBER)
        return _late_close_observation._latched_close_ends(
            self.github, self._spec(), owner, self.github.read_pinned_state(owner),
        )

    def _closed_again(self, scheduler, *, reopened_early: bool) -> None:
        """The tick that reads the owner closed beside the worker, and the reopen after it."""
        owner = self.github.get_issue(_deferral.OWNER_NUMBER)
        owner.closed = True
        classify = _poll_reading._classify_pollable_issue
        reopening = _ReopenedOnClassify(owner, classify) if reopened_early else classify
        with patch.object(_poll_reading, "_classify_pollable_issue", reopening):
            self._ticked(scheduler, held=True)
        owner.closed = False


class ReceiptedThenRestartedTest(ClosedOwnerCase, unittest.TestCase):
    """A fresh cycle's close, read while this process remembers the old cycle's receipt.

    The poll read the owner closed beside this process's worker and put cycle
    4's receipt on the thread, and the cleanup that reading owed was still
    pending when another poller on this host settled that cycle and an
    operator restarted it. The owner is closed again beside this process's
    worker -- a close of the fresh cycle -- then reopened, and this process is
    restarted before any pass reaches it: the thread is all the next one has.
    """

    def test_the_fresh_close_outlives_the_restart(self) -> None:
        fresh = self._closed_again_after_a_receipt()
        self._fresh_process()
        stand_in = Mock()

        with patch(".".join(_stage_targets._STAGE_HANDLER_TARGETS[LABEL_IMPLEMENTING]), stand_in):
            self._ticked(self._scheduler())

        self.assertTrue(_thread_says(self.github, fresh), "the fresh cycle's close is on the thread")
        self.assertTrue(self._generation().cancelled, "the next process ends the fresh cycle from it")
        stand_in.assert_not_called()

    def _closed_again_after_a_receipt(self) -> int:
        """Cycle 4's close receipted beside the worker, the restart, and the fresh close and reopen.

        Answers the fresh cycle's id.
        """
        self._seeded_owner()
        owner = self.github.get_issue(_deferral.OWNER_NUMBER)
        owner.labels = [FakeLabel(LABEL_IMPLEMENTING)]
        with _worker_holding(self) as scheduler:
            self._ticked(scheduler, held=True)
        self.assertTrue(_thread_says(self.github, _deferral.CYCLE_ID), "the old cycle's receipt landed")
        restarted_elsewhere(self.github)
        owner.closed = True
        with _worker_holding(self) as scheduler:
            self._ticked(scheduler, held=True)
        owner.closed = False
        return self._generation().cycle_id


class RestartedByOurWorkerTest(ClosedOwnerCase, unittest.TestCase):
    """A close the poll found ending nothing, refused as this process's worker restarts the cycle."""

    def test_the_old_close_spares_the_fresh_cycle(self) -> None:
        self._seeded_owner()
        owner = self.github.get_issue(_deferral.OWNER_NUMBER)
        owner.labels = [FakeLabel(LABEL_IMPLEMENTING)]
        self._ended_over()
        restart = RestartedAfter(self.github, _dispatch_partition._partition_pollable_issues, signed=False)

        with _worker_holding(self) as scheduler:
            with patch.object(_dispatch_partition, "_partition_pollable_issues", restart):
                self._ticked(scheduler, held=True)
            ended = _late_close_observation._latched_close_ends(
                self.github, self._spec(), owner, self.github.read_pinned_state(owner),
            )

        fresh = self._generation()
        self.assertGreater(fresh.cycle_id, _deferral.CYCLE_ID)
        self.assertFalse(_thread_says(self.github, fresh.cycle_id), "no receipt names the fresh cycle")
        self.assertFalse(ended or fresh.cancelled, "and the old close ends nothing")
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset())


@contextlib.contextmanager
def _worker_holding(case: ClosedOwnerCase):
    """This process's worker holding the owner, as its scheduler and its writer claim say.

    Hands back the scheduler that is tracking it, which refuses every submit
    for the owner while the block runs.
    """
    scheduler = case._scheduler()
    with scheduler.track_active(_deferral.REPO_SLUG, _deferral.OWNER_NUMBER) as tracked, \
            writer_claims.issue_writer(case.github.repo_id, _deferral.OWNER_NUMBER) as held:
        case.assertTrue(tracked and held, "the worker holds the owner")
        yield scheduler


def _thread_says(github, cycle_id: int) -> bool:
    """Whether the owner's thread carries the receipt for this cycle's close."""
    receipt = receipt_for(_deferral.OWNER_NUMBER, cycle_id)
    return any(receipt in body for _, body in github.posted_comments)


class _ReopenedOnClassify:
    """Classify the polled issue, then reopen it before anything reads it again."""

    def __init__(self, owner, classify) -> None:
        self._owner = owner
        self._classify = classify

    def __call__(self, *asked):
        """Answer the classification, then reopen the owner."""
        answered = self._classify(*asked)
        self._owner.closed = False
        return answered


if __name__ == "__main__":
    unittest.main()
