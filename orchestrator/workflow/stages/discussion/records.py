# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finished publication writes down, and who is told about it.

All four records land in one durable write -- the park's where the pull request
is still open, and the caller's own where it has already been decided -- so an
issue is never left carrying a PR number without the branch it is open against
or a plan path without the PR that reviews it. That same write retires the
in-flight marker, because what the marker was there to say -- somebody has to
finish this -- is exactly what these records now answer.

Which write it rides depends on what the pull request is. An OPEN one is a
design still waiting on the humans, so the records ride the park that tells
them where to read it. One they have already DECIDED -- merged, or closed
without merging, which only the recovery ever adopts -- is not: telling
somebody to go and review what they have just settled would answer a verdict
with instructions, so there the records are persisted on their own and nothing
is said on the thread. `terminal` reads them on the next tick and
`plan_terminal` finishes the issue `done` or `rejected`, with the usage receipt
and the teardown, which is the whole of what is left to say.

Two of those records are not bookkeeping. `pr_number` and `branch` are what a
later checkout is restored from, and the round anchor is moved onto the
published tip because the implementing relabel guard measures the branch
against it: left at the tip the round opened on, the very commit this stage
just published would read as work nobody vouched for, and the operator moving
the issue on to be built would be told to reset it away.
"""
from __future__ import annotations

import logging

from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.workflow.stages.discussion import (
    models as _models,
    plan_pr as _plan_pr,
    publication_parks as _publication_parks,
    settled_prs as _settled_prs,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _record_landed_plan(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact, plan_pr,
) -> None:
    """Finish a publication whose pull request already carries the commit.

    Nothing is pushed and nothing is opened, because both would be wrong: what
    the push would send is on the branch already, and what the open would ask
    for exists. What is left to do is what the crash skipped -- writing down
    which PR the plan is on -- and the records that do it are the same ones a
    live publication ends with, so the issue comes out of this holding exactly
    what it would have held had the tick not died.

    A merge is one way in, and pushing there would recreate a ref GitHub
    deleted on purpose and ask for a pull request with no commits between its
    two refs. A close without merging is the second, and pushing there would
    ask the humans for a design they have just turned down -- on a REPLACEMENT
    pull request, leaving their rejection with nothing pointing at it. The
    third is an open pull request whose head a human moved past this commit
    while still carrying it, and pushing there would send the older SHA over
    their work.

    What the park says depends on which of them it was, because the park is
    what the humans read. An OPEN one is a design still waiting on them, and
    the message says where to review it and how to have it built. A DECIDED one
    is not: they merged or closed it already, and telling them to go and review
    it would be answering a verdict they have given with instructions they have
    no use for. So the records are written on their own there, and what speaks
    instead is the very next tick's terminal: `terminal` reads them, and
    `plan_terminal` finishes the issue `done` or `rejected` with the usage
    receipt and the teardown.
    The open-round flag is retired by hand on that path, because the park
    funnel is what retires it everywhere else: a round whose plan is on a pull
    request has reported, and a flag left standing would have a later tick
    treat somebody else's commit as this round's.

    Nothing happens at all without a session to name, which is asked before
    the pull request is touched rather than after: this path reaches one
    ahead of the push's own refusal, so a plan nothing can attribute would
    otherwise be recorded as published here and never reach it.

    The body is then made to name that session, through the same check the
    ordinary reuse runs. What the lookup that found this pull request proves is
    only that it is on this branch, against this base, and carries this commit
    -- never that anything here opened it. A human can open one by hand on the
    branch the plan was pushed to, and merging it or writing on top of it puts
    it on exactly this path; recorded as the artifact, the plan would be
    reachable from the issue and described by a body about something else, or
    by no body at all. Naming the session is the whole reason the body exists,
    so an adoption is not finished until it does.

    One that already names it is left exactly as it stands, merged or not: it
    is this stage's own pull request, opened by the publication that crashed,
    and a design the humans have merged or written their own commit on top of
    is not one to rewrite back at them -- annotations and all.

    The lookup that found the pull request is a request, so the checkout the
    artifact was read from is proven the issue's own again first
    (`creation._proven_checkout`): a tree switched onto the flat branch while
    it ran raises `naming.BranchRefused` with no body edited, nothing
    recorded, and the publication marker standing for the tick that finds the
    checkout restored. It is proven again behind the body's edit, before the
    records that retire the marker, since that edit is a request too.
    """
    _worktree_creation._proven_checkout(run.spec, run.issue.number, artifact.worktree)
    if not _plan_pr._attributable_plan(run, artifact):
        return
    log.info(
        "issue=#%s plan %s is already on PR #%d (%s); recording it rather "
        "than publishing again", run.issue.number, artifact.plan_path,
        plan_pr.number, run.gh.pr_state(plan_pr),
    )
    _plan_pr._attribute_reused_pr(run, artifact, plan_pr)
    _worktree_creation._proven_checkout(run.spec, run.issue.number, artifact.worktree)
    _record_published_plan(run, artifact, plan_pr.number)
    if run.gh.pr_state(plan_pr) == _settled_prs._OPEN_PR_STATE:
        _publication_parks._park_published_plan(run, artifact, plan_pr.number)
        return
    run.state.set(_state._ROUND_OPEN, None)
    run.gh.write_pinned_state(run.issue, run.state)


def _record_published_plan(
    run: _models._DiscussionRun,
    artifact: _models._PlanArtifact,
    pr_number: int,
) -> None:
    """Stage what was published, where it lives, and what certifies it.

    All four land in one durable write -- the park's where the pull request is
    still open, and the caller's own where it has already been decided and
    there is nothing to say on the thread -- so an issue is never left carrying
    a PR number without the branch it is open against or a plan path without
    the PR that reviews it.

    The anchor is the load-bearing one. It records the branch and the tip this
    stage vouches for, and moving it onto the published commit is what lets
    the operator relabel the issue to be built: the implementing guard reads
    the branch against that SHA, and an anchor still pointing at the tip the
    round opened on would convict the branch of the very commit this
    publication just put on a PR -- and offer, as the remedy, resetting it
    away.

    The commit that PR carries is recorded beside its number, because the
    number alone does not say what is on it. The implementing stage reads that
    SHA against the PR's head to know whether a merge there is a human agreeing
    to a design or work finishing, and asking GitHub is what makes the answer
    right even when a tick pushed onto this PR and died before recording it.
    Until that stage retires the path record above, the path is what answers:
    the humans may amend their own plan on its PR, and a head they moved is not
    an implementation to close the issue on.

    The in-flight marker is retired in the same write, because what it was
    there to say -- somebody has to finish this -- is exactly what these
    records now answer.
    """
    run.state.set(_state._PLAN_PATH, artifact.plan_path)
    run.state.set(_state._BRANCH, artifact.branch)
    run.state.set(_state._PR_NUMBER, pr_number)
    run.state.set(_state._PLAN_SHA, artifact.head_sha)
    run.state.set(_state._ROUND_BRANCH, artifact.branch)
    run.state.set(_state._ROUND_SHA, artifact.head_sha)
    run.state.set(_state._PUBLISHING_SHA, None)
    log.info(
        "issue=#%s published plan %s as PR #%d on %s",
        run.issue.number, artifact.plan_path, pr_number, artifact.branch,
    )
