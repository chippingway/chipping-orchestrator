# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a failed local verify says to the operator who has to fix it.

The approval gate runs `VERIFY_COMMANDS` and only ever asks whether the
result was ok. Everything a non-ok result is worth is here, and it is written
for a human reading the issue rather than the orchestrator's logs: the failing
command, how it failed, and the tail of what it printed. `head_changed`
surfaces both short SHAs because the operator's next move differs by which
commit appeared -- keep it and re-spawn the reviewer on the new HEAD, or
revert it and re-run.

The captured output is quoted exactly as the runner produced it. Re-redacting
here would be a no-op for anything already collapsed to `***` and would still
miss a secret straddling the truncation cut, so the redact-before-truncate
pass inside the runner is the only place that can be right about it.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards, messages as _messages
from orchestrator.workflow.stages.validating import state as _state


def _verify_failure_detail(verify) -> str:
    """One-line description of a non-ok local-verify result, naming the
    failing command and its failure mode.

    The `head_changed` branch surfaces both short SHAs so the operator can
    `git show` the stray commit and decide whether to keep it (re-spawn the
    reviewer on the new HEAD) or revert it before re-trying.
    """
    if verify.status == "timeout":
        return (
            f"`{verify.command}` timed out after "
            f"{config.VERIFY_TIMEOUT}s"
        )
    if verify.status == "dirty":
        files = ", ".join(
            f"`{file_path}`" for file_path in verify.dirty_files[:10]
        )
        if len(verify.dirty_files) > 10:
            elided = len(verify.dirty_files) - 10
            files = f"{files}, … (+{elided} more)"
        return f"`{verify.command}` left the worktree dirty: {files}"
    if verify.status == "head_changed":
        before = (verify.head_before or "")[:_state._SHORT_SHA_LEN] or "(no HEAD)"
        after = (verify.head_after or "")[:_state._SHORT_SHA_LEN] or "(no HEAD)"
        return (
            f"`{verify.command}` moved HEAD ({before} -> {after}); "
            "verify commands must not commit"
        )
    exit_display = "?" if verify.exit_code is None else verify.exit_code
    return (
        f"`{verify.command}` exited with code "
        f"{exit_display}"
    )


def _park_verify_failure(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    verify,
) -> None:
    """Park `validating` on a local-verify failure.

    The park comment names the failing command, its exit code (or
    timeout), and a redacted / truncated tail of the captured output so
    the operator can triage without pulling the orchestrator's logs.
    `park_reason` is set to a stable token (`verify_failed`,
    `verify_timeout`, or `verify_dirty`) so dashboards and future
    transient-recovery logic can branch on the failure mode.
    """
    reason = _state._VERIFY_STATUS_TO_REASON.get(verify.status, "verify_failed")
    detail = _verify_failure_detail(verify)

    message = (
        f"{config.HITL_MENTIONS} local verification failed; PR not handed "
        f"off to in_review. {detail}."
    )
    # `verify.output` is already redacted-then-truncated by the runner;
    # re-redacting here would be a no-op for any match `redact_secrets`
    # already collapsed to `***`, AND would not catch a partial secret
    # that straddled the truncation cut -- the only safe way to handle
    # that case is the redact-before-truncate pass inside the runner.
    output = verify.output or ""
    if output.strip():
        quoted = _messages._as_blockquote(output.rstrip())
        message = f"{message}\n\n_Verify output (tail):_\n\n{quoted}"

    _guards._park_awaiting_human(gh, issue, state, message, reason=reason)
    state.set(_state._PARK_REASON, reason)
