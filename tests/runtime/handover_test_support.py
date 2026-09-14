# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a handover race needs: a live scheduler and the real host lock.

Neither can be doubled here. The question is whether this process ever gives
its presence on the host up while it still has work, and the two things that
answer it are the scheduler that holds the work and the `flock` that holds the
host -- a stand-in for either would agree with whichever ordering the test was
written against.

What IS wrapped is the claim, and only to watch it: `WatchedHandover` delegates
to the real presence and records what this process looked like at each edge of
the handover. That is where the answer lives, because both gaps a wrong
ordering leaves are edges rather than states -- the moment the presence goes,
and the moment it comes back.
"""
from __future__ import annotations

import contextlib
import tempfile
import threading
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.runtime import exclusion, host_lock
from orchestrator.scheduler import IssueScheduler
from tests.runtime import polling_test_support as _support

_WORKTREES_ATTR = "WORKTREES_DIR"
_RETRY_ATTR = "_PRESENCE_RETRY_SECONDS"
_BRIEF_RETRY_SECONDS = 0.01
# Two slots, so the probe submission is never refused for a full pool: what it
# is asked to report is whether admission is closed, and a cap would answer
# the same way for the wrong reason.
_CAP = 2
_WORKER_ISSUE_NUMBER = 7
_PROBE_ISSUE_NUMBER = 8
_EVENT_TIMEOUT_SECONDS = 2.0
_WORKER_TIMEOUT_SECONDS = 5.0

# The bound a barrier is given when the test means the drain to succeed, and
# the one it is given when the test means it to run out.
PATIENT_BARRIER_SECONDS = 5.0

BRIEF_BARRIER_SECONDS = 0.1

# When the gated worker is let go: after the drain is already waiting on it, so
# the barrier really has to wait rather than finding the pool empty.
RELEASE_DELAY_SECONDS = 0.05


class _GatedWorker:
    """A counted worker that runs until the test lets it finish."""

    def __init__(
        self, started: threading.Event, release: threading.Event,
    ) -> None:
        self._started = started
        self._release = release

    def __call__(self) -> None:
        self._started.set()
        self._release.wait(timeout=_WORKER_TIMEOUT_SECONDS)


class WatchedHandover:
    """The real presence claim, with both edges of its handover recorded.

    `edges` is what this process looked like each time the host changed hands,
    in order: the count of work in flight and whether admission was open. An
    empty list is a pass that never handed anything over at all, which is what
    a run refused the quiet it asked for must look like.
    """

    taken = True

    def __init__(self, host_claim, probe) -> None:
        self.edges: list[tuple[int, bool]] = []
        self._host_claim = host_claim
        self._probe = probe

    @contextlib.contextmanager
    def exclusive(self) -> Iterator[bool]:
        self.edges.append(self._probe())
        try:
            with self._host_claim.exclusive() as sole:
                yield sole
        finally:
            self.edges.append(self._probe())


class _HandoverTestCase(unittest.TestCase):
    """One live scheduler and one real host lock, under a checkout root of
    this test's own so no claim is the operator's.
    """

    def setUp(self) -> None:
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        for patched in (
            patch.object(config, _WORKTREES_ATTR, self.root),
            patch.object(host_lock, _RETRY_ATTR, _BRIEF_RETRY_SECONDS),
        ):
            patched.start()
            self.addCleanup(patched.stop)
        self.scheduler = IssueScheduler(global_cap=_CAP, per_repo_cap=_CAP)
        self.addCleanup(self.scheduler.shutdown)
        self.clients = _support.build_clients([_support.ALPHA_REPO])
        self.release = threading.Event()
        self.addCleanup(self.release.set)

    def start_gated_worker(self) -> None:
        """Put one counted worker in the pool and wait until it is running."""
        started = threading.Event()
        self.assertTrue(self.scheduler.submit(
            _support.ALPHA_REPO,
            _WORKER_ISSUE_NUMBER,
            _GatedWorker(started, self.release),
        ))
        self.assertTrue(started.wait(timeout=_EVENT_TIMEOUT_SECONDS))
        self.assertEqual(self.scheduler.active_count(), 1)

    def release_shortly(self) -> None:
        """Let that worker finish, once the drain is already waiting on it."""
        threading.Timer(RELEASE_DELAY_SECONDS, self.release.set).start()

    def probe(self) -> tuple[int, bool]:
        """What this process has running, and whether it is admitting work.

        Admission is read by submitting, because that is the only thing the
        answer is about: a barred scheduler refuses the submission, and a
        scheduler this test could ask any other way would be one the pass does
        not go through.
        """
        return (
            self.scheduler.active_count(),
            self.scheduler.submit(
                _support.ALPHA_REPO, _PROBE_ISSUE_NUMBER, _noop,
            ),
        )

    def host_is_free(self) -> bool:
        """Whether another process could take this host right now.

        Asked the way a maintenance process asks it, through the claim rather
        than through the lock: a separate file description, an exclusive
        request that does not wait, and the answer that decides whether that
        process would act.
        """
        with exclusion.artifact_exclusivity() as host:
            return host.taken


def _noop() -> None:
    """The worker a probe submission would run if admission were open."""
