# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a relabel this stage will not honour is refused, and what it tells an operator.

The refusal re-parks the issue as `<stage>_unsafe_relabel` and is idempotent:
once that reason is standing, repeated ticks say nothing further and the issue
waits until an operator resets the worktree or deletes the branch. Pinned state
is written on every one of those ticks even so, because the reading that
convicted the branch is not the only thing the tick staged -- what has already
been decided durably must not be dropped by the refusal that follows it.

What the comment says has to be actionable without destroying work worth
keeping, which is why the remediation is chosen from the record rather than
being one sentence for every finding. Resetting to base and deleting the branch
are both right for a stage whose branch should carry nothing; a discussion held
on a branch that arrived with a PR's commits needs the round anchor as its
reset target instead, and a publication nobody finished needs the label that
finishes it before anything is thrown away at all.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.discussion.state import (
    _PUBLISHING_SHA,
    _ROUND_BRANCH,
    _ROUND_SHA,
)
from orchestrator.workflow.stages.implementing import state as _state
from orchestrator.workflow.stages.implementing.relabel_hazard import (
    _ReadOnlyRelabelHazard,
)
from orchestrator.workflow.state import WorkflowLabel

_UNSAFE_RELABEL_SUFFIX = "_unsafe_relabel"


def _refuse_read_only_relabel(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    stage: str,
    hazard: _ReadOnlyRelabelHazard,
) -> bool:
    """Park the relabel this stage refuses to ship, and hold the tick.

    Always True: a refused relabel owns its tick outright. The park itself is
    said once -- the reason already standing is the same refusal, and an
    operator who has not cleared the hazard has not been told anything new --
    while the write below it happens either way, since the reason is only one
    of the things this tick may have settled.
    """
    unsafe_reason = f"{stage}{_UNSAFE_RELABEL_SUFFIX}"
    if state.get(_state._PARK_REASON) != unsafe_reason:
        _park_unsafe_read_only_relabel(gh, issue, state, stage, hazard)
    gh.write_pinned_state(issue, state)
    return True


def _park_unsafe_read_only_relabel(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    stage: str,
    hazard: _ReadOnlyRelabelHazard,
) -> None:
    unsafe_reason = f"{stage}{_UNSAFE_RELABEL_SUFFIX}"
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} relabeled to `{WorkflowLabel.IMPLEMENTING}`, "
        f"but {_unsafe_relabel_finding(state, stage)} left "
        f"{hazard.trigger}. Nothing the {stage} stage leaves in the worktree "
        "is shipped as a dev implementation -- a discussion publishes the one "
        "plan it confirmed, itself and through its own check, and this is not "
        f"that -- so the orchestrator refuses to push it. "
        f"{_relabel_remediation(state, hazard)}",
        reason=unsafe_reason,
    )
    state.set(_state._PARK_REASON, unsafe_reason)


def _unsafe_relabel_finding(state: PinnedState, stage: str) -> str:
    """What this issue was carrying when the relabel arrived.

    The unfinished publication is named first, because the reason standing
    beside one is `discussion_publishing` -- a state, not a park anybody was
    ever shown a comment for. Every other park names itself, and its reason is
    what an operator matches against the comment that wrote it. An issue with
    neither is one whose round never reached a disposition at all.
    """
    if state.get(_PUBLISHING_SHA):
        return f"a {stage}-stage publication that never finished"
    park_reason = state.get(_state._PARK_REASON)
    if isinstance(park_reason, str) and park_reason:
        return f"the prior {stage}-stage park (`{park_reason}`)"
    return f"a {stage}-stage round that never reported"


def _relabel_remediation(
    state: PinnedState, hazard: _ReadOnlyRelabelHazard,
) -> str:
    """Say how to clear the hazard without destroying work worth keeping.

    Resetting to base and deleting the branch are both right for a stage whose
    branch should carry nothing, which is the question stage's case. A
    discussion can be held on a branch that arrived with a PR's commits on it,
    and both of those would discard the PR; the round anchor names the tip that
    branch was at before the agent touched it, so when one is recorded for this
    same branch it is the reset target that leaves the inherited work in place
    -- and it is what this guard re-measures the branch against next tick.

    A publication in flight is told the other way round. The commit under it is
    the agreed plan, and it may already be pushed with a pull request open
    against it, so the first thing to offer is the label that finishes what was
    started: the `discussion` stage picks its own marker up and publishes.
    Resetting is still there, but it is the answer for somebody who has decided
    to drop the plan, not the first thing an operator should read.
    """
    if state.get(_PUBLISHING_SHA):
        return (
            f"Relabel back to `{WorkflowLabel.DISCUSSION}` and that stage "
            "finishes the publication it began -- the commit may already be "
            "pushed with a pull request open against it. To drop the plan "
            f"instead: {_reset_instruction(state, hazard)}"
        )
    return _reset_instruction(state, hazard)


def _reset_instruction(
    state: PinnedState, hazard: _ReadOnlyRelabelHazard,
) -> str:
    """The reset that clears the branch, aimed at the tip worth keeping."""
    round_sha = state.get(_ROUND_SHA)
    if round_sha and str(state.get(_ROUND_BRANCH)) == hazard.branch:
        return (
            f"Reset the worktree to `{round_sha}` -- the tip the last "
            "conversation round opened on, so any commits the branch already "
            "carried survive -- before re-relabeling: `git -C <worktree> "
            f"reset --hard {round_sha} && git -C <worktree> clean -fd`."
        )
    return (
        "Reset the worktree (e.g. `git -C <worktree> reset --hard "
        "origin/<base> && git -C <worktree> clean -fd`), or delete the "
        f"local branch (`git branch -D {hazard.branch}` in `target_root`), "
        "before re-relabeling so the dev agent starts from a clean base."
    )
