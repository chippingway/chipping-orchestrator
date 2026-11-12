# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A Codex home on disk, laid out as codex-cli 0.167.1 lays out its session logs, and the exits read against it.

The native reader is exercised against real directories: a temporary `CODEX_HOME` whose `sessions/YYYY/MM/DD`
directories hold the captured log under its own name, beside whatever else a test lays out -- other sessions' logs,
older and newer dates, names that only look like the log -- and the exit context a finished Codex run hands the
reader, carrying the launch observed for it.
"""

import os
from collections.abc import Iterable
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.observability.analytics.recording.models import AgentExitContext
from orchestrator.observability.analytics.trajectories import codex_sessions
from orchestrator.observability.analytics.trajectories.codex_launch import LaunchObservation, PriorLog
from orchestrator.observability.usage import request_scan
from tests.observability.usage import usage_codex_native_capture as capture

SESSIONS = "sessions"
OTHER_SESSION = "01a1d00a-0000-7000-8000-000000000000"


def day_directory(home: Path, day: Iterable[str] = capture.DAY) -> Path:
    """The day directory `day` names under `home`'s sessions, created."""
    directory = Path(home, SESSIONS, *day)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_log(
    home: Path,
    text: str,
    *,
    day: Iterable[str] = capture.DAY,
    name: str = capture.LOG_NAME,
) -> Path:
    """Write a log of `text` under `home`, in the day directory `day` names, as `name`."""
    directory = day_directory(home, day)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def discovered(home: Path) -> Path | str:
    """What the lookup finds under `home` for the captured session, within the bounds in force."""
    return codex_sessions.discovered_log(home, capture.SESSION_ID, request_scan.current_limits())


def read(home: Path) -> tuple[list[int], dict[str, int]]:
    """The line numbers the reader hands over for the captured session's fresh exit, and the gaps it recorded."""
    session = codex_sessions.native_session(exit_context(home))
    positions = [position for position, _ in session.lines]
    return positions, dict(+session.scan.gaps)


def launch(home: Path, invocation: capture.Invocation) -> LaunchObservation:
    """The launch of `invocation` as observed against `home`: a resume's log as it held the lines before its own.

    The log under `home` is the captured one as it stood at the exit, so what the launch counted is the file it is,
    holding the invocation's `start` lines; a `start` of None is a launch that counted none.
    """
    if not invocation.resumed:
        return LaunchObservation(home, invocation.launched_at)
    if invocation.start is None:
        return LaunchObservation(home, invocation.launched_at, PriorLog(0, 0, 0, None))
    current = os.stat(Path(home, SESSIONS, *capture.DAY, capture.LOG_NAME))
    size = len(capture.log_text(invocation.start).encode())
    prior = PriorLog(current.st_dev, current.st_ino, size, invocation.start)
    return LaunchObservation(home, invocation.launched_at, prior)


def exit_context(
    home: Path,
    invocation: capture.Invocation = capture.FRESH,
    session_id: str | None = capture.SESSION_ID,
    observed: bool = True,
) -> AgentExitContext:
    """The exit of `invocation` as the trajectory sink reads it, its launch observed against `home` unless not."""
    return AgentExitContext(
        repo="owner/repo",
        issue=1,
        stage="implementing",
        agent_role="developer",
        backend="codex",
        agent_spec="codex",
        resume_session_id=session_id if invocation.resumed else None,
        agent_result=AgentResult(session_id, "", 0, False, invocation.stdout, ""),
        duration_s=float(0),
        review_round=None,
        retry_count=None,
        fallback_model=None,
        prompt=None,
        cwd=Path("/workspace"),
        launch_observation=launch(home, invocation) if observed else None,
    )
