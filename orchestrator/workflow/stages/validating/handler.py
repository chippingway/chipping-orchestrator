# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One validating tick, in the order its questions have to be asked.

The terminals come first because a PR a human already settled, or an issue
closed without one, makes the whole round pointless -- and running the
reviewer against a branch that landed, or against work somebody turned down,
would pull a finished issue back into the loop. Both pull-request endings are
decided off ONE guarded reading: a merge finalizes `done`, and a close nobody
merged finalizes `rejected`, which leaves the ISSUE open and so is invisible
to the closed-issue terminal behind it. One reading rather than a fetch each,
since a merge landing between two would be answered open to the first and
merged to the second, and the reviewer would spawn behind both.

A squash this issue began and did not finish is answered next, ahead of every
route that can point an agent at the branch, because a branch mid-rewrite is
not one any of them may be run over. Reached only from the approval road it
survives every tick whose reviewer times out, crashes, or votes
CHANGES_REQUESTED: an already-landed collapse never gets its handoff, a record
nothing can read reaches `fixing` without the park it owes, and a body edit
resumes the dev on a checkout standing on a commit nobody accounted for. Above
the awaiting-human branch as well as the drift one, since the refusals it
takes ARE parks -- the reply to one belongs to the collapse rather than to the
dev, and a park nobody has answered yet holds the tick without being
re-mentioned every poll.

Drift comes next, ahead of the awaiting-human branch, because a body edit
mid-review means the work under review is answering the wrong requirements;
the three parks that defer back out of it are the ones whose reply belongs to
the reviewer or to the operator's round-cap command instead of to the dev. On
a parked tick the awaiting context -- and its one frozen reply batch -- is
built first, and the drift check measures the requirements by what that park
had already read: the replies past it are the batch's to deliver, so they
reach the awaiting-human branch rather than the drift resume.

The awaiting-human branch then either finishes the tick or clears the park
into a fresh reviewer round, which is why it answers in words rather than a
bool: `"return"` means handled, and `"spawn_reviewer"` means fall through to
the round-cap check and the spawn below.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import terminals as _terminals
from orchestrator.workflow.stages.validating import (
    awaiting_resume as _awaiting_resume,
    collapse as _collapse,
    drift as _drift,
    models as _models,
    reviewer as _reviewer,
    state as _state,
)


def _finalize_validating_terminal(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """Terminal short-circuits checked before the reviewer runs; True when one
    fired and the caller must return.

    External merge: a human merged the PR while the reviewer was queued.
    Finalize to `done` rather than running the reviewer against a branch that
    already landed. Closed PR: one somebody closed without merging, which
    leaves the ISSUE open and so is invisible to the counterpart below --
    flip to `rejected` rather than spawning a reviewer against work a human
    has already rejected. Both come off ONE reading, since two fetches are
    two moments and a merge landing between them reads open to the first and
    merged to the second -- which the closed arc is right to ignore, while
    the reviewer spawns behind it. Closed-issue counterpart: the closed-`validating`
    sweep yields issues a human closed without a merged PR; flip to `rejected`
    so the reviewer does not spawn against a closed issue and the PR is not
    relabeled back to `in_review`. The in_review / fixing handlers carry
    equivalent terminal checks.
    """
    if _terminals._pr_terminal_stops_the_tick(gh, spec, issue, state):
        return True
    return _terminals._finalize_if_issue_closed(gh, spec, issue, state)


def _handle_validating(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    state = gh.read_pinned_state(issue)
    pr_number = state.get("pr_number")

    if _finalize_validating_terminal(gh, spec, issue, state):
        return

    # A squash this issue began and did not finish is answered before any
    # route below can point an agent at the branch. Asked only on the approval
    # road it is not asked at all on a tick whose reviewer times out, crashes,
    # or votes CHANGES_REQUESTED -- so a collapse the remote already carries
    # never gets its handoff, a record nothing can read never gets its park,
    # and the dev is resumed on a branch standing on a commit nobody accounted
    # for. It owns the park it takes as well: a refusal parks, and a reply to
    # that park belongs to the collapse rather than to the dev.
    if _collapse._recovers_a_recorded_collapse(gh, spec, issue, state):
        return

    # User-content drift resume runs before the awaiting-human and reviewer
    # branches: a body edit mid-review must resume the dev on the new body
    # rather than re-review stale work. Returns True when it fully handled the
    # tick; a reviewer-side (`reviewer_timeout` / `reviewer_failed`) or
    # `review_cap` park defers to the awaiting-human branch below (that branch
    # owns the human's "retry" / `/orchestrator add-review-rounds` comment).
    parked = (
        _models._AwaitingValidation.build(gh, spec, issue, state)
        if state.get("awaiting_human") else None
    )
    if _drift._resume_dev_on_validating_drift(gh, spec, issue, state, parked):
        return

    # Awaiting-human path: human replied after a park (or a transient
    # condition self-resolved). The helper resumes the dev on their feedback,
    # recovers transient parks silently, or clears a reviewer-side / review-cap
    # park into a reviewer re-run. "return" -> the tick is fully handled;
    # "spawn_reviewer" -> fall through to the round-cap check and reviewer
    # spawn below.
    if parked is not None:
        outcome = _awaiting_resume._handle_validating_awaiting_human(parked)
        if outcome == _state._OUTCOME_RETURN:
            return

    reviewer_run = _reviewer._run_reviewer_round(gh, spec, issue, state, pr_number)
    if reviewer_run is None:
        return

    _reviewer._dispatch_reviewer_result(gh, spec, issue, state, reviewer_run)
