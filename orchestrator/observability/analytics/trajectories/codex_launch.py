# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the opt-in trajectory sink observes of a Codex launch: where its native session log lives, what that log held,
and when the launch was.

Codex keeps a run's requests in its own session log rather than on stdout, and a resumed session's log already holds
every earlier invocation's lines, appended to the same file with nothing marking where one process's lines end. The
exit can place this invocation in it only by what was true at the launch, so just before the tracked spawn launches a
Codex process it asks `observed_launch` for that: the `CODEX_HOME` the process's effective environment -- the very one
the Codex backend builds, an override in the run's options included -- points the CLI at, or Codex's own `~/.codex`
where it names none; the moment, as precisely as the clock gives it; and, for a resume, the log the session already has
(`PriorLog`): which file it is, how many bytes it held, and how many whole lines, since everything the process appends
lies past them. The log is looked up the way the exit looks it up, by the session the run resumes, and its lines are
counted within the read bound; a log whose last line was unfinished leaves no count, since what the process appends
would join that line. Nothing the CLI is launched with changes; with the trajectory sink off, or for another backend,
nothing is observed and nothing read, and an observation that fails costs the launch nothing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from orchestrator.observability.analytics import config as analytics_config, sink
from orchestrator.observability.analytics.trajectories.codex_sessions import discovered_log
from orchestrator.observability.usage import protocol, request_scan

_NEWLINE = b"\n"
_COUNT_CHUNK = 1_048_576


@dataclass(frozen=True)
class PriorLog:
    """A resumed session's log as it stood at the launch: the file it was, its bytes, and its whole lines.

    `lines` counts the lines within the read bound -- one more where the log ran past it, so no line the exit reads is
    taken for the invocation's -- and is None where the last line was unfinished, which leaves no count.
    """

    device: int
    inode: int
    size: int
    lines: int | None

    def holds(self, stream: IO[bytes]) -> bool:
        """Whether a log opened at the exit is this one, grown or not, not another file or a shrunk one."""
        current = os.fstat(stream.fileno())
        same_file = (current.st_dev, current.st_ino) == (self.device, self.inode)
        return same_file and current.st_size >= self.size


@dataclass(frozen=True)
class LaunchObservation:
    """What the trajectory sink observed of one Codex process just before it was launched.

    `codex_home` is the directory the effective launch environment points the CLI's state at, `launched_at` the moment
    of the launch in UTC, as precisely as the clock gives it, and `prior` the log a resumed session already had -- None
    for a fresh run, and for a resume whose log the launch could not find or read.
    """

    codex_home: Path
    launched_at: datetime
    prior: PriorLog | None = None


def codex_home(environ: Mapping[str, str], cwd: Path) -> Path:
    """The `CODEX_HOME` an environment points the CLI at: its own, against `cwd` where relative, else `~/.codex`."""
    configured = environ.get("CODEX_HOME")
    if configured:
        return Path(cwd, configured)
    home = environ.get("HOME")
    return Path(home, ".codex") if home else Path.home() / ".codex"


def _whole_lines(stream: IO[bytes], size: int, bound: int) -> int | None:
    """The whole lines of a log `size` bytes long, counted within `bound` bytes; None where its last is unfinished."""
    remaining = min(size, bound)
    lines = 0
    last = _NEWLINE
    while remaining > 0:
        chunk = stream.read(min(_COUNT_CHUNK, remaining))
        if not chunk:
            break
        lines += chunk.count(_NEWLINE)
        last = chunk[-1:]
        remaining -= len(chunk)
    if size > bound:
        return lines + 1
    return lines if last == _NEWLINE else None


def prior_log(home: Path, session_id: str) -> PriorLog | None:
    """The log a resumed session already has under `home`, as it stands; None where none is found or can be read."""
    limits = request_scan.current_limits()
    found = discovered_log(home, session_id, limits)
    if isinstance(found, str):
        return None
    try:
        with found.open("rb") as stream:
            current = os.fstat(stream.fileno())
            lines = _whole_lines(stream, current.st_size, limits.log_bytes)
    except OSError:
        return None
    return PriorLog(current.st_dev, current.st_ino, current.st_size, lines)


def _observed(
    cwd: Path,
    extra_env: dict[str, str] | None,
    resume_session_id: str | None,
) -> LaunchObservation:
    """The observation itself: the home the launch environment names, the log a resume already has, and the moment.

    The environment is the one the Codex backend launches the process with, built by the same owner from the same
    options. That owner is named inside the call, so the trajectory owners cost an importer nothing of it.
    """
    from orchestrator.agents import environment

    home = codex_home(environment.agent_env(extra_env), cwd)
    prior = None if resume_session_id is None else prior_log(home, resume_session_id)
    return LaunchObservation(home, datetime.now(UTC), prior)


def observed_launch(
    backend: str,
    cwd: Path,
    extra_env: dict[str, str] | None,
    resume_session_id: str | None,
) -> LaunchObservation | None:
    """What a Codex launch looks like to the trajectory sink, observed only while it is on; None otherwise."""
    if backend != protocol.CODEX or analytics_config.live_settings().trajectory_log_path is None:
        return None
    try:
        return _observed(cwd, extra_env, resume_session_id)
    except Exception:  # noqa: BLE001 - an observation that fails costs the launch nothing
        sink.log.exception("analytics: codex launch observation failed; its request usage will be unavailable")
        return None
