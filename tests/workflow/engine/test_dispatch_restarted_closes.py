# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close of a restarted cycle, read beside this process's own worker.

A poll read the owner closed while its record named cycle 4. Another poller on
this host then settled that cycle and an operator restarted it, and this
process's worker took the owner up on the fresh cycle. The submit that worker
refused hands the old reading back to the latch, and no read can tie it to the
fresh cycle -- so it is held, with no receipt. What it may not do is stand in
the way of the next close: the owner is closed again, which is a close of the
fresh cycle, and reopened, and the worker's barriers have to end that cycle
with it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.scheduler import writer_claims
from orchestrator.workflow.engine import (
    dispatch_closure as _dispatch_closure,
    poll_models as _poll_models,
    poll_reading as _poll_reading,
)
from orchestrator.workflow.stages.decomposition import late_close_observation as _late_close_observation
from tests.support.fakes import FakeLabel
from tests.workflow.engine import cleanup_deferral_support as _deferral
from tests.workflow.engine.contended_close_support import ClosedOwnerCase, restarted_elsewhere
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

                self.assertTrue(self._thread_says(fresh), "the thread says the fresh cycle's close")
                self.assertTrue(ended, "the worker's barrier ends the fresh cycle")
                self.assertTrue(self._generation().cancelled)

    def _restarted_owner(self) -> int:
        """The owner restarted elsewhere behind an old reading the worker's refused submit hands back.

        Answers the fresh cycle's id.
        """
        self._seeded_owner()
        self.github.get_issue(_deferral.OWNER_NUMBER).labels = [FakeLabel(LABEL_IMPLEMENTING)]
        read_before = read_now()
        restarted_elsewhere(self.github)
        with writer_claims.issue_writer(self.github.repo_id, _deferral.OWNER_NUMBER) as held:
            self.assertTrue(held)
            _dispatch_closure._refused_submit(
                self.github, self._spec(), _deferral.OWNER_NUMBER,
                _poll_models._PollReading(closed=True, read_at=read_before),
            )
        self.assertEqual(self._observed(_deferral.REPO_SLUG), frozenset((_deferral.OWNER_NUMBER,)))
        return self._generation().cycle_id

    def _closed_again_beside_the_worker(self, *, reopened_early: bool) -> bool:
        """Close and reopen the owner while this process's worker holds it.

        Answers whether that worker's cancellation barrier, asked once the
        owner is open again, ends the fresh cycle.
        """
        scheduler = self._scheduler()
        with scheduler.track_active(_deferral.REPO_SLUG, _deferral.OWNER_NUMBER) as tracked, \
                writer_claims.issue_writer(self.github.repo_id, _deferral.OWNER_NUMBER) as held:
            self.assertTrue(tracked and held, "the worker holds the owner")
            self._closed_again(scheduler, reopened_early=reopened_early)
            return self._barrier_ends()

    def _thread_says(self, cycle_id: int) -> bool:
        """Whether the owner's thread carries the receipt for this cycle's close."""
        receipt = receipt_for(_deferral.OWNER_NUMBER, cycle_id)
        return any(receipt in body for _, body in self.github.posted_comments)

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
