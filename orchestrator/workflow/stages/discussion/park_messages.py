# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a park quotes back: the readings it was decided on, and the way out.

Nothing here writes. Every function takes a reading somebody else already took
and renders the part of a comment an operator acts on, which is why the three
park owners can be split by what they mutate while the wording stays one thing:
the same bounded path list, the same reading of a committed artifact, and the
same reset command are quoted from all three, and two parks describing one
checkout in two ways would leave an operator reconciling them.

The reset target is the load-bearing one, because "reset the worktree" read as
"reset to base" would throw away a pull request. The branch an issue arrives on
can already be ahead of base -- a PR-backed issue relabeled here carries its
dev's commits -- so what these quote is the anchor the round opened on, the one
target that drops what the agent wrote and keeps everything under it. It is
also what the implementing relabel guard measures the branch against once the
operator has reset, so a park that quoted anything else would ask for a tree
that stage then refuses.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.workflow.stages.discussion import models as _models, state as _state

_PATHS_SHOWN = 10


def _paths_markdown(paths: tuple[str, ...]) -> str:
    """Render a bounded path list, naming how many it did not show."""
    shown_paths = paths[:_PATHS_SHOWN]
    display_lines = [f"- `{file_path}`" for file_path in shown_paths]
    hidden_count = len(paths) - len(shown_paths)
    if hidden_count:
        display_lines.append(f"- ... ({hidden_count} more)")
    return "\n".join(display_lines)


def _reset_target(run: _models._DiscussionRun) -> str:
    """Name the SHA a commit park has to be reset back to, not just "reset".

    The branch an issue arrives on can already be ahead of base -- a PR-backed
    issue relabeled here carries its dev's commits -- so "reset the worktree"
    read as "reset to base" would throw away the PR. The anchor is the exact
    tip the round opened on, which is the one target that drops what the agent
    wrote and keeps everything under it, and it is also what the implementing
    relabel guard checks the branch against afterwards.
    """
    anchor = run.state.get(_state._ROUND_SHA)
    if not anchor:
        return "Reset the worktree before resuming."
    return (
        f"Reset the worktree to `{anchor}` -- the tip this round opened on, so "
        "anything the branch already carried survives -- before resuming: "
        f"`git -C <worktree> reset --hard {anchor} && "
        "git -C <worktree> clean -fd`."
    )


def _committed_reading(artifact: _models._PlanArtifact) -> str:
    """Say what the commits changed, and whether the plan survived them.

    A round with no recorded base is reported as having no reading at all
    rather than as an empty diff: the paths below were measured from
    somewhere, and an operator told "changes nothing" about a comparison that
    never happened would reset a branch on the strength of it.
    """
    if not artifact.base_sha:
        return (
            "The commit this round was measured from was never recorded, so "
            "what this branch changes against the base branch could not be "
            "established."
        )
    if not artifact.changed_paths:
        return (
            "The commits on this branch change nothing against the base "
            "branch."
        )
    listing = (
        "Committed against the base branch:\n"
        f"{_paths_markdown(artifact.changed_paths)}"
    )
    if artifact.plan_in_head:
        return listing
    # A deletion changes exactly the path an addition would, so the diff on
    # its own reads as the artifact being asked for. Saying which happened is
    # the difference between "your plan needs trimming" and "there is no plan".
    return f"{listing}\n\n`{artifact.plan_path}` is not in the branch's HEAD."


def _artifact_reading(artifact: _models._PlanArtifact) -> str:
    """Quote what the branch actually carries, in the halves it is judged by.

    Every half is named even when only one of them is why the publication was
    refused: an operator deciding what to reset needs to see the committed
    diff and the loose edits together, and a plan that is absent -- never
    written, or deleted by the commit that named its path -- is a fact the
    listing has to state rather than imply by omission.

    An unreadable worktree is reported as exactly that. It is not a clean tree
    and not a dirty one; what it means is that nothing here could tell, which
    an operator has to know before they go looking for edits that may not be
    there.

    A commit made off the branch is reported for the opposite reason: every
    reading above it comes back exactly as it would for a plan written the way
    it was asked for, so without saying which ref HEAD is on the operator
    reads a refusal whose every stated fact looks right.
    """
    committed = _committed_reading(artifact)
    if not artifact.head_attached:
        committed = (
            f"{committed}\n\nHEAD is not `{artifact.branch}`: the commit was "
            "made on a detached HEAD or on another ref, so that branch is not "
            "on it -- and nothing here moves a ref an agent left behind."
        )
    if not artifact.tree_readable:
        return (
            f"{committed}\n\nThe worktree's state could not be read "
            "(`git status` failed), so nothing was assumed about it."
        )
    if not artifact.dirty_files:
        return committed
    return (
        f"{committed}\n\nUncommitted in the worktree "
        f"({len(artifact.dirty_files)}):\n"
        f"{_paths_markdown(artifact.dirty_files)}"
    )


def _unpublishable_plan_message(
    run: _models._DiscussionRun, artifact: _models._PlanArtifact, found: str,
) -> str:
    """The refusal every unpublishable commit gets, framed by where it came from."""
    return (
        f"{config.HITL_MENTIONS} {found}, but the only thing this stage "
        f"publishes is `{artifact.plan_path}` committed on its own, with a "
        "clean worktree, once you have confirmed the design on this thread. "
        "Nothing was pushed and no pull request was opened."
        f"\n\n{_artifact_reading(artifact)}\n\n{_reset_target(run)}"
    )


def _stale_publication_standing(published: bool) -> str:
    """What the remote says is out there, which is not what the tree says."""
    if published:
        return (
            "The commit is on the remote branch, so the plan is published "
            "whatever this checkout is on -- nothing here recorded it, and no "
            "round is opening over the top of it."
        )
    return (
        "Nothing was pushed: whatever moved it is not the commit this stage "
        "checked, and it is not published on that commit's behalf."
    )


def _stale_publication_remedy(
    run: _models._DiscussionRun, published: bool,
) -> str:
    """The other way out, which a published commit does not have locally."""
    if published:
        return (
            "to drop the plan instead, close its pull request and delete the "
            "remote branch -- a reset here cannot, and this stage keeps the "
            "record until the commit is gone from the remote."
        )
    return f"to drop it and keep discussing: {_reset_target(run)}"
