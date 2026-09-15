# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Write and prove the rejected terminal of a fully settled cancelled cycle.

A terminal is first recorded as owed, then applied, then confirmed.
A later pass may recover confirmation from the orchestrator's own label
history, which is the evidence an operator's restart gesture requires.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import (
    client as _client,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    endings as _endings,
    models as _late_models,
)
from orchestrator.workflow.stages.decomposition import (
    late_cancellation_reading as _late_cancellation_reading,
    late_cancellation_state as _late_cancellation_state,
)
from orchestrator.workflow.state import (
    WorkflowLabel,
)

log = logging.getLogger("orchestrator.workflow")



def _retired(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Hand a settled cycle its terminal, or say what is still holding it.

    `rejected` is the honest end of a cycle whose owner a human closed, and it
    is also what stops this pass repeating: every label the closed-owner sweep
    queries is one the owner keeps until this write lands, so writing it is
    the only thing that takes the issue out of the sweep.

    Which is exactly why it may not be written early. An issue that has left
    the sweep is one nothing revisits, so a terminal taken over an unreclaimed
    branch or a retained ref would leave that object on the remote with
    nothing left to come back for it. The label staying put IS the retry, and
    the reason it stays is logged on every visit that holds -- a cleanup that
    never finishes and never says why is the one shape an operator cannot act
    on.

    An issue already wearing the terminal is left alone rather than written
    again. The sweep does not yield one, so that is the pass driven straight
    at an owner somebody already settled -- and re-setting a label costs a
    write and a second `stage_enter` on a state the issue never re-entered.
    It is asked after the hold rather than before it, so an owner that
    somehow wears the terminal over something still owed says so out loud.

    Written UNGUARDED, because it is not a transition. The graph describes the
    moves this workflow makes, and the move this corrects is one it did not:
    an agent's ordinary decomposition outcome landing on the owner after the
    close that cancelled the cycle it was running for. Under `enforce` a
    guarded write would raise there, every visit, and the owner would sit
    closed on a label no query reaches -- refusing the repair of a move the
    guard never described, which is the opposite of what the guard is for.

    It is recorded in two phases, exactly as an external obligation is. The
    DECISION goes down first -- which cycle this terminal is for -- because a
    tick that dies between the write and the record of it needs something
    durable to come back to. The PROOF goes down after, and only for a write
    that landed, because an operator authorizes a fresh cycle by REMOVING this
    label and the removal leaves an issue indistinguishable from one whose
    workflow label a human stripped mid-cleanup. An attempt is not a terminal:
    treating the decision as proof would let a write GitHub refused authorize
    a restart nobody asked for, on an owner that is unlabeled for the reason
    it always was.

    The proof this pass takes is the write RETURNING, and it is not re-derived
    by reading the issue back: the label a read finds on this object is only
    what that same write left there, and on any object the write did not go
    through it is the label the issue wore a moment ago, which records
    nothing. That matters most exactly where nothing would notice -- a closed
    owner leaves the sweep on this write and gets no second visit to see the
    label for itself.

    A write GitHub refuses is left for the next visit rather than raised: the
    obligations are settled and recorded by then, and the only thing missing
    is the label that says so -- which is exactly what the unproved decision
    brings this pass back for.
    """
    held = _late_cancellation_reading._outstanding(generation)
    if held:
        log.info(
            "issue=#%d is closed and cancelled, and still owes the remote: "
            "%s; it stays swept until it does not",
            issue.number, ", ".join(held),
        )
        return
    if gh.workflow_label(issue) == WorkflowLabel.REJECTED:
        _terminal_recorded(gh, issue, state, generation)
        return
    _endings.record_terminal(state, generation.cycle_id, confirmed=False)
    _late_cancellation_state._persisted(gh, issue, state, generation)
    try:
        gh.set_workflow_label(issue, WorkflowLabel.REJECTED, guarded=False)
    except Exception:
        log.exception(
            "issue=#%d settled everything its cancelled cycle owed but could "
            "not be moved to rejected; the next sweep writes the label",
            issue.number,
        )
        return
    _terminal_recorded(gh, issue, state, generation)


def _terminal_proved(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Record a `rejected` this pass can SEE on the issue, once.

    The reading half of the receipt, and what makes the record available to
    passes that made no write at all: a cancellation that reached its terminal
    before this record existed carries no proof of it, and a tick that died
    between the label landing and the receipt carries none either. Both are an
    issue visibly wearing `rejected` over a cancelled cycle, which is a thing
    any visit can see and write down -- so the operator's FIRST removal is the
    one that authorizes the fresh cycle.

    Asked of the label as this pass FOUND it, which is why it is not what the
    pass that writes the terminal uses: that pass holds its own write
    returning, and a read after it could only repeat what the write left on
    the object it went through.
    """
    if gh.workflow_label(issue) != WorkflowLabel.REJECTED:
        return
    _terminal_recorded(gh, issue, state, generation)


def _terminal_recovered(
    gh: _client.GitHubClient,
    issue: Issue,
    label: str | None,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Prove a terminal a dead process left unrecorded, off the remote itself.

    The one window neither half of the receipt covers. The decision goes down,
    the label write lands, and the process dies before the proof -- and what
    is left is an issue on `rejected` that nothing revisits, since a terminal
    is on no sweep's list. The operator reopens it and takes the label off,
    and now the record shows a decision with no proof, which is the same thing
    a label write GitHub REFUSED leaves behind. One of those is a gesture and
    the other is an ending still owed, and no local reading tells them apart.

    So the remote is asked, and only from BEHIND the reconciliation: what
    decides whether anything is still owed is the record this pass has just
    settled, not the one it found. An obligation the ending discovers rather
    than reads -- the branch a supersession left behind and never wrote down
    -- is on no ledger until `_reconciled` puts it there, so adopting a proof
    in front of that would let the restart project away a branch nobody had
    looked for yet. Everywhere else this returns before it costs anything: the
    proof is already recorded, something is still owed, or the issue is
    wearing a label and the question does not arise.

    What is asked is which workflow label THIS orchestrator applied last, not
    whether `rejected` was ever applied at all. Both halves narrow it. The
    actor, because a collaborator may apply and remove that same name by hand
    and a terminal is a write this orchestrator makes -- reading somebody
    else's back would let a label nobody here wrote stand in for one it did.
    And the newest, because an issue reaches this terminal once per cycle, so
    an older one's is still in the history and adopting that would authorize a
    fresh cycle off a removal an operator made two cycles ago. The cycles are
    separated by construction: a cycle exists only because a restart retired
    its marker, and a restart retires only once its own target label has
    landed as one of THIS orchestrator's applications -- a target it finds
    somebody else applied is taken off and put back for exactly this reason --
    so a stale `rejected` always has a later application of its own after it.

    Fail-closed on every other answer. A history whose newest application is
    some other state is an ending still owed, one that names nothing this
    vocabulary recognizes says as much, and one that could not be read vouches
    for nothing; each writes the terminal again rather than starting a fresh
    cycle on a removal nobody made.
    """
    if not _terminal_unproved(label, state, generation):
        return
    if gh.last_workflow_label_applied(issue) != WorkflowLabel.REJECTED:
        return
    log.warning(
        "issue=#%d carried %s for cancelled cycle %d and no pass recorded "
        "it; adopting the remote's own history so the removal an operator "
        "has already made is the one that authorizes a fresh cycle",
        issue.number, WorkflowLabel.REJECTED, generation.cycle_id,
    )
    _terminal_recorded(gh, issue, state, generation)


def _terminal_unproved(
    label: str | None,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> bool:
    """Whether this issue is the one window the remote has to answer for.

    Four local answers, and the remote is asked only past all of them. The
    issue wears no label, over a cycle a close ended, with nothing left owed
    and no proof its terminal ever landed -- which is what an operator's
    removal leaves, and equally what a crash between the label and the receipt
    does, and what a cancellation that ended before this record existed
    carries. The DECISION is deliberately not required: a record written by a
    binary that had no such field is exactly the case the reading exists to
    recover, and demanding one would leave every cancellation that predates it
    needing a second removal.

    "Nothing owed" is what bounds the cost. An unlabeled owner whose cleanup
    is unfinished is visited every tick, and asking the remote on each of
    those would put a paginated walk on the steady state; asking only once
    settled costs one walk per removal, because the tick that gets no proof
    writes the terminal back and the issue stops being unlabeled.
    """
    if label is not None or not generation.is_present:
        return False
    if not generation.cancelled or _late_cancellation_reading._unsettled(generation):
        return False
    return not _endings.terminal_confirmed(state, generation.cycle_id)


def _terminal_recorded(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Write down that this cycle's terminal is on the issue, once.

    Reached two ways, and they are the same claim from either side of the
    write: a pass that just set the label and was not refused knows it landed,
    and a pass that finds the label already there can see that it did. What
    neither is, and what may not reach here, is an attempt that raised.

    Bounded by what it records: a cycle already proved is left alone, so the
    guard that brings a tick back to a cancelled owner every tick costs a
    pinned write once rather than one per visit.
    """
    if _endings.terminal_confirmed(state, generation.cycle_id):
        return
    log.info(
        "issue=#%d carries %s over cancelled cycle %d; recording the terminal "
        "an operator removes to authorize a fresh one",
        issue.number, WorkflowLabel.REJECTED, generation.cycle_id,
    )
    _endings.record_terminal(state, generation.cycle_id, confirmed=True)
    _late_cancellation_state._persisted(gh, issue, state, generation)
