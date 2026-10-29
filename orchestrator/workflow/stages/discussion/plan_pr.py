# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The plan's pull request, and the session every one of them has to name.

One is opened only when the branch does not already have an open one against
the base. A tick that died between `open_pr` and the pinned write left a pull
request up with nothing pointing at it, and the next tick re-derives the same
publishable artifact from the same branch -- so asking for the open one first
is what turns that replay into a reuse instead of a duplicate GitHub would 422,
and why the `pr_opened` event is emitted only on the branch that really opened
one, so a recovered publication is not counted twice. That lookup is a request,
so the checkout is proven the issue's own again behind it, before the body is
edited or anything is opened.

What comes back from that lookup is only guaranteed to be open on this branch
against this base, never that anything here opened it. A human can open one by
hand on the branch the plan was pushed to, and an issue can arrive at this
stage with one already up. So the reuse fixes up the body rather than trusting
it, and what it checks for is the named SESSION: that line is the whole reason
the body exists, since it is what lets a reviewer follow a published plan back
to the conversation that agreed it. Its presence leaves everything else the
body says alone, including a human's own additions to ours.

Which is why a plan nothing can attribute is refused before any of this, on
every path that touches a pull request. A round that opened a NEW conversation
drops the previous pin before it spawns and records the id it opened only when
it reports, so one cut short in between leaves a valid plan commit with no
session to name -- and every ending is wrong for it.
"""
from __future__ import annotations

import logging

from orchestrator.git.publication import titles as _titles
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.workflow.stages.discussion import (
    models as _models,
    publication_parks as _publication_parks,
    session as _session,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_PR_OPENED_EVENT = "pr_opened"


def _reuse_or_open_plan_pr(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
):
    """Return the plan's PR, reusing the open one a prior tick left behind.

    A tick that died between opening the PR and writing its records left the
    PR up and nothing pointing at it, and the next tick re-derives the same
    publishable artifact from the same branch. Asking for the open PR first is
    what turns that replay into a reuse instead of a duplicate -- and why the
    `pr_opened` event is emitted only on the branch that really opened one, so
    a recovered publication is not counted twice.

    What comes back is only guaranteed to be open on this branch, not to be
    the one a previous tick of this stage opened, so the reuse fixes up the
    body rather than trusting it.

    Behind the lookup the checkout is proven the issue's own again
    (`creation._proven_checkout`), ahead of the body's edit or the open: the
    lookup is a request, and a tree switched onto the flat branch while it
    ran raises `naming.BranchRefused` with nothing opened or edited, and the
    publication's marker standing for the recovery that finds the checkout
    restored. Where one is to be opened, the title is read off the branch's
    history first and the proof taken immediately before the open, since
    that read is a window of its own.
    """
    plan_pr = run.gh.find_open_pr(
        branch=artifact.branch, base=run.spec.base_branch,
    )
    if plan_pr is not None:
        _worktree_creation._proven_checkout(run.spec, run.issue.number, artifact.worktree)
        log.info(
            "issue=#%s reusing existing plan PR #%d for %s",
            run.issue.number, plan_pr.number, artifact.branch,
        )
        _attribute_reused_pr(run, artifact, plan_pr)
        return plan_pr
    title = _plan_pr_title(run, artifact)
    body = _plan_pr_body(run, artifact)
    _worktree_creation._proven_checkout(run.spec, run.issue.number, artifact.worktree)
    plan_pr = run.gh.open_pr(
        branch=artifact.branch, base=run.spec.base_branch, title=title, body=body,
    )
    run.gh.emit_event(
        _PR_OPENED_EVENT,
        issue_number=run.issue.number,
        stage=_state._DISCUSSION_STAGE,
        pr_number=plan_pr.number,
        branch=artifact.branch,
        sha=artifact.head_sha or None,
    )
    return plan_pr


def _attribute_reused_pr(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact, plan_pr,
) -> None:
    """Make a reused PR say which session's plan it is now carrying.

    A PR open on this branch is not necessarily one of ours: it can be a PR an
    issue arrived here with, or one an operator opened by hand, and adopting
    it silently would leave the published plan described by a body about
    something else. The named session is the whole point of the body -- it is
    what lets a reviewer find the conversation the plan came out of -- so its
    absence is what triggers the rewrite, and its presence leaves whatever
    else the body says alone, including a human's own additions to ours.
    """
    if _plan_pr_attribution(run) in (plan_pr.body or ""):
        return
    log.info(
        "issue=#%s rewriting reused plan PR #%d body to name this stage",
        run.issue.number, plan_pr.number,
    )
    run.gh.edit_pr_body(plan_pr, _plan_pr_body(run, artifact))


def _attributable_plan(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> bool:
    """True when there is a conversation to publish this plan under.

    The one question every path that touches a pull request has to answer
    first, because the answer is what the body says and what a reviewer
    follows back to the design being agreed. A round that opened a NEW
    conversation drops the previous pin before it spawns and records the id it
    opened only when it reports, so one cut short in between leaves a valid
    plan commit nothing here can name -- and every ending is wrong for it. The
    push would open a pull request under a placeholder; the ADOPTION of one
    already carrying the commit is worse, since that pull request need not be
    ours at all (the lookup proves branch, base and commit and nothing else),
    and it would be recorded as the published plan and rewritten to say
    `session None`.

    The refusal asks for the reset that makes a re-run possible, and it is
    written once. Its own reason is what the repeat reads, so an operator who
    has not answered yet is not told again on every poll -- which matters for
    the adoption in particular: that path is reached ahead of the turn-taking
    gate, by a marker the reply has not spent.
    """
    if _session._recorded_session_id(run.state) is not None:
        return True
    if run.state.get(
        _state._PARK_REASON,
    ) != _state._DISCUSSION_PLAN_UNATTRIBUTED:
        _publication_parks._park_unattributed_plan(run, artifact)
    return False


def _plan_pr_title(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> str:
    """Title the plan PR the way a dev PR is titled: from its own commit.

    The agent wrote the plan and its subject in the repository's own style, so
    reusing that subject makes the PR read like the repository it lands in.
    The issue title and the prefix inferred from recent base history are the
    same two fallbacks every other PR here falls to.
    """
    first_subject = _titles._first_commit_subject(
        run.spec, artifact.worktree,
    )
    fallback_prefix = _titles._infer_subject_prefix(
        run.spec, artifact.worktree, run.issue,
    )
    return _titles._pr_title_from_commit_or_issue(
        run.issue, first_subject, fallback_prefix,
    )


def _plan_pr_attribution(run: _models._DiscussionRun) -> str:
    """Name the session whose plan a PR carries.

    Read from the identity the conversation is pinned to rather than from the
    current config, for the same reason every round is: a `DECOMPOSE_AGENT`
    flip must not re-attribute what already ran. It is its own line because
    two owners need it -- the body that states it, and the reuse that checks
    a PR of unknown provenance for it before adopting that PR as the plan's.

    The id is always there to name: a publication with none is refused before
    it reaches here, rather than published under a placeholder no reviewer
    could follow.
    """
    session = _session._locked_discussion_session(run.state)
    return (
        f"Generated by orchestrator ({session.backend} session "
        f"`{session.session_id}`) in the `discussion` stage."
    )


def _plan_pr_body(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> str:
    """Say what the PR is, which session wrote it, and what deciding it does.

    What a decision on it MEANS is the part a reviewer cannot infer from the
    diff: this pull request is the design being agreed, so taking it finishes
    the issue rather than starting anything, and having the plan built is a
    relabel made BEFORE either button is pressed. This body is the only thing
    that reaches the person about to press one.

    No closing keyword appears anywhere in it all the same, and that is not a
    contradiction. What a merge meant is this stage's to record -- the stamp,
    the usage receipt, the event, and the teardown all ride the terminal it
    drains -- and `Resolves #N` would have GitHub close the issue with none of
    it written. The keyword also outlives the label it was written under: a
    relabel to `workflow:implementing` hands the developer this very pull
    request, and a closing keyword there would let a merge of the plan alone
    close the issue as finished work -- the exact reading `discussion_plan_path`
    exists to refuse.
    """
    issue_number = run.issue.number
    plan_summary = (
        "The resolved decisions, the evidence behind them, the alternatives "
        "considered, the risks, and the implementation plan are in "
        f"`{artifact.plan_path}`; this branch changes nothing else, and no "
        "implementation starts from here. Merging it is agreeing to the "
        f"design: the orchestrator finishes #{issue_number} as `done`, closes "
        "it, and removes the branch this pull request was opened from. "
        "Closing this pull request unmerged finishes the issue as `rejected` "
        f"the same way. To have the plan BUILT instead, relabel #{issue_number} "
        "`workflow:implementing` before doing either."
    )
    return "\n".join((
        f"Plan for #{issue_number}, as agreed on the issue thread.",
        "",
        _plan_pr_attribution(run),
        "",
        plan_summary,
    ))
