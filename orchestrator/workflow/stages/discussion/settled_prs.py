# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Asking whether a commit is already on a pull request, and in what state.

Three things the humans can do leave a publication finished somewhere this host
cannot see, and every path that would push has to rule all three out first. A
MERGE took the branch with it and put the design in the base, so pushing would
recreate a ref GitHub deleted and ask for a pull request with no commits
between its two refs. A CLOSE without merging is the design turned down, so
pushing would open a REPLACEMENT proposing it all over again -- with the issue
then held on that replacement and their rejection left with nothing pointing at
it. An OPEN one whose head they moved past this commit carries it already, so
the only thing a push could send is the older SHA over their own work.

The lookups are by COMMIT, which is what makes an answer of any state safe to
look at: a branch name outlives every pull request opened on it, so widening
the search past `find_open_pr` is only sound because the SHA narrows it back to
the one this publication put there. A lookup nobody could take is handed
straight back rather than narrowed, because the narrowing is what would turn it
into a "no" -- and the pull requests this owner exists to find are exactly the
ones whose commit list is the last place they are still visible.

What a caller may DO with each state is not settled here. A merge is the end of
the matter wherever it is read; a close is the end of it only once an
operator's reset has been ruled out, which belongs to
`recovery._settle_moved_marker` and to nothing on this page.
"""
from __future__ import annotations

from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.workflow.stages.discussion import (
    artifact as _artifact,
    models as _models,
)

# What `pr_state` calls a pull request still taking commits, and the state an
# already-carried publication is adopted rather than pushed to.
_OPEN_PR_STATE = "open"

# What `pr_state` calls a design the humans turned down. It is the one verdict
# a settle cannot act on the moment it sees it: an operator answering the stale
# park may close the stray pull request as part of the very reset that park
# asked for, so the close is only a verdict once the reset has been ruled out.
_CLOSED_PR_STATE = "closed"

# The states a lookup by commit narrows to: every verdict the humans can leave
# on a pull request, since to a publication a merge and a close are the same
# "nothing left to push here". Which of them the caller may act on, and when,
# is the caller's own -- see `_settled_plan_pr` below and
# `recovery._settle_moved_marker`.
_DECIDED_PR_STATES = frozenset((_CLOSED_PR_STATE, "merged"))


def _settled_plan_pr(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact, commit: str,
):
    """The pull request that leaves this commit nothing to publish, if any.

    Asked in the order the two lookups cost: the merged and closed readings are
    one lookup between them, while the open reading has to establish the remote
    tip and its ancestry first. `PR_LOOKUP_UNREADABLE` from either
    short-circuits the rest, since it is truthy and says the question could not
    be put at all.

    What a caller may DO with a close is not decided here, because it depends
    on where the branch is: `recovery._settle_moved_marker` holds that one
    answer back until it has ruled out an operator's reset, since answering the
    stale park can mean closing the stray pull request as well as resetting the
    branch.
    """
    return _plan_pr_by_commit(
        run, artifact, commit, _DECIDED_PR_STATES,
    ) or _plan_pr_overtaken(run, artifact, commit)


def _plan_pr_by_commit(
    run: _models._DiscussionRun,
    artifact: _models._PlanArtifact,
    commit: str,
    wanted_states: frozenset,
):
    """The pull request carrying this commit, when it is in one of these states.

    Searched by commit and across every state, which is the pair of things
    `find_open_pr` cannot do. A tick that opened the plan PR and died before
    persisting its number leaves nothing pinned pointing at it, and by the time
    anything comes back a human may have merged it -- which closes the PR and,
    with auto-delete on, takes the head branch with it. Read as "no PR and no
    branch", the recovery pushes the branch back into existence and asks for a
    second pull request GitHub refuses for having no commits between the two
    refs; read as "nothing was published", it drops the marker and opens
    another round over a design that already merged.

    The commit is what makes an answer of any state safe to look at: a branch
    name outlives every pull request opened on it, so widening the search is
    only sound because the SHA narrows it back to the one this publication put
    there. Which states count is the CALLER's, and so is WHEN each of them may
    be acted on.

    A lookup nobody could take is handed straight back rather than narrowed,
    because the narrowing is what would turn it into a "no": the pull request
    this exists to find has a moved head and possibly a deleted branch, so its
    commit list is the only place it is still visible, and one failed read of
    that list is enough to have the recovery republish over a design the humans
    already settled.
    """
    plan_pr = run.gh.find_pr_for_commit(
        branch=artifact.branch,
        base=run.spec.base_branch,
        head_sha=commit,
    )
    if plan_pr is _pr_reads.PR_LOOKUP_UNREADABLE:
        return plan_pr
    if plan_pr is None or run.gh.pr_state(plan_pr) not in wanted_states:
        return None
    return plan_pr


def _plan_pr_overtaken(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact, commit: str,
):
    """An open pull request carrying this commit with newer work on top of it.

    The other way a publication is already finished. A tick that opened the PR
    and died before recording its number leaves a window a human can push into
    -- their own correction to the design, or the base merged in to make the PR
    mergeable -- and what they leave is a branch head that DESCENDS from the
    commit this publication put there. Nothing is left to push: the commit is
    on the branch, the pull request carries it, and the only thing a push could
    do is send the older SHA over their work.

    Which is exactly what the lease refuses, and refusing was never the
    problem: the problem is what a refusal leaves behind. Parked
    `discussion_push_failed` with no `pr_number` written, the issue sits on a
    pull request nothing recorded, and the reply that retries the publication
    finds the same newer head and refuses again -- a plan published, reviewable,
    and unreachable from the issue that produced it.

    Both readings are needed to say it, and neither alone: the remote head has
    to CONTAIN this commit (a tip that merely differs is somebody else's branch,
    and the divergence park is right about it), and a pull request has to carry
    it (a branch pushed past with no PR is a publication that never opened one).

    The containment half is only askable once that head is in this store. It is
    a commit made after this checkout was, so a retained worktree has never
    seen it, and git refuses an id it cannot resolve -- which would read their
    fast-forward as the divergence this is here to tell apart. A tip nothing
    can bring in is left to the lease the push is held to, which refuses and
    says what is there rather than adopting a pull request on a reading never
    taken.

    A pull-request lookup nobody could take is handed back as itself, for the
    same reason the merged one is: read as "no PR carries this", the branch is
    pushed and the reviewer's own commit goes under the older SHA.

    `commit` is named rather than taken off the artifact because the two
    callers hold it in different places. A checkout still on the published
    commit is asked about its own tip; a checkout REBUILT after the host lost
    it comes back on whatever the remote branch is at -- the reviewer's head,
    not ours -- and there the marker is the only record of what was published.
    Read off the artifact in that case, this asks whether their head descends
    from itself, answers no, and the plan the humans are looking at is refused
    for good.
    """
    remote_tip = _branch_transport._remote_branch_tip(
        run.spec, artifact.worktree, artifact.branch,
    )
    moved_past = (
        remote_tip
        and remote_tip != commit
        and _artifact._readable_remote_tip(run, artifact, remote_tip)
        and _verification_probes._commit_contains(
            artifact.worktree, commit, remote_tip,
        )
    )
    if not moved_past:
        return None
    plan_pr = run.gh.find_pr_for_commit(
        branch=artifact.branch,
        base=run.spec.base_branch,
        head_sha=commit,
    )
    if plan_pr is _pr_reads.PR_LOOKUP_UNREADABLE:
        return plan_pr
    if plan_pr is None or run.gh.pr_state(plan_pr) != _OPEN_PR_STATE:
        return None
    return plan_pr
