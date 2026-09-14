# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one pass that comes back to an owner nobody will dispatch again.

A split records what it owes the remote on the generation ledger and lets the
umbrella's terminal settle it. That works for every issue that reaches the
terminal. It does not work for the one a human closed halfway: a closed
`decomposing` or `umbrella` issue is outside every other pass this
orchestrator makes, so the branch its superseded candidate sat on, the
immutable ref its children were cut from, and the pull request it was holding
would be held by a repository nothing ever asked about again.

So this owner exists, and its whole shape is decided by what it must NOT do.
It is cleanup, not recovery: no agent is spawned, no workflow is resumed, no
child is created or activated, and no child that already exists is touched at
all. The issue is closed, and the close is a human decision this pass has no
standing to reverse -- what it acts on is the cycle, which ends, and the
ledger, which is the record of what the orchestrator put on somebody's
repository and is therefore the one thing it still owes.

What that ending consists of is the cancellation owner's, next door: the mark
that goes down before any external call, the held pull request it closes over
one notice, the branch and the ref it hands to the reclamation rules unchanged,
and the `rejected` terminal a fully settled cycle earns. What is here is one
of the two entries into it -- the re-read of the close, and the one reading
that says whether there is a cycle to end at all. The other is the
dispatcher's own guard, which takes the same ending for an owner a human
reopened before it finished.

The close is re-read rather than trusted because the reading that routed this
issue was taken on the polling thread and the worker refetched it afterwards.
What that second reading decides is what this pass DOES, though, and never
whether the cycle ends: being here at all means a close was observed, by the
poll that yielded the issue or by the dispatcher that routed it, and an
observed close cancels the generation irreversibly. So an issue that is open
again is marked all the same and stopped there -- nothing external is done to
an issue somebody just reopened, and the ending it now owes is the
dispatcher's own guard's from the next tick, which is the one pass that owns a
reopened cancelled owner.

An issue with no recorded generation is every issue the initial decomposer
ever made, and it leaves without a write of its own.

Nothing here decides a terminal by measuring the workflow. The umbrella's own
branch is where a settled ledger earns a `done`, and an issue a human already
closed has nothing left to earn -- so the only terminal this path ever writes
is the one that says the cycle it was carrying ended without publishing.

The other label it writes is not a terminal and is not a decision about the
workflow either: it is what keeps a closed owner reachable. This sweep queries
four labels -- the two an adjudication runs under, and the two an interrupted
ending can be left on by a decomposition outcome that landed after the close
was observed -- and an owner moved off all four by hand is one nothing would
bring a tick back to. So an owner that still owes the remote is put back under
one the sweep asks for, and the held observation covers the window until it is.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_cancellation as _late_cancellation,
    late_cancellation_reading as _late_cancellation_reading,
    late_cancellation_state as _late_cancellation_state,
    late_close_observation as _late_close_observation,
    late_close_reading as _late_close_reading,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _handle_closed_owner_cleanup(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue,
) -> None:
    """Settle what one closed snapshot owner still owes the remote.

    The whole of what a closed owner earns. It is reached only from the
    dispatcher's cleanup route, which is what guarantees the properties this
    pass is allowed to have: an issue on this path is never handed to the
    stage handler its label names, so nothing below can spawn the decomposer,
    resume an adjudication, or walk the dependency graph.

    Reaching it is also what says a close was OBSERVED -- the route is taken
    on a closed reading and on nothing else -- so an issue this pass finds
    open again has been reopened since that reading rather than never closed.
    It is marked cancelled all the same, because an observed close ends the
    cycle irreversibly, and nothing else is done to it here: acting externally
    on an issue somebody has just reopened is not this pass's to do, and the
    mark is what hands it to the dispatcher's own guard, which owns a reopened
    cancelled owner from the next tick and settles it there.

    An owner with no cycle left is asked one question before it is stepped
    over, and then finished rather than stepped over. The question is the
    retirement's own correlation: a terminal that made its retirement durable
    and then died leaves a record naming which cycle it dropped, and a close
    observed inside that write leaves a receipt on the thread naming the same
    one. Where the two agree the cycle goes back cancelled and this pass ends
    it like any other. Where they do not -- no correlation, or no receipt --
    what is left is an umbrella whose terminal is due and whose label never
    landed, which is `umbrella` and closed, exactly what this sweep queries.

    An owner the pass leaves still owing something is put back under a label
    the sweep queries -- see `_kept_in_the_sweep`. The observation that routed
    this visit is memory, and the label is the only durable thing that reaches
    a closed issue, so an ending left under a label outside the queried four
    would otherwise be finished by no later process.
    """
    state = gh.read_pinned_state(issue)
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        generation = _late_close_observation._retired_close_adopted(
            gh, spec, issue, state,
        )
    if generation is None:
        _finished_terminal(gh, issue, state)
        return
    withheld = _withheld(issue)
    if withheld is not None:
        log.info(
            "issue=#%s carries a late cycle a close ended, and %s; marking "
            "the cancellation and doing nothing else this visit",
            issue.number, withheld,
        )
        _late_cancellation_state._marked(gh, issue, state, generation)
        return
    _late_cancellation._reconcile_closed_owner(
        gh, spec, issue, state, generation,
    )
    _kept_in_the_sweep(gh, issue, state)


def _kept_in_the_sweep(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Put a closed owner back under a label that will bring a tick back.

    The held observation routes an owner here whatever its label says, and it
    is memory: a restart loses it, and the label is then the only thing left
    that reaches a closed issue at all. The sweep queries four of them -- the
    two an adjudication runs under and the two an interrupted ending can be
    left on -- and a label OUTSIDE all four is one nothing would ever bring a
    tick back to. A hand relabel puts an owner there, and so does an operator
    moving a closed owner onto a terminal over a cycle that still owes
    something.

    Only while something is still OWED, and only from a label outside those
    four. An ending that finished wrote `rejected` and is meant to leave the
    sweep; an owner already on a queried label is already reachable and is
    left exactly where it is, terminal included.

    Which of the two comes from the record, the same way the half-finished
    decomposition recovery reads it: an issue whose split converted it carries
    the umbrella flag, and one that never got that far is still where every
    adjudication runs. Nothing is dispatched under either while the cycle is
    cancelled -- the guard ahead of every handler refuses it and settles the
    ending instead -- and the terminal that ending earns takes the issue back
    out of the sweep for good.

    Written UNGUARDED, because it is not a transition: the graph describes the
    moves this workflow makes, and this repairs one it did not make. A write
    GitHub refuses is logged rather than raised -- the observation this pass
    is still carrying is what brings the next tick back to try again.
    """
    if not _late_cancellation_reading._still_owed(
        _late_state.read_late_generation(state),
    ):
        return
    if gh.workflow_label(issue) in _late_close_reading._SWEPT_LABELS:
        return
    label = (
        WorkflowLabel.UMBRELLA if state.get(_state._UMBRELLA)
        else WorkflowLabel.DECOMPOSING
    )
    log.warning(
        "issue=#%s is closed with a cancelled cycle that still owes the "
        "remote, under a label no closed sweep queries; putting %r back so a "
        "later tick reaches it", issue.number, str(label),
    )
    try:
        gh.set_workflow_label(issue, label, guarded=False)
    except Exception:
        log.exception(
            "issue=#%s could not be put back under a swept label; the held "
            "observation is what brings the next tick back to it",
            issue.number,
        )


def _finished_terminal(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Write the terminal an umbrella earned and a crash took the label off.

    The umbrella's own terminal is one pinned write and then two requests: the
    label, and the close. The write is what makes the decision durable -- it
    stamps the resolution and retires the cycle together -- so an owner
    carrying that stamp with no cycle left is one whose terminal is due and
    whose label simply never landed. `done` is written here rather than left
    for a human, because the alternative is an issue this sweep yields on
    every pass forever.

    Anything else with no cycle is not this pass's: every umbrella the initial
    decomposer made carries no generation and no stamp, and a closed one is a
    hard human stop with nothing to finalize.

    A write GitHub refuses is logged rather than raised. The label staying put
    IS the retry -- the owner keeps `umbrella`, which is what this sweep asks
    for, so the next pass writes what this one could not.
    """
    if state.get(_state._UMBRELLA_RESOLVED_AT) is None:
        return
    if gh.workflow_label(issue) == WorkflowLabel.DONE:
        return
    log.info(
        "issue=#%s recorded its umbrella terminal and never got the label; "
        "writing it now", issue.number,
    )
    try:
        gh.set_workflow_label(issue, WorkflowLabel.DONE)
    except Exception:
        log.exception(
            "issue=#%s could not be handed the terminal its record already "
            "earned; it stays swept until it is", issue.number,
        )


def _withheld(issue: Issue) -> str | None:
    """Why this visit may mark the cancellation and do nothing more.

    Two reasons, and neither of them is about the cycle: it ended when the
    close was observed, and that is what the mark records. What they defer is
    the external work the ending owes -- which is the whole of what a pass
    over an issue in either of these states may not do.

    An issue open again was reopened between the poll and the worker's
    refetch. Acting externally on one somebody has just reopened is not this
    pass's to do; the dispatcher's own guard owns it from the next tick.

    An issue carrying `backlog` or `paused` is one an operator has parked
    outside the state machine, and a pass that closed its pull request or
    deleted its branch would be reacting exactly where they said not to. The
    mark costs nothing and loses nothing: it is a fact about a close that
    already happened, and the cleanup resumes on the tick the label comes off.
    """
    if not issue_is_closed(issue):
        return "is open again"
    skip_label = hard_skip_control_label(issue)
    if skip_label is None:
        return None
    return f"an operator has parked it with {skip_label!r}"
