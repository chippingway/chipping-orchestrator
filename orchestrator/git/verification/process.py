# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One verify command's subprocess lifecycle and its `VerifyCommandOutcome` verdict.

Spawning, group teardown, and bounded draining live beside the classification
that reads their outcome because the verdict depends on how the shell was torn
down: a timeout keeps only what the bounded drain rescued, while a completed
command is judged on its exit code plus the worktree probes. The shell is
started into its own process group and drained through the agent package's
process-group owner, so the shutdown sweep reaches an in-flight verify child
exactly as it reaches an agent run.
"""
from __future__ import annotations

import functools
import os
import signal
import subprocess
from contextlib import suppress
from pathlib import Path

from orchestrator.agents import process_groups as _process_groups
from orchestrator.git.verification import (
    models as _models,
    output as _output,
    probes as _probes,
    status as _worktree_status,
)

_DRAIN_BUDGET_SECONDS = 5


def _combine_output(stdout: str, stderr: str) -> str:
    """Merge a command's captured stdout and stderr into one block.

    stderr is appended after stdout (newline-separated when stdout did not
    end in one) so a failing build with all its diagnostics on stderr
    surfaces in a single block in the park comment.
    """
    combined = stdout or ""
    if stderr:
        if combined and not combined.endswith("\n"):
            combined = f"{combined}\n"
        combined += stderr
    return combined


def _kill_verify_group(proc: subprocess.Popen) -> None:
    """SIGKILL a timed-out verify command's whole process group.

    `start_new_session=True` made `proc.pid` a group leader, so one `killpg`
    tears down the shell AND every descendant (`make -j` workers, pytest-xdist
    forkers, backgrounded `&` subshells) together -- a plain `proc.kill()`
    reaps only the shell and lets a survivor keep mutating the worktree after
    the orchestrator has already posted `verify_timeout` and parked the issue.
    `os.getpgid(proc.pid)` reads that group id; `ProcessLookupError` /
    `PermissionError` cover the race where the shell exited between the
    timeout firing and this call (nothing left to kill).
    """
    with suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def _drain_verify_output(proc: subprocess.Popen) -> tuple[str, str]:
    """Read whatever a killed verify shell buffered, killing harder if it hangs.

    A bounded first drain covers the normal case. If it times out -- a
    descendant that escaped the group via its own `setsid` is still holding
    the pipe fd open -- `proc.kill()` reaps the leader and a second bounded
    drain runs. Returns `("", "")` if both drains time out.
    """
    drained = _process_groups.communicate_bounded(proc, _DRAIN_BUDGET_SECONDS)
    if drained is None:
        proc.kill()
        drained = _process_groups.communicate_bounded(proc, _DRAIN_BUDGET_SECONDS)
    return ("", "") if drained is None else drained


def _spawn_verify_command(
    worktree: Path, command: str, child_env: dict[str, str],
) -> subprocess.Popen:
    """Start one verify shell in the process group used for bounded cleanup."""
    return subprocess.Popen(
        command,
        shell=True,
        cwd=str(worktree),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=child_env,
    )


def _timeout_verify_result(
    proc: subprocess.Popen,
    command: str,
    baselines: tuple[str, str],
) -> _models.VerifyCommandOutcome:
    """Kill a timed-out verify group and retain its bounded partial output.

    Nothing is read after the kill, so the after-readings stay None rather
    than repeating the baseline as though HEAD and its tree had been observed.
    """
    _kill_verify_group(proc)
    partial_output = _combine_output(*_drain_verify_output(proc))
    head_before, tree_before = baselines
    return _models.VerifyCommandOutcome(
        command=command,
        status=_models.VERIFY_STATUS_TIMEOUT,
        exit_code=None,
        output=_output._truncate_verify_output(partial_output),
        head_before=head_before,
        tree_before=tree_before,
    )


def _completed_verify_result(
    proc: subprocess.Popen,
    command: str,
    drained: tuple[str, str],
    worktree: Path,
    baselines: tuple[str, str],
) -> _models.VerifyCommandOutcome:
    """Classify one completed command into its outcome record.

    HEAD and its tree are read after every command, a failing one included, so
    the transcript records what each command left behind. A zero exit passes
    only on a status read that proved the worktree clean, and then only if
    both readings match the baseline.
    """
    head_after = _probes._head_sha(worktree)
    readings = (head_after, _probes._tree_sha(worktree, head_after))
    outcome = functools.partial(
        _models.VerifyCommandOutcome,
        command=command,
        exit_code=proc.returncode,
        output=_output._truncate_verify_output(_combine_output(*drained)),
        head_before=baselines[0],
        head_after=readings[0],
        tree_before=baselines[1],
        tree_after=readings[1],
    )
    if proc.returncode != 0:
        return outcome(status=_models.VERIFY_STATUS_FAILED)
    status = _worktree_status._worktree_status(worktree)
    if not status.is_clean:
        return outcome(status=_models.VERIFY_STATUS_DIRTY, dirty_files=status.paths)
    return outcome(status=_identity_verdict(baselines, readings))


def _identity_verdict(baselines: tuple[str, str], readings: tuple[str, str]) -> str:
    """What a clean zero exit earns from HEAD and its tree, read before and after.

    The tree after is resolved from the HEAD read after, so under an unchanged
    HEAD a different tree is a read that failed or a store that no longer
    answers for the commit -- either way the run cannot say which tree it
    tested, and says so apart from a HEAD that moved.
    """
    (head_before, tree_before), (head_after, tree_after) = baselines, readings
    if head_after != head_before:
        return _models.VERIFY_STATUS_HEAD_CHANGED
    if tree_after != tree_before:
        return _models.VERIFY_STATUS_TREE_CHANGED
    return _models.VERIFY_STATUS_OK
