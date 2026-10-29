# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fresh pinned reads and durable state writes at the agent-launch charge boundary.

A failed or unreadable record refuses the launch, and so does one showing a
launch its caller owed once already made by another road, or no longer
standing on what its caller holds it to. Only fields changed by this charge
are merged back into the caller state, preserving its staged changes."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github import pinned_refusal as _pinned_refusal
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _pinned_commit,
    record_admission as _record_admission,
    run_ledger_values as _run_ledger_values,
)

log = logging.getLogger("orchestrator.workflow")


# Absence, as a value the merge below can compare against. `None` is a field a
# pinned state legitimately carries, so it cannot stand for one that is not
# there.
_UNSET = object()

# What a launch whose charge meets a record admission refuses does about it.
_CHARGE_ABANDONED = "abandoning the launch and the stage handler that asked for it"


@dataclass(frozen=True)
class OwedLaunch:
    """A launch owed exactly once -- a handed change request's developer -- and what else it stands on.

    `at` is the lifetime run count it is owed at, which its start records
    (`run_ledger_values.AGENT_RUN_OWED_STARTED`). Whatever its caller held
    the launch to is requests old by the time the circuit charges and starts
    it, so the circuit asks again at that boundary: `resolves` makes the
    requests its standing takes beyond the pinned comment -- the subject
    resolved again -- right behind the charge, and `stands` judges each
    reading of the comment the charge is written from, the one its start is
    written over last. False from either refuses the launch. None of either is
    a launch standing on nothing but its count.
    """

    at: int
    resolves: Callable[[], bool] | None = None
    stands: Callable[[PinnedState], bool] | None = None


@dataclass(frozen=True)
class AgentRunBudget:
    """What a launch has to name for its charge to be askable at all.

    Two objects rather than one, because they answer different halves and
    neither substitutes for the other. The `issue` is what a charge is written
    on, what a park is taken against, and what a notice is said to. The
    `state` is the caller's own in-memory object, which the charge is merged
    back into so the write that dispositions the run at the end of it does not
    hand the issue back the count of one that never launched.

    `owed` is for a caller whose launch is owed exactly once, and names the
    count it is owed at and what else it stands on; None for every launch
    owed however often it is asked for.
    """

    issue: Issue
    state: PinnedState
    owed: OwedLaunch | None = None

    @property
    def owed_at(self) -> int | None:
        """The lifetime run count the launch is owed at, where it is owed exactly once."""
        return None if self.owed is None else self.owed.at

    def made_elsewhere(self, durable: PinnedState) -> bool:
        """Whether `durable` shows the launch this budget is owed once already made by another road.

        Asked on the very reading the charge is taken on, since whatever the
        caller checked before it is requests old by then, and a launch another
        road started in between is there alone to see. That launch is the one
        whose start recorded `owed_at` (`run_ledger_values._owed_started`) --
        not merely a count past it, which a reviewer or any other road's run
        moves just the same -- save a start the caller's own state carries:
        every write this circuit takes is merged back onto that state, so a
        continuation of the launch -- a poisoned session's fresh retry, a
        recovery prompt -- is its own, not another road's. A charge standing
        unstarted recorded no start, and a reservation taken for this very
        launch is honored.
        """
        owed_at = self.owed_at
        if owed_at is None:
            return False
        own = _run_ledger_values._owed_started(self.state) == owed_at
        return not own and _run_ledger_values._owed_started(durable) == owed_at


def _durable_state(gh: GitHubClient, issue: Issue) -> PinnedState | None:
    """The pinned state a charge may be written onto, or nothing.

    Two readings are refused rather than charged. A request that failed leaves
    no count to charge against at all, and is answered None: the launch is
    refused as a run that never started, and the poll comes back. A pinned
    comment admission refuses -- one that would not parse, or one under a
    version this build does not admit -- reads back empty, which is
    indistinguishable from an issue that has spent nothing, so a charge taken
    on it would both hand the issue a fresh lifetime and overwrite whatever the
    comment was still holding. That one RAISES (`pinned_refusal.RecordRefused`)
    rather than answering: this is the one boundary every agent launch is
    charged at, so a comment a human edited into a refused record mid-tick
    launches nothing however deep in a handler the launch is -- and a handler
    told only "never invoked" would go on to its own exit roads, a scratch
    checkout's teardown among them, over an issue whose every artifact is now
    a human's to dispose of. The dispatcher abandons the handler on it.
    """
    try:
        durable = gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not be read for the agent-run charge its next "
            "launch owes; invoking nothing this tick",
            issue.number,
        )
        return None
    if _record_admission.refuses(issue, durable, _CHARGE_ABANDONED):
        raise _pinned_refusal.RecordRefused(f"issue #{issue.number} refused admission at its agent-run charge")
    return durable


def _persist(
    gh: GitHubClient,
    budget: AgentRunBudget,
    durable: PinnedState,
    recorded: dict,
) -> bool:
    """Take one staged phase of the charge durably, and hand it to the caller.

    `recorded` is what the durable state carried before the phase was staged
    on it, so the whole of one phase goes out in one write and the count and
    the launch it was taken for are never on the issue apart. What the caller
    learns is only what this write actually landed: a refused request leaves
    the issue exactly as it was, so nothing is merged and the caller's own
    state goes on describing a charge nobody took.

    The writer raises `pinned_refusal.RecordRefused` over a record a human
    edited into one admission refuses since the charge read it, with nothing
    written, and that refusal propagates past this owner so the handler is
    abandoned rather than told only that nothing was invoked. Every other
    failure it raises is a write nobody took, answered False. Its quiet
    refusals -- a withheld state, a state the next reading would refuse --
    return without raising, so the write is asked whether that very attempt
    landed (`record_admission.written`) rather than trusted for not raising.
    Each of these invokes nothing: the reservation and the start are each a
    write a process may only follow.
    """
    try:
        landed = _record_admission.written(gh, budget.issue, durable)
    except _pinned_refusal.RecordRefused:
        raise
    except Exception:
        log.exception(
            "issue=#%d could not record the agent run its next launch is "
            "charged; invoking nothing rather than spawning a run the ledger "
            "would never see",
            budget.issue.number,
        )
        return False
    if not landed:
        log.error(
            "issue=#%d its pinned comment took no record of the agent run its "
            "next launch is charged; invoking nothing rather than spawning a "
            "run the ledger would never see",
            budget.issue.number,
        )
        return False
    _merge_circuit_fields(recorded, durable, budget.state)
    return True


def _merge_circuit_fields(
    recorded: dict, durable: PinnedState, state: PinnedState,
) -> None:
    """Carry this owner's own writes onto the state the caller still holds.

    Scoped by what actually changed between the durable read and the durable
    write, which is the only definition of "this owner's fields" that stays
    true as the park beside it grows a field. Everything else the durable
    state carries is left alone: the caller's copy may hold a staged edit of
    the same field, and this is not the write that decides it.

    Without this the caller's own write at the end of the run would put the
    charge back the way its read found it -- the issue would have paid for the
    run and be handed the count of an issue that never launched one.

    The comment carries them once this owner's write has landed, so the caller's
    state remembers them as read (`pinned_commit.takes_in`): a guarded commit
    behind this one counts them as the comment's rather than as its own.

    The pinned comment's identity travels with them where the caller has none.
    An issue whose state was created by this write is one the caller would
    otherwise pin a second comment for.
    """
    laid = [
        key for key in set(recorded) | set(durable.state_data)
        if durable.state_data.get(key, _UNSET) != recorded.get(key, _UNSET)
    ]
    for key in laid:
        written = durable.state_data.get(key, _UNSET)
        if written is _UNSET:
            state.state_data.pop(key, None)
        else:
            state.set(key, written)
    _pinned_commit.takes_in(state, durable.state_data, laid)
    if state.comment_id is None:
        state.comment_id = durable.comment_id
