# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the opt-in trajectory sink observes of a Codex launch: where its native session log lives, and when it began.

Codex keeps a run's requests in its own session log rather than on stdout, and a resumed session's log already holds
every earlier invocation's lines, so the exit can place this invocation in it only by what was true at the launch. Just
before the tracked spawn launches a Codex process it asks `observed_launch` for that: the `CODEX_HOME` the process's
effective environment -- the very one the Codex backend builds, an override in the run's options included -- points
the CLI at, or Codex's own `~/.codex` where it names none, and the moment, to the millisecond the CLI stamps its lines
to. The observation reads nothing on disk and changes nothing the CLI is launched with; with the trajectory sink off,
or for another backend, it is not made at all, and one that fails costs the launch nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.observability.analytics import config as analytics_config, sink
from orchestrator.observability.usage import protocol

_MICROSECONDS_PER_MILLISECOND = 1_000


@dataclass(frozen=True)
class LaunchObservation:
    """What the trajectory sink observed of one Codex process just before it was launched.

    `codex_home` is the directory the effective launch environment points the CLI's state at, and `launched_at` the
    moment of the launch in UTC, cut to the millisecond the CLI stamps its own lines to, so a line the process wrote
    in that same millisecond is never placed before it.
    """

    codex_home: Path
    launched_at: datetime


def codex_home(environ: Mapping[str, str], cwd: Path) -> Path:
    """The `CODEX_HOME` an environment points the CLI at: its own, against `cwd` where relative, else `~/.codex`."""
    configured = environ.get("CODEX_HOME")
    if configured:
        return Path(cwd, configured)
    home = environ.get("HOME")
    return Path(home, ".codex") if home else Path.home() / ".codex"


def _observed(cwd: Path, extra_env: dict[str, str] | None) -> LaunchObservation:
    """The observation itself: the home the launch environment names, and the moment, cut to the millisecond.

    The environment is the one the Codex backend launches the process with, built by the same owner from the same
    options. That owner is named inside the call, so the trajectory owners cost an importer nothing of it.
    """
    from orchestrator.agents import environment

    home = codex_home(environment.agent_env(extra_env), cwd)
    now = datetime.now(UTC)
    cut = now.microsecond - now.microsecond % _MICROSECONDS_PER_MILLISECOND
    return LaunchObservation(home, now.replace(microsecond=cut))


def observed_launch(
    backend: str,
    cwd: Path,
    extra_env: dict[str, str] | None,
) -> LaunchObservation | None:
    """What a Codex launch looks like to the trajectory sink, observed only while it is on; None otherwise."""
    if backend != protocol.CODEX or analytics_config.live_settings().trajectory_log_path is None:
        return None
    try:
        return _observed(cwd, extra_env)
    except Exception:  # noqa: BLE001 - an observation that fails costs the launch nothing
        sink.log.exception("analytics: codex launch observation failed; its request usage will be unavailable")
        return None
