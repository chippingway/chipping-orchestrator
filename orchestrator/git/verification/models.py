# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Verification result models, transcript records, and the output budget.

The budget lives beside the models because every `output` a caller receives
has already been redacted and truncated to it, so a change to one without
the other would publish output the model documents as post-budget.

The context revision is minted here too, from the configuration a run was
given, so the runner that records it and `is_reusable` that checks it spell
it once.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

_VERIFY_OUTPUT_BUDGET = 4096

# Folded into every context revision. Changing what a run executes under
# without changing its configuration -- the child environment policy, the
# readings taken after each command -- bumps it, so evidence recorded under
# the earlier rules stops matching.
_CONTEXT_SCHEME = "verify-context-v1"

VERIFY_STATUS_OK = "ok"
VERIFY_STATUS_FAILED = "failed"
VERIFY_STATUS_TIMEOUT = "timeout"
VERIFY_STATUS_DIRTY = "dirty"
VERIFY_STATUS_HEAD_CHANGED = "head_changed"
VERIFY_STATUS_TREE_CHANGED = "tree_changed"
VERIFY_STATUS_NOT_RUN = "not_run"

VERIFY_STATUSES = (
    VERIFY_STATUS_OK,
    VERIFY_STATUS_FAILED,
    VERIFY_STATUS_TIMEOUT,
    VERIFY_STATUS_DIRTY,
    VERIFY_STATUS_HEAD_CHANGED,
    VERIFY_STATUS_TREE_CHANGED,
    VERIFY_STATUS_NOT_RUN,
)


def _context_revision(commands: tuple[str, ...], timeout: int) -> str:
    """Revision of the verification context `commands` and `timeout` define.

    A digest rather than a counter, because two runs share a context exactly
    when they share its configuration: the same commands, in the same order,
    under the same per-command timeout. A caller deciding whether evidence
    carries to another tree compares this value, and lowercase hex is a token
    the verification artifact header carries verbatim.
    """
    canonical = json.dumps(
        {"scheme": _CONTEXT_SCHEME, "commands": list(commands), "timeout": timeout},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class VerifyCommandOutcome:
    """What one attempted verify command did, read after it finished.

    `status` takes the `VerifyResult` values other than ``"not_run"``, and is
    ``"ok"`` only when the command exited 0 and every reading after it matched
    the baseline. `head_before` / `tree_before` are the commit and tree the run
    started on. `head_after` / `tree_after` are what was read once the command
    exited: ``""`` when that read failed, and None when no read was taken -- a
    timed-out command's group is killed and nothing after it is read.
    `dirty_files` are the paths the status read named.
    """

    command: str
    status: str
    exit_code: int | None = None
    output: str = ""
    dirty_files: tuple[str, ...] = ()
    head_before: str | None = None
    head_after: str | None = None
    tree_before: str | None = None
    tree_after: str | None = None


@dataclass(frozen=True)
class VerifyResult:
    """Outcome and evidence transcript of running configured `VERIFY_COMMANDS`.

    `status` is one of:

    * ``"ok"``           -- every command exited 0 and left HEAD, its tree,
                            and a clean worktree exactly as the run found them.
    * ``"failed"``       -- a command exited non-zero, or the commit and tree
                            to verify could not be read, in which case no
                            command ran.
    * ``"timeout"``      -- a command hit the per-command wall-clock cap.
    * ``"dirty"``        -- the worktree could not be proven clean, either
                            before the first command (then none ran) or after
                            a command that exited 0: git named uncommitted
                            paths, or its status read failed. Treated as a
                            verify failure because handing off a dirty tree
                            to in_review would advertise the PR as ready for
                            human merge with state the dev never committed,
                            and a command that cleaned up after itself would
                            leave evidence for content no recorded tree holds.
    * ``"head_changed"`` -- a command moved `HEAD` (it ran `git commit` or
                            `git reset` etc.) while leaving the tree clean.
                            Treated as a verify failure because the squash-
                            on-approval + force-push that follows would
                            otherwise publish an unreviewed verify-created
                            commit. `head_before` / `head_after` record the
                            SHAs so the operator can identify which commit
                            the verify produced.
    * ``"tree_changed"`` -- HEAD still names the tested commit, but its tree
                            no longer reads as the one recorded before the
                            run. Refused like a moved HEAD, since evidence
                            has to describe one tree.
    * ``"not_run"``      -- the commands tuple was empty, so nothing ran and
                            nothing was read. The optional gate keeps its
                            no-op, and the result says so rather than passing.

    `commit` and `tree_identity` are the commit this run verified and its full
    tree, both read before the first command. The tree is resolved from that
    commit's object id rather than from `HEAD`, so the two name one commit even
    if HEAD moves between the reads. They are None when the run never had them:
    ``"not_run"``, or a ``"failed"`` run that could not read them.
    `configured_commands` is the exact ordered `VERIFY_COMMANDS` tuple, and
    `attempted_commands` holds one outcome per command that ran, in order: the
    commands after a refusal never run and appear nowhere, so pass and skip
    counts come from this run's own transcript and never from another run.
    `timeout` is the configured per-command cap in seconds, and
    `context_revision` is the `_context_revision` those commands and that
    timeout mint.

    The refusal fields (`command`, `exit_code`, `output`, `dirty_files`,
    `head_before` / `head_after`, `tree_before` / `tree_after`) restate what a
    caller switching on `status` reports: the refusing command's outcome, or,
    for a refusal before any command ran, the readings that refused it, with
    `command` None. An ``"ok"`` or ``"not_run"`` result leaves them empty.

    `output`, here and on every `VerifyCommandOutcome`, is already redacted
    (via `credentials.redact_secrets`) AND truncated to the last
    `_VERIFY_OUTPUT_BUDGET` UTF-8 bytes -- callers can post it verbatim. The
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
    tree_before: str | None = None
    tree_after: str | None = None

    @property
    def is_reusable(self) -> bool:
        """Whether this result is passing evidence another reader may rely on.

        Only an ``"ok"`` run qualifies, and only when the record proves it on
        its own: the tested commit and tree, a positive timeout, the context
        revision its commands and timeout mint, and a transcript naming exactly
        the configured commands in order, each of which passed on that same
        commit and tree. A record missing any of it is not evidence, whatever
        its status says.
        """
        if self.status != VERIFY_STATUS_OK or not (self.commit and self.tree_identity):
            return False
        if not self.configured_commands or self.timeout is None or self.timeout <= 0:
            return False
        if self.context_revision != _context_revision(self.configured_commands, self.timeout):
            return False
        ran = tuple(outcome.command for outcome in self.attempted_commands)
        return ran == self.configured_commands and all(
            _passed_on(outcome, self.commit, self.tree_identity)
            for outcome in self.attempted_commands
        )


def _passed_on(outcome: VerifyCommandOutcome, commit: str, tree: str) -> bool:
    """Whether `outcome` exited 0 clean and read `commit` and `tree` on both sides."""
    if outcome.status != VERIFY_STATUS_OK or outcome.exit_code != 0 or outcome.dirty_files:
        return False
    readings = (outcome.head_before, outcome.head_after, outcome.tree_before, outcome.tree_after)
    return readings == (commit, commit, tree, tree)
