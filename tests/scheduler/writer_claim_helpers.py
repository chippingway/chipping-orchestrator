# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Writer claims another process takes through the claim owner alone.

The other process runs the program below over the shared namespace
`tests/support/writer_claim_processes.py` sets up, keyed by the repository id
it is handed, and asks nothing of a client or a dispatch seam: what these
tests hold up is the claim itself.
"""
from __future__ import annotations

import itertools
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import DEFAULT

from orchestrator.scheduler import writer_claims
from tests.support import writer_claim_processes as _processes

# The late cycle a holder in `retire` mode says it is retiring, and the one a
# holder in `cut-note` mode fails to: two digits, so a note cut after the first
# would name another cycle.
RETIRED_CYCLE = 4
CUT_CYCLE = 43

# What a holder in `paused` mode reports once it has the lock.
LOCKED = "locked"

# The holder program. It reports what the claim answered, then does what its
# mode says with it: holds it until told to let go, notes on it that the hold
# is retiring a late cycle and then holds it, raises out of it and stays
# alive, or lets it go at once. The `cut-` modes run out of room on the claim
# file one byte into a record -- the note of a retirement, which it then holds
# behind, the stamp of its release, or the signature an acquisition writes
# into the file it has just emptied, which refuses it the claim -- as a
# file-size limit makes a write land short, and give the room back once that
# write is over. A holder in `paused` mode stops the moment it has the lock,
# before it has read or emptied the file, and goes on once told to.
_HOLDER = f"""
import fcntl
import resource
import signal
import sys

from orchestrator.scheduler import claim_notes, writer_claims

repo_id, number, mode = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
unlimited = resource.getrlimit(resource.RLIMIT_FSIZE)
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)


def capped(record, size=None):
    if size is None:
        size = writer_claims.claim_path(repo_id, number).stat().st_size
    resource.setrlimit(resource.RLIMIT_FSIZE, (size + len(record) + 1, unlimited[1]))


if mode == "cut-signature":
    capped("", size=0)
if mode == "paused":
    locking = fcntl.flock

    def paused(claim_file, flags):
        locking(claim_file, flags)
        if flags & fcntl.LOCK_EX:
            print("{LOCKED}", flush=True)
            sys.stdin.readline()

    fcntl.flock = paused
try:
    with writer_claims.issue_writer(repo_id, number) as held:
        if mode == "retire":
            claim_notes.note_retirement(repo_id, number, {RETIRED_CYCLE})
        if mode == "cut-note":
            capped(claim_notes._RETIRING)
            claim_notes.note_retirement(repo_id, number, {CUT_CYCLE})
            resource.setrlimit(resource.RLIMIT_FSIZE, unlimited)
        print("held" if held else "refused", flush=True)
        if mode == "raise":
            raise RuntimeError("the body failed")
        if mode in ("hold", "retire", "cut-note"):
            sys.stdin.readline()
        if mode == "cut-release":
            capped(writer_claims.RELEASED_LINE)
except RuntimeError:
    print("released", flush=True)
    sys.stdin.readline()
resource.setrlimit(resource.RLIMIT_FSIZE, unlimited)
"""


class SharedNamespaceCase(_processes.SharedNamespaceCase):
    """A checkout root of this test's own, claimed in by real processes."""

    def other_process(self, repo_id: int, issue_number: int, mode: str) -> _processes.OtherProcess:
        return self.run_elsewhere(_HOLDER, repo_id, issue_number, mode)

    def granted_here(self, repo_id: int, issue_number: int) -> bool:
        """Whether this process could claim the key right now."""
        with writer_claims.issue_writer(repo_id, issue_number) as held:
            return held

    def held_and_let_go(self, repo_id: int, issue_number: int) -> None:
        """Another process takes the key, lets go at once, and exits."""
        holder = self.other_process(repo_id, issue_number, "try")
        self.assertEqual(holder.said(), _processes.HELD)
        self.assertEqual(holder.exited(), 0)

    def held_first(self, repo_id: int, issue_number: int) -> Iterator[object]:
        """What a patched `fcntl.flock` answers, the first time only once others have held the key.

        So the file this process has opened -- and created, where it was
        missing -- is taken by another process that lets go, then by a third
        whose signature a file-size limit cuts short, leaving it empty,
        before this process's own request for the lock goes through. Every
        answer is `DEFAULT`, which is the real call.
        """
        self.held_and_let_go(repo_id, issue_number)
        emptied = self.other_process(repo_id, issue_number, "cut-signature")
        self.assertEqual(emptied.said(), _processes.REFUSED)
        self.assertEqual(emptied.exited(), 0)
        self.assertEqual(writer_claims.claim_path(repo_id, issue_number).read_text(encoding="utf-8"), "")
        yield from itertools.repeat(DEFAULT)


def descriptors_on(path: Path) -> int:
    """How many of this process's descriptors are open on `path`."""
    descriptor_root = Path("/proc/self/fd")
    target = str(path)
    count = 0
    for descriptor in descriptor_root.iterdir():
        try:
            opened = os.readlink(descriptor)
        except OSError:
            continue
        count += opened == target
    return count
