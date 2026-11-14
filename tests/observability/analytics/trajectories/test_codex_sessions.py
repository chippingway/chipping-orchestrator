# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A Codex run's native session log looked up and read off a real `CODEX_HOME`, within every lookup and read bound."""

import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.observability.analytics.recording.models import AgentExitContext
from orchestrator.observability.analytics.trajectories import codex_sessions
from orchestrator.observability.usage import request_coverage as coverage, request_scan
from tests.observability.analytics.trajectories import codex_session_support as support
from tests.observability.usage import usage_codex_native_capture as capture

_OTHER_LOG = f"rollout-2026-11-13T09-00-00-{support.OTHER_SESSION}.jsonl"
_SECOND_LOG = f"rollout-x-{capture.SESSION_ID}.jsonl"
_NEWER_DAY = ("2026", "11", "13")
_NEWEST_DAY = ("2026", "11", "14")
_OLDER_DAY = ("2026", "10", "01")
_FRESH_TEXT = capture.log_text(capture.FRESH.end)
_FRESH_LINES = capture.log_lines(capture.FRESH.end)
# The fresh invocation's last request, cut halfway as a process killed mid-write leaves it.
_CUT_LINE = _FRESH_LINES[-2][:100]
# The bytes of the fresh invocation's first five lines, each with its newline.
_FIVE_LINES = len(capture.log_text(5).encode())
# A line bound the session_meta and the longer lines run past, and the lines it leaves to read.
_LINE_BOUND = 300
_SHORT = tuple(len(text) < _LINE_BOUND for text in _FRESH_LINES)
_SHORT_LINES = tuple(position for position, short in enumerate(_SHORT) if short)
_OVERSIZE_COUNT = capture.FRESH.end - len(_SHORT_LINES)
_LISTABLE = 0o700
# A byte bound far shorter than one line of the log, and a line far longer than it.
_BYTE_BOUND = 16
_LONG_LINE = b"".join((b'{"arbitrary":"', b"x" * 1000, b'"}\n'))
# A line kept until it crosses the byte bound, and one too long to keep, skipped through until it does.
_BUDGET_CASES = (("crossing line", request_scan.MAX_LINE_CHARS), ("skipped line", _BYTE_BOUND // 2))
_NOT_ROOT = os.geteuid() != 0
_SCAN_LIMIT = MappingProxyType({coverage.SCAN_LIMIT: 1})
# Names only near the session's own: its id run on from another word, kept in a backup, and with no rollout prefix.
_NEAR_LOGS = (
    f"rollout-2026-11-12T20-54-56-x{capture.SESSION_ID}.jsonl",
    f"{capture.LOG_NAME}.bak",
    f"{capture.SESSION_ID}.jsonl",
)
# A log's day directory, as its year, month, and day, beside its file name.
_DatedLog = tuple[tuple[str, ...], str]
_OWN_LOG = (capture.DAY, capture.LOG_NAME)
# Logs no lookup adopts, each under the day it is written in: none at all, only another session's or names near its
# own, and two of its name, in one day or under two dates.
_NO_ONE_LOG = (
    ("no sessions directory", (), coverage.NATIVE_LOG_MISSING),
    ("only another session's", ((capture.DAY, _OTHER_LOG),), coverage.NATIVE_LOG_MISSING),
    ("only names near its own", tuple((capture.DAY, name) for name in _NEAR_LOGS), coverage.NATIVE_LOG_MISSING),
    ("two of its name", (_OWN_LOG, (capture.DAY, _SECOND_LOG)), coverage.NATIVE_IDENTITY_UNPROVEN),
    ("two under two dates", (_OWN_LOG, (_NEWER_DAY, capture.LOG_NAME)), coverage.NATIVE_IDENTITY_UNPROVEN),
)
# The sessions, year, month, and day directories are four listings, and the walk examines five entries.
_LOOKUP_BOUNDS = (("MAX_SESSION_DIRECTORIES", 3), ("MAX_SESSION_ENTRIES", 4))
_READ_BOUNDS = (
    ("bytes", ("MAX_LOG_BYTES", _FIVE_LINES), (tuple(range(5)), _SCAN_LIMIT)),
    ("lines", ("MAX_EVENTS", 3), (tuple(range(3)), _SCAN_LIMIT)),
    ("line size", ("MAX_LINE_CHARS", _LINE_BOUND), (_SHORT_LINES, {coverage.OVERSIZE_LINES: _OVERSIZE_COUNT})),
)
_UNCOUNTED = capture.RESUMED._replace(start=None)
# Fewer lines than the resumed invocation's launch counted.
_SHORTER = capture.RESUMED.start // 2
_RESUMED_TEXT = capture.log_text(capture.RESUMED.end)
_NO_PROOF = (
    ("no session", {"session_id": None}, coverage.NO_SESSION_IDENTITY),
    ("an empty session", {"session_id": ""}, coverage.NO_SESSION_IDENTITY),
    ("no launch", {"observed": False}, coverage.NO_LAUNCH_OBSERVATION),
    ("a resume its launch counted nothing for", {"invocation": _UNCOUNTED}, coverage.INVOCATION_UNATTRIBUTED),
)


def _reasons(context: AgentExitContext) -> dict[str, int]:
    """Why the collection of `context`'s exit is short of its invocation's requests, as its coverage says."""
    return dict(support.collected(context).coverage.reasons)


class _FailingLog(BytesIO):
    """A log that fails to read past its first line."""

    def readline(self, size: int = -1) -> bytes:
        if self.tell():
            raise OSError("read failed")
        return super().readline(size)


class _CountedLog(BytesIO):
    """A log that keeps how many bytes were read off it by the time it was closed."""

    def __init__(self, initial: bytes) -> None:
        super().__init__(initial)
        self.bytes_read = 0

    def close(self) -> None:
        self.bytes_read = self.tell()
        super().close()


class _HomeTest(unittest.TestCase):
    """A test with a fresh, empty `CODEX_HOME` of its own."""

    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory()))


class SessionLookupTest(_HomeTest):
    """The log is looked up by the returned session alone, newest date first, and only a file of its exact name."""

    def test_a_log_under_an_older_date(self) -> None:
        # A resumed session's log stays under the date it began; other sessions' logs, newer and older, and
        # directories no date names, are passed over.
        support.write_log(self.home, "", day=_NEWER_DAY, name=_OTHER_LOG)
        support.write_log(self.home, "", day=_OLDER_DAY, name=_OTHER_LOG)
        expected = support.write_log(self.home, _FRESH_TEXT)
        support.day_directory(self.home, ("archive",))
        self.assertEqual(support.discovered(self.home), expected)

    def test_only_a_regular_file_of_its_name(self) -> None:
        # A link or a directory named as the log, on a newer date, is no log; the regular file under its own date is.
        expected = support.write_log(self.home, _FRESH_TEXT, day=_OLDER_DAY)
        (support.day_directory(self.home, _NEWER_DAY) / capture.LOG_NAME).symlink_to(expected)
        (support.day_directory(self.home, _NEWEST_DAY) / capture.LOG_NAME).mkdir()
        self.assertEqual(support.discovered(self.home), expected)

    def test_no_one_log(self) -> None:
        for name, logs, reason in _NO_ONE_LOG:
            with self.subTest(name):
                self.assertEqual(support.discovered(self._home_holding(logs)), reason)

    @unittest.skipUnless(_NOT_ROOT, "root reads any directory")
    def test_an_unlistable_sessions_directory(self) -> None:
        support.write_log(self.home, _FRESH_TEXT)
        sessions = self.home / support.SESSIONS
        sessions.chmod(0)
        self.addCleanup(sessions.chmod, _LISTABLE)
        self.assertEqual(support.discovered(self.home), coverage.NATIVE_LOG_UNREADABLE)

    def test_lookup_bounds(self) -> None:
        support.write_log(self.home, _FRESH_TEXT)
        support.write_log(self.home, "", name=_OTHER_LOG)
        for bound in _LOOKUP_BOUNDS:
            with self.subTest(bound[0]), patch.object(request_scan, *bound):
                self.assertEqual(support.discovered(self.home), coverage.DISCOVERY_LIMIT)

    def _home_holding(self, logs: tuple[_DatedLog, ...]) -> Path:
        """A `CODEX_HOME` of its own holding an empty file of each name, under the day it is paired with."""
        home = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for day, log_name in logs:
            support.write_log(home, "", day=day, name=log_name)
        return home


class SessionReadTest(_HomeTest):
    """The log is read a line at a time within its byte, line, and line-size bounds, each bound reached a gap."""

    def test_the_log_is_read_whole(self) -> None:
        support.write_log(self.home, _FRESH_TEXT)
        positions, gaps = support.read(self.home)
        self.assertEqual(positions, list(range(capture.FRESH.end)))
        self.assertEqual(gaps, {})

    def test_a_read_failing_partway(self) -> None:
        failing = _FailingLog(_FRESH_TEXT.encode())
        support.write_log(self.home, "")
        with patch.object(Path, "open", return_value=failing):
            read = support.read(self.home)
        self.assertEqual(read, ([0], {coverage.NATIVE_READ_INTERRUPTED: 1}))
        self.assertTrue(failing.closed)

    def test_a_resume_reads_the_file_it_counted(self) -> None:
        # The resumed run's own lines are the ones past the count; another file put under its name since, or the
        # counted one cut shorter, holds none the count places.
        path = support.write_log(self.home, _RESUMED_TEXT)
        context = support.exit_context(self.home, capture.RESUMED)
        usage = support.collected(context)
        self.assertEqual([observation.position for observation in usage.observations], [32])
        replacement = path.with_name("replacement")
        replacement.write_text(_RESUMED_TEXT, encoding="utf-8")
        replacement.replace(path)
        self.assertEqual(_reasons(context), {coverage.INVOCATION_UNATTRIBUTED: 1})
        shrunk = support.exit_context(self.home, capture.RESUMED)
        path.write_text(capture.log_text(_SHORTER), encoding="utf-8")
        self.assertEqual(_reasons(shrunk), {coverage.INVOCATION_UNATTRIBUTED: 1})

    def test_a_log_under_two_dates(self) -> None:
        # A copy of the log under another date leaves no one log, so the exit attributes nothing from either.
        for day in (capture.DAY, _NEWER_DAY):
            support.write_log(self.home, _FRESH_TEXT, day=day)
        usage = support.collected(support.exit_context(self.home))
        self.assertEqual(dict(usage.coverage.reasons), {coverage.NATIVE_IDENTITY_UNPROVEN: 1})
        self.assertEqual(usage.observations, ())

    def test_an_unfinished_last_line(self) -> None:
        # A log whose last line the process never finished writing reads up to it, the cut line a malformed one.
        support.write_log(self.home, _FRESH_TEXT + _CUT_LINE)
        usage = support.collected(support.exit_context(self.home))
        self.assertEqual(dict(usage.coverage.reasons), {coverage.MALFORMED_LINES: 1})
        self.assertEqual(len(usage.observations), 3)

    def test_nothing_is_looked_up_without_proof(self) -> None:
        # A run that returned no session, or whose launch was not observed, is looked up nowhere.
        for name, options, reason in _NO_PROOF:
            with self.subTest(name), patch.object(codex_sessions.os, "scandir") as scandir:
                context = support.exit_context(self.home, **options)
                self.assertEqual(_reasons(context), {reason: 1})
                scandir.assert_not_called()

    @unittest.skipUnless(_NOT_ROOT, "root reads any file")
    def test_an_unopenable_log(self) -> None:
        support.write_log(self.home, _FRESH_TEXT).chmod(0)
        context = support.exit_context(self.home)
        self.assertEqual(_reasons(context), {coverage.NATIVE_LOG_UNREADABLE: 1})


class SessionReadBoundTest(_HomeTest):
    """Each read bound holds, and a bound reached is a gap that says the read stopped short."""

    def test_read_bounds(self) -> None:
        # A line too long to keep is skipped through, and the lines after it keep their place in the log.
        support.write_log(self.home, _FRESH_TEXT)
        for name, bound, expected in _READ_BOUNDS:
            with self.subTest(name), patch.object(request_scan, *bound):
                positions, gaps = support.read(self.home)
                self.assertEqual((tuple(positions), gaps), expected)

    def test_an_overlong_line_past_the_byte_bound(self) -> None:
        # Skipping through a line too long to keep is charged to the byte bound like any other read.
        support.write_log(self.home, _FRESH_TEXT)
        with (
            patch.object(request_scan, "MAX_LINE_CHARS", _LINE_BOUND),
            patch.object(request_scan, "MAX_LOG_BYTES", _LINE_BOUND * 2),
        ):
            read = support.read(self.home)
        self.assertEqual(read, ([], {coverage.OVERSIZE_LINES: 1, coverage.SCAN_LIMIT: 1}))

    def test_no_read_past_the_byte_bound(self) -> None:
        # A line crossing the bound, and one too long to keep skipped through across it, are read no further than the
        # bound and the one byte showing the log goes on past it.
        support.write_log(self.home, "")
        self.enterContext(patch.object(request_scan, "MAX_LOG_BYTES", _BYTE_BOUND))
        for name, line_bound in _BUDGET_CASES:
            counted = _CountedLog(_LONG_LINE)
            with (
                self.subTest(name),
                patch.object(request_scan, "MAX_LINE_CHARS", line_bound),
                patch.object(Path, "open", return_value=counted),
            ):
                gaps = support.read(self.home)[1]
                self.assertEqual(gaps.get(coverage.SCAN_LIMIT), 1)
                self.assertLessEqual(counted.bytes_read, _BYTE_BOUND + 1)


if __name__ == "__main__":
    unittest.main()
