# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Verification result models, transcript records, and the output budget.

The budget lives beside the models because every `output` a caller receives
has already been redacted and truncated to it, so a change to one without
the other would publish output the model documents as post-budget.
"""
from __future__ import annotations

from dataclasses import dataclass

_VERIFY_OUTPUT_BUDGET = 4096

VERIFY_STATUS_OK = "ok"
VERIFY_STATUS_FAILED = "failed"
VERIFY_STATUS_TIMEOUT = "timeout"
VERIFY_STATUS_DIRTY = "dirty"
VERIFY_STATUS_HEAD_CHANGED = "head_changed"
VERIFY_STATUS_NOT_RUN = "not_run"

VERIFY_STATUSES = (
    VERIFY_STATUS_OK,
    VERIFY_STATUS_FAILED,
    VERIFY_STATUS_TIMEOUT,
    VERIFY_STATUS_DIRTY,
    VERIFY_STATUS_HEAD_CHANGED,
    VERIFY_STATUS_NOT_RUN,
)


@dataclass(frozen=True)
class VerifyCommandOutcome:
    """Outcome of attempting one configured verify command.

    Preserves the exact command string, its outcome status, exit code,
    bounded redacted output, dirty files, and HEAD movement.
    """

    command: str
    status: str
    exit_code: int | None = None
    output: str = ""
    dirty_files: tuple[str, ...] = ()
    head_before: str | None = None
    head_after: str | None = None


@dataclass(frozen=True)
class VerifyResult:
    """Outcome and evidence transcript of running configured `VERIFY_COMMANDS`.

    `status` is one of:

    * ``"ok"``           -- every command exited 0 and the worktree was clean.
    * ``"failed"``       -- a command exited non-zero or tree identity was unreadable.
    * ``"timeout"``      -- a command hit the per-command wall-clock cap.
    * ``"dirty"``        -- every command exited 0 but the worktree carried
                            uncommitted changes afterwards; treated as a
                            verify failure because handing off a dirty tree
                            to in_review would advertise the PR as ready for
                            human merge with state the dev never committed.
    * ``"head_changed"`` -- a command moved `HEAD` (it ran `git commit` or
                            `git reset` etc.) while leaving the tree clean.
                            Treated as a verify failure because the squash-
                            on-approval + force-push that follows would
                            otherwise publish an unreviewed verify-created
                            commit. `head_before` / `head_after` record the
                            SHAs so the operator can identify which commit
                            the verify produced.
    * ``"not_run"``      -- empty commands tuple; retains the optional gate's
                            existing no-op behavior, but produces an explicit
                            not-run result rather than reusable passing evidence.

    `commit` and `tree_identity` record the tested commit SHA and full tree
    identity established before command execution. `configured_commands`
    preserves the exact ordered `VERIFY_COMMANDS` tuple. `attempted_commands`
    records each attempted command outcome and its bounded redacted output in
    the order executed; later commands are skipped on refusal and never derived
    from another run. `timeout` records the configured wall-clock timeout in
    seconds, and `context_revision` records the explicit workflow context
    revision.

    The non-ok fields (`command`, `exit_code`, `output`, `dirty_files`,
    `head_before` / `head_after`) describe the terminal outcome for callers
    switching on `status`.

    `output` is already redacted (via `credentials.redact_secrets`) AND truncated to
    `_VERIFY_OUTPUT_BUDGET` bytes -- callers can post it verbatim. The
    redact pass runs before truncation so a secret straddling the cut
    cannot leak a partial value (see `_truncate_verify_output`).
    """

    status: str
    commit: str | None = None
    tree_identity: str | None = None
    configured_commands: tuple[str, ...] = ()
    attempted_commands: tuple[VerifyCommandOutcome, ...] = ()
    timeout: int | None = None
    context_revision: str | None = None
    command: str | None = None
    exit_code: int | None = None
    output: str = ""
    dirty_files: tuple[str, ...] = ()
    head_before: str | None = None
    head_after: str | None = None

    @property
    def tree(self) -> str | None:
        """Full tree identity alias for `tree_identity`."""
        return self.tree_identity

    @property
    def commands(self) -> tuple[VerifyCommandOutcome, ...]:
        """Attempted commands alias for `attempted_commands`."""
        return self.attempted_commands

    @property
    def verify_commands(self) -> tuple[str, ...]:
        """Configured commands alias for `configured_commands`."""
        return self.configured_commands

    @property
    def is_reusable(self) -> bool:
        """Whether this result represents reusable passing verification evidence.

        An empty commands tuple, missing commit or tree identity, or non-ok
        outcome is never reusable evidence.
        """
        return (
            self.status == VERIFY_STATUS_OK
            and bool(self.configured_commands)
            and bool(self.commit)
            and bool(self.tree_identity)
        )
