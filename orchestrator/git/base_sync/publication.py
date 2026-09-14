# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Force-publishing one clean rebase, and the surfaces it then lands on.

The lease-pinned push is the commit point of the whole auto-rebase: until
the rewritten branch is on the remote, the head the reviewer votes on is
still the pre-rebase SHA. So every check that can still refuse -- an
unreadable HEAD, a rewrite that moved nothing, a tree that came back dirty
-- runs before it and hands off to ``guards``, and the lease itself is
pinned to that same pre-rebase SHA so a foreign update rejects the push
instead of being clobbered. Only an accepted push earns the tail: the PR
notice, the audit event, the `validating` relabel, and last the
`write_pinned_state` that commits the cleared anchor and reset review
round, so a tick that dies partway leaves the anchor pinned for the next
one to recover from.

The rebase is also a REWRITE of whatever the branch was standing on, and on
an issue whose exemption names that commit it is the rewrite that would
punish it: the exemption names one commit and only it, so the replayed
object is measured past the same ceiling and the change a human already
adjudicated goes back into adjudication with a pull request open over it.
So the gate is handed evidence beside the candidate, and ``transfers``
assembles it: the pair the exemption already records, the pair the rebase
produced, and the publication and pre-rebase anchor the push is made against.
It is assembled there rather than here because the tick that makes the rewrite
is not the only one that needs it. Nothing rules on it either place:
`late_transfer` grants or refuses the permit, and a refusal simply leaves the
ordinary cumulative gate to measure the rebase like any other candidate, which
is what a base advance that changed the contribution has to get.
"""
from __future__ import annotations

from orchestrator.git.base_sync import attempts, guards, transfers
from orchestrator.git.base_sync.models import _AutoRebaseContext
from orchestrator.git.base_sync.state import _REVIEW_ROUND, log
from orchestrator.git.verification import probes, status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.state import WorkflowLabel, stage_name


def _gated_publication():
    """The size gate the rebase push passes, imported where it is used.

    A rebase onto a base that has moved changes what the branch adds to it, so
    the pull request can cross the ceiling with nobody having written a line.
    Lazily bound for the reason the comment owner beside it is: the gate sits
    in the workflow layer above this package, and binding it at module load
    would make every git-side import pay for the stage tree it pulls in.
    """
    from orchestrator.workflow.stages.implementing import late_push
    return late_push


def _gate_records():
    """The subject and terms one gated publication is described by.

    The gate's own record owner, reached the same way and for the same
    reason: what this package hands the gate is a subject built from the
    context it already holds, and building one costs the same upward hop the
    call does.
    """
    from orchestrator.workflow.stages.implementing import late_records
    return late_records


def _post_auto_rebase_notice(
    context: _AutoRebaseContext,
    after_sha: str,
) -> None:
    """Post the best-effort PR notice for a published clean rebase."""
    # Lazy import: the comment owner sits in the workflow layer above this
    # package, so binding it at module load would make every git-side
    # import pay for the GitHub client and prompt state it pulls in.
    from orchestrator.workflow.engine import comments as _comments
    spec = context.spec
    after_short = after_sha[:8]
    try:
        _comments._post_pr_comment(
            context.gh,
            context.pr_number,
            context.state,
            f":mag: PR was {context.behind} commit(s) behind "
            f"`{spec.remote_name}/{spec.base_branch}`; "
            "orchestrator auto-rebased the branch and re-pushed it. "
            f"Routing `{context.label}` -> `{WorkflowLabel.VALIDATING}` so "
            f"the reviewer re-runs against the new head (`{after_short}`).",
        )
    except Exception:  # noqa: BLE001 - the PR notice is best effort at the GitHub boundary
        log.exception(
            "issue=#%s could not post auto-rebase notice to PR #%s",
            context.issue.number,
            context.pr_number,
        )


def _emit_auto_rebase_event(
    context: _AutoRebaseContext,
    after_sha: str,
) -> None:
    """Emit the stable audit shape for a published clean rebase."""
    context.gh.emit_event(
        "base_rebased",
        issue_number=context.issue.number,
        stage=stage_name(context.label),
        pr_number=context.pr_number,
        sha=after_sha,
        method="auto_clean_rebase",
        review_round=int(context.state.get(_REVIEW_ROUND) or 0),
        retry_count=context.state.get("retry_count"),
    )


def _finalize_auto_rebase(
    context: _AutoRebaseContext,
    branch: str,
    after_sha: str,
) -> None:
    """Publish the notice, audit event, validating route, and pinned state.

    The announcement is made durable in the middle of that sequence and the
    break is the point. Everything this tail announces -- the notice on the
    pull request, the `base_rebased` event on both sinks -- goes out before
    the relabel, and the write that clears the attempt goes out after it, so a
    process lost in between would come back to a record that looks unfinished
    and say all of it a second time for one publication that happened once.
    Written while the anchor and the replay still stand, since those are what
    bring that tick back at all, and the clear rides this tail's own last
    write so they stand until every road is behind it.

    The round is reset ahead of the event rather than with the clear, because
    the event reports the round the reviewer is being asked to spend afresh on
    the rewritten head, and a crash past that write leaves the same 0 the
    finish itself would have written.
    """
    _post_auto_rebase_notice(context, after_sha)
    context.state.set(_REVIEW_ROUND, 0)
    log.info(
        "issue=#%d auto base rebase pushed %s/%s -> %s; routing %r -> "
        "validating",
        context.issue.number,
        context.spec.remote_name,
        branch,
        after_sha[:8],
        context.label,
    )
    _emit_auto_rebase_event(context, after_sha)
    attempts._announces(context, after_sha)
    attempts._clears_the_attempt(context.state)
    context.gh.set_workflow_label(context.issue, WorkflowLabel.VALIDATING)
    context.gh.write_pinned_state(context.issue, context.state)


def _publish_auto_rebase(
    context: _AutoRebaseContext,
    before_sha: str,
) -> None:
    """Validate and force-publish a successfully rebased PR worktree."""
    after_sha = probes._head_sha(context.worktree)
    if not after_sha:
        guards._park_unreadable_post_rebase_head(context, before_sha)
        return
    if after_sha == before_sha:
        guards._finish_noop_auto_rebase(context)
        return

    # Before the first step that can leave this replay standing. The head is
    # what says the divergence a later tick finds is this attempt's own work
    # rather than a worktree somebody rebuilt, and everything below -- the
    # dirty park, the gate that may hand the issue to an adjudication, the
    # push, the finalize -- leaves a rewritten branch behind if the process
    # dies under it.
    attempts._records_the_replay(context, after_sha)
    dirty_files = _worktree_status._worktree_dirty_files(context.worktree)
    if dirty_files:
        guards._park_dirty_auto_rebase(context, before_sha, dirty_files)
        return

    branch = _naming._resolve_branch_name(
        context.state, context.spec, context.issue.number,
    )
    records = _gate_records()
    published = _gated_publication()._publishes(
        records._gate(
            context.gh, context.spec, context.issue, context.state,
            context.worktree,
        ),
        branch,
        records._Entered(
            head=before_sha or "",
            reconciling=True,
            # The head this refresh read for itself, and the one the notice,
            # the audit event, and the log line below all name. Between that
            # read and the gate's own the worktree is writable, so a commit
            # landing in the window would be pushed and receipted here while
            # the tail went on to finalize the SHA this owner read. Named, the
            # two are one decision and a checkout that moved refuses before
            # anything reaches the remote.
            candidate=after_sha,
            # What this rebase replaced, so a replay of the exact commit an
            # adjudication accepted is recognized as the same contribution
            # rather than measured past the same ceiling and adjudicated a
            # second time with a pull request already open over it.
            rewrite=transfers._rewritten_by_the_rebase(
                context, before_sha, after_sha,
            ),
        ),
    )
    if published.held:
        # The size gate owns the issue from here -- parked, or handed to the
        # adjudication under `workflow:decomposing` -- so the notice, the
        # audit event, and the `validating` route below are not this refresh's
        # to make. The pinned write still is: a park leaves its flags in
        # memory for the caller that took it.
        context.gh.write_pinned_state(context.issue, context.state)
        return
    if not published.landed:
        guards._park_failed_auto_rebase_push(context, before_sha, branch)
        return
    _finalize_auto_rebase(context, branch, after_sha)
