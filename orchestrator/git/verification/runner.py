# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Sequencing owner for a configured `VERIFY_COMMANDS` run.

This is the entry point the validating stage calls: it snapshots HEAD and full
tree identity, builds the stripped child environment once, and runs the commands
in order until one of them earns a refusal. Per-command spawning, teardown, and
classification belong to the `process` owner; this module owns only the
ordering, fail-fast decision, and transcript recording.
"""
from __future__ import annotations

import os
from pathlib import Path

from orchestrator.agents import environment as _environment, process_groups as _process_groups, processes as _processes
from orchestrator.git.verification import models as _models, probes as _probes, process as _process


def _run_verify_command(
    worktree: Path,
    command: str,
    timeout: int,
    child_env: dict[str, str],
    baselines: tuple[str, str],
) -> _models.VerifyCommandOutcome:
    """Run and classify one command while registering its process group."""
    proc = _process._spawn_verify_command(worktree, command, child_env)
    with _processes.registered(proc):
        drained = _process_groups.communicate_bounded(proc, timeout)
        if drained is None:
            return _process._timeout_verify_result(proc, command)
        return _process._completed_verify_result(
            proc, command, drained, worktree, baselines,
        )


def _not_run_result(
    head: str, tree: str, timeout: int, revision: str | None,
) -> _models.VerifyResult:
    return _models.VerifyResult(
        status=_models.VERIFY_STATUS_NOT_RUN,
        commit=head or None,
        tree_identity=tree or None,
        configured_commands=(),
        attempted_commands=(),
        timeout=timeout,
        context_revision=revision,
    )


def _unreadable_tree_result(
    head: str,
    commands: tuple[str, ...],
    timeout: int,
    revision: str | None,
) -> _models.VerifyResult:
    return _models.VerifyResult(
        status=_models.VERIFY_STATUS_FAILED,
        commit=head or None,
        tree_identity=None,
        configured_commands=commands,
        attempted_commands=(),
        timeout=timeout,
        context_revision=revision,
        output="unreadable tree identity",
        head_before=head,
        head_after=head,
    )


def _run_command_sequence(
    worktree: Path,
    commands: tuple[str, ...],
    timeout: int,
    child_env: dict[str, str],
    baselines: tuple[str, str],
) -> tuple[_models.VerifyCommandOutcome, tuple[_models.VerifyCommandOutcome, ...]]:
    attempted: list[_models.VerifyCommandOutcome] = []
    for command in commands:
        outcome = _run_verify_command(
            worktree, command, timeout, child_env, baselines,
        )
        attempted.append(outcome)
        if outcome.status != _models.VERIFY_STATUS_OK:
            return outcome, tuple(attempted)
    return outcome, tuple(attempted)


def _run_verify_commands(
    worktree: Path,
    commands: tuple[str, ...],
    timeout: int,
    *,
    context_revision: str | None = None,
) -> _models.VerifyResult:
    """Run each command sequentially in `worktree` with a bounded timeout.

    Empty `commands` (the default) produces an explicit ``status="not_run"``
    result so the gate retains its existing no-op behavior without manufacturing
    passing verification evidence. When commands are configured, HEAD and full
    tree identity are snapshotted beforehand; an unreadable tree baseline fails
    closed.

    Commands are spawned via the shell so quoting / pipes / `&&` work the way
    an operator would type them; stdout and stderr are merged and bounded with
    secrets redacted before truncation. The shell runs with a child environment
    stripped of GitHub credentials, production-secret-shaped variables, AND the
    agent's own provider-auth keys (`filter_agent_env` with
    `allow_provider_auth=False`).

    The first non-zero exit, timeout, post-run dirty tree, or HEAD/tree
    mutation wins -- later commands are not run, since the gate is "everything
    passed" and the operator only needs the first failure to triage. Attempted
    commands, per-command outcomes, exit codes, and outputs are preserved in
    order in the verification transcript; pass and skip counts are never derived
    from another run.
    """
    head_before = _probes._head_sha(worktree)
    tree_before = _probes._tree_sha(worktree)

    if not commands:
        return _not_run_result(head_before, tree_before, timeout, context_revision)

    if not tree_before:
        return _unreadable_tree_result(
            head_before, commands, timeout, context_revision,
        )

    child_env = _environment.filter_agent_env(
        dict(os.environ), allow_provider_auth=False,
    )
    terminal, attempted = _run_command_sequence(
        worktree, commands, timeout, child_env, (head_before, tree_before),
    )
    if terminal.status != _models.VERIFY_STATUS_OK:
        return _models.VerifyResult(
            status=terminal.status,
            commit=head_before or None,
            tree_identity=tree_before or None,
            configured_commands=commands,
            attempted_commands=attempted,
            timeout=timeout,
            context_revision=context_revision,
            command=terminal.command,
            exit_code=terminal.exit_code,
            output=terminal.output,
            dirty_files=terminal.dirty_files,
            head_before=terminal.head_before or head_before,
            head_after=terminal.head_after or head_before,
        )

    return _models.VerifyResult(
        status=_models.VERIFY_STATUS_OK,
        commit=head_before or None,
        tree_identity=tree_before or None,
        configured_commands=commands,
        attempted_commands=attempted,
        timeout=timeout,
        context_revision=context_revision,
        head_before=head_before,
        head_after=head_before,
    )
