# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The Codex native session log a tracked run's request usage is read from: its lookup and its bounded read.

Codex keeps the requests of a run in its own session log, not on stdout, so a Codex trajectory record's request usage
is read from that log at exit, inside the request collection's failure boundary, and so only while the opt-in
trajectory sink is on.

The lookup. `native_session` looks the run's session up by the id the run returned, never by a guess: a run that
returned none, or whose launch the sink did not observe (`codex_launch`), is looked up nowhere, and neither is a
resumed run whose launch counted no lines of its log, since nothing would place its own. The log is
`sessions/YYYY/MM/DD/rollout-<time>-<session id>.jsonl` under the observed home, under the date the session began --
an older one where the run resumed it -- so the date directories are walked newest first, matching only a regular file
whose name ends in exactly that id, and the walk is held to `MAX_SESSION_DIRECTORIES` directories and
`MAX_SESSION_ENTRIES` entries. Whether the file found is the session's own is not taken from its name: the collector
proves it from the file. A resumed run's has to be the very file its launch counted, on the same device and inode and
no shorter than it was then; any other is `invocation-unattributed`.

The read. The log is read a line at a time and handed to the collector as it is read, so no more than one line is
held at once, and it is held to `MAX_LOG_BYTES` bytes, `MAX_EVENTS` lines, and `MAX_LINE_CHARS` bytes a line: no read
asks for more than the bytes the bound has left and one more, the one that shows the log goes on past it, a longer
line is skipped through without being kept, and a bound that stops the read, or a read that fails partway, is
recorded for the collector to state. A log that is missing, cannot be listed or opened, or is found twice is no log at
all, and the collection says which.
"""

from __future__ import annotations

import operator
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING

from orchestrator.observability.usage import request_codex, request_coverage as coverage, request_scan
from orchestrator.observability.usage.request_codex_scope import Invocation

if TYPE_CHECKING:
    from orchestrator.observability.analytics.recording.models import AgentExitContext
    from orchestrator.observability.analytics.trajectories.codex_launch import PriorLog

_SESSIONS = "sessions"
_ROLLOUT = "rollout-"
_LOG_SUFFIX = ".jsonl"
_NEWLINE = b"\n"
# A year, a month, and a day directory are named by that many digits.
_DATE_WIDTHS = (4, 2, 2)
_SKIP_CHUNK = 65_536
_BY_NAME = operator.attrgetter("name")


@dataclass
class _Lookup:
    """One bounded walk of a sessions directory, newest date first, for the log of one session."""

    limits: request_scan.CollectionLimits
    suffix: str
    directories: int = 0
    entries: int = 0

    def walk(self, root: Path) -> Path | str:
        """The log the first day directory holding one names, newest first, or why none was adopted.

        Two there are no one log.
        """
        for day in self.days(root):
            candidates = self.found(day)
            if candidates:
                return candidates[0] if len(candidates) == 1 else coverage.NATIVE_IDENTITY_UNPROVEN
        return coverage.NATIVE_LOG_MISSING

    def days(self, root: Path) -> Iterator[Path]:
        """Every day directory under `root`, newest first."""
        years = self.dated(root, _DATE_WIDTHS[0])
        for year in years:
            for month in self.dated(year, _DATE_WIDTHS[1]):
                yield from self.dated(month, _DATE_WIDTHS[2])

    def dated(self, directory: Path, width: int) -> list[Path]:
        """The subdirectories of `directory` named by a date part of `width` digits, newest first."""
        named = [
            entry for entry in self.listed(directory)
            if len(entry.name) == width and entry.name.isdigit()
        ]
        named.sort(key=_BY_NAME, reverse=True)
        return [Path(entry.path) for entry in named if entry.is_dir(follow_symlinks=False)]

    def found(self, day: Path) -> list[Path]:
        """The regular files in `day` named as this session's log."""
        named = [
            entry for entry in self.listed(day)
            if entry.name.startswith(_ROLLOUT) and entry.name.endswith(self.suffix)
        ]
        return [Path(entry.path) for entry in named if entry.is_file(follow_symlinks=False)]

    def listed(self, directory: Path) -> list[os.DirEntry[str]]:
        """Every entry of `directory`, each charged to the walk; past a bound the walk stops."""
        self.directories += 1
        if self.directories > self.limits.session_directories:
            raise _Exhausted
        listed = []
        with os.scandir(directory) as scanned:
            for entry in scanned:
                self.entries += 1
                if self.entries > self.limits.session_entries:
                    raise _Exhausted
                listed.append(entry)
        return listed


class _Exhausted(Exception):
    """A lookup bound stopped the walk before the log was found."""


def discovered_log(home: Path, session_id: str, limits: request_scan.CollectionLimits) -> Path | str:
    """The log of `session_id` under `home`, or the reason none was adopted."""
    lookup = _Lookup(limits, f"-{session_id}{_LOG_SUFFIX}")
    try:
        return lookup.walk(home / _SESSIONS)
    except _Exhausted:
        return coverage.DISCOVERY_LIMIT
    except FileNotFoundError:
        return coverage.NATIVE_LOG_MISSING
    except OSError:
        return coverage.NATIVE_LOG_UNREADABLE


@dataclass
class _LogReader:
    """One open log read a line at a time within the read bounds, every byte read charged to the byte bound."""

    stream: IO[bytes]
    scan: request_scan.EventScan
    consumed: int = 0

    def lines(self) -> Iterator[tuple[int, str]]:
        """Each line within the bounds, numbered by its place in the log; the log is closed after the last.

        A read that fails partway stops there, and says so.
        """
        try:
            yield from self._read()
        except OSError:
            self.scan.gaps[coverage.NATIVE_READ_INTERRUPTED] += 1
        finally:
            self.stream.close()

    def _read(self) -> Iterator[tuple[int, str]]:
        limits = self.scan.limits
        for position in range(limits.events):
            raw = self._next()
            if raw is None:
                return
            if raw:
                yield position, raw.decode(errors="replace")
        self.scan.gaps[coverage.SCAN_LIMIT] += bool(self.stream.read(1))

    def _next(self) -> bytes | None:
        """The next line; empty where it was too long and skipped through, None at the end or past the byte bound."""
        line_bound = self.scan.limits.line_chars
        raw = self.stream.readline(self._capped(line_bound + 1))
        if not raw or not self._charged(len(raw)):
            return None
        if len(raw) <= line_bound or raw.endswith(_NEWLINE):
            return raw
        self.scan.oversize()
        return b"" if self._skipped() else None

    def _skipped(self) -> bool:
        """Read past the rest of an overlong line; False where the byte bound stopped it first."""
        while True:
            chunk = self.stream.readline(self._capped(_SKIP_CHUNK))
            if not self._charged(len(chunk)):
                return False
            if not chunk or chunk.endswith(_NEWLINE):
                return True

    def _capped(self, wanted: int) -> int:
        """`wanted` bytes, or the ones the byte bound has left and one more -- the one showing the log goes on past it.

        No read asks for more, so the whole read never takes more than the bound and that one byte.
        """
        return min(wanted, self.scan.limits.log_bytes - self.consumed + 1)

    def _charged(self, size: int) -> bool:
        """Charge bytes read to the byte bound; False, and a gap, where they take the read past it."""
        self.consumed += size
        if self.consumed <= self.scan.limits.log_bytes:
            return True
        self.scan.gaps[coverage.SCAN_LIMIT] += 1
        return False


def _invocation(context: AgentExitContext) -> Invocation:
    """What the exit knows of the process: the session it returned, whether it resumed it, when it was launched, and
    how many whole lines its log held then."""
    launch = context.launch_observation
    prior = None if launch is None else launch.prior
    return Invocation(
        session_id=context.agent_result.session_id,
        resumed=context.resume_session_id is not None,
        launched_at=None if launch is None else launch.launched_at,
        prior_lines=None if prior is None else prior.lines,
    )


def _opened(
    invocation: Invocation,
    found: Path | str,
    limits: request_scan.CollectionLimits,
    prior: PriorLog | None,
) -> request_codex.NativeSession:
    """The log found, open for its read; or why there is none to read.

    A resumed run's log has to be the very file the launch counted, grown or as it was: another file under its name,
    or one shorter than it was, holds no line the count places.
    """
    if isinstance(found, str):
        return request_codex.NativeSession(invocation, unavailable=found)
    try:
        stream = found.open("rb")
    except OSError:
        return request_codex.NativeSession(invocation, unavailable=coverage.NATIVE_LOG_UNREADABLE)
    if prior is not None and not prior.holds(stream):
        stream.close()
        return request_codex.NativeSession(invocation, unavailable=coverage.INVOCATION_UNATTRIBUTED)
    scan = request_scan.EventScan(limits)
    return request_codex.NativeSession(invocation, _LogReader(stream, scan).lines(), scan)


def native_session(context: AgentExitContext) -> request_codex.NativeSession:
    """The native session log of one finished Codex run, as its collector reads it, or why there is none to read.

    A resumed run whose launch counted no lines of its log has nothing placing its lines, so its log is not read.
    """
    invocation = _invocation(context)
    launch = context.launch_observation
    if invocation.session_id is None:
        return request_codex.NativeSession(invocation, unavailable=coverage.NO_SESSION_IDENTITY)
    if launch is None:
        return request_codex.NativeSession(invocation, unavailable=coverage.NO_LAUNCH_OBSERVATION)
    if invocation.resumed and invocation.prior_lines is None:
        return request_codex.NativeSession(invocation, unavailable=coverage.INVOCATION_UNATTRIBUTED)
    limits = request_scan.current_limits()
    found = discovered_log(launch.codex_home, invocation.session_id, limits)
    return _opened(invocation, found, limits, launch.prior if invocation.resumed else None)
