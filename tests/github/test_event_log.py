# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The audit log read back with every rotated copy logrotate leaves beside it, plain or compressed, and nothing else."""
from __future__ import annotations

import bz2
import gzip
import json
import lzma
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from orchestrator.github import event_log as _event_log

_LOG_NAME = "events.jsonl"
_REBASED = "base_rebased"
_FILED = MappingProxyType({"event": _REBASED, "issue": 949, "sha": "c1c2c3c4c5c6c7c8c9c0c1c2c3c4c5c6c7c8c9c0"})
_SPAWNED = MappingProxyType({"event": "agent_spawn", "issue": 949})
# A rotated copy of the log under each name logrotate gives one, and what writes it.
_ROTATED_COPIES = (
    (f"{_LOG_NAME}.1", Path.open),
    (f"{_LOG_NAME}.2.gz", gzip.open),
    (f"{_LOG_NAME}-20261012.bz2", bz2.open),
    (f"{_LOG_NAME}-20261011.xz", lzma.open),
)


def _line(record) -> str:
    """`record` as the sink appends it."""
    return f"{json.dumps(dict(record))}\n"


class RotatedCopiesTest(unittest.TestCase):
    """Every copy beside the log is read with it; a copy that will not read is no answer, and no copy is an absence."""

    def setUp(self) -> None:
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.event_path = self.directory / _LOG_NAME

    def test_every_rotated_copy_is_read(self) -> None:
        # Rotations moved filed events out of the log into copies beside it,
        # plain or compressed: each is read with the log. An entry named
        # otherwise, and a directory named as a copy, are no copies of it.
        self.event_path.write_text(_line(_SPAWNED))
        for name, opens in _ROTATED_COPIES:
            with opens(self.directory / name, "wt", encoding="utf-8") as rotated:
                rotated.write(_line({**_FILED, "copy": name}))
        (self.directory / f"other-{_LOG_NAME}").write_text(_line({**_FILED, "copy": "other"}))
        (self.directory / f"{_LOG_NAME}.d").mkdir()

        logged = _event_log.logged(self.event_path, _REBASED)

        expected = [rotation[0] for rotation in _ROTATED_COPIES]
        self.assertCountEqual([record["copy"] for record in logged], expected)

    def test_a_copy_that_will_not_read_is_no_answer(self) -> None:
        # A compressed copy cut short, as one still being written is, and a
        # copy gone by the time it is opened -- a dangling link stands for one
        # a rotation renamed away -- each say nothing either way; the log read
        # once they are gone still answers.
        self.event_path.write_text(_line(_FILED))
        cut_short = self.event_path.with_name(f"{_LOG_NAME}.1.gz")
        compressed = gzip.compress(self.event_path.read_bytes())
        cut_short.write_bytes(compressed[:-8])
        with self.assertLogs(_event_log.log, "WARNING"):
            truncated = _event_log.logged(self.event_path, _REBASED)
        cut_short.unlink()
        gone = self.event_path.with_name(f"{_LOG_NAME}.2")
        gone.symlink_to(self.directory / "renamed")
        with self.assertLogs(_event_log.log, "WARNING"):
            vanished = _event_log.logged(self.event_path, _REBASED)
        gone.unlink()
        self.assertEqual((truncated, vanished), (None, None))
        self.assertEqual(_event_log.logged(self.event_path, _REBASED), [_FILED])

    def test_no_copy_is_an_absence(self) -> None:
        # A directory never made, and one holding no log, carry nothing filed.
        unmade = self.directory / "unmade" / _LOG_NAME
        found = (_event_log.logged(unmade, _REBASED), _event_log.logged(self.event_path, _REBASED))
        self.assertEqual(found, ([], []))


if __name__ == "__main__":
    unittest.main()
