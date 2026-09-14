# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The live scheduler a barrier test drives, and the claims it holds on it.

The two things the hold waits on are reached from different places: a counted
worker is what ``submit`` puts in the pool, and a tracked claim is what a
handler already running takes for itself. A test that only ever went through
``submit`` could not tell the two apart, so the claim here is taken on a bare
thread and given back on demand.

Nothing about the scheduler itself is doubled. What the hold is worth is
decided by the executor and the two claim sets, so a stand-in for either would
hand the fixture's own answer back.
"""
from __future__ import annotations

import contextlib
import threading
import unittest
from functools import partial

from orchestrator.scheduler.service import IssueScheduler
from tests.scheduler.coordination_helpers import _release_after
from tests.scheduler.worker_helpers import _worker

PRIMARY_REPO = "owner/repo"
SCHEDULER_LOGGER = "orchestrator.scheduler"
FORBIDDEN_WORKER_MESSAGE = "must not run"
EVENT_TIMEOUT_SECONDS = 2.0
WORKER_TIMEOUT_SECONDS = 5.0
RELEASE_DELAY_SECONDS = 0.05
WORKER_ISSUE_NUMBER = 7
CLAIMED_ISSUE_NUMBER = 11
LATE_ISSUE_NUMBER = 13

# The bound a test that expects the hold to be refused gives it: short enough
# not to wait out a real one, long enough that a slow thread start is not read
# as a host that would not go quiet.
BRIEF_BARRIER_TIMEOUT_SECONDS = 0.2

# The bound a test that expects the hold to be granted gives it, sized so a
# loaded machine still drains inside it. A test relying on this one asserts on
# the answer rather than on how long it took.
GENEROUS_BARRIER_TIMEOUT_SECONDS = 5.0


# Wide enough that no test here is ever refused by a cap: what these tests are
# about is the hold, and a submission turned away for a full pool would pass
# them for the wrong reason.
_CAP = 4


def _forbidden_worker() -> None:
    """A worker every admission test expects the scheduler to refuse."""
    raise AssertionError(FORBIDDEN_WORKER_MESSAGE)


def _claiming_worker(
    scheduler: IssueScheduler,
    issue_number: int,
    signals: tuple[threading.Event, threading.Event],
    answers: list[bool],
) -> None:
    """Work already admitted that asks for a tracked claim mid-flight.

    The shape of a family bucket reaching its next issue: the worker was let in
    before the hold and takes its per-issue claim after it, which is the one
    way a claim could still appear once the barrier has read the counts.
    """
    start, release = signals
    start.set()
    release.wait(timeout=WORKER_TIMEOUT_SECONDS)
    with scheduler.track_active(PRIMARY_REPO, issue_number) as claimed:
        answers.append(claimed)


class _HeldClaim:
    """One tracked claim, held on its own thread until it is given back."""

    def __init__(self, scheduler: IssueScheduler, issue_number: int) -> None:
        self.release = threading.Event()
        self._scheduler = scheduler
        self._issue_number = issue_number
        self._taken = threading.Event()
        self._holder = threading.Thread(target=self._hold, daemon=True)

    def take(self, test_case) -> None:
        """Hold the claim, and give it back however the test ends."""
        test_case.addCleanup(self.give_back)
        self._holder.start()
        test_case.assertTrue(self._taken.wait(timeout=EVENT_TIMEOUT_SECONDS))

    def give_back(self) -> None:
        self.release.set()
        self._holder.join(timeout=WORKER_TIMEOUT_SECONDS)

    def _hold(self) -> None:
        with self._scheduler.track_active(
            PRIMARY_REPO, self._issue_number,
        ) as claimed:
            if claimed:
                self._taken.set()
            self.release.wait(timeout=WORKER_TIMEOUT_SECONDS)


class _BarrierTestCase(unittest.TestCase):
    """One live scheduler per test, with the hold and the gates spelled once.

    Every gate is released through a cleanup, so an assertion that fails cannot
    leave the hold on, a worker parked in the pool, or the shutdown at the end
    of the test waiting on either.
    """

    def setUp(self) -> None:
        self.scheduler = IssueScheduler(global_cap=_CAP, per_repo_cap=_CAP)
        self.addCleanup(self.scheduler.shutdown)

    def held(
        self, *, timeout: float = GENEROUS_BARRIER_TIMEOUT_SECONDS,
    ) -> contextlib.AbstractContextManager[bool]:
        """Take the hold with the bound this test means to give it."""
        return self.scheduler.maintenance_barrier(timeout=timeout)

    def gate(self) -> threading.Event:
        """One gate a worker or a claim waits on, released after the test."""
        gate = threading.Event()
        self.addCleanup(gate.set)
        return gate

    def start_gated_worker(self, release: threading.Event) -> None:
        """Put one counted worker in the pool and wait until it is running."""
        start = threading.Event()
        self.assertTrue(self.scheduler.submit(
            PRIMARY_REPO,
            WORKER_ISSUE_NUMBER,
            partial(_worker, start, release),
        ))
        self.assertTrue(start.wait(timeout=EVENT_TIMEOUT_SECONDS))

    def release_shortly(self, gate: threading.Event) -> None:
        """Let a gate go from another thread, once the hold is already waiting."""
        threading.Thread(
            target=_release_after,
            args=(RELEASE_DELAY_SECONDS, gate),
            daemon=True,
        ).start()
