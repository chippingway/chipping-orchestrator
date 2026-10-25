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
in. The split's attempt goes with it, but not its rationale: what the split
kept for the parent's own pass is what the parent goes back to.

What the issue says is not read here, parent or child. An issue on `blocked` is
held until its prerequisites permit release, and an edit made while it waits is
no reason to move it: the poll hashes nothing, records or replaces no baseline,
and reroutes nothing to `decomposing`, so the baseline, the manifest, the
dependency graph, and the children it tracks all stand as they were, and
nothing is told, orphaned, split again, or run. A child waiting on its siblings
has nothing to poll at all -- its parent's walk is what releases it. Its
requirements are compared once it legitimately enters `ready`, which decides on
exactly that baseline before anything implements. A `paused` or `backlog` is
no edit: a parent whose children all finished is fetched afresh before it
goes back to `ready`, and an operator's hold applied while the poll ran keeps
it `blocked` -- and the relabel moves only the workflow label, so no hold
applied meanwhile is written away.

`ready` is the other end, and it is the entry point for an auto-created child,
a parent whose children are all done, and a parent whose decomposer voted
`single`. Its handler only reads the claimed record and hands it to `ready`,
which compares the requirements against the preserved baseline before
anything implements: a change -- or a split's child with no baseline at all --
is rerouted to `decomposing`, and an issue that reads unchanged is handed on
behind a guarded checkpoint (`ready_handoff`). That handoff seeds the same
pickup anchor the unlabeled-issue start writes and ratchets
`last_action_comment_id` past every comment on the thread, which is what keeps
decomposing-era feedback from being replayed as fresh PR feedback later: the
implementer reads the whole thread at spawn, so by the time the PR reaches
`in_review` those comments are already incorporated, and the watermark seed
would otherwise resume the developer and bounce the PR back out of review.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    record_admission as _record_admission,
    retiring_cycles as _retiring_cycles,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    activation as _activation,
    late_cleanup as _late_cleanup,
    late_close_observation as _late_close_observation,
    parents as _parents,
    ready as _ready,
    state as _state,
    umbrella as _umbrella,
    umbrella_terminal as _umbrella_terminal,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _handle_ready(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    """`ready` is the entry point for an auto-created child, a parent whose
    children are all done, and a parent whose decomposer voted `single`.

    What it decides is owned by `ready`: whether the requirements still read
    as the baseline says, rerouting the issue to `decomposing` where they do
    not, and otherwise the guarded handoff -- pickup, consumption, relabel --
    behind which the implementer runs on this same tick. It is asked of the
    reading taken under the issue's writer claim, held to admission here.
    """
    _ready.enters(gh, spec, issue, _record_admission.admitted_state(gh, issue))


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


def _unheld(gh: GitHubClient, issue: Issue) -> Issue | None:
    """The parent as GitHub answers for it now, where no `paused` or `backlog` stands on it; None otherwise.

    The dispatcher's hold check is as old as the tick, and the scan behind it
    is a request per child: an operator who applies either hold while it runs
    has asked the parent to stop, finished children or not. An issue nobody
    could fetch holds as well, until a tick can say the hold is off.
    """
    try:
        fetched = gh.get_issue(issue.number)
    except Exception:
        log.exception("issue=#%d could not be read for a hold ahead of going back to ready; holding it", issue.number)
        return None
    hold = hard_skip_control_label(fetched)
    if hold is None:
        return fetched
    log.info(
        "issue=#%d carries %r; its children are done, and it waits on blocked until that is lifted",
        issue.number, str(hold),
    )
    return None


def _complete_blocked_parent(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Say every child resolved and hand the parent back to `ready`, on the issue as it reads right then.

    A hold read behind the notice stops the relabel with nothing written: the
    parent waits on `blocked`, and the tick after the hold is lifted says it
    again and goes back. The relabel moves only the workflow label
    (`move_workflow_label`), so a hold applied at any point -- after that last
    reading included -- is never written away.
    """
    _comments._post_issue_comment(
        gh, issue, state,
        ":white_check_mark: all children resolved; ready for implementation.",
    )
    current = _unheld(gh, issue)
    if current is None:
        return
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    gh.move_workflow_label(current, WorkflowLabel.READY)
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
    parent recording no attempt costs no write here. The split's rationale
    stays: its children are done, and what it kept for the parent's own pass
    is the work this hands the parent back to.

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
    retiring = _retiring_cycles.retiring(spec.slug, issue.number, live.cycle_id, gh.repo_id)
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

    No content check runs first: an edit made while the issue waits leaves
    its baseline, manifest, and graph as they stand, and the dependency
    progress below goes on regardless -- the walk releases what its graph
    permits, and a parent whose children all resolved finishes waiting on
    `ready`, where the requirements are compared.
    """
    state = _record_admission.admitted_state(gh, issue)
    children = state.get(_state._CHILDREN) or []

    if not children:
        _handle_empty_blocked_parent(gh, issue, state)
        return

    scan = _parents._usable_child_scan(gh, spec, issue, state, children)
    if scan is None:
        return
    if all(label == _state._DONE for label in scan.labels.values()):
        if _unheld(gh, issue) is None:
            return
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
