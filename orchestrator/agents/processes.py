# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared process registry and the agent runs spawned into it.

Agent runs and the verify runner both spawn children into their own process
group (``start_new_session=True``) and register the group leader here so the
shutdown sweep can reach an in-flight run. Process creation and the shared
shutdown registry live in this owner; tests intercept launches at
``orchestrator.agents.processes.subprocess.Popen``. The drain, the group-liveness
probe, and the signal escalation each teardown here spends belong to the
``process_groups`` owner beside it. Callers import ``terminate_all_running``
directly from this owner.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from orchestrator.agents import models as _agent_models, process_groups as _process_groups

_running_procs: set[subprocess.Popen] = set()
_running_procs_lock = threading.Lock()

_INTERRUPTED_RETURNCODES = frozenset((-signal.SIGTERM, -signal.SIGKILL))


def register_proc(proc: subprocess.Popen) -> None:
    """Register a live process-group leader for shutdown cleanup."""
    with _running_procs_lock:
        _running_procs.add(proc)


def unregister_proc(proc: subprocess.Popen) -> None:
    """Remove a completed process-group leader from the registry."""
    with _running_procs_lock:
        _running_procs.discard(proc)


@contextmanager
def registered(proc: subprocess.Popen) -> Iterator[subprocess.Popen]:
    """Keep a process reachable by the shutdown sweep for one run."""
    register_proc(proc)
    try:
        yield proc
    finally:
        unregister_proc(proc)


def terminate_all_running(grace: float = 5.0) -> int:
    """SIGTERM every registered group, then SIGKILL deadline stragglers."""
    with _running_procs_lock:
        running_procs = list(_running_procs)
    if not running_procs:
        return 0
    for proc in running_procs:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    for proc in running_procs:
        remaining = max(0, deadline - time.monotonic())
        _process_groups.sigkill_unless_group_gone(proc, remaining)
    return len(running_procs)


def run_subprocess(
    command: list[str],
    cwd: Path,
    environ: dict[str, str],
    timeout: int,
) -> _agent_models.SubprocessResult:
    """Run one agent in a registered, independently killable process group."""
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    with registered(proc):
        drained = _process_groups.communicate_bounded(proc, timeout)
        if drained is None:
            _process_groups.terminate_process_group(proc)
            drained = _process_groups.communicate_bounded(proc, 10)
            stdout, stderr = ("", "") if drained is None else drained
            return _agent_models.SubprocessResult(stdout, stderr, -1, True, False)
        stdout, stderr = drained
        interrupted = proc.returncode in _INTERRUPTED_RETURNCODES
        return _agent_models.SubprocessResult(
            stdout,
            stderr,
            proc.returncode,
            False,
            interrupted,
        )
