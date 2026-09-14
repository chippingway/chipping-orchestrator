# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two ways a `decomposing` issue is handed to implementation.

Neither is a decomposition, which is why they sit apart from the tick that
runs one. The kill switch hands on an issue that was only ever waiting to be
decomposed, and the settled candidate hands on one whose size question has
already been ANSWERED -- and both end the same way: the label moves, and the
implementing handler runs on the same tick rather than a poll later.

That last step is what the two share and why they are one owner. A label write
leaves the object it was made against reporting the label it arrived with, so
the handler has to be given a freshly read issue or the relabel IT ends in is
checked against a state that is no longer true.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_park_state as _late_park_state,
    late_reconcile as _late_reconcile,
    late_relabel as _late_relabel,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import handler as _implementing
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_SETTLED_NOTICE = (
    ":straight_ruler: the committed implementation for this issue now measures "
    "under the size ceiling, so there is nothing left to adjudicate; routing "
    "it to `{label}` for publication."
)


def _route_disabled_to_implementing(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """DECOMPOSE kill-switch bailout.

    Returns True when the caller must return: decomposition is disabled, and
    the issue was either routed to implementation or left exactly where it is
    because a live late generation may not be routed. False means the caller
    should proceed to spawn the decomposer.

    Every path after this point spawns the decomposer (fresh or via the
    awaiting_human resume), so an operator who restarts with DECOMPOSE=off
    after `_handle_pickup` already labeled the issue `decomposing` -- or
    while it is parked there awaiting a human -- would still see the
    disabled rollout create manifests and child issues. Drop into the
    legacy implementing flow exactly as `_handle_pickup` does on a freshly
    unlabeled issue. The half-finished recovery above must keep running
    regardless of the flag: abandoning orphan children (already on GitHub)
    because new decompositions are now disabled would strand work, which
    is not what a kill switch should do.

    A live late generation stops the route for that same reason, one step
    further on. Such an issue is not waiting to be decomposed -- its
    implementation is already committed and measured past the ceiling -- so
    the legacy route would publish an oversized candidate as though a `single`
    verdict had been recorded for it, which is the one outcome the size gate
    exists to prevent. The switch still keeps new candidates out of the gate;
    it does not decide the ones already in it.
    """
    if config.DECOMPOSE:
        return False
    if _late_relabel._refuses_disabled_route(state):
        log.info(
            "issue=#%d carries a live oversized candidate; DECOMPOSE=off "
            "leaves it under adjudication rather than routing it to "
            "implementation", issue.number,
        )
        return True
    _comments._post_issue_comment(
        gh, issue, state,
        ":robot: decomposition is disabled; routing this issue "
        "to implementation.",
    )
    # Clear decomposer-side park state. Without this,
    # `_handle_implementing` reads `awaiting_human=True` and
    # tries to resume a dev session that was never spawned --
    # at best it stalls on `comments_after`, at worst the
    # follow-up text becomes the sole prompt instead of the
    # real implement prompt.
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    # Mark every comment visible at this transition as
    # "already consumed", mirroring `_handle_ready`'s ratchet.
    # `_handle_implementing` will read the full issue thread
    # via `_recent_comments_text` when it builds the implement
    # prompt, so the dev sees any decomposing-era human
    # feedback at spawn. Without this bump, the
    # validating->in_review watermark seed later sees those
    # same comments as fresh PR feedback (because they sit
    # AFTER the now-stale `last_action_comment_id` from the
    # decomposer-era park) and bounces the dev unnecessarily.
    # One-way ratchet so we never lower a higher prior value.
    latest = gh.latest_comment_id(issue)
    if isinstance(latest, int):
        prior = state.get(_state._LAST_ACTION_COMMENT_ID)
        if not isinstance(prior, int) or latest > prior:
            state.set(_state._LAST_ACTION_COMMENT_ID, latest)
    gh.set_workflow_label(issue, WorkflowLabel.IMPLEMENTING)
    gh.write_pinned_state(issue, state)
    _hand_on_to_implementing(gh, spec, issue)
    return True


def _hand_on_to_implementing(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue,
) -> None:
    """Run the implementing tick this relabel hands the issue to.

    The issue is FETCHED again first, and that is the whole of what this owner
    adds. A label write does not refresh the object it was made against, so
    the one in hand still reports `workflow:decomposing` -- and the handler
    below it ends in a relabel of its own, which the transition guard reads
    against whatever the issue says it currently is. Handed the stale object
    it sees `decomposing -> validating`, an edge the graph does not declare,
    and under `WORKFLOW_TRANSITION_GUARD=enforce` it raises -- after the
    branch is pushed and the pull request is open.

    A read that fails ends the tick instead of running on the stale object.
    The label is already durable, so the next tick dispatches this issue to
    the implementing handler on a freshly read one and nothing is lost but a
    poll.
    """
    try:
        handed = gh.get_issue(issue.number)
    except Exception:
        log.exception(
            "issue=#%s could not be re-read after its relabel to %s; leaving "
            "the tick for the next poll rather than publishing against a "
            "stale label", issue.number, WorkflowLabel.IMPLEMENTING,
        )
        return
    _implementing._handle_implementing(gh, spec, handed)


def _settled_candidate_owns_the_tick(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Hand a candidate the gate has finished with back to publication.

    The way out of this label for an implementation nobody has to decompose:
    the label goes back to `workflow:implementing` and the tick falls into that
    handler exactly as the kill-switch route does, so the ordinary publication
    reconciles the exact commit already committed on the branch.

    What this owes the pull requests first is exactly what an accepted verdict
    owes them, and for the same reasons: this generation put a "do not merge"
    notice on a pull request and holds the only copy of the description it
    displaced, and `pr_number` still names whichever change the issue carried
    into the gate. Both are dropped by the retirement the implementing gate
    takes a moment later -- which reads a record about SIZE and knows nothing
    about either -- so a notice left standing has nothing left to reclaim it,
    and a recorded pull request a human merged while the revision ran ends the
    issue as `done` before the revised candidate is ever published. So the hold
    comes off and the pointer is moved to the pull request the measured commit
    is actually on, before anything else moves.

    The record itself is deliberately KEPT across the handoff, and retiring it
    is the implementing gate's own step rather than this one's. It is what
    makes the handoff recoverable: the record is the only thing that says this
    issue's size question was asked and answered, so a tick that dropped it
    and then failed to move the label -- or died between the two -- would
    leave a `decomposing` issue with nothing on it to tell the initial
    decomposer apart from a settled candidate, and the next tick would re-plan
    work that is already written. Kept, every crash in the window is repaired
    by re-reading it: before the label the handback simply runs again, finding
    the hold already off and the pointer already moved, and after it the gate
    finds a measurement it recorded for the commit in hand and settles it
    there, retiring it durably ahead of the push it licenses.
    """
    if not _late_relabel._settles_to_implementing(state):
        return False
    log.info(
        "issue=#%d carries a committed candidate the size gate settled under "
        "the ceiling; handing it back to implementation rather than "
        "decomposing it again", issue.number,
    )
    context = _LateContext(
        gh=gh, spec=spec, issue=issue, state=state,
        generation=_late_state.read_late_generation(state),
    )
    if not _late_reconcile._released_hold(context):
        return True
    if not _late_reconcile._reconciled_pr(context):
        return True
    _comments._post_issue_comment(
        gh, issue, state, _SETTLED_NOTICE.format(label=WorkflowLabel.IMPLEMENTING),
    )
    _late_park_state._persist(context)
    gh.set_workflow_label(issue, WorkflowLabel.IMPLEMENTING)
    _hand_on_to_implementing(gh, spec, issue)
    return True
