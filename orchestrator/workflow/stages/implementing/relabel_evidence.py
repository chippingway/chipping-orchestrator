# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a read-only relabel has grounds to vouch for a tip sitting on.

"Ahead of base" is the question by default, and it is the whole question for a
question-stage park, whose own contract already refuses to finish a round on a
branch carrying anything. The discussion stage tolerates the commits an issue
arrives with, so the same question would convict it of its dev's work and
strand an issue no operator could unstick. What is asked there instead is
whether the tip is one some record names.

Two records name one. The SHA the last round opened on is the first: that
anchor is written before the spawn and survives every park the stage takes --
including the ones that found a commit, which quote it as the tip to reset back
to -- so it is the tip's position against it, not the anchor's presence, that
says whether the stage vouches for what is there. The head the recorded plan PR
is on is the second, because that is the design as its reviewers left it: the
branch may already have been brought forward onto that head by an earlier
attempt at the handoff that died before recording it, and the humans themselves
may have pulled their own amendment down. Neither is a commit anybody here
made.

Nothing else certifies, and deliberately not the tip a publication is in flight
on: that commit is the plan this stage wrote, which is the one thing that may
never leave here as a dev push.

A MERGED plan takes the older question back, and it has to. Its handoff puts
the branch and the checkout on the BASE -- the design landed, so the base
carries it -- and the move happens before the write that records it, so a tick
that dies in between leaves a tip no record names. Matched exactly, that reads
as unreviewed work, and the remediation would then offer the round anchor as
the reset target: an operator told to move a branch backwards off the commit
the merge produced. A tip carrying nothing beyond base carries nothing of
anybody's either, which is exactly what ahead-of-base answers, and it is the
same reading already trusted for the stage with no anchor at all. The move is
idempotent, so the next tick simply makes it again against whatever the base is
by then.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.discussion.state import _ROUND_SHA
from orchestrator.workflow.stages.implementing.plan_reading import _ReviewedPlan


def _certified_tips(state: PinnedState, reviewed_sha: str) -> frozenset:
    """Every commit this guard has grounds to vouch for a checkout sitting on.

    The tip the round opened on, because everything at or under it predates
    this stage, and the head the recorded plan PR is on, because that is the
    design as its reviewers left it. Nothing else.
    """
    anchor = str(state.get(_ROUND_SHA) or "")
    return frozenset(tip for tip in (anchor, reviewed_sha) if tip)


def _tip_is_uncertified(
    state: PinnedState,
    reviewed: _ReviewedPlan,
    tip: str,
    ahead_of_base: bool,
) -> bool:
    """Whether a recorded branch's tip is one nothing here can vouch for.

    A recorded tip is matched exactly, which is what a discussion held on an
    inherited PR branch needs: that branch is legitimately ahead of base, so
    the older question would convict it of its dev's commits.

    A merged plan is the exception, and the reason is the handoff it is about
    to get: once the plan has merged, a branch carrying nothing beyond base is
    certified by carrying nothing.
    """
    if tip in _certified_tips(state, reviewed.head):
        return False
    return ahead_of_base or not reviewed.merged


def _checkout_certified(
    spec: _config_models.RepoSpec,
    worktree: Path,
    head: str,
    state: PinnedState,
    reviewed: _ReviewedPlan,
) -> bool:
    """Whether this checkout is sitting somewhere the guard can vouch for.

    A recorded tip is the sharper question and the one a discussion needs: its
    branch may legitimately be ahead of base, carrying a PR's commits the round
    opened on top of, so only an exact match with what was recorded certifies.

    With nothing recorded there is nothing to match against, and the question
    stage is the caller that has nothing: its checkout is recreated from base
    every spawn and its contract forbids finishing on a branch carrying
    anything. So the older question is asked instead, and asked of the CHECKOUT
    -- `_has_new_commits` reads `HEAD` against `<remote>/<base>`, which is what
    makes it answer for a commit made while detached as readily as for one on
    the branch.

    A merged plan is asked the older question too, and for the reason the
    branch reading beside this one gives: its handoff resets the checkout to
    the base, and the write recording where it landed comes after the reset --
    so the tick that dies in between leaves a tree on a commit no record names,
    which an exact match would convict of the base branch itself.
    """
    certified = _certified_tips(state, reviewed.head)
    if head in certified:
        return True
    if certified and not reviewed.merged:
        return False
    return not _worktree_creation._has_new_commits(spec, worktree)
