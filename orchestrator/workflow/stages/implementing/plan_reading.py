# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the recorded plan PR carries, and where that leaves the branch.

Two readings, and both halves of a read-only relabel rest on them: the guard
that screens an operator's move to `implementing` takes them once before it
rules on anything, and the reconcile that keeps an accepted handoff in step
with its pull request takes them again on every tick until a developer
publishes. Neither may decide on a remembered answer. Between the publication
and the relabel the humans have had that design on a pull request -- they can
correct the Markdown on it, or merge the base into its branch to make it
mergeable -- and a head they moved is the one thing no record here can report.

The second reading has to move the ref before it can answer. Where the
developer starts is where the branch REALLY ends up, never where the anchoring
meant to put it, so the checkout is brought forward first and what comes back
is what gets recorded. A move that established nothing is not a tip at all: the
caller holds rather than spawning a developer on a design its reviewers
replaced, whose ordinary push would read their head off the remote as its own
lease and overwrite it.

A read that fails is the same answer both times -- nothing was established --
and it ends the tick where it happened, writing nothing, since every decision
behind it is durable and the next tick asks again from the same state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import (
    anchoring as _anchoring,
    naming as _naming,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.discussion.state import (
    _PR_NUMBER,
    _ROUND_SHA,
    _plan_published,
)

log = logging.getLogger("orchestrator.workflow")

# What `pr_state` calls a pull request whose head landed on the base branch.
_MERGED_PR_STATE = "merged"


@dataclass(frozen=True)
class _ReviewedPlan:
    """What GitHub says this issue's plan PR is, right now.

    `head` is the commit it carries -- the design as its reviewers left it --
    and `merged` says that design landed. The second changes where the
    developer starts: a merged plan is in the base along with everything else
    that has landed since, and the branch it was open against may not even
    exist any more, so the base is the tip to build from rather than the commit
    that merged.

    An issue with no published plan carries neither, which is every
    question-stage park and every discussion that never got as far as an
    artifact.
    """

    head: str = ""
    merged: bool = False


@dataclass(frozen=True)
class _HandoffTip:
    """The tip a relabel hands over, or that it cannot be handed over yet.

    `pending` is the second one, and it is not a tip at all: the reviewed head
    could not be put on the branch, so there is nothing this stage may record
    and nothing it may run. Accepting the relabel anyway would spawn the
    developer on a commit the reviewers moved past and let the ordinary push
    that follows read their head off the remote as its own lease.
    """

    sha: str | None = None
    pending: bool = False


def _reviewed_plan(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _ReviewedPlan | None:
    """Read the plan PR this issue records, or answer that it could not be.

    `None` is the read that failed, and it ends the tick rather than falling
    back. Everything downstream of this answer is a durable decision -- which
    tip the developer starts from, and which commit stands in for the path
    record about to be retired -- so a tick that cannot take the reading must
    not make those decisions on the strength of a stale one.

    A PR with no readable head is the same answer as a PR that could not be
    fetched. Both mean nothing was established, which is not what an issue with
    no plan PR at all reports.
    """
    if not _plan_published(state):
        return _ReviewedPlan()
    return _read_plan_pr(gh, issue, state.get(_PR_NUMBER))


def _read_plan_pr(
    gh: GitHubClient, issue: Issue, pr_number,
) -> _ReviewedPlan | None:
    """Ask GitHub what one recorded plan PR is on, and whether it landed.

    Split from the reading above because two callers decide differently that
    there IS a plan PR to ask about. The relabel guard has the path record; the
    reconcile in `plan_handoff` does not, since retiring that record is the very
    thing the handoff did.
    """
    try:
        plan_pr = gh.get_pr(int(pr_number))
    except Exception:
        log.exception(
            "issue=#%s could not fetch plan PR #%s while accepting the "
            "relabel; deferring the tick", issue.number, pr_number,
        )
        return None
    head = getattr(plan_pr.head, "sha", None)
    if not head:
        return None
    return _ReviewedPlan(
        head=head, merged=gh.pr_state(plan_pr) == _MERGED_PR_STATE,
    )


def _inherited_tip(
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    reviewed: _ReviewedPlan,
) -> _HandoffTip:
    """The tip the developer starts from, once the branch is where it belongs.

    The round anchor is the answer on every issue without a plan PR, and on one
    whose PR is still on the commit this stage published: it is the tip the
    guard certified, and the spawn path reads it back to keep the commits an
    issue arrived with from passing as a dev run to finish.

    A plan PR the humans moved is the other case, and the branch is brought
    forward onto that head before anything is written or spawned. The developer
    has to build on the design its reviewers actually approved, and a push from
    a tip that does not contain their amendment is what would overwrite it.

    A plan PR that MERGED is the third case, and the anchor is wrong for it
    even when it matches: the design landed, so the base carries it along with
    everything else that has landed since, and the branch it was open against
    may be deleted. Left on the commit that merged, the developer starts behind
    the branch they are building for and their PR opens against a base they
    never saw. So the move is asked for with no head at all, which is how the
    anchor is told to put the checkout on the base.

    What comes back is where the branch REALLY ends up, never where the move
    intended to put it: the reviewed head, or the base. A move that established
    neither leaves the handoff pending rather than recording the
    anchor -- the checkout would still be behind the reviewers, and a baseline
    naming any other commit would have the spawn path read the difference as an
    interrupted dev run and push it with no agent having run at all.
    """
    anchor = state.get(_ROUND_SHA)
    if not reviewed.head:
        return _HandoffTip(sha=anchor)
    onto = "" if reviewed.merged else reviewed.head
    if onto and onto == str(anchor or ""):
        return _HandoffTip(sha=anchor)
    anchored = _anchoring._anchor_pr_worktree(
        spec,
        issue.number,
        branch=_naming._resolve_branch_name(state, spec, issue.number),
        head_sha=onto,
    )
    if anchored is None:
        log.warning(
            "issue=#%s holding the plan handoff: the checkout could not be "
            "put on %s", issue.number, onto or "the base branch",
        )
        return _HandoffTip(pending=True)
    return _HandoffTip(sha=anchored)
