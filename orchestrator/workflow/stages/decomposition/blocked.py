# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A parent waiting on its children, and the issue that is done waiting.

`blocked` is a poll: read the children, park on one the orchestrator cannot
interpret, release the ones whose dependencies are satisfied, and flip the
parent to `ready` once every child is `done`. A parent with no recorded
children at all did not get here through a split, so it parks rather than
guessing -- the label was almost certainly applied by hand. A parent a late
split made that a genuine edit re-decomposed into children beside work of its
own settles what that split still owes the remote before the flip, and stays
`blocked` while a ref is still held for a consumer that has not ended: nothing
comes back to that ledger once it has left. Settled, the split's cycle is
retired in a write of its own ahead of the flip, so the implementation it goes
back to starts a cycle of its own rather than resuming the one it was split
in.

`ready` is the other end, and it is the entry point for both an auto-created
child and a parent whose decomposer voted `single`. It seeds the same pickup
anchor the unlabeled-issue start writes, then ratchets `last_action_comment_id`
past every comment currently on the thread. That ratchet is what keeps
decomposing-era feedback from being replayed as fresh PR feedback later: the
implementer reads the whole thread at spawn, so by the time the PR reaches
`in_review` those comments are already incorporated, and the watermark seed
would otherwise resume the developer and bounce the PR back out of review.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    retiring_cycles as _retiring_cycles,
    usage as _usage,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    activation as _activation,
    late_cleanup as _late_cleanup,
    late_close_observation as _late_close_observation,
    parents as _parents,
    state as _state,
    umbrella as _umbrella,
    umbrella_terminal as _umbrella_terminal,
)
from orchestrator.workflow.stages.implementing import handler as _implementing
from orchestrator.workflow.state import WorkflowLabel


def _handle_ready(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    """`ready` is the entry point for an auto-created child or for a parent
    whose decomposer voted `single`. Both cases need the same pickup-state
    seeding the legacy `_handle_pickup` did before flipping to
    `implementing`, so the validating handoff watermark and the in_review
    legacy migration have an anchor comment they can key on.
    """
    state = gh.read_pinned_state(issue)
    # User-content drift before implementation has started: route back to
    # decomposing so the manifest is re-derived against the new body. A
    # non-umbrella parent can reach `ready` after every child resolves
    # (`_handle_blocked`'s all-done branch flips `blocked` -> `ready`), so
    # the parent may STILL carry `children` / `dep_graph` /
    # `expected_children_count` from the prior manifest. `_route_parent_drift`
    # (via `_route_drift_to_decomposing`) wipes that tracking alongside the
    # locked decomposer session, so the next `_handle_decomposing` tick's
    # half-finished recovery branch does not fire and just flip the issue
    # back to `blocked` without re-running the decomposer.
    if _parents._route_parent_drift(gh, issue, state):
        return
    if state.get("pickup_comment_id") is None:
        if not state.get(_state._CREATED_AT):
            state.set(_state._CREATED_AT, _usage._now_iso())
        pickup = _comments._post_issue_comment(
            gh, issue, state,
            ":robot: orchestrator picking this up; starting implementation.",
        )
        pickup_id = getattr(pickup, "id", None)
        if pickup_id is not None:
            state.set("pickup_comment_id", int(pickup_id))
    # Mark every comment visible right now as "already consumed". For a
    # parent that came through `decomposing` / `blocked`, `pickup_comment_id`
    # was anchored on the original "decomposing" comment, so any human
    # feedback posted while children were resolving sits AFTER pickup and
    # would be classified as post-pickup, unconsumed feedback by the
    # in_review watermark seed. The implementer reads the full thread via
    # `_recent_comments_text` at spawn, so by the time the PR reaches
    # `in_review` those comments have been incorporated; replaying them
    # would resume the dev and bounce the PR back to validating instead
    # of allowing merge. Bumping `last_action_comment_id` lets
    # `_seed_watermark_past_self`'s `consumed_through` walk advance past
    # them. The next park (or the validating handoff) will overwrite this
    # value, so it's a transient marker for the in-progress handoff only.
    latest = gh.latest_comment_id(issue)
    if isinstance(latest, int):
        prior = state.get(_state._LAST_ACTION_COMMENT_ID)
        if not isinstance(prior, int) or latest > prior:
            state.set(_state._LAST_ACTION_COMMENT_ID, latest)
    gh.set_workflow_label(issue, WorkflowLabel.IMPLEMENTING)
    gh.write_pinned_state(issue, state)
    _implementing._handle_implementing(gh, spec, issue)


def _handle_empty_blocked_parent(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    if state.get(_state._PARENT_NUMBER) or state.get(_state._AWAITING_HUMAN):
        return
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} `{WorkflowLabel.BLOCKED}` without "
        "recorded children; "
        "manual relabel suspected.",
        reason="blocked_no_children",
    )
    gh.write_pinned_state(issue, state)


def _complete_blocked_parent(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    _comments._post_issue_comment(
        gh, issue, state,
        ":white_check_mark: all children resolved; ready for implementation.",
    )
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    gh.set_workflow_label(issue, WorkflowLabel.READY)
    gh.write_pinned_state(issue, state)


def _retired_for_implementation(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Whether a settled parent may go back to its own work, its late cycle retired first.

    Asked once what a late split recorded on it is settled -- see
    `_settled_before_implementation` -- and retired in a pinned write of its
    own BEFORE the label leaves `blocked`. The size gate the implementation
    reaches reads a live cycle as a candidate of this issue's still to be
    measured, so a parent handed back over its split's cycle would try to
    recover that superseded commit from a worktree long gone, and a later
    split of its own would read the old register as slices already cut. The
    retirement drops the candidate, the register, and the cycle identity, and
    keeps both ledgers and the cycle it retired -- exactly what the umbrella's
    terminal keeps, which is what lets a later split of this issue prove its
    lineage and number its own cycle past this one.

    The ordinary split's attempt goes too: every child its receipts name has
    resolved, so there is nothing left for a recovery to adopt by it. It goes
    in the retirement's write where there is a cycle, and in a write of its
    own where there is none -- either way while the label is still `blocked`,
    because the flip sets the label before it writes, and a pass that died
    between the two would leave the attempt standing on a `ready` parent. A
    parent recording no attempt costs no write here.

    A retirement is taken inside the window the umbrella's terminal takes it
    in, for the same reason: a close latched in front of it ends the cycle
    instead, and one observed during the write puts the cycle back and
    cancels it there, so the ending has something to run from. Either keeps
    the parent `blocked`.
    """
    attempt = state.get(_state._SPLIT_ATTEMPT)
    state.set(_state._SPLIT_ATTEMPT, None)
    if not _late_state.read_late_generation(state).is_present:
        if attempt is not None:
            gh.write_pinned_state(issue, state)
        return True
    if _late_close_observation._latched_close_ends(gh, spec, issue, state):
        return False
    live = _umbrella_terminal._retired_cycle(state)
    retiring = _retiring_cycles.retiring(spec.slug, issue.number, live.cycle_id)
    with retiring.held():
        gh.write_pinned_state(issue, state)
    return not _umbrella._reinstated(gh, issue, state, live, retiring)


def _handle_blocked(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    """Poll children to decide whether the parent unblocks (or one of the
    children unblocks).

    The orchestrator's parallel tick path (see
    `dispatch._FAMILY_AWARE_LABELS`) submits the whole family-aware
    bucket as a single drain task on one worker thread, so only one of
    `decomposing`, `blocked`, or `umbrella` runs at a time within a
    process's tick -- even when other issues fan out across worker
    threads. Issues outside the family-aware bucket (`implementing`,
    `validating`, `in_review`, `resolving_conflict`) may run
    concurrently alongside, but their handlers do not write across
    parent/child boundaries. Neither holds across processes: another
    poller on this host dispatches a child under the child's own writer
    claim, so every write this tick makes to a child is made under that
    claim too, and the release walk reads the child again behind it.
    """
    state = gh.read_pinned_state(issue)
    children = state.get(_state._CHILDREN) or []

    if _parents._route_parent_drift(gh, issue, state):
        return

    if not children:
        _handle_empty_blocked_parent(gh, issue, state)
        return

    scan = _parents._usable_child_scan(gh, spec, issue, state, children)
    if scan is None:
        return
    if all(label == _state._DONE for label in scan.labels.values()):
        if _late_cleanup._settled_before_implementation(
            gh, spec, issue, state, scan,
        ) and _retired_for_implementation(gh, spec, issue, state):
            _complete_blocked_parent(gh, issue, state)
        return

    held = _activation._activate_ready_children(
        gh, spec, issue, state, scan,
    )
    _activation._log_held_children(
        issue, "blocked", children, scan.labels, held,
    )
