# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The endings a reading of the committed plan earns, refused or published.

Every park here has an artifact to report on, so every one of them quotes the
same reading of it. Only the published plan touches the round anchor, and it
moves it forward onto the commit it just put on a PR -- the one case where the
branch's new tip IS what this stage vouches for. Every refusal leaves the
anchor exactly where the round opened it, because a commit is precisely when
that number has to survive: it is the only recorded point that separates what
the agent wrote from what the branch already carried, so it is both the reset
target these parks quote and what the implementing relabel guard measures the
branch against once the operator has reset. Clearing it on the way out would
leave a PR-backed issue with commits ahead of base and nothing left to certify
them, refused forever with no non-destructive way back.

The two refusals of a committed artifact are distinct and share one reason
code. Both mean the branch is not the plan file alone, and both quote the same
reading of it, but one is a round reporting on itself and the other is a commit
found by a tick that opened no round at all -- so the operator is told which,
and told why nothing ran this time.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.workflow.stages.discussion import (
    models as _models,
    park_messages as _park_messages,
    parks as _parks,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

# What a refusal calls a tip whose read failed, so the message still says
# which of the two SHAs it could not name.
_UNREADABLE_TIP = "an unreadable tip"


def _park_unpublishable_plan(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> None:
    _parks._park_discussion(
        run,
        _park_messages._unpublishable_plan_message(
            run, artifact, "the discussion round committed in the worktree",
        ),
        reason=_state._DISCUSSION_PLAN_INVALID,
    )


def _park_recovered_commit(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> None:
    """Park on a commit a round left without ever reaching a disposition.

    The round that made it was withheld or cut short before it could say so,
    so this park is the first time the commit is named. It runs INSTEAD of a
    new round, which is what stops the next one from opening on the commit and
    reporting it as work the branch arrived carrying.
    """
    _parks._park_discussion(
        run,
        _park_messages._unpublishable_plan_message(
            run,
            artifact,
            "a discussion round that did not finish (paused mid-run, or "
            "interrupted) left a commit in the per-issue worktree and no "
            "further round was opened",
        ),
        reason=_state._DISCUSSION_PLAN_INVALID,
    )


def _park_published_plan(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
    pr_number: int,
) -> None:
    """Hand back an issue whose agreed design is now on a PR to review.

    Still a park, and still under this stage's own prefix: the label does not
    move, and what happens next is a human's -- reviewing the plan, then
    relabeling the issue to have it built. The comment says both, because an
    issue that keeps its `discussion` label while its stage has stopped
    opening rounds is otherwise indistinguishable from one waiting on an
    answer.
    """
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} the design confirmed on this thread is "
        f"written up in `{artifact.plan_path}` and opened as PR "
        f"#{pr_number}. That branch changes nothing else -- it was checked "
        "against the base branch before anything was pushed. Review the plan "
        f"there, and relabel this issue to `{WorkflowLabel.IMPLEMENTING}` "
        "when it should be built; no further discussion round is opened "
        "while the plan PR stands.",
        reason=_state._DISCUSSION_PLAN_PUBLISHED,
    )


def _park_unattributed_plan(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> None:
    """Report a valid plan with no conversation to publish it under.

    The artifact passed every check the branch can answer; what it has no
    answer for is which discussion produced it, and that is what the PR body
    exists to say. It happens when a backend hands back no session id, and
    when a round that opened a new conversation is cut short before it can
    record the one it opened.

    The remedy is a re-run, so the message asks for the reset that makes one
    possible: the commit has to come off the branch before a round may open on
    it, and the round that follows writes the same plan under a session a
    reviewer can follow back.
    """
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} the agreed plan is committed in "
        f"`{artifact.plan_path}`, but no session id was recorded for the "
        "round that wrote it -- the backend handed none back, or the round "
        "was cut short before it could. A published plan has to name the "
        "conversation it came out of, so nothing was pushed and the commit is "
        f"untouched. {_park_messages._reset_target(run)} The next reply then "
        "re-runs the discussion, which writes the plan again under a session "
        "that can be followed back; relabeling to "
        f"`{WorkflowLabel.IMPLEMENTING}` builds from the file as it stands "
        "instead.",
        reason=_state._DISCUSSION_PLAN_UNATTRIBUTED,
    )


def _park_stale_publication(
    run: _models._DiscussionRun,
    artifact: _models._PlanArtifact,
    in_flight: str,
    published: bool,
) -> None:
    """Report a publication whose commit the branch has moved off.

    Named rather than described, both SHAs: the one that was checked and
    pushed for, and the one the branch is on instead. Restoring the first is
    what lets the publication finish on its own next tick, which is why it is
    the remedy offered before the one that ends the conversation's artifact.

    What the remote holds decides the rest of it, because it decides whether
    the other remedy is even available. With nothing of ours on that branch, a
    local reset ends the plan and the message can offer it. With the commit
    still out there -- pushed from a checkout whose ref never moved, or left by
    a tick that died after opening the pull request -- the plan is published
    whatever this tree says, so telling an operator to reset would tell them to
    lose track of a PR that stays open either way. That one is dropped where it
    really lives, and this stage will not spend the record until it is.
    """
    branch_tip = artifact.head_sha or _UNREADABLE_TIP
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} a publication of `{artifact.plan_path}` was "
        f"in flight on `{in_flight}`, but the branch is at "
        f"`{branch_tip}` now. "
        f"{_park_messages._stale_publication_standing(published)} Restore "
        f"`{in_flight}` on `{artifact.branch}` and it is published on the "
        f"next tick; {_park_messages._stale_publication_remedy(run, published)}"
        f"\n\n{_park_messages._artifact_reading(artifact)}",
        reason=_state._DISCUSSION_STALE_PUBLISH,
    )


def _park_diverged_plan_branch(
    run: _models._DiscussionRun,
    artifact: _models._PlanArtifact,
    remote_tip: str | None,
) -> None:
    """Report a remote branch this publication is not allowed to overwrite.

    Shares the failed-push reason because the operator's way out is the same
    one: the plan is still committed, nothing was published, and a reply
    retries the publication once the remote and the branch agree again. What
    differs is why, so the message names the tip that is there -- or says the
    remote could not be read at all, which is not the same as a remote that
    moved and must not be reported as one.

    Written every time rather than once, unlike the repair parks: each tick
    that reaches here has taken a fresh reading of a remote somebody else is
    moving, and the answer an operator needs is the current one.
    """
    if remote_tip is None:
        found = (
            "the remote could not be asked what "
            f"`{artifact.branch}` is at (see the orchestrator logs)"
        )
    else:
        found = (
            f"`{artifact.branch}` is at `{remote_tip}` on the remote, and the "
            "commit this plan is on does not descend from it -- somebody has "
            "written on that branch, or the branch was reset out from under "
            "what it carried"
        )
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} the agreed plan is committed in "
        f"`{artifact.plan_path}`, but {found}. Nothing was pushed and nothing "
        f"was overwritten: `{artifact.head_sha}` does not contain what is "
        "there, so publishing it would have discarded it. Reconcile the "
        "branch with the remote and reply here to retry the publication, or, "
        "to drop the plan and keep discussing: "
        f"{_park_messages._reset_target(run)}",
        reason=_state._DISCUSSION_PUSH_FAILED,
    )


def _park_failed_plan_push(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact,
) -> None:
    """Report a valid plan that could not be pushed, and what to do with it.

    The commit is left exactly where it is: it is the agreed design, and the
    remedies are ordered so the destructive one is last. A reply on this park
    retries the publication -- the branch still carries the same publishable
    artifact -- so an operator who fixes the token, the network, or the remote
    can say so on the thread instead of resetting the plan away.
    """
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} the agreed plan is committed in "
        f"`{artifact.plan_path}`, but pushing `{artifact.branch}` failed; see "
        "the orchestrator logs. Nothing was published and the commit is still "
        "in the per-issue worktree. Fix the push and reply here to retry it, "
        "or, to drop the plan and keep discussing: "
        f"{_park_messages._reset_target(run)}",
        reason=_state._DISCUSSION_PUSH_FAILED,
    )
