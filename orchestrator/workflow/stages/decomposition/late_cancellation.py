# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Route cancelled late cycles through guarded cleanup and terminal reconciliation.

A cancelled cycle is never dispatched to an ordinary stage. Hard-skip
controls retain its mark while deferring effects, and the rejected terminal
is written only after all external obligations are settled.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github import (
    client as _client,
    labels as _labels,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    endings as _endings,
    models as _late_models,
    state as _late_state,
)
from orchestrator.workflow.stages.decomposition import (
    late_cancellation_cleanup as _late_cancellation_cleanup,
    late_cancellation_terminal as _late_cancellation_terminal,
    late_close_observation as _late_close_observation,
)
from orchestrator.workflow.state import (
    WorkflowLabel,
    is_allowed_transition,
)

log = logging.getLogger("orchestrator.workflow")

# The two labels a cancelled cycle's own decomposer can leave its owner on: a
# run spawned before the close writes one of them as its ordinary outcome, and
# a close observed inside that run lands ahead of it. Neither declares an edge
# to `rejected`, so the terminal an owner left there earns is one the graph
# alone would refuse and nothing else would ever write.
_RELABELLED_MID_ENDING = (WorkflowLabel.READY, WorkflowLabel.BLOCKED)


def _reconcile_closed_owner(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """End one late cycle whose owner is gone, as far as this visit can.

    The closed half of the ending: the reconciliation below, and then the
    terminal, which is asked last and of what the whole pass left.
    """
    settled = _late_cancellation_cleanup._reconciled(gh, spec, issue, state, generation)
    _late_cancellation_terminal._retired(gh, issue, state, settled)


def _refuses_cancelled(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether this issue is a cancelled cycle's ending and nothing else.

    The open half, and the reason it exists: a cancellation is irreversible
    within its cycle, so a human who reopens the issue does not get that cycle
    back. Between the reopen and the ending the issue would otherwise be
    dispatched to the handler its label names, and EVERY label names a handler
    that acts: one spawns the decomposer, one walks the dependency graph and
    activates children, the rest drive a delivery stage against a branch and a
    pull request this cycle no longer owns. Any of them would be the cancelled
    cycle resumed, so none of them is reached -- what the label is decides
    nothing about whether this refuses.

    What it does decide is where the ending can be written. `rejected` is what
    the CYCLE earns rather than what a closed issue earns: it is what the
    operator removes to authorize a restart, and reaching it is the only way
    back into ordinary work that does not silently resume a cycle a close
    already ended. It is written from the states the transition graph declares
    the edge from and nowhere else -- under a label it does not, the
    reconciliation still runs, the refusal still stands, and the cycle stays
    cancelled where it is rather than being relabelled out from under whoever
    put the issue there. A reopened owner that settles is retired exactly as a
    closed one is, and left open, since closing an issue a human just reopened
    is not this owner's to do.

    Running the reconciliation rather than merely refusing is what makes the
    refusal end: the closed-owner sweep visits closed issues only, so this is
    the one pass that would ever come back to a reopened owner, and a refusal
    with nothing behind it would freeze the issue until somebody closed it
    again.

    The unlabeled state is refused with every other one, and by this owner.
    The restart is asked one guard ahead, so an issue reaching here with no
    label is one that guard has already declined -- because the cycle still
    owes something, or because nothing on the record proves the terminal was
    applied and then removed. Either way the issue is not a fresh attempt and
    is not ordinary work: letting it fall through would hand a cancelled cycle
    to the pickup path, which greets it as new and mints a SECOND pinned
    comment that shadows the one this reading came from.

    What the unlabeled state does still decide is whether the terminal may be
    written from it, which `_ends_here` answers off the record rather than off
    the label. An operator who has taken `rejected` off is not handed it back;
    an issue that never got it -- a workflow label a human stripped
    mid-cleanup, so the ending had no state to write from -- is, once the
    cleanup it interrupted finishes.

    A record with no cycle on it is asked one more question before it is
    waved through, and only where the record itself says there is one to ask:
    a retirement that dropped a cycle records which cycle it dropped, so a
    close observed inside that very write is one a later process can still
    adopt off the thread.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        generation = _late_close_observation._retired_close_adopted(gh, spec, issue, state)
        if generation is None:
            return False
    generation = _late_close_observation._closed_under_a_label(gh, issue, state, generation)
    generation = _late_close_observation._inherited_close(gh, spec, issue, state, generation)
    if not generation.cancelled:
        return False
    log.warning(
        "repo=%s issue=#%s wears %r over a cancelled late cycle; settling "
        "that cycle rather than dispatching the issue",
        spec.slug, issue.number, label,
    )
    if _parked_ending(spec, issue):
        return True
    settled = _late_cancellation_cleanup._reconciled(gh, spec, issue, state, generation)
    _late_cancellation_terminal._terminal_proved(gh, issue, state, settled)
    _late_cancellation_terminal._terminal_recovered(gh, issue, label, state, settled)
    if _ends_here(state, settled, label):
        _late_cancellation_terminal._retired(gh, issue, state, settled)
    return True


def _parked_ending(spec: _config_models.RepoSpec, issue: Issue) -> bool:
    """Whether a control label defers everything past the mark.

    `backlog` and `paused` park an issue outside the state machine, and the
    ending is external work: a held pull request closed, a branch deleted, a
    ref reclaimed. Doing any of it would be reacting exactly where an operator
    said not to.

    The MARK is not deferred with it, and is already down by the time this is
    asked. A close ends the cycle irreversibly, and the pass this filter is
    about is the only one that would ever record it -- an owner parked while
    closed would otherwise come back from a reopen and an unpause with a live
    generation and spawn against it. So the fact is written and the reaction
    waits for the tick the label comes off.
    """
    skip_label = _labels.hard_skip_control_label(issue)
    if skip_label is None:
        return False
    log.info(
        "repo=%s issue=#%s has %r over a cancelled late cycle; the mark "
        "stands and everything it owes waits for the label to come off",
        spec.slug, issue.number, skip_label,
    )
    return True


def _ends_here(
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
    label: str | None,
) -> bool:
    """Whether the cycle's terminal may be written from where the issue is.

    The transition graph answers for every label a WORKFLOW wrote: each state
    a late cycle can be interrupted on declares the edge to `rejected`, and a
    state that does not -- `question`, applied by an operator who wants the
    issue discussed rather than ended -- is refused and said out loud on every
    visit rather than relabelled out from under whoever put it there. What
    ends that refusal is the same handshake as always: an operator taking the
    label off.

    The graph cannot answer for the two labels this cycle's OWN agent leaves
    behind. A decomposer spawned before the close writes `ready` or `blocked`
    as its ordinary outcome, and a close observed inside that run lands ahead
    of it -- so the ending, already irreversible, finds the owner wearing a
    decomposition outcome its own cancellation voided. Neither label declares
    that edge, so an ending refused there would be refused on every visit the
    cleanup sweep makes, forever: the sweep is what brings a tick back to such
    an owner, and the terminal is the only thing that lets it stop.

    From the UNLABELED state the RECORD answers instead of the label, because
    the label cannot tell apart the issues that reach it wearing none. One is
    the restart handshake: an operator took `rejected` off, and re-applying it
    would undo the one authorization a restart has. Another never got the
    terminal at all -- a human stripped the workflow label while the cleanup
    was still running, so every visit since has found the ending owed under a
    state it could not be written from. A third had it attempted and refused.
    What separates the first from the other two is the PROOF half of the
    terminal record: a cycle whose `rejected` was seen on the issue has been
    through the handshake, and one carrying only the decision, or nothing at
    all, is owed the write rather than holding the removal of one.
    """
    if label is None:
        return not _endings.terminal_confirmed(state, generation.cycle_id)
    if label in _RELABELLED_MID_ENDING:
        return True
    return is_allowed_transition(label, WorkflowLabel.REJECTED)
