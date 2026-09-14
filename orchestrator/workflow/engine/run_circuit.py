# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one launch pays before a process exists, and what turns it away.

The ledger beside this owner records what an issue may spend and what it has
already spent; the park beyond it is where an issue with nothing left stops.
This is the one place between the two: the boundary every role in this
repository reaches an agent through, and so the only place a charge can be
taken that no road walks around. A gate written into each spawning handler
instead would be a gate the next handler is added without.

Two durable writes rather than one, because the window between them is the
only thing that can tell a launch that never ran from one that did. `reserved`
says a run is charged and no process has been invoked; `started` says the
invocation is what happens next. Both land BEFORE a process exists, because a
charge taken behind the spawn is one a crash, a timeout, or a shutdown kill
collects for free -- and those are exactly the runs a lifetime ceiling is
there to stop an issue repeating. A tick that dies between the two leaves
`reserved`, and the launch it was taken for runs on that charge rather than
paying twice. A tick that dies anywhere after `started` leaves a run nobody
can prove did not happen, so the next launch pays for itself: read as spent,
the issue loses at most a run it may already have had; read as unspent, a
crash loop is a way to spend a lifetime without ever moving past it.

Which launch a standing charge belongs to is written down with it. The
fingerprint is derived from what a request IS -- the role, the stage, the
backend and the spec behind it, the session it resumes, the round and the
attempt it is -- and never from the prompt it carries, which is rebuilt from a
thread that moves between ticks and would make one launch look like a new one
every poll. So a charge is reused by the launch that took it and by nothing
else.

The writes go to freshly read durable state, and only what this owner touched
comes back. Everything the caller is holding is mid-tick: a reviewer spec
staged ahead of the spawn, a watermark a reply moved, a retry slot charged, a
session id about to be replaced. Those belong to the handler's own single
write, which decides at the END of the run whether they are kept at all, and a
charge that flushed them would publish half a tick as though the run had
already been dispositioned. The re-read is what makes the charge authoritative
against whatever else moved since the tick's own read; the merge is what keeps
the caller's later write from putting the charge back the way it found it.

Nothing is invoked unless the charge landed. An unreadable pinned comment, a
refused write, and an allowance with nothing left all end the same way: no
process, and a result that reads as a run which did not happen -- the answer
every spawning handler in this repository already returns without writing
durable state for. Only the last of the three is a decision about the issue,
so only that one parks it and says so.

Each of the three durable steps is reported to both observability sinks by
`run_budget.py`, and reported AFTER the write that makes it durable. That
order is what keeps the stream a count of what happened rather than of what
was attempted: a refused write leaves no record, and a launch honoring a
charge an earlier tick left standing reports the start it paid for and no
second reservation. The two readings a launch is refused on without any
decision about the issue -- a state nobody could read, a write nobody could
take -- record nothing at all, because nothing about the issue changed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    run_budget as _run_budget,
    run_ledger as _run_ledger,
    run_limit as _run_limit,
)
from orchestrator.workflow.engine.run_budget import AgentRunLaunch
from orchestrator.workflow.engine.run_ledger import AgentRunLedger

log = logging.getLogger("orchestrator.workflow")

# What a launch that never happened reports as its status. Negative, like
# every other code in this repository that is not an ordinary exit, because
# there was no process to take one from.
_NO_PROCESS_EXIT_CODE = -1

# Absence, as a value the merge below can compare against. `None` is a field a
# pinned state legitimately carries, so it cannot stand for one that is not
# there.
_UNSET = object()


@dataclass(frozen=True)
class AgentRunBudget:
    """What a launch has to name for its charge to be askable at all.

    Two objects rather than one, because they answer different halves and
    neither substitutes for the other. The `issue` is what a charge is written
    on, what a park is taken against, and what a notice is said to. The
    `state` is the caller's own in-memory object, which the charge is merged
    back into so the write that dispositions the run at the end of it does not
    hand the issue back the count of one that never launched.
    """

    issue: Issue
    state: PinnedState


def _refused_run() -> AgentResult:
    """What a launch this owner turned away answers its caller with.

    Marked as an interrupted run because that is what it is to everything
    above: a run with no trustworthy outcome, whose whole contract is that the
    handler returns without writing durable state. Every spawning stage
    already reads that answer through `_ignore_if_interrupted`, so a refusal
    reaches a park, a watermark, and a session record the same way a shutdown
    kill does -- by reaching none of them.

    And marked as never invoked, which a shutdown kill is not. Several stages
    inspect the worktree BEFORE they ask about interruption, on purpose: a run
    the sweep killed can have written before it died, and what it left is an
    operator's to look at whether or not the run counted. A refusal wrote
    nothing, so a tree that is dirty for some older reason is not this
    launch's doing -- and a park taken in its name would overwrite the one
    this owner just recorded with a reason about a process that never existed.
    `_ignore_if_never_invoked` is what those roads ask first.
    """
    return AgentResult(
        session_id=None,
        last_message="",
        exit_code=_NO_PROCESS_EXIT_CODE,
        timed_out=False,
        stdout="",
        stderr="",
        interrupted=True,
        invoked=False,
    )


def _charge_launch(
    gh: GitHubClient, budget: AgentRunBudget, launch: AgentRunLaunch,
) -> bool:
    """Whether this launch has paid for the process it is about to invoke.

    The whole circuit, in the order its answers have to be taken. The ledger
    is read off durable state rather than off the caller's, because the
    caller's has been carried since the tick's own read and a charge decided
    on a stale count is a ceiling enforced against a number that has moved.

    A charge already standing for this launch is one a previous tick took and
    never spawned, so it is honored rather than charged again -- and honored
    without asking the allowance, since the run it stands for is already paid
    for and refusing it would spend the charge on nothing. Every other launch
    is a new attempt: it is refused where the allowance has nothing left, and
    otherwise reserved, started, and let through.
    """
    durable = _durable_state(gh, budget.issue)
    if durable is None:
        return False
    ledger = _run_ledger._read_ledger(durable)
    if not ledger.pending_for(launch.fingerprint):
        if ledger.spent:
            _park_spent(gh, budget, durable, ledger, launch)
            return False
        if not _reserve(gh, budget, durable, launch):
            return False
    return _start(gh, budget, durable, launch)


def _reserve(
    gh: GitHubClient,
    budget: AgentRunBudget,
    durable: PinnedState,
    launch: AgentRunLaunch,
) -> bool:
    """Charge this launch one run, and record the charge if it landed.

    The record follows the write rather than the staging, so what reaches a
    sink is a run this issue durably owes rather than one a refused request
    left it never charged for.
    """
    recorded = dict(durable.data)
    charged = _run_ledger._reserve_run(durable, launch.fingerprint)
    if not _persist(gh, budget, durable, recorded):
        return False
    _run_budget._emit_charge(
        gh, budget.issue, _run_budget.BudgetPhase.RESERVED, charged, launch,
    )
    return True


def _start(
    gh: GitHubClient,
    budget: AgentRunBudget,
    durable: PinnedState,
    launch: AgentRunLaunch,
) -> bool:
    """Move this launch's charge to the phase a spawn is about to happen in.

    Recorded once per charge rather than once per launch that reached here: a
    launch honoring a reservation an earlier tick left standing pays for no
    new run, so the only budget transition it has to report is this one.
    """
    recorded = dict(durable.data)
    _run_ledger._start_reserved_run(durable)
    if not _persist(gh, budget, durable, recorded):
        return False
    _run_budget._emit_charge(
        gh,
        budget.issue,
        _run_budget.BudgetPhase.STARTED,
        _run_ledger._read_ledger(durable),
        launch,
    )
    return True


def _durable_state(gh: GitHubClient, issue: Issue) -> PinnedState | None:
    """The pinned state a charge may be written onto, or nothing.

    Two readings are refused rather than charged. A request that failed leaves
    no count to charge against at all. A pinned comment that would not parse
    reads back empty, which is indistinguishable from an issue that has spent
    nothing -- so a charge taken on it would both hand the issue a fresh
    lifetime and overwrite whatever the comment was still holding. Neither is
    worth a spawn: an agent run is minutes of somebody's compute, and the poll
    comes back.
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
    if not durable.parsed:
        log.error(
            "issue=#%d carries a pinned comment that will not parse; invoking "
            "nothing rather than charging an agent run against a count no "
            "read produced",
            issue.number,
        )
        return None
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
    """
    try:
        gh.write_pinned_state(budget.issue, durable)
    except Exception:
        log.exception(
            "issue=#%d could not record the agent run its next launch is "
            "charged; invoking nothing rather than spawning a run the ledger "
            "would never see",
            budget.issue.number,
        )
        return False
    _merge_circuit_fields(recorded, durable, budget.state)
    return True


def _park_spent(
    gh: GitHubClient,
    budget: AgentRunBudget,
    durable: PinnedState,
    ledger: AgentRunLedger,
    launch: AgentRunLaunch,
) -> None:
    """Stop this issue on the reading the refusal was made on.

    The park owner is handed the ledger rather than taking one, so the
    sentence a human is shown quotes the allowance and the spend this launch
    was actually turned away on. It writes the durable half itself, which is
    why the caller's object is merged into afterwards rather than written:
    a refusal is answered with an interrupted run, and the handler above is
    about to return without a write of its own.

    The launch travels with them for the same reason: the park is the whole of
    what an issue's lifetime ends in, and the record it leaves on the budget
    stream is the only place the work the ceiling actually stopped is named.

    A park that could not be taken still refuses the launch. The allowance is
    spent either way, and the poll comes back to a park that was never
    recorded -- while a spawn let through because the announcement failed is a
    run nothing gets back.
    """
    recorded = dict(durable.data)
    try:
        _run_limit._park_exhausted(gh, budget.issue, durable, ledger, launch)
    except Exception:
        log.exception(
            "issue=#%d has spent every agent run it is allowed, and the park "
            "that says so could not be taken; invoking nothing regardless",
            budget.issue.number,
        )
        return
    _merge_circuit_fields(recorded, durable, budget.state)


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

    The pinned comment's identity travels with them where the caller has none.
    An issue whose state was created by this write is one the caller would
    otherwise pin a second comment for.
    """
    for key in set(recorded) | set(durable.data):
        written = durable.data.get(key, _UNSET)
        if written == recorded.get(key, _UNSET):
            continue
        if written is _UNSET:
            state.data.pop(key, None)
        else:
            state.set(key, written)
    if state.comment_id is None:
        state.comment_id = durable.comment_id
