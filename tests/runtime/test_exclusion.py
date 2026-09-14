# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which process on this host may take its artifacts, across processes.

The lock is real in every case here, on a real file under a redirected
checkout root, because that is the whole subject: `flock` is what makes a
claim outlive the object holding it and die with the process holding it, and a
double of it would agree with whichever test wrote it.

Two independently opened handles on one file are what stand in for two
processes. `flock` grants per open file description rather than per process, so
a claim taken through one handle is refused through the other exactly as it
would be across a fork -- which is what lets the overlap cases be driven here
at all.

Every wait a test drives is released from a thread. The waiting side of this
contract has no deadline by design: a poller may not go on while a pass
deletes, so what ends its wait is the pass giving the host back and nothing
else.
"""

from __future__ import annotations

import fcntl
import logging
import time
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.runtime import exclusion, host_lock
from tests.runtime import exclusion_test_support as _support

_RUNTIME_LOGGER = "orchestrator"
_DEFERRED_LOG = "deferring the whole maintenance pass"
_UNREADABLE_LOG = "could not open the host artifact lock"
_WAITING_LOG = "waiting for the process holding this host's artifacts"
_BLOCKING_FILE = "in-the-way"
_NESTED_ROOT = "root"
_FLOCK_ATTR = "flock"
_BROKEN_LOG = "could not be worked with"
# Every failure that is not contention -- ENOTSUP on a filesystem with no
# `flock`, ENOLCK on a full lock table, EBADF on a descriptor that is not one --
# reaches Python as a plain `OSError`. Only a non-blocking request that would
# have waited raises `BlockingIOError`, which is the whole of the distinction
# under test.
_BROKEN_LOCK = OSError("flock is not supported here")
_RETRY_ATTR = "_PRESENCE_RETRY_SECONDS"
_BRIEF_RETRY_SECONDS = 0.01


class LivePollingProcessTest(_support._HostRoot):
    """A live polling process anywhere on this host defers the whole pass.

    This is the case an in-process barrier cannot answer: the work is owned by
    a scheduler in another process, so the timer's own scheduler is empty, its
    hold is granted instantly, and its claim guard reports nothing running.
    The claim on the host is what refuses it.
    """

    def test_a_polling_claim_refuses_exclusivity(self) -> None:
        self.held_elsewhere(fcntl.LOCK_SH)
        with (
            self.assertLogs(_RUNTIME_LOGGER, level=logging.INFO) as logs,
            exclusion.artifact_exclusivity() as host,
        ):
            self.assertFalse(host.taken)
            self.assertTrue(any(
                _DEFERRED_LOG in message for message in logs.output
            ))

    def test_this_run_s_own_presence_refuses_it_too(self) -> None:
        # The daemon's own announcement, taken the way `cli` takes it: while it
        # stands, no separate maintenance run on this host may act.
        with (
            exclusion.polling_presence(),
            exclusion.artifact_exclusivity() as host,
        ):
            self.assertFalse(host.taken)

        with exclusion.artifact_exclusivity() as regained:
            self.assertTrue(regained.taken)

    def test_polling_runs_do_not_exclude_each_other(self) -> None:
        # Shared on purpose: what a presence excludes is a teardown, not a
        # second poller, whose own scheduler bounds its own work.
        self.held_elsewhere(fcntl.LOCK_SH)
        with (
            # Announced without a word, which is what says it never had to
            # wait for the poller already there.
            self.assertNoLogs(_RUNTIME_LOGGER, level=logging.INFO),
            exclusion.polling_presence(),
        ):
            # And the two of them together still keep a pass out.
            self.assertFalse(self.taken_elsewhere(fcntl.LOCK_EX))


class PollingWaitsForAPassTest(_support._HostRoot):
    """A polling run starting while a pass holds the host waits it out whole.

    There is no bound on this side and there must not be one: a run that gave
    up and polled anyway would have its first tick creating checkouts in a
    directory being torn down, and one that gave up and refused to poll would
    be a crash loop under a supervisor that restarts on exit. What makes the
    wait finite is the pass bounding its own hold.
    """

    def test_it_waits_until_the_pass_releases(self) -> None:
        self.release_shortly(self.held_elsewhere(fcntl.LOCK_EX))
        asked = time.monotonic()
        with (
            patch.object(host_lock, _RETRY_ATTR, _BRIEF_RETRY_SECONDS),
            self.assertLogs(_RUNTIME_LOGGER, level=logging.INFO) as logs,
            exclusion.polling_presence(),
        ):
            # It got in only after the pass gave the host back, and it is
            # holding a presence now: no pass may start beside it.
            self.assertGreaterEqual(
                time.monotonic() - asked, _support._RELEASE_DELAY_SECONDS,
            )
            self.assertFalse(self.taken_elsewhere(fcntl.LOCK_EX))
            self.assertTrue(any(
                _WAITING_LOG in message for message in logs.output
            ))


class RecurringPassTest(_support._HostRoot):
    """A polling run's own pass takes this host as exclusively as a timer does.

    A presence is shared, so it does not exclude the run that holds it: its
    pass hands the presence over, takes the host, and takes the presence back.
    Without that, one daemon could be deleting artifacts while another polls
    the same host -- submissions and teardown at once, which is what the claim
    exists to stop.
    """

    def test_the_pass_takes_the_host_off_every_poller(self) -> None:
        with exclusion.polling_presence() as host:
            with host.exclusive() as sole:
                self.assertTrue(sole)
                # Nothing else may poll and nothing else may sweep: neither
                # claim can be granted while this pass holds the host.
                self.assertFalse(self.taken_elsewhere(fcntl.LOCK_SH))
                self.assertFalse(self.taken_elsewhere(fcntl.LOCK_EX))

            # And the presence is back, so a pass elsewhere is refused again
            # while a second poller is not.
            self.assertFalse(self.taken_elsewhere(fcntl.LOCK_EX))
            self.assertTrue(self.taken_elsewhere(fcntl.LOCK_SH))

    def test_another_poller_defers_the_pass(self) -> None:
        # The second daemon's presence is exactly what this pass may not act
        # through, and the handover is what makes it visible at all.
        self.held_elsewhere(fcntl.LOCK_SH)
        with exclusion.polling_presence() as host:
            with host.exclusive() as sole:
                self.assertFalse(sole)

            self.assertFalse(self.taken_elsewhere(fcntl.LOCK_EX))

    def test_the_presence_returns_on_a_raise(self) -> None:
        with exclusion.polling_presence() as host:
            with self.assertRaises(RuntimeError), host.exclusive() as sole:
                self.assertTrue(sole)
                raise RuntimeError(_DEFERRED_LOG)

            # Given back around the body, so a pass that died leaves this run
            # announced rather than holding the host it stopped inside.
            self.assertFalse(self.taken_elsewhere(fcntl.LOCK_EX))
            self.assertTrue(self.taken_elsewhere(fcntl.LOCK_SH))

class MaintenanceExclusivityTest(_support._HostRoot):
    """Two maintenance passes exclude each other, and a pass gives the host back."""

    def test_a_second_pass_is_refused_while_one_runs(self) -> None:
        self.held_elsewhere(fcntl.LOCK_EX)
        with exclusion.artifact_exclusivity() as host:
            self.assertFalse(host.taken)

    def test_the_host_comes_back_after_a_pass(self) -> None:
        # Released around the body rather than at exit, so the nightly run
        # after this one is not refused by the one before it.
        for attempt in range(2):
            with (
                self.subTest(attempt=attempt),
                exclusion.artifact_exclusivity() as host,
            ):
                self.assertTrue(host.taken)

    def test_the_host_comes_back_when_the_body_raises(self) -> None:
        with (
            self.assertRaises(RuntimeError),
            exclusion.artifact_exclusivity() as host,
        ):
            self.assertTrue(host.taken)
            raise RuntimeError(_DEFERRED_LOG)

        with exclusion.artifact_exclusivity() as regained:
            self.assertTrue(regained.taken)


class BrokenLockTest(_support._HostRoot):
    """A lock that does not work is not a lock somebody is holding.

    The two are one `OSError` apart and mean opposite things. Contention is a
    holder that will let go, and it is waited out; anything else -- a
    filesystem with no `flock`, a lock table with no room -- says nothing about
    another process at all. Read as contention it would be waited out too, and
    that wait has no end: nobody is there to release it.
    """

    def test_a_broken_lock_is_not_read_as_contention(self) -> None:
        # The distinction itself, where it is drawn: a request that would have
        # waited raises `BlockingIOError` and is the one refusal that means a
        # holder. Anything else is raised, because there is nobody to wait for.
        lock_file = host_lock._created()
        self.addCleanup(lock_file.close)
        with (
            patch.object(fcntl, _FLOCK_ATTR, side_effect=_BROKEN_LOCK),
            self.assertRaises(OSError),
        ):
            host_lock._taken(lock_file, fcntl.LOCK_EX)

    def test_a_pass_does_not_act_on_a_broken_lock(self) -> None:
        with (
            patch.object(fcntl, _FLOCK_ATTR, side_effect=_BROKEN_LOCK),
            self.assertLogs(_RUNTIME_LOGGER, level=logging.WARNING) as logs,
        ):
            answered = self.claim_answered(exclusion.artifact_exclusivity)

            self.assertEqual(answered, [False])
            self.assertTrue(any(
                _BROKEN_LOG in message for message in logs.output
            ))

    def test_a_polling_run_goes_on_without_a_claim(self) -> None:
        # Told it has no claim rather than left waiting for one: there is no
        # holder here for a wait to end on.
        with (
            patch.object(fcntl, _FLOCK_ATTR, side_effect=_BROKEN_LOCK),
            self.assertLogs(_RUNTIME_LOGGER, level=logging.WARNING),
        ):
            self.assertEqual(
                self.claim_answered(exclusion.polling_presence), [False],
            )

    def test_a_handover_that_breaks_defers_the_pass(self) -> None:
        # The worst moment for it: this run has already given its presence up.
        # The pass is refused rather than the failure escaping it, and the
        # presence is asked for again on the way out.
        with (
            exclusion.polling_presence() as host,
            patch.object(fcntl, _FLOCK_ATTR, side_effect=_BROKEN_LOCK),
            self.assertLogs(_RUNTIME_LOGGER, level=logging.WARNING),
        ):
            self.assertEqual(self.claim_answered(host.exclusive), [False])


class UnusableLockTest(_support._HostRoot):
    """A host that cannot be coordinated on is one nothing is reclaimed on.

    The two callers rank the same failure differently, and both readings are
    the safe one: a polling run that could not announce itself still polls,
    because refusing to poll would leave a supervised deployment with nothing
    running; a pass that could not be told whether anything else is live does
    not act, because the artifacts are what it would spend on the guess.
    """

    def setUp(self) -> None:
        super().setUp()
        blocking_file = self.root / _BLOCKING_FILE
        blocking_file.touch()
        # A checkout root under a regular file: the directory the lock needs
        # cannot be created, which is the shape an unwritable root has here.
        unusable = patch.object(
            config, _support._WORKTREES_ATTR, blocking_file / _NESTED_ROOT,
        )
        unusable.start()
        self.addCleanup(unusable.stop)

    def test_a_pass_that_cannot_be_told_does_not_act(self) -> None:
        with (
            self.assertLogs(_RUNTIME_LOGGER, level=logging.WARNING) as logs,
            exclusion.artifact_exclusivity() as host,
        ):
            self.assertFalse(host.taken)
            with host.exclusive() as sole:
                self.assertFalse(sole)
            self.assertTrue(any(
                _UNREADABLE_LOG in message for message in logs.output
            ))

    def test_a_polling_run_says_so_and_goes_on(self) -> None:
        with (
            self.assertLogs(_RUNTIME_LOGGER, level=logging.WARNING) as logs,
            exclusion.polling_presence() as host,
        ):
            # It polls, and its pass acts on nothing: a run that could not be
            # told what else is live on this host may not delete from it.
            with host.exclusive() as sole:
                self.assertFalse(sole)
            self.assertTrue(any(
                _UNREADABLE_LOG in message for message in logs.output
            ))


if __name__ == "__main__":
    unittest.main()
