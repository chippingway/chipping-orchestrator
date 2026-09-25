# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Sequencing owner for a configured `VERIFY_COMMANDS` run.

This is the entry point the validating stage calls: it mints the context
revision from the configuration it was given, reads the commit and full tree
to verify, proves the worktree clean, builds the stripped child environment
once, and runs the commands in order until one of them earns a refusal.
Per-command spawning, teardown, and classification belong to the `process`
owner; this module owns only the baseline, the ordering, the fail-fast
decision, and the transcript the result records.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

from orchestrator.agents import environment as _environment, process_groups as _process_groups, processes as _processes
from orchestrator.git.verification import (
    models as _models,
    probes as _probes,
    process as _process,
    status as _worktree_status,
)


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
            return _process._timeout_verify_result(proc, command, baselines)
        return _process._completed_verify_result(
            proc, command, drained, worktree, baselines,
        )


def _run_command_sequence(
    worktree: Path,
    commands: tuple[str, ...],
    timeout: int,
    child_env: dict[str, str],
    baselines: tuple[str, str],
) -> tuple[_models.VerifyCommandOutcome, ...]:
    """Outcomes of `commands` in order, ending at the first that refused."""
    attempted: list[_models.VerifyCommandOutcome] = []
    for command in commands:
        outcome = _run_verify_command(
            worktree, command, timeout, child_env, baselines,
        )
        attempted.append(outcome)
        if outcome.status != _models.VERIFY_STATUS_OK:
            break
    return tuple(attempted)


def _run_verify_commands(
    worktree: Path,
    commands: tuple[str, ...],
    timeout: int,
) -> _models.VerifyResult:
    """Run each command sequentially in `worktree` with a bounded timeout.

    Every result carries the configuration it ran under and the context
    revision minted from it, so no caller can hand back a result without one.
    Empty `commands` (the default) returns ``status="not_run"`` without
    reading or running anything: the gate keeps its no-op, and the result says
    that nothing was verified rather than passing.

    Otherwise the commit and its tree are read first, the tree from the
    commit's object id so both name one commit, and the worktree has to read
    clean before any command runs -- a command that cleaned up changes already
    there would otherwise pass over content no recorded tree holds. Either
    reading failing refuses before anything runs.

    Commands are spawned via the shell so quoting / pipes / `&&` work the way
    an operator would type them; stdout and stderr are merged so a failing
    build with all its diagnostics on stderr surfaces in one block in the park
    comment.

    The first non-zero exit, timeout, dirty or unprovable tree, moved HEAD, or
    changed tree wins -- later commands are not run, since the gate is
    "everything passed" and the operator only needs the first failure to
    triage. Dirtiness, HEAD, and tree are read AFTER EACH command so a failure
    is attributed to the command that caused it, with that command's captured
    output preserved for the park comment. The HEAD check guards against a
    verify command that `git commit`s its own fixups: without it, a clean tree
    + zero exit would look like `ok`, and the squash-on-approval + force-push
    that follows would publish an unreviewed verify-created commit.
    """
    record = functools.partial(
        _models.VerifyResult,
        configured_commands=commands,
        timeout=timeout,
        context_revision=_models._context_revision(commands, timeout),
    )
    if not commands:
        return record(status=_models.VERIFY_STATUS_NOT_RUN)
    commit = _probes._head_sha(worktree)
    tree = _probes._tree_sha(worktree, commit)
    if not tree:
        return record(
            status=_models.VERIFY_STATUS_FAILED, head_before=commit, tree_before=tree,
        )
    return _run_from_baseline(
        worktree,
        commands,
        timeout,
        (commit, tree),
        functools.partial(record, commit=commit, tree_identity=tree),
    )


def _run_from_baseline(
    worktree: Path,
    commands: tuple[str, ...],
    timeout: int,
    baselines: tuple[str, str],
    record: functools.partial[_models.VerifyResult],
) -> _models.VerifyResult:
    """Run `commands` from the commit and tree in `baselines` once the worktree reads clean."""
    status = _worktree_status._worktree_status(worktree)
    if not status.is_clean:
        return record(
            status=_models.VERIFY_STATUS_DIRTY,
            dirty_files=status.paths,
            head_before=baselines[0],
            tree_before=baselines[1],
        )
    # Strip GitHub credentials, production-secret-shaped variables,
    # write-credential locators (SSH-agent / askpass), AND the agent's
    # own provider-auth keys from the child environment. Verify commands
    # run operator-configured shell against code the agent just produced;
    # without this, a prompt-injected `pytest` plugin (or a hostile
    # dependency the agent pulled in) could read `$GITHUB_TOKEN` /
    # `$STRIPE_API_KEY` / `$ANTHROPIC_API_KEY` / `$SSH_AUTH_SOCK` / ...
    # straight out of the orchestrator's environment and exfiltrate or
    # push as the operator. `allow_provider_auth=False` is stricter than
    # the agent subprocess case: the agent CLI needs its provider key to
    # reach its model, but the verify shell does not. An operator who
    # legitimately needs a secret in a verify command must load it from
    # disk inside a wrapper script (`VERIFY_COMMANDS=./run-verify.sh`);
    # inline `KEY=value pytest ...` is unsafe because the failure park
    # comment publishes `verify.command` verbatim on the issue.
    child_env = _environment.filter_agent_env(
        dict(os.environ), allow_provider_auth=False,
    )
    attempted = _run_command_sequence(
        worktree, commands, timeout, child_env, baselines,
    )
    terminal = attempted[-1]
    if terminal.status == _models.VERIFY_STATUS_OK:
        return record(status=_models.VERIFY_STATUS_OK, attempted_commands=attempted)
    return record(
        status=terminal.status,
        attempted_commands=attempted,
        command=terminal.command,
        exit_code=terminal.exit_code,
        output=terminal.output,
        dirty_files=terminal.dirty_files,
        head_before=terminal.head_before,
        head_after=terminal.head_after,
        tree_before=terminal.tree_before,
        tree_after=terminal.tree_after,
    )
