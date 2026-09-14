# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Poll umbrella children and guard completion against outstanding late-split work.

Child activation, cleanup settlement, and terminal publication each honor
observed owner closure. A close racing retirement restores the live cycle
so its cancellation still has the evidence it needs.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    retiring_cycles as _retiring_cycles,
    usage as _usage,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    activation as _activation,
    late_cancellation_state as _late_cancellation_state,
    late_cleanup as _late_cleanup,
    late_close_observation as _late_close_observation,
    late_publication as _late_publication,
    parents as _parents,
    state as _state,
    umbrella_terminal as _umbrella_terminal,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _handle_empty_umbrella(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    if state.get(_state._AWAITING_HUMAN):
        return
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} `{WorkflowLabel.UMBRELLA}` without "
        "recorded children; "
        "manual relabel suspected.",
        reason="umbrella_no_children",
    )
    gh.write_pinned_state(issue, state)


def _complete_umbrella(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> None:
    """Say the umbrella is resolved, hand it `done`, and close it.

    `done` is the write that cannot be recovered from: it takes the issue off
    every label the closed-owner sweep queries, so nothing would ever visit it
    again. What makes it safe is not a correction behind it but the write
    AHEAD of it -- one pinned write that stamps the resolution and RETIRES the
    generation together, and past which there is no live cycle for a close to
    end.

    So the latch is asked for the last time immediately before that write,
    with no request standing between the answer and it, and a close observed
    there stops the terminal outright: the owner keeps `umbrella` with the
    mark down, and the ending retires it to `rejected` from a label the sweep
    still queries. A close arriving AFTER it is a human closing an issue this
    orchestrator had already finished -- every child resolved, every
    obligation reclaimed, the cycle over -- which is not a cancellation and
    leaves nothing to correct.

    Every window a crash can land in is one the next pass repairs. Before the
    pinned write the owner is on `umbrella` with a live cycle, which is what
    the sweep and the umbrella poll both already own. After it the owner is on
    `umbrella` with the resolution recorded and no cycle at all, and both of
    those passes finish the terminal from the record rather than starting the
    walk again -- which is also why the closing notice is said once, gated on
    the same stamp.

    That write is itself a request, so what the window observed is asked once
    more BEHIND it -- and taken as the window closes rather than before it, so
    no interval is left for a poll to latch a close in. There the answer is
    not a refusal but a reinstatement: the cycle goes back on the record from
    this call's own memory and is cancelled there, so a close observed while
    the cycle was still live is one the ending can still be entered from.
    """
    if state.get(_state._UMBRELLA_RESOLVED_AT) is None:
        _umbrella_terminal._resolution_said(gh, issue, state)
    if _late_close_observation._latched_close_ends(gh, spec, issue, state):
        return
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    state.set(_state._UMBRELLA_RESOLVED_AT, _usage._now_iso())
    if _late_close_observation._latched_close_ends(gh, spec, issue, state):
        return
    if _publication_holds_the_terminal(gh, issue, state):
        return
    live = _umbrella_terminal._retired_cycle(state)
    retiring = _retiring_cycles.retiring(spec.slug, issue.number, live.cycle_id)
    with retiring.held():
        gh.write_pinned_state(issue, state)
    if _reinstated(gh, issue, state, live, retiring):
        return
    _umbrella_terminal._finished_umbrella(gh, issue)


def _publication_holds_the_terminal(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Whether the change this split closed still lets the terminal fire.

    Asked immediately in front of the retirement write, because that write IS
    the boundary: past it the publication group is gone, and the label and
    close behind it take the issue off every surface a tick would come back
    through. Nothing would ever ask again, and what would be left is an open
    change carrying superseded work under a parent this workflow had declared
    finished.

    The settlement the terminal waits on asks the same question before
    anything is said, so what reaches here is only a reopen that landed inside
    the resolution comment or the latches beside it -- each of them a request,
    and none of them a moment a reading taken in front of them survives.

    A refusal writes nothing at all. The record on the remote is exactly as
    this pass found it: the group intact, the cycle live, the label `umbrella`
    -- so the next tick asks earlier, where refusing costs nothing, and every
    tick after that until a human settles the pull request. The one thing
    already spent is the sentence, and the thread is what stops that repeating.
    """
    undone = _late_publication._release_undone(gh, issue, state)
    if not undone:
        return False
    log.error(
        "issue=#%s holds the terminal its children earned: %s",
        issue.number, undone,
    )
    return True


def _reinstated(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    live: LateGeneration,
    retiring: _retiring_cycles.RetiringCycle,
) -> bool:
    """Put back a cycle the retirement write dropped a moment too early.

    The write is a request like every other, so a poll can observe the close
    inside it -- and the reading that observation leaves is durable on the
    thread while the record it names has just stopped naming a cycle. What
    answers that HERE is the generation still in the call's own memory, which
    is the fastest answer there is and the only one a live process needs. The
    correlation the write records beside the clear -- see `_retired_cycle` --
    is for the process that never reaches this barrier at all.

    It goes back exactly as it was and is cancelled from there, so the owner
    keeps `umbrella` with the mark down and the ending retires it to
    `rejected` from a label the closed-owner sweep still queries. The
    terminal is not written: the label and the close below it are what this
    refuses, and everything already said stands.

    Asked OF the window rather than of the latch. The window decides what it
    observed as it closes, under the lock that closes it, so there is no
    interval between the answer and the exit for a poll to latch a close and
    post a receipt in -- and an umbrella with no cycle to retire carries a
    window that advertised nothing and observed nothing.
    """
    if not retiring.observed:
        return False
    log.warning(
        "issue=#%s was observed closed as its umbrella terminal retired "
        "cycle %d; putting that cycle back so the ending has something to "
        "run from",
        issue.number, live.cycle_id,
    )
    _late_cancellation_state._marked(gh, issue, state, live)
    return True


def _completed_or_cancelled(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _ChildScan,
) -> None:
    """Resolve this umbrella, unless a close arrived while it was settling.

    Every child is resolved, so this is the last tick that could settle what
    the issue still owes a remote -- and the only one that will come back if
    it cannot. A refusal keeps the label, which is the retry.

    The settlement is itself remote work: a branch delete, a ref delete, a
    receipt on each child cut from a reclaimed ref. So the latch is asked
    AGAIN behind it, because `done` is the one write on this path that cannot
    be recovered from -- it takes the issue off every label the closed-owner
    sweep queries and closes it, and a cancellation that bypassed it would be
    stranded for good with nothing left to visit the issue.
    """
    if not _late_cleanup._settled_for_terminal(gh, spec, issue, state, scan):
        return
    if _late_close_observation._latched_close_ends(gh, spec, issue, state):
        return
    _complete_umbrella(gh, spec, issue, state)


def _handle_umbrella(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    """Poll children on an umbrella parent that has no implementation of
    its own.

    Mirrors `_handle_blocked` for the rejected/manually-closed checks and
    the dep-graph activation walk, but the all-done branch resolves the
    umbrella to `done` and closes the issue instead of flipping it to
    `ready` -- there is no implementation pass for an umbrella, so the
    only terminal path is "every child resolved -> close".
    """
    state = gh.read_pinned_state(issue)

    # An umbrella parent NEVER enters implementation -- it just closes when
    # every child resolves -- so a body edit cannot be picked up by any
    # later stage's drift check. Route it back to decomposing here so the
    # new manifest is re-derived against the updated body; without this
    # route-back, an edited umbrella would silently close to `done` against
    # the stale manifest once the old children finished.
    if _parents._route_parent_drift(gh, issue, state):
        return

    children = state.get(_state._CHILDREN) or []
    if not children:
        _handle_empty_umbrella(gh, issue, state)
        return

    scan = _parents._read_child_labels(gh, issue, children)
    if scan is None:
        return
    _acted_on_children(gh, spec, issue, state, scan)


def _acted_on_children(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _ChildScan,
) -> None:
    """Do what this reading of the children earns, if anything still may.

    Split from the read above because the read is where the poll gets its
    chance: a scan is a request per child, and everything here ACTS on what
    it found -- it reclaims a remote a settled split still owes, or it hands
    the issue `done` and closes it, or it releases a child to an agent. A
    close observed inside the scan reaches no other pass, so the barrier is
    the first thing past it.

    `done` is the worst of the three to get wrong, and it is why the barrier
    is here rather than one layer down: that write takes the issue off both
    labels the closed-owner sweep queries, so a cancellation it bypassed
    would never be recorded by anything.
    """
    if _late_close_observation._latched_close_ends(gh, spec, issue, state):
        return
    if _parents._parked_on_children(gh, spec, issue, state, scan):
        # Parked for a human, and still the owner of what its split put on the
        # remote. Every disposition that parks an umbrella closed the child it
        # names -- a rejection and a manual close both do -- so the rule that
        # owns the ref has just been satisfied by the very reading that
        # stopped the tick. Settling here is what keeps that from waiting on a
        # human: nothing else revisits an OPEN umbrella, so a parent parked
        # over a reclaimable ref would hold it for as long as the park stood.
        # It decides no terminal -- the park is the parent's answer, unchanged
        # -- and reports only what it actually did.
        _late_cleanup._settle(gh, spec, issue, state, scan)
        return
    if all(label == _state._DONE for label in scan.labels.values()):
        _completed_or_cancelled(gh, spec, issue, state, scan)
        return
    held = _activation._activate_ready_children(
        gh, spec, issue, state, scan,
    )
    _activation._log_held_children(
        issue, _state._UMBRELLA, scan.children, scan.labels, held,
    )
