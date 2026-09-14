# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One documenting tick, in the order its questions have to be asked.

The preconditions come first because each of them makes the spawn pointless or
unanchored. Drift comes next, ahead of the parked-no-input fast path, so a body
edit still unwinds an issue that is sitting parked -- the reverse order would
leave a stale approval standing behind a park nobody replied to.

The tick opens by ending the handoff record that brought the issue here, if
one is still standing: the approval that moved the label drops it in a write
behind that move, so a record this stage can see is that write having failed,
and only this stage's having the issue proves the move itself landed.

After the run the order matters just as much: the interruption and live-pause
refusals both precede the disposition and both return WITHOUT writing pinned
state, so the mutations the pass staged -- the advanced watermark, the
pre-spawn `docs_checked_sha` -- are discarded and the next process re-derives
the tick from what durable state still says. Committed docs work stays on the
branch and republishes through the recovered-commit shortcut.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import guards as _guards, usage as _usage
from orchestrator.workflow.stages.documenting import (
    drift as _drift,
    handoff as _handoff,
    models as _models,
    outcomes as _outcomes,
    preconditions as _preconditions,
    publication as _publication,
    run as _run,
)


def _drive_documenting_pass(ctx: _models._DocumentingContext):
    """Prepare the worktree, run the docs pass, and return the run outcome.

    Returns a `_DocumentingRun` ready for disposition, or None when the tick
    is already fully handled and the caller must return without disposition:
    a fetch / diverged-branch park, a docs pass a settled adjudication
    finished, an awaiting-human resume with no new comment, a shutdown-sweep
    interruption, or an operator pause.
    """
    wt = _worktree_creation._ensure_pr_worktree(
        ctx.spec, ctx.issue.number, branch=ctx.branch,
    )

    run = _documenting_run(ctx, wt)
    if run is None:
        return None

    ctx.state.set("last_agent_action_at", _usage._now_iso())

    # Shutdown-sweep interruption: a docs run the orchestrator killed
    # mid-flight has no trustworthy result (the recovered `ahead > 0` shape
    # synthesizes its own non-interrupted result, so only a real resume /
    # fresh-docs spawn can land here). Ignore it and return WITHOUT writing
    # pinned state -- the pre-spawn `docs_checked_sha` / watermark mutations
    # are discarded so the next process re-runs the docs pass.
    if _guards._ignore_if_interrupted(ctx.issue, run.agent_result):
        return None

    # Live pause applied while the docs agent ran: honor the decision the
    # resume helper already made (the recovered `ahead > 0` shape ran no agent
    # and reports False). Stop before the disposition posts a PR comment,
    # pushes, advances to `in_review`, or writes pinned state. The committed
    # docs work stays on the branch and republishes through the
    # recovered-worktree path once the label is removed.
    if run.paused:
        return None

    return run


def _documenting_run(ctx: _models._DocumentingContext, wt):
    """Prepare the checkout and produce the run this tick disposes.

    Returns None wherever there is nothing left for a disposition to act on: a
    fetch or diverged-branch park, a docs pass a settled adjudication finished
    here, or one of the run shapes that ends the tick on its own.

    The settled pass is asked between the two because it is a claim about the
    reading above and an answer instead of the run below. The size gate holds
    a docs commit off its pull request, the adjudication publishes it, and the
    label comes back here with the handoff still owed -- so the branch reads
    as in sync with its remote, which is what an issue no docs pass has run
    for reads as, and the run below would spawn a second agent over work the
    first one already published.
    """
    standing = _run._prepare_documenting_worktree(ctx, wt)
    if standing is None:
        return None
    ahead, remote_head = standing
    if _publication._finished_settled_docs(ctx, wt, ahead):
        return None
    return _run._run_documenting_dev(ctx, wt, ahead, remote_head)


def _handle_documenting(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    state = gh.read_pinned_state(issue)
    pr_number = state.get("pr_number")

    # A handoff record `validating` left behind is one whose relabel landed --
    # this stage has the issue -- and whose cleanup write did not. Ended here
    # because nothing else can: the route that reads it back cannot tell that
    # record from one whose relabel never happened, and would answer a drift
    # unwind's re-review by relabelling the unchanged head straight back.
    _handoff._ends_the_validating_handoff(gh, issue, state)

    if _preconditions._documenting_preconditions_handled(
        gh, spec, issue, state, pr_number,
    ):
        return

    ctx = _models._DocumentingContext(
        gh, spec, issue, state,
        _naming._resolve_branch_name(state, spec, issue.number),
        pr_number,
    )

    if _drift._reconcile_documenting_drift(ctx):
        return

    if _preconditions._documenting_parked_no_input(gh, issue, state):
        return

    run = _drive_documenting_pass(ctx)
    if run is None:
        return

    _outcomes._dispose_documenting_outcome(ctx, run)
