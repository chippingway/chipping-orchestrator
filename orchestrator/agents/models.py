# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Agent run options, result models, the identity of the process a result came from, and unfinished-step and
terminal-failure diagnostics."""
from __future__ import annotations

import signal
from dataclasses import dataclass
from typing import NamedTuple

from orchestrator import config
from orchestrator.observability.usage.agy_events import ToolLifecycle
from orchestrator.observability.usage.metrics import UsageMetrics


@dataclass(frozen=True)
class TerminalFailure:
    """How a backend's failed run ended, read from its failure channels rather than `last_message`.

    Only the Antigravity backend fills it, on every run it normalizes to a failure:
    a missing, unsuccessful, or interrupted terminal result, or a successful
    one with unfinished tool steps behind it.

    `process_exit_code` is what the subprocess itself returned, or None where
    no return was captured: a run the timeout killed reports the runner's `-1`
    sentinel in place of whatever the killed process exited with. AGY
    normalizes a zero return to `AgentResult.exit_code == 1` on failure, so the
    normalized code is no proof the CLI exited with it. `status` is the
    terminal result's status, None when no terminal result named one; it and
    `error`, the terminal error, are both redacted before they are bounded,
    so a cut can never leave half a secret behind.

    `quota_exhausted` is the account-quota verdict, taken from failure evidence
    alone: the error an unsuccessful terminal carried and the CLI's own `error:`
    and `AGY_ERROR:` stderr lines. An exit code, the terminal response, and
    assistant or tool text never decide it. `quota_reset` is the reset
    interval as AGY phrased it, such as `2h42m39s`, or None when it named none.
    """

    process_exit_code: int | None
    status: str | None = None
    error: str = ""
    quota_exhausted: bool = False
    quota_reset: str | None = None


@dataclass(frozen=True)
class AgentInvocation:
    """Which actual process invocation one result came from, as its usage is accounted by.

    Minted once per process the tracked spawn starts
    (`workflow/engine/invocations.py`), and never per logical request: a
    request's fingerprint is deliberately the same across every attempt at one
    round, and a CLI session id is optional and shared by every resume of a
    conversation, so neither tells two runs of an identical request apart.

    `repo`, `issue`, `comment`, and `cycle` name the record the invocation
    belongs to -- the repository and issue whose pinned comment charged it,
    that comment's id, and the workflow cycle it was on: 0 where it named
    none, and None where the identity it carried was unreadable, which no
    record's cycle ever matches. `ordinal` is the lifetime charge the process
    was started under, which goes up by one per charge and is never refunded
    or reused, so it orders this issue's invocations and is what a retired
    accounting receipt is still refused by. `nonce` is random, so two
    invocations stay distinct even where a damaged count hands them one
    ordinal.
    """

    repo: str
    issue: int
    comment: int | None
    cycle: int | None
    ordinal: int
    nonce: str


@dataclass
class AgentResult:
    """Normalized outcome returned by any supported agent backend."""

    session_id: str | None
    last_message: str
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str
    interrupted: bool = False
    usage: UsageMetrics | None = None
    # Whether a process was invoked for this result at all. True for every
    # run any backend produced, including the ones a shutdown kill or a
    # timeout cut short -- those reached a CLI, and what they left behind on
    # disk is theirs. False for every result no process produced: a launch
    # turned away before the spawn, and the ones a stage SYNTHESIZES when it
    # publishes committed work an earlier run left behind. The stages have to
    # be able to tell those apart from a run's own output -- a worktree they
    # would otherwise read a killed run's leavings out of carries nothing this
    # result put there, and a developer-report contract answered by a sentence
    # the orchestrator wrote itself is no report at all.
    invoked: bool = True
    # Unfinished tool steps reported by a backend's lifecycle reducer (such
    # as Antigravity tool lifecycles where active commands remained when a
    # terminal envelope was emitted). Empty for completed or non-AGY runs.
    unfinished_steps: tuple[ToolLifecycle, ...] = ()
    # The failure diagnostics a backend read off a run it normalized to a
    # failure. None for successful runs and for backends that keep no such
    # record.
    terminal_failure: TerminalFailure | None = None
    # The process invocation this result came from, stamped by the tracked
    # spawn once a charged process returns. None for every result no process
    # produced, and for one a backend returned outside that spawn: neither has
    # a run whose usage could be accounted once.
    invocation: AgentInvocation | None = None


@dataclass(frozen=True)
class AgentRunOptions:
    """Optional controls shared by fresh agent runs and session resumes."""

    resume_session_id: str | None = None
    extra_env: dict[str, str] | None = None
    timeout: int | None = None
    extra_args: tuple[str, ...] = ()

    @property
    def timeout_seconds(self) -> int:
        return self.timeout or config.AGENT_TIMEOUT


class SubprocessResult(NamedTuple):
    """Captured process streams and termination classification."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    interrupted: bool


_SHELL_SIGNAL_EXIT_BASE = 128
_INTERRUPTED_EXIT_CODES = frozenset((
    -signal.SIGTERM,
    -signal.SIGKILL,
    _SHELL_SIGNAL_EXIT_BASE + signal.SIGTERM,
    _SHELL_SIGNAL_EXIT_BASE + signal.SIGKILL,
))


def is_signal_interrupted(agent_result: AgentResult) -> bool:
    """True when `agent_result` was terminated by an operating system signal
    (such as SIGTERM/SIGKILL from the shutdown sweep), as opposed to a backend
    cancellation or error exit."""
    if getattr(agent_result, "timed_out", None) is True:
        return False
    if not getattr(agent_result, "interrupted", False):
        return False
    exit_code = getattr(agent_result, "exit_code", None)
    if not isinstance(exit_code, int):
        return False
    return exit_code in _INTERRUPTED_EXIT_CODES


def is_shutdown_sweep_interrupted(agent_result: AgentResult) -> bool:
    """True when `agent_result` represents a genuine shutdown interruption.

    A process-signal interruption (SIGTERM/SIGKILL or shell-signal return code)
    is ALWAYS a shutdown sweep kill regardless of whether partial output
    happened to contain active tool steps. For backend cancellations (e.g. AGY
    CANCELED/INTERRUPTED statuses with normal process exit codes), only runs
    without structured unfinished tool steps are ignored as interruptions; runs
    carrying structured unfinished steps are execution failures that must
    proceed to disposition. So is a backend cancellation whose failure record
    names an exhausted account quota: the CLI stopped itself on the quota, and
    ignored as a shutdown it would leave the issue unparked for the next tick
    to spend another run on. Timed-out runs are never shutdown interruptions.
    """
    if getattr(agent_result, "timed_out", None) is True:
        return False
    if not getattr(agent_result, "interrupted", False):
        return False
    if is_signal_interrupted(agent_result):
        return True
    failure = getattr(agent_result, "terminal_failure", None)
    if isinstance(failure, TerminalFailure) and failure.quota_exhausted:
        return False
    unfinished = getattr(agent_result, "unfinished_steps", ())
    return not (isinstance(unfinished, (tuple, list)) and bool(unfinished))
