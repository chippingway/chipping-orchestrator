# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an interrupted auto-rebase can still be proven to have done.

Nothing here selects an outcome; this owner only establishes the facts one is
selected from. The pinned recovery anchor says which SHA the PR head carried
before the rewrite, so the local head plus the freshly fetched remote head are
what tell an already-published rewrite apart from one that never got pushed.
Every read that cannot produce both of those SHAs -- a failed fetch, a failed
or empty `rev-parse` -- resolves to the same fail-closed answer: reset onto the
anchor and park. A recovery that guessed instead would force-push over a PR
head it never saw.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.git import branch_transport, commands
from orchestrator.git.base_sync import attempts, persistence
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.state import (
    _ERROR_SNIPPET_LEN,
    _REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    log,
)
from orchestrator.git.publication import probes as publication_probes
from orchestrator.git.verification import probes as verification_probes
from orchestrator.git.worktrees import naming as _naming


def _abort_recovery_unverified(
    context: _AutoRebaseRecoveryContext, detail: str,
) -> bool:
    """Restore the recovery anchor when the remote state cannot be verified."""
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number} could not safely finalize: {detail} "
            "The issue is parked so the same-tick stage handlers do "
            "NOT run against a SHA the PR may not carry. Reply "
            "on this issue with anything once the underlying "
            "problem is fixed and the orchestrator will re-"
            "attempt the auto rebase on the next polling tick."
        ),
        reason=_REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    )
    return True


def _clear_ineligible_recovery(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Clear an interrupted-rebase anchor after an operator relabel.

    The checkout stands back on the anchor, off any head a finish of the
    attempt captured or settled evidence for, so that evidence is retired on
    the state the clear writes first (`settles_over_a_reset`) -- False keeps
    the attempt -- and the clear lands through `lands_a_clear`, which a
    successor another road settled meanwhile refuses.
    """
    settles = context.settles_over_a_reset
    if settles is not None and not settles():
        log.warning(
            "issue=#%d auto-rebase recovery: the verification evidence settled for the landed head could not be "
            "retired with the attempt; keeping the attempt rather than clearing it under label %r",
            context.issue.number,
            context.label,
        )
        return True
    if not _lands_the_clear(context):
        return True
    log.info(
        "issue=#%d auto-rebase recovery: label %r is no longer in "
        "the refresh-driven set; clearing pending flag",
        context.issue.number,
        context.label,
    )
    return True


def _fetch_recovery_snapshot(
    context: _AutoRebaseRecoveryContext,
) -> _AutoRebaseRecoverySnapshot | None:
    """Fetch the PR branch and capture the local recovery head."""
    spec = context.spec
    branch = _naming._resolve_branch_name(
        context.state, spec, context.issue.number,
    )
    fetch_result = branch_transport._authed_fetch(
        spec,
        f"+refs/heads/{branch}:refs/remotes/"
        f"{spec.remote_name}/{branch}",
        cwd=context.worktree,
    )
    if fetch_result.returncode != 0:
        fetch_error = (fetch_result.stderr or "").strip()
        log.warning(
            "issue=#%d auto-rebase recovery fetch of %s/%s failed: %s; "
            "aborting recovery and parking awaiting human",
            context.issue.number,
            spec.remote_name,
            branch,
            fetch_error,
        )
        error_snippet = fetch_error[:_ERROR_SNIPPET_LEN]
        _abort_recovery_unverified(
            context,
            f"the fetch of `{spec.remote_name}/{branch}` "
            "needed to verify the recovered SHA against the remote PR "
            f"head failed (`{error_snippet}`).",
        )
        return None
    return _AutoRebaseRecoverySnapshot(
        branch=branch,
        local_head=verification_probes._head_sha(context.worktree) or "",
    )


def _clear_unchanged_recovery(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Clear an anchor when HEAD never moved beyond the pre-rebase SHA; True holds where the clear did not land."""
    if not _lands_the_clear(context):
        return True
    log.info(
        "issue=#%d auto-rebase recovery: local HEAD matches pre-"
        "rebase SHA `%s`; clearing flag and falling through to "
        "the normal rebase flow",
        context.issue.number,
        context.pending_pre_rebase_sha[:8],
    )
    return False


def _lands_the_clear(context: _AutoRebaseRecoveryContext) -> bool:
    """Clear the attempt through the context's guarded clear (`lands_a_clear`), or whole with none; whether it landed.

    Guarded, a record another road wrote while the recovery read the checkout
    or fetched -- a transaction, a successor, its revision floor -- refuses it
    rather than being written over, and the caller holds the tick.
    """
    attempts._clears_the_attempt(context.state)
    lands = context.lands_a_clear
    if lands is None:
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    return lands(context)


def _read_remote_recovery_head(
    context: _AutoRebaseRecoveryContext,
    branch: str,
) -> str | None:
    """Read the freshly fetched remote PR head or park fail-closed."""
    spec = context.spec
    remote_ref = f"refs/remotes/{spec.remote_name}/{branch}"
    remote_head_result = commands._git_hardened(
        "rev-parse", remote_ref, cwd=context.worktree,
    )
    if remote_head_result.returncode != 0:
        remote_error = (remote_head_result.stderr or "").strip()
        log.warning(
            "issue=#%d auto-rebase recovery: rev-parse of %s failed "
            "after fetch: %s; aborting recovery and parking awaiting human",
            context.issue.number,
            remote_ref,
            remote_error,
        )
        remote_error = remote_error[:_ERROR_SNIPPET_LEN]
        _abort_recovery_unverified(
            context,
            f"`git rev-parse {remote_ref}` failed after the fetch "
            f"(`{remote_error}`), so the remote PR head SHA "
            "needed for the equality check could not be read.",
        )
        return None
    remote_head = (remote_head_result.stdout or "").strip()
    if remote_head:
        return remote_head
    log.warning(
        "issue=#%d auto-rebase recovery: rev-parse of %s returned "
        "no SHA; aborting recovery and parking awaiting human",
        context.issue.number,
        remote_ref,
    )
    _abort_recovery_unverified(
        context,
        f"`git rev-parse {remote_ref}` returned no SHA after the "
        "fetch, so the remote PR head SHA needed for the equality "
        "check could not be read.",
    )
    return None


def _complete_recovery_snapshot(
    context: _AutoRebaseRecoveryContext,
    snapshot: _AutoRebaseRecoverySnapshot,
) -> _AutoRebaseRecoverySnapshot | None:
    """Add the verified remote head and divergence counts to a snapshot."""
    remote_head = _read_remote_recovery_head(context, snapshot.branch)
    if remote_head is None:
        return None
    if snapshot.local_head == remote_head:
        return _AutoRebaseRecoverySnapshot(
            branch=snapshot.branch,
            local_head=snapshot.local_head,
            remote_head=remote_head,
        )
    # A reading that did not happen answers zero and zero, which is what an
    # in-sync branch answers -- and the heads above already disagree, so the
    # classifier behind this rejects that pair rather than acting on it.
    divergence = publication_probes._branch_divergence(
        context.spec, context.worktree, snapshot.branch,
    )
    return _AutoRebaseRecoverySnapshot(
        branch=snapshot.branch,
        local_head=snapshot.local_head,
        remote_head=remote_head,
        ahead=divergence.ahead,
        behind=divergence.behind,
    )
