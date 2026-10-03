# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The approval's local verify gate, and what a failed run says to the operator who has to fix it.

The approval gate runs `VERIFY_COMMANDS` under `VERIFY_TIMEOUT` over the
round's checkout (`_runs_the_gate`), ahead of the squash, and advances on
``"ok"`` and on the ``"not_run"`` an empty configuration returns. The
evidence the approval rests on is the verified evidence its proof was taken
over (`approved_evidence`); where its squash publishes another head, a passing
run of the gate on the approved head is what is carried onto it, as
orchestrator-executed evidence naming the commit it ran on, and the reviewer's
evidence where the run binds nothing -- an empty configuration's included
(`squash_evidence`). Everything any other result
is worth is here, and it is written for a human reading the issue rather than
the orchestrator's logs: the failing command, how it failed, and the tail of
what it printed -- or, when the run refused before any command, the reading
that refused it. `head_changed` surfaces both short SHAs because the
operator's next move differs by which commit appeared -- keep it and re-spawn
the reviewer on the new HEAD, or revert it and re-run. `tree_changed`
surfaces both short tree ids and says HEAD stayed put.

What is worded here is the park's reason and notice, and nothing more: the
park itself is the approval arc's to file (`approval`), through the funnel
every park of a reviewed subject takes (`review_parks`), since a failure over
a subject that moved while its notice was posted is no failure of the
approval, and a fresh reviewer answers it.

The captured output is quoted exactly as the runner produced it. Re-redacting
here would be a no-op for anything already collapsed to `***` and would still
miss a secret straddling the truncation cut, so the redact-before-truncate
pass inside the runner is the only place that can be right about it.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator import config
from orchestrator.git.verification import models as _verify_models, runner as _verify_runner
from orchestrator.workflow.engine import messages as _messages
from orchestrator.workflow.stages.validating import state as _state


def _runs_the_gate(worktree: Path) -> _verify_models.VerifyResult:
    """The approval's local run of the configured commands over `worktree`, under the configured timeout."""
    return _verify_runner._run_verify_commands(worktree, config.VERIFY_COMMANDS, config.VERIFY_TIMEOUT)


def _verify_failure_detail(verify) -> str:
    """One-line description of a refused local-verify result, naming the
    failing command and its failure mode.

    The `head_changed` branch surfaces both short SHAs so the operator can
    `git show` the stray commit and decide whether to keep it (re-spawn the
    reviewer on the new HEAD) or revert it before re-trying. A timeout names
    the cap the run recorded rather than the current setting, which may have
    changed since the command was killed.
    """
    if verify.command is None:
        return _refused_before_commands(verify)
    command = f"`{verify.command}`"
    if verify.status == "timeout":
        cap = "" if verify.timeout is None else f" after {verify.timeout}s"
        return f"{command} timed out{cap}"
    if verify.status == "dirty":
        return _dirty_detail(
            verify.dirty_files,
            f"{command} left the worktree dirty",
            f"{command} exited 0 but the worktree status could not be read",
        )
    if verify.status in {"head_changed", "tree_changed"}:
        return _identity_change_detail(verify, command)
    exit_display = "?" if verify.exit_code is None else verify.exit_code
    return f"{command} exited with code {exit_display}"


def _refused_before_commands(verify) -> str:
    """What stopped a run before its first command: the worktree or identity."""
    if verify.status == "dirty":
        return _dirty_detail(
            verify.dirty_files,
            "the worktree was dirty before any command ran",
            "the worktree status could not be read before any command ran",
        )
    return "the commit and tree to verify could not be read, so no command ran"


def _dirty_detail(dirty_files: tuple[str, ...], named: str, unread: str) -> str:
    """`named` with the first ten paths git named, or `unread` if it named none.

    A status read that failed names nothing, which a list would render as an
    empty sentence about a tree nobody proved clean.
    """
    if not dirty_files:
        return unread
    files = ", ".join(f"`{file_path}`" for file_path in dirty_files[:10])
    if len(dirty_files) > 10:
        elided = len(dirty_files) - 10
        files = f"{files}, … (+{elided} more)"
    return f"{named}: {files}"


def _identity_change_detail(verify, command: str) -> str:
    """Name the HEAD or tree a command left behind, before and after."""
    if verify.status == "head_changed":
        before = (verify.head_before or "")[:_state._SHORT_SHA_LEN] or "(no HEAD)"
        after = (verify.head_after or "")[:_state._SHORT_SHA_LEN] or "(no HEAD)"
        return (
            f"{command} moved HEAD ({before} -> {after}); "
            "verify commands must not commit"
        )
    before = (verify.tree_before or "")[:_state._SHORT_SHA_LEN] or "(unreadable)"
    after = (verify.tree_after or "")[:_state._SHORT_SHA_LEN] or "(unreadable)"
    return (
        f"{command} left HEAD in place but its tree no longer reads as the "
        f"tested one ({before} -> {after})"
    )


def _verify_failure_park(verify) -> tuple[str, str]:
    """The reason and the words of the park a local-verify failure earns.

    The notice names the failing command, its exit code (or timeout), and a
    redacted / truncated tail of the captured output so the operator can
    triage without pulling the orchestrator's logs. The reason is a stable
    token (`verify_failed`, `verify_timeout`, `verify_dirty`,
    `verify_head_changed`, or `verify_tree_changed`) so dashboards and future
    transient-recovery logic can branch on the failure mode. The funnel that
    posts the notice mentions the humans it asks (`review_parks`).
    """
    reason = _state._VERIFY_STATUS_TO_REASON.get(verify.status, "verify_failed")
    detail = _verify_failure_detail(verify)

    message = f"local verification failed; PR not handed off to in_review. {detail}."
    # `verify.output` is already redacted-then-truncated by the runner;
    # re-redacting here would be a no-op for any match `redact_secrets`
    # already collapsed to `***`, AND would not catch a partial secret
    # that straddled the truncation cut -- the only safe way to handle
    # that case is the redact-before-truncate pass inside the runner.
    output = verify.output or ""
    if output.strip():
        quoted = _messages._as_blockquote(output.rstrip())
        message = f"{message}\n\n_Verify output (tail):_\n\n{quoted}"
    return reason, message
