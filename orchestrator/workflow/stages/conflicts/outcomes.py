# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finished dev run left behind, in the order it has to be read.

Three dispositions precede any look at HEAD, and the order is load-bearing. A
shutdown-sweep interruption comes first because a killed run's output cannot be
trusted at all -- it returns without writing pinned state, so the whole tick's
in-memory bookkeeping is discarded and the next process re-runs from durable
state. Then a timeout, then a rebase still mid-flight, because a HEAD that
moved during an unfinished rebase says nothing about whether the conflicts were
resolved.

Only after those does the HEAD comparison mean anything: unchanged is a
question or silence and parks like the implementing handler does, a dirty tree
refuses to publish an incomplete branch, and a real new commit is pushed. The
`conflict_round` bump lives on the success path alone -- a human-reply resume
that lands cleanly should consume a slot, but a timeout or push failure on the
same counter should not, or the cap would fire on rounds that never ran.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.config import settings as config
from orchestrator.git.base_sync import pre_pr as _base_sync_pre_pr
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import guards as _guards, messages as _messages
from orchestrator.workflow.stages.conflicts import (
    models as _models,
    parks as _conflict_parks,
    transitions as _transitions,
)
from orchestrator.workflow.stages.implementing import (
    late_push as _late_push,
    late_records as _late_records,
    parks as _dev_parks,
)


def _post_conflict_resolution_result(
    ctx: _models._ConflictContext,
    run: _models._ConflictResumeRun,
    before_sha: str,
    conflict_round: int,
    *,
    force_with_lease: str | None = None,
) -> None:
    """Common post-agent handling for both fresh conflict resolution
    and the awaiting-human resume path.

    Calls `gh.write_pinned_state` before returning on every branch EXCEPT
    the shutdown-sweep-interrupted short-circuit (inside
    `_park_stalled_conflict_result`), which returns without writing so
    durable GitHub state stays retryable. The caller returns immediately
    after invoking this helper either way. Increments `conflict_round`
    only on the success path -- failure paths leave the counter alone so a
    human-reply resume that lands cleanly still consumes a slot, but a
    timeout/dirty/push-failure on the same counter does not. A successful
    push hands straight back to `validating` so the reviewer re-runs
    against the resolved branch; the single docs pass is deferred to the
    post-approval handoff to `documenting` in `_handle_validating`.
    """
    wt = run.worktree
    # Interrupt / timeout / still-mid-rebase dispositions park (or, for the
    # shutdown-sweep interrupt, silently drop) and signal the caller to stop.
    if _park_stalled_conflict_result(ctx, run):
        return

    after_sha = _verification_probes._head_sha(wt)
    if not after_sha or after_sha == before_sha:
        # Agent did not finish the rebase. Treat as a question / silence park,
        # mirroring the implementing handler.
        _dev_parks._on_question(ctx.gh, ctx.issue, ctx.state, run.dev_result)
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return

    dirty = _worktree_status._worktree_dirty_files(wt)
    if dirty:
        _dev_parks._on_dirty_worktree(
            ctx.gh, ctx.issue, ctx.state, run.dev_result, dirty,
        )
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return

    _finalize_conflict_resolution(
        ctx, wt, after_sha, conflict_round, force_with_lease=force_with_lease,
    )


def _park_stalled_conflict_result(
    ctx: _models._ConflictContext, run: _models._ConflictResumeRun,
) -> bool:
    """Park (or silently drop) a conflict-resolution run that never landed
    a usable commit. Returns True when the tick is fully handled.

    Covers the three dispositions that precede any HEAD inspection: a
    shutdown-sweep interruption (drop the result, return WITHOUT writing
    pinned state so the rebase re-runs from durable state), an agent
    timeout, and a rebase left mid-flight. Returns False to let the caller
    inspect HEAD for a completed resolution.
    """
    dev_result = run.dev_result
    # Shutdown-sweep interruption: a conflict-resolution run the orchestrator
    # killed mid-flight has no trustworthy result, so ignore it and return
    # WITHOUT writing pinned state -- the caller's in-memory watermark /
    # session mutations are discarded and the next process re-runs the rebase
    # from durable state. Must precede the timeout / unfinished-rebase branches.
    if _guards._ignore_if_interrupted(ctx.issue, dev_result):
        return True

    if dev_result.timed_out:
        _conflict_parks._park_conflict(
            ctx,
            f"{config.HITL_MENTIONS} dev agent timed out resolving rebase "
            f"conflicts after {config.AGENT_TIMEOUT}s; manual intervention "
            "needed.",
            reason="agent_timeout",
        )
        return True

    if not _base_sync_pre_pr._rebase_in_progress(run.worktree):
        return False

    raw = dev_result.last_message.strip()
    quoted = ""
    if raw:
        quoted = f"\n\nAgent output:\n\n{_messages._as_blockquote(raw)}"
    _conflict_parks._park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} rebase is still in progress after the "
        "dev agent returned; finish it manually or comment with "
        f"guidance to resume.{quoted}",
        reason="rebase_in_progress",
    )
    return True


def _finalize_conflict_resolution(
    ctx: _models._ConflictContext,
    wt: Path,
    after_sha: str,
    conflict_round: int,
    *,
    force_with_lease: str | None = None,
) -> None:
    """Push a completed conflict resolution and flip to `validating`.

    Parks on push failure; on success bumps `conflict_round`, emits the
    `agent_resolved` audit event, and hands to `validating` so the
    reviewer re-runs against the resolved branch. Writes pinned state on
    every exit.

    A resolution is a candidate for a pull request the remote already carries
    like any other -- an agent resolving conflicts writes code, and a rebase
    onto a base that has moved changes what the branch adds to it -- so the
    size gate stands in front of this push too. A held candidate ends the tick
    here: the gate has parked the issue or handed it to the adjudication, and
    the hand to `validating` below would move it off the state the gate just
    set. The lease stays the CALLER's, because both callers read the head
    their push replaces before the agent ran and the gate reads that pull
    request again after it: a fresh conflict names the pre-rebase head it
    rebased from, and a resumed park names the tip the pull request was
    fetched at. Left to the reading taken afterwards, a push that landed
    while the agent was out would become the lease this force-push replaces.
    """
    branch = _naming._resolve_branch_name(
        ctx.state, ctx.spec, ctx.issue.number,
    )
    published = _late_push._publishes(
        _late_records._gate(ctx.gh, ctx.spec, ctx.issue, ctx.state, wt),
        branch,
        _late_records._Entered(
            head=force_with_lease or "",
            # The commit the resolution left, so a checkout something moved
            # between that read and the gate's own is refused rather than
            # measured and pushed as this round's resolution.
            candidate=after_sha,
            # The round this resolution earned, handed to the gate for the
            # exit where this caller never reaches the tail: a hold relabels to
            # the adjudication, and the resumed tick would read the published
            # commit as a branch already carrying its base -- the no-op flip,
            # which resolves nothing and stamps no `last_conflict_resolved_at`.
            spends=_transitions._settles_the_held_round(
                "agent_resolved", after_sha,
            ),
        ),
    )
    if published.held:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    if not published.landed:
        _conflict_parks._park_conflict(
            ctx,
            f"{config.HITL_MENTIONS} git push failed after conflict "
            "resolution; see orchestrator logs.",
            reason="push_failed",
        )
        return

    # Pushed branch diff (fresh conflict resolution OR awaiting-human resume
    # that landed a commit) -> hand straight back to validating; the single
    # docs pass runs after final reviewer approval.
    _transitions._hand_resolved_round_to_validating(
        ctx, conflict_round, ctx.state.get("pr_number"),
        outcome="agent_resolved", sha=after_sha,
    )
