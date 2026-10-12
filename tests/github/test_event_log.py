# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The audit log read back with every rotated copy logrotate leaves beside it, plain or compressed, and nothing else.

A rotation running between the listing of the copies and their read is read
again over, so the event it moved is still found; one that never settles is
no answer, never an absence.
"""
from __future__ import annotations

import bz2
import gzip
import json
import lzma
import tempfile
import unittest
from functools import partial
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github import event_log as _event_log, events as _events

_LOG_NAME = "events.jsonl"
_REBASED = "base_rebased"
_FILED = MappingProxyType({"event": _REBASED, "issue": 949, "sha": "c1c2c3c4c5c6c7c8c9c0c1c2c3c4c5c6c7c8c9c0"})
_SPAWNED = MappingProxyType({"event": "agent_spawn", "issue": 949})
# How long the header gzip writes ahead of the compressed body is, with no name.
_GZIP_HEADER = 10
# The first byte of a final deflate block of the type deflate reserves, which no decoder reads.
_RESERVED_BLOCK = 7
# The member a test record names the copy it was written to in.
_COPY = "copy"
# Each suffix a compressed copy's name ends in, which the log's own name may end in too.
_COMPRESSED_SUFFIXES = (".gz", ".bz2", ".xz")
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


def _compressed(record) -> bytes:
    """A gzip copy of the log carrying `record` alone, as logrotate's `compress` leaves one."""
    return gzip.compress(_line(record).encode(), mtime=0)


class _Rotations:
    """How logrotate rotates the log at `event_path`, each one rotation of it."""

    def renames(self, event_path: Path, *, aside: str = ".1") -> None:
        """Rotate as the default `create` does: the log renamed to its copy named `aside` it, and created afresh."""
        event_path.rename(event_path.with_name(f"{_LOG_NAME}{aside}"))
        event_path.touch()

    def renames_aside(self, event_path: Path) -> None:
        """Rotate the log to a copy under a name no rotation used before, as `dateext` does once a day."""
        rotated = len(list(event_path.parent.iterdir()))
        self.renames(event_path, aside=f"-{rotated}")

    def copies_and_truncates(self, event_path: Path) -> None:
        """Rotate as `copytruncate` with `dateext` does: the log copied beside itself, then truncated."""
        event_path.with_name(f"{_LOG_NAME}-20261012").write_bytes(event_path.read_bytes())
        event_path.write_bytes(b"")

    def compresses_the_copy(self, event_path: Path) -> None:
        """Compress the log's first copy as a delayed `compress` does: the gzip copy written, the plain one removed."""
        plain = event_path.with_name(f"{_LOG_NAME}.1")
        plain.with_name(f"{_LOG_NAME}.1.gz").write_bytes(gzip.compress(plain.read_bytes()))
        plain.unlink()


_ROTATE = _Rotations()

# Each rotation run between the listing and the read: what it is, a rotation
# made before the lookup, if any, and the one made under it.
_ROTATIONS = (
    ("renamed and created afresh", None, _ROTATE.renames),
    ("copied and truncated", None, _ROTATE.copies_and_truncates),
    ("its first copy compressed", _ROTATE.renames, _ROTATE.compresses_the_copy),
)


class _Damages:
    """How a gzip copy beside the log can fail to read, each written at `copy` over `record`."""

    def cuts_short(self, copy: Path, record) -> None:
        """Write the copy cut short, as one still being written is."""
        copy.write_bytes(_compressed(record)[:-8])

    def damages_the_body(self, copy: Path, record) -> None:
        """Write the copy with its compressed body damaged: its first block given a type deflate reserves."""
        damaged = bytearray(_compressed(record))
        damaged[_GZIP_HEADER] = _RESERVED_BLOCK
        copy.write_bytes(damaged)

    def dangles(self, copy: Path, _record) -> None:
        """Name the copy as a link whose target is gone."""
        copy.symlink_to(copy.with_name("renamed"))


_DAMAGE = _Damages()

# Each way a copy fails to read: what it is, and what writes it.
_DAMAGED = (
    ("cut short", _DAMAGE.cuts_short),
    ("a damaged body", _DAMAGE.damages_the_body),
    ("a dangling link", _DAMAGE.dangles),
)


class _RotatesAhead:
    """A copy's read, with `rotates` run on the log ahead of the first `times` of them: after the listing."""

    def __init__(self, reads, rotates, event_path: Path, times: int) -> None:
        self._reads = reads
        self._rotates = partial(rotates, event_path)
        self._left = times

    def __call__(self, *read):
        """Rotate the log while any rotation is left, then read the copy `read` names as it now stands."""
        if self._left:
            self._left -= 1
            self._rotates()
        return self._reads(*read)


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
                rotated.write(_line({**_FILED, _COPY: name}))
        (self.directory / f"other-{_LOG_NAME}").write_text(_line({**_FILED, _COPY: "other"}))
        (self.directory / f"{_LOG_NAME}.d").mkdir()

        logged = _event_log.logged(self.event_path, _REBASED)

        expected = [rotation[0] for rotation in _ROTATED_COPIES]
        self.assertCountEqual([record[_COPY] for record in logged], expected)

    def test_a_copy_that_will_not_read_is_no_answer(self) -> None:
        # A compressed copy cut short, as one still being written is, one
        # whose compressed body is damaged, and a copy that stays listed and
        # cannot be looked at -- a dangling link -- each say nothing either
        # way, though the log beside it reads; once the copy is put right, the
        # log and the copy answer again.
        self.event_path.write_text(_line(_SPAWNED))
        copy = self.event_path.with_name(f"{_LOG_NAME}.1.gz")
        for name, damages in _DAMAGED:
            with self.subTest(copy=name):
                copy.unlink(missing_ok=True)
                damages(copy, _FILED)
                with self.assertLogs(_event_log.log, "WARNING"):
                    unread = _event_log.logged(self.event_path, _REBASED)
                copy.unlink()
                copy.write_bytes(_compressed(_FILED))
                answered = _event_log.logged(self.event_path, _REBASED)

                self.assertEqual((unread, answered), (None, [_FILED]))

    def test_a_log_named_as_compressed_reads_plain(self) -> None:
        # The log's own name ends as a compressed copy's would; its writer
        # appends plain JSON lines all the same, so it is read plain, and a
        # copy rotated off it is still read as its own suffix says.
        for suffix in _COMPRESSED_SUFFIXES:
            with self.subTest(suffix=suffix):
                event_path = self.directory / f"{_LOG_NAME}{suffix}"
                _events.append_event_line(event_path, {**_FILED, _COPY: "log"})
                rotated = event_path.with_name(f"{event_path.name}.1.gz")
                rotated.write_bytes(_compressed({**_FILED, _COPY: "rotated"}))

                logged = _event_log.logged(event_path, _REBASED)

                self.assertCountEqual([record[_COPY] for record in logged], ["log", "rotated"])

    def test_no_copy_is_an_absence(self) -> None:
        # A directory never made, and one holding no log, carry nothing filed.
        unmade = self.directory / "unmade" / _LOG_NAME
        found = (_event_log.logged(unmade, _REBASED), _event_log.logged(self.event_path, _REBASED))
        self.assertEqual(found, ([], []))


class ConcurrentRotationTest(unittest.TestCase):
    """A rotation run between the listing and the read is read again over; one that never settles is no answer."""

    def setUp(self) -> None:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.event_path = directory / _LOG_NAME
        self.event_path.write_text(_line(_FILED))

    def test_a_rotation_under_the_read_is_read_again(self) -> None:
        # The log is read empty behind the rotation, and the copy now carrying
        # the event is one the listing never named, or one gone by its open:
        # the copies are listed again behind the read, and read again over the
        # new listing, which finds the event once.
        for name, ahead, under in _ROTATIONS:
            with self.subTest(rotation=name):
                self.setUp()
                if ahead is not None:
                    ahead(self.event_path)
                with self._rotating(under, times=1):
                    logged = self._logged()

                self.assertEqual((logged, self.event_path.read_bytes()), ([_FILED], b""))

    def test_an_unsettled_rotation_is_no_answer(self) -> None:
        # The log rotated aside ahead of every read: no reading held still,
        # so the answer is no answer rather than an absence the finish would
        # file over, though every copy still carries what it was rotated with.
        with self._rotating(_ROTATE.renames_aside, times=100), self.assertLogs(_event_log.log, "WARNING"):
            logged = self._logged()

        self.assertIsNone(logged)
        self.assertEqual(self._logged(), [_FILED])

    def _logged(self) -> list | None:
        """Every `base_rebased` record the log and its copies carry, as the reader answers."""
        return _event_log.logged(self.event_path, _REBASED)

    def _rotating(self, rotates, *, times: int):
        """The reader with `rotates` run on the log ahead of the first `times` reads of a copy."""
        rotating = _RotatesAhead(_event_log._named_in, rotates, self.event_path, times)
        return patch.object(_event_log, "_named_in", rotating)


if __name__ == "__main__":
    unittest.main()
