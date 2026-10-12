# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a host crash leaves of the quota retirement record, and the developer launches it holds.

Only what reached the host's disk survives a crash, so every change to the
record is flushed -- its bytes, and the directory entries that reach it --
before anything a later launch could rest on goes on, and a launch whose
record the disk will not flush is not made.
"""
from __future__ import annotations

import errno
import importlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.workflow.stages.implementing import quota_record as _quota_record
from tests.workflow.stages.implementing import (
    quota_retirement_test_support as quota,
    retry_test_support as support,
)

_flush = os.fsync
# Where this process's open descriptors are named, which says what a flush was of.
_DESCRIPTORS = Path("/proc/self/fd")


class _Disk:
    """The records as a host crash would leave them: only what was flushed survives."""

    def __init__(self) -> None:
        self.durable: dict[Path, bytes] = {}
        self.entries: set[Path] = set()

    def fsync(self, descriptor: int) -> None:
        """Flush `descriptor`, noting what that put on disk: a file's bytes, or a directory's entries."""
        flushed = Path(os.readlink(_DESCRIPTORS / str(descriptor)))
        if flushed.is_dir():
            self.entries.update(flushed.iterdir())
        else:
            self.durable[flushed] = flushed.read_bytes()
        _flush(descriptor)

    def crash(self, record: Path) -> None:
        """Leave `record` as a crash would: its last flushed bytes where its entry was flushed too, else gone."""
        if record in self.entries and record in self.durable:
            record.write_bytes(self.durable[record])
        else:
            record.unlink(missing_ok=True)


@unittest.skipUnless(_DESCRIPTORS.is_dir(), "names a flushed descriptor through /proc")
class QuotaRetirementDurabilityTest(quota.QuotaTicks, unittest.TestCase):
    """The record a launch rests on is on the host's disk before the launch is made."""

    def test_host_crash_keeps_the_owed_retirement(self) -> None:
        # The reply's resume is the issue's first launch on this host, so its
        # arming makes the record. The quota stops it at once, naming no
        # conversation, and the edit landing the retirement goes unanswered;
        # then the host crashes, keeping only what reached its disk. The
        # restarted poller still owes the retirement: it launches nothing while
        # the edit goes unanswered, and once it is answered the reply goes to a
        # fresh conversation.
        github, issue = self._issue(**quota.PARKED)
        quota.reply(github, issue, support.GUIDANCE_REPLY)
        disk = _Disk()
        github.pinned_failures.refused.add(quota.ISSUE)
        with patch.object(os, "fsync", disk.fsync):
            self._tick(github, issue, quota.UNNAMED_QUOTA, has_new_commits=False)
        disk.crash(_quota_record._located(github, issue))
        importlib.reload(_quota_record)

        held = self._replied(github, issue)
        github.pinned_failures.refused.clear()

        self.assertEqual(
            (held.called, quota.launch(self._replied(github, issue))),
            (False, quota.FRESH_LAUNCH),
        )

    def test_unflushed_arming_holds_the_launch(self) -> None:
        # The disk will not flush the record the reply's resume is armed with,
        # so the launch is not made: the reply waits under its park, uncharged
        # and with nothing written, and the arming the disk never confirmed is
        # taken back. Once the disk flushes again the reply resumes the pinned
        # conversation, which nothing stopped.
        github, issue = self._issue(**quota.PARKED)
        quota.reply(github, issue, support.GUIDANCE_REPLY)
        with patch.object(os, "fsync", side_effect=OSError(errno.EIO, "the disk did not flush")):
            held = self._replied(github, issue)

        self.assertEqual(
            (held.called, github.posted_comments),
            (False, []),
        )
        self.assertEqual(
            self._pinned(github, quota.RUNS, *quota.PARK),
            {quota.RUNS: None, **quota.PARK},
        )
        resumed = self._replied(github, issue)
        self.assertEqual(quota.launch(resumed)[0], quota.PINNED_SESSION)


if __name__ == "__main__":
    unittest.main()
