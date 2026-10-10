# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recovery refusals for an unreadable head, unpinned lease, or dirty checkout.

A recovered push needs the exact commit and remote tip its proof named.
A status read that failed cannot establish a clean tree. Each refusal keeps
the recovered work in place and records the park that the next tick reads.

A recovered push is also work reaching the pull request, so it goes out only
under a report that describes it (`_parked_undescribed_push`): never over a
report owed and unrecorded, never with a head other than the one a saved
report names, and never ahead of the settlement of a report already bound.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator import config
from orchestrator.git.verification import status as _worktree_status
from orchestrator.workflow.engine import (
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
)
from orchestrator.workflow.stages.conflicts import (
    models as _models,
    parks as _conflict_parks,
    resume_records as _resume_records,
    state as _state,
)
from orchestrator.workflow.stages.validating import drift_reports as _drift_reports, report_hold as _report_hold
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")



_UNNAMEABLE_PUSH_PARK = (
    "{mentions} this issue's worktree carries {ahead} commit(s) an earlier "
    "tick never pushed, and the commit they leave the branch on could not be "
    "read. That id is what the push would be named against, so without it "
    "anything committed over the worktree before the push goes out in its "
    "place -- under a lease proved against the head the branch used to be on. "
    "It is also what a round this push finishes is recorded under, in the "
    "audit event and in the receipt a size-gate hold leaves behind, and a "
    "receipt naming no commit is one no later tick can prove. Nothing was "
    "pushed and nothing was discarded. Repair the checkout so its head reads, "
    "and the next tick publishes them again."
)


def _parked_unnameable_push(
    ctx: _models._ConflictContext,
    sync: _models._WorktreeSync,
    recovered_sha: str,
) -> bool:
    """Refuse a recovered push whose commit nothing could read.

    Naming the commit is what makes the push and everything recorded about it
    one decision. The gate proves the checkout independently, and the worktree
    is writable in between: unnamed, a commit landing in that window is the
    one measured and force-pushed -- under a lease this owner proved against
    the head the branch used to be on -- while nothing here ever read it.
    That holds on both roads, so the reading is required on both.

    Where the push also FINISHES a round -- the branch already carries its
    base -- the same id is what the round is recorded under, in the audit
    event the tail emits and in the receipt a size-gate hold leaves for the
    tick that resumes behind the adjudication. The receipt is the one that
    outlives the tick: it goes down in the push's own durable write, so a
    crash between that write and the tail would come back to
    `("recovered_push", "")` -- a pair naming no commit, which every later
    tick refuses because nothing can prove it, on a branch that is in sync by
    then, so the round a push really landed is reported as the flip that
    resolves nothing.
    """
    if recovered_sha:
        return False
    log.error(
        "issue=#%d resolving_conflict: nothing could read the commit %d "
        "recovered commit(s) leave the branch on; refusing to publish a push "
        "nothing could name",
        ctx.issue.number, sync.ahead,
    )
    _conflict_parks._park_conflict(
        ctx,
        _UNNAMEABLE_PUSH_PARK.format(
            mentions=config.HITL_MENTIONS, ahead=sync.ahead,
        ),
        reason=_state._REASON_UNREADABLE_HEAD,
        # Said once, for the reason the reading is retried at all: a later
        # tick's own head read is what clears this, not a reply.
        once=True,
    )
    return True


def _parked_unpinnable_recovery(
    ctx: _models._ConflictContext,
    sync: _models._WorktreeSync,
    lease: str,
) -> bool:
    """Whether this recovered push has no head to pin itself against.

    The lease is the whole of what keeps a force-push off a pull request
    somebody moved while the commits were sitting unpushed, and the one
    fallback available here is the head read at push time -- which is exactly
    the move it exists to catch. So a tip nothing could read parks with the
    commits still on the branch, the same way every other reading this stage
    could not take does.

    False is the ordinary answer, and it is where the road below carries on.
    """
    if lease:
        return False
    spec = ctx.spec
    remote_ref = f"{spec.remote_name}/{sync.branch}"
    log.error(
        "issue=#%d resolving_conflict: %d recovered commit(s) are ahead of "
        "%s and nothing could name the head they were proved against; "
        "refusing to force-push under a lease git would take for itself",
        ctx.issue.number, sync.ahead, remote_ref,
    )
    _conflict_parks._park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} this issue's worktree carries {sync.ahead} "
        f"commit(s) an earlier tick never pushed, and the head `{remote_ref}` "
        "was standing on when that was established could not be read -- so "
        "there is nothing to pin the force-push against, and pinning it to "
        "the head read now would adopt whatever landed while the commits were "
        "waiting. Nothing was pushed and nothing was discarded. The next tick "
        "fetches and reads it again.",
        reason=_state._REASON_UNPINNABLE_RECOVERY,
        once=True,
    )
    return True


def _parked_dirty_recovery(
    ctx: _models._ConflictContext, wt: Path,
) -> bool:
    """Refuse a recovered push taken over a tree nothing proved clean.

    If the previous tick crashed before its own dirty check ran, the worktree
    may carry edits the unpushed commit does NOT contain. Pushing in that
    state would publish a SHA that silently omits them, and the reviewer at
    validating would later run on a local tree that does not match the pull
    request. Mirrors `_on_dirty_worktree`: park awaiting human, no flip.

    Proved, not merely un-named. A status read that established nothing names
    no paths and so does a tree with nothing in it, so asking for the paths
    alone waves the first through as the second -- and the size gate's own
    tree proof is no backstop, since it is part of the measurement an install
    running `DECOMPOSE=off` never takes. The two failures part on what a human
    has to do: uncommitted work is removed or committed, while a status nobody
    could read is a checkout to repair, which the next tick's own reading
    clears.
    """
    tree = _worktree_status._worktree_status(wt)
    if tree.is_clean:
        return False
    if not tree.readable:
        _conflict_parks._park_unreadable_worktree(ctx)
        return True
    _conflict_parks._park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} worktree has {len(tree.paths)} "
        "uncommitted change(s) alongside recovered conflict "
        "resolution; refusing to push an incomplete branch. "
        "Resolve the dirty tree manually before resuming.",
        reason="dirty_worktree",
    )
    return True


def _parked_undescribed_push(
    ctx: _models._ConflictContext, recovered_sha: str,
) -> bool:
    """Refuse a recovered push no report of this issue's would describe.

    Three shapes, and each is work reaching the pull request with nothing on
    it accounting for that work. The first is committed work the issue owes a
    report NOBODY recorded: a body edit's resume that committed and wrote no
    report parks for one, and a reply that only acknowledges the edit answers
    that park without writing it -- the debt stands, the flags are down, and
    the commit is still ahead of the remote, which is exactly what this
    recovery publishes. Refused, the issue parks again for the report, as the
    review hold on `validating` parks for it.

    The second is anything but the commit a saved report describes. A body
    edit's resume that recorded its report and died before its push leaves
    the commit it meant to publish named beside that report. A checkout that
    has since moved on -- still ahead of the remote, so nothing about the
    branch looks wrong -- would publish some other head, and the hold behind
    it would then bind the report to that head and hand it to a reviewer. So
    the push is refused, the issue parks for the report the branch as it
    stands is owed, and the record is kept for whoever answers it.

    The third is a report already BOUND and not yet settled, with no delivery
    beside it to replace it: a report alone whose settlement a crash cut
    short, and a commit the checkout gained since. The transaction is held to
    the head it was bound to, so a push moving the pull request off that head
    leaves a report that can never settle, and the round it counts hands a
    reviewer a head nobody described. So it is settled first, through the
    same hold the rebase waits behind: settled, the push goes ahead as any
    recovered commit does; where the checkout cannot vouch for it, the hold
    parks for a human, and where a later tick may settle it, nothing moves.
    """
    bound = _record_state.carries_pending_report(
        ctx.state,
    ) and not _delivery_state.carries_delivered_report(ctx.state)
    if bound or _drift_reports._owes_an_unrecorded_report(ctx.state):
        return _report_hold._owed_report_holds(
            ctx.gh, ctx.spec, ctx.issue, ctx.state, WorkflowLabel.RESOLVING_CONFLICT,
        )
    return _resume_records._refuses_another_head(ctx, recovered_sha)
