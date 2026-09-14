# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Open, acquire, and wait for the host artifact lock.

Only contention may be retried: a broken lock cannot establish whether another
process is live. The exclusion owner decides what each claim may do with that
answer and holds the descriptor for the lifetime of the claim.
"""
from __future__ import annotations

import fcntl
import logging
import time
from pathlib import Path
from typing import TextIO

from orchestrator import config

log = logging.getLogger("orchestrator")

# Named for what it guards rather than for who takes it, and hidden, because it
# is this deployment's own bookkeeping sitting in a directory whose other
# entries are checkouts the artifact scan reads. A dotted name is no issue
# number, so the scan passes over it as it does over any other entry it cannot
# derive.
_LOCK_FILE_NAME = ".artifact-maintenance.lock"

# How often a run waiting for the host asks again, and how often it says so
# while it waits. The retry is short because what it is waiting out is one
# candidate's teardown; the notice is spaced so a long wait is visible in the
# log without filling it.
_PRESENCE_RETRY_SECONDS = 0.5

_PRESENCE_NOTICE_SECONDS = 15.0


def _lock_path() -> Path:
    """Where this host's artifact lock lives, read at the call.

    Off the configuration each time rather than bound at import, so a process
    coordinates over the checkout root it was started with.
    """
    return config.WORKTREES_DIR / _LOCK_FILE_NAME


def _created() -> TextIO:
    """Open the host's lock file, creating its directory if it is not there.

    Appending rather than writing, so nothing is truncated under a holder, and
    the file stays empty on purpose: what it carries is the lock, and a line
    written by one of several shared holders would only describe one of them.
    """
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    return lock_path.open("a", encoding="utf-8")


def _opened() -> TextIO | None:
    """The host's lock file, or `None` if this host cannot be coordinated on.

    An unwritable or unreachable checkout root is the whole of that case, and
    what it costs is each caller's to decide: a polling run says so and goes on
    polling, and a maintenance pass that cannot be told whether anything else
    is live does not run at all.
    """
    try:
        return _created()
    except OSError:
        log.warning(
            "could not open the host artifact lock at %s; this process cannot "
            "coordinate with another over these artifacts",
            _lock_path(), exc_info=True,
        )
        return None


def _unusable(error: OSError) -> None:
    """Say that this host's lock is broken rather than held."""
    log.warning(
        "the host artifact lock at %s could not be worked with (%s); this "
        "process cannot coordinate with another over these artifacts",
        _lock_path(), error,
    )


def _taken(lock_file: TextIO, flags: int) -> bool:
    """Whether the lock could be taken right now, without waiting on it.

    `False` is the lock being HELD and nothing else. `BlockingIOError` is
    exactly what a non-blocking request that would have waited raises, so it is
    the one refusal that means another process has this host.

    Every other `OSError` is raised rather than reported as contention. A
    filesystem that does not implement `flock`, a lock table with no room, a
    descriptor that is not one: none of them are a holder, so waiting for one
    to let go would be a wait nothing could ever end, and a pass told they were
    contention would defer forever on a host nobody is on.
    """
    try:
        fcntl.flock(lock_file, flags | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _waited(lock_file: TextIO, flags: int) -> None:
    """Take the lock, however long the pass holding this host takes.

    Unbounded on purpose, and the one place in this file that waits at all. The
    caller is a process about to submit work on a host something else may be
    deleting from, so there is no answer for it other than the lock: giving up
    and going on is what would let a tick and a teardown overlap, and giving up
    and refusing to poll would be a crash loop under a supervisor that restarts
    on exit.

    What makes it finite is on the other side. A pass bounds its own hold and
    releases the host at a candidate boundary, so the wait is one candidate's
    teardown -- and a pass whose process dies holds nothing at all, since the
    kernel drops the lock with the file description.

    Retried rather than blocked in the kernel so the wait stays interruptible:
    a run stalled here still takes a second signal, which is what an operator
    reaches for when they have decided not to wait.

    Only a lock somebody HOLDS is waited for. A lock that does not work raises
    out of here on the first attempt, because there is nothing to wait for and
    the caller has a different answer to give for it.
    """
    if _taken(lock_file, flags):
        return
    waited_since = time.monotonic()
    announced = waited_since
    log.info("waiting for the process holding this host's artifacts")
    while not _taken(lock_file, flags):
        time.sleep(_PRESENCE_RETRY_SECONDS)
        if time.monotonic() - announced >= _PRESENCE_NOTICE_SECONDS:
            announced = time.monotonic()
            log.warning(
                "still waiting for this host's artifacts after %.0fs",
                announced - waited_since,
            )
    log.info(
        "took this host's artifacts after %.0fs",
        time.monotonic() - waited_since,
    )
