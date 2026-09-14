# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a discussion stops being worked, and what it holds on to until then.

The published plan is what ends this conversation, and the pull request
carrying it is the only thing that says how -- so the tick opens by asking
GitHub about that pull request, ahead of every local reading and every path
that could spawn: an issue whose design the humans have already taken or
turned down must not have another round opened over the top of it, and the
answer to "which of the two" is not on this host. `plan_terminal` holds what
comes back of it, the two terminal arcs and the hold an undecided or unreadable
one takes.

That reading answers for a closed issue as much as an open one, which is why it
is taken before the close is even looked at. An operator who closes the issue
while its plan PR is up has said nothing about the plan, so the stage keeps the
label it was on -- which is what leaves the issue inside the closed-issue sweep
-- and waits for the pull request itself to say which terminal applies.
Flipping it to a terminal label there would end the sweep's interest in the
issue on the one reading nobody has taken yet, and the branch would outlive
every pass that knows to clean it up.

A closed issue with NO recorded pull request is where the marker is read, and
it is read before anything is finalized. `discussion_publishing_sha` names a
commit a publication began pushing, and the window between the pull request
being opened and its number being written is one a human can decide inside: a
tick that died there leaves a real pull request with nothing pinned pointing
at it. Taken for a discussion that never published, an OPEN one would have the
issue flipped to a terminal label -- out of the closed-issue sweep, with its
branch and worktree left for nothing to reap -- while its plan sat on a pull
request still waiting for a review nobody would come back for. So the marker's
commit is asked about across every state, and what comes back decides: a
decided pull request is finalized here (its number recorded first, since that
is what the tail names and what cleanup resolves the branch from), an open one
holds exactly as a recorded one does, and a lookup nobody could take decides
nothing at all.

Only once that answer is "there is no pull request" is the close the whole
signal. It finalizes to `rejected` -- the human stop signal, recorded the way
every other stage records it -- and that flip is what takes the issue back out
of the sweep, which would otherwise re-surface it on every pass forever.
Nothing is torn down there: the branch may be carrying an unpublished plan
commit, or belong to a pull request this issue merely arrived here holding, and
this stage does not delete either on the strength of a closed issue alone.

An OPEN issue is not asked any of that. Its unfinished publication belongs to
`publication`, which finishes the push, adopts the pull request already
carrying the commit, and records what it found -- and which refuses to publish
over one the humans have decided, so the terminal above sees it on the tick
after.
"""
from __future__ import annotations

import logging

from orchestrator.git.worktrees import naming as _naming
from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.github.issues import (
    _ISSUE_STATE_CLOSED,
    _ISSUE_STATE_OPEN,
    _STATE_ATTR,
)
from orchestrator.workflow.engine import (
    terminal_context as _terminal_context,
    terminal_effects as _terminal_effects,
)
from orchestrator.workflow.stages.discussion import (
    models as _models,
    plan_terminal as _plan_terminal,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# What `pr_state` calls a plan still taking commits -- the state that decides
# nothing, and therefore the one a hold is measured by.
_OPEN_PR_STATE = "open"


def _drain_discussion_terminals(run: _models._DiscussionRun) -> bool:
    """True when this tick is over before any round could open.

    Asked first, and asked of GitHub rather than of the checkout, because
    both endings this stage has are things a human did somewhere else: they
    merged the plan, they closed it, or they closed the issue carrying it.

    The published-plan reading comes first and answers for the closed issue as
    well as the open one. An issue an operator closed while its plan PR is
    still up is not a discussion to finalize -- the design is still with the
    humans -- so it holds here with its label, its worktree, and its branches
    exactly as they stand until the pull request itself resolves.

    An OPEN issue with no such record has nothing here to decide: whatever its
    publication left behind is `publication`'s to finish, and a tick that
    finalized on that state would be ending a conversation still running.
    """
    if _state._plan_published(run.state):
        return _plan_terminal._drain_plan_pr(run)
    if not _issue_closed(run.issue):
        return False
    return _finalize_closed_discussion(run)


def _issue_closed(issue) -> bool:
    """Whether a human has closed the issue this discussion is on."""
    return getattr(
        issue, _STATE_ATTR, _ISSUE_STATE_OPEN,
    ) == _ISSUE_STATE_CLOSED


def _finalize_closed_discussion(run: _models._DiscussionRun) -> bool:
    """Decide a closed issue whose plan PR is not in the records yet.

    "Not in the records" is not the same as "does not exist", and the
    difference is a crash window: the publication opens the pull request
    before it writes the number down, so a tick that died in between leaves
    one nothing pinned points at. The marker it wrote first is what points at
    it instead, and this is where that is spent -- ahead of the pre-PR
    finalize below, which would otherwise take a human's open plan PR for a
    discussion that never published one and flip the issue out of the
    closed-issue sweep that is the only thing still watching it.

    A decided pull request is finalized on the spot, exactly as a recorded one
    would be. An open one holds for the same reason a recorded open one does.
    A lookup GitHub declined decides nothing and is asked again next tick --
    the issue is already closed, so holding costs a poll and risks nothing.

    The branch is resolved ONCE, here, before anything writes: the lookup that
    finds the pull request and the record that decides which ref gets reaped
    have to name the same one, and the resolver's own answer moves under a
    write. It reads `pr_number` in the absence of a pinned `branch` and infers
    the pre-namespace `orchestrator/issue-N` from it, which is right for a
    legacy in-flight PR and wrong for everything else -- so a branch resolved
    AFTER the recovered number was set would reap a ref this stage never
    pushed, leaving the real local and remote branches behind.
    """
    branch = _plan_branch(run)
    plan_pr = _interrupted_plan_pr(run, branch)
    if plan_pr is _pr_reads.PR_LOOKUP_UNREADABLE:
        log.warning(
            "issue=#%s holding a closed discussion: GitHub could not say "
            "whether its unfinished publication is on a pull request",
            run.issue.number,
        )
        return True
    if plan_pr is None:
        _reject_closed_discussion(run)
        return True
    if run.gh.pr_state(plan_pr) != _OPEN_PR_STATE:
        _record_recovered_pr(run, plan_pr, branch)
        _plan_terminal._finalize_by_pr_state(run, plan_pr)
    return True


def _interrupted_plan_pr(run: _models._DiscussionRun, branch: str):
    """The pull request an unfinished publication left behind, if there is one.

    None covers both ways there is nothing to find: no publication was in
    flight at all, and one was but no pull request carries the commit it named
    -- a push that never landed, or one whose pull request was never opened.
    Either way the close below is the whole signal.

    Searched by that commit across every state, for the same reason the
    publication's own recovery searches that way: a branch name outlives every
    pull request opened on it, and the humans can merge or close one inside the
    window this exists for -- which takes it out of the open set entirely, and
    with auto-delete on takes its head branch too.

    `branch` is handed in rather than resolved here so the ref this searches
    and the ref the finalize reaps are the same one -- see the caller.
    """
    in_flight = run.state.get(_state._PUBLISHING_SHA)
    if not in_flight:
        return None
    return run.gh.find_pr_for_commit(
        branch=branch,
        base=run.spec.base_branch,
        head_sha=str(in_flight),
    )


def _plan_branch(run: _models._DiscussionRun) -> str:
    """The ref the publication pushed to, resolved the way every reader does."""
    return _naming._resolve_branch_name(
        run.state, run.spec, run.issue.number,
    )


def _record_recovered_pr(
    run: _models._DiscussionRun, plan_pr, branch: str,
) -> None:
    """Name the pull request this issue is about to be finalized against.

    The terminal tail reads the number off pinned state and resolves the
    branch it reaps from there too, so the record the crash skipped has to be
    made before the finalize rather than after it. It rides that finalize's own
    write, which is also what retires the marker: what it was there to say --
    somebody has to finish this -- is what this tick is doing.

    The branch is pinned beside the number, and it is the one the CALLER
    resolved before either was set. Left to the resolver to work out
    afterwards, a state carrying a recovered number and no pinned branch reads
    as a legacy in-flight pull request and answers `orchestrator/issue-N` --
    a ref this stage never pushed, whose reap would leave the real local and
    remote branches standing.

    The plan path is deliberately NOT written beside them. That record is the
    publication's claim to have validated an artifact, and nothing here
    inspected one; the issue is ending either way, and a claim nobody checked
    would outlive it in the pinned comment.
    """
    run.state.set(_state._BRANCH, branch)
    run.state.set(_state._PR_NUMBER, plan_pr.number)
    run.state.set(_state._PUBLISHING_SHA, None)


def _reject_closed_discussion(run: _models._DiscussionRun) -> None:
    """Record a discussion a human closed before it published anything.

    The same tail every stage's manual close takes -- the
    `closed_without_merge_at` stamp, the `rejected` label, the usage receipt
    ahead of the single write -- and no event, because there is no pull request
    for one to name. The flip is what takes the issue back out of the
    closed-issue sweep; without it the sweep would re-surface this issue on
    every pass and find the same nothing to do.

    No teardown rides with it, deliberately. This stage opened no pull request
    here, so what is on the branch is either an unpublished plan commit or the
    history of a pull request the issue arrived carrying, and neither is
    something a closed issue alone justifies deleting.
    """
    _terminal_effects._finalize_closed_issue_with_open_pr(
        _terminal_context._ReviewTerminalContext(
            gh=run.gh,
            spec=run.spec,
            issue=run.issue,
            state=run.state,
            pr=None,
            stage=_state._DISCUSSION_STAGE,
        ),
    )
