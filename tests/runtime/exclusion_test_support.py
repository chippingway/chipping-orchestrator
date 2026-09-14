# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real host-lock handles and bounded thread waits for exclusion tests."""
from __future__ import annotations

import fcntl
import tempfile
import threading
import unittest
from pathlib import Path
from typing import TextIO
from unittest.mock import patch

from orchestrator import config
from orchestrator.runtime import host_lock

_WORKTREES_ATTR = "WORKTREES_DIR"
# How long a claim that must not wait is given before the test calls it a wait
# that never ends. Generous, because what it separates is "answered" from
# "spinning on a holder that does not exist".
_PROMPT_SECONDS = 1.0
_UNENDING_WAIT = "the claim never came back"
# Long enough that a wait really has to wait, short enough not to slow the
# suite: the assertion is that the wait outlasted it, not how long it took.
_RELEASE_DELAY_SECONDS = 0.05


class _HostRoot(unittest.TestCase):
    """One checkout root per test, with the lock file inside it."""

    def setUp(self) -> None:
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        redirected = patch.object(config, _WORKTREES_ATTR, self.root)
        redirected.start()
        self.addCleanup(redirected.stop)

    def held_elsewhere(self, flags: int) -> TextIO:
        """Take the host's lock through a handle of another process's kind.

        A second open file description on the same file, which `flock` treats
        as independently as it treats another process's -- so this is a live
        claim nothing in this interpreter's own bookkeeping knows about.
        """
        lock_file = host_lock._created()
        self.addCleanup(lock_file.close)
        fcntl.flock(lock_file, flags | fcntl.LOCK_NB)
        self.addCleanup(fcntl.flock, lock_file, fcntl.LOCK_UN)
        return lock_file

    def release_shortly(self, lock_file: TextIO) -> None:
        """Give that claim back from another thread, once a wait is under way.

        Unlocking is idempotent, so the cleanup that also unlocks this handle
        is free to run before or after: `LOCK_UN` on a file this process no
        longer holds is not an error.
        """
        threading.Timer(
            _RELEASE_DELAY_SECONDS,
            fcntl.flock,
            args=(lock_file, fcntl.LOCK_UN),
        ).start()

    def taken_elsewhere(self, flags: int) -> bool:
        """Whether another process could claim this host right now."""
        lock_file = host_lock._created()
        with lock_file:
            granted = host_lock._taken(lock_file, flags)
            if granted:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            return granted

    def claim_answered(self, claim) -> list:
        """Take one claim on a thread, and hand back what it answered.

        On a thread because a lock this file reads as CONTENDED is waited for
        without a deadline: a failure misread as contention would spin here
        forever, and a test that hangs the suite reports nothing. Bounded, the
        same regression fails instead.
        """
        answers: list = []
        answering = threading.Thread(
            target=_recorded_claim, args=(claim, answers), daemon=True,
        )
        answering.start()
        answering.join(timeout=_PROMPT_SECONDS)
        self.assertFalse(answering.is_alive(), _UNENDING_WAIT)
        return answers


def _recorded_claim(claim, answers: list) -> None:
    """Take one claim on this thread and record what it answered.

    A claim answers with itself and a handover with a bare grant, and the
    question either one is being asked is the same: did this process get what
    it asked for.
    """
    with claim() as answered:
        answers.append(getattr(answered, "taken", answered))
