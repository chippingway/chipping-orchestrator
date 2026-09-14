# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hold exhausted agent-run work while admitting grants and terminal cleanup.

A closed issue or ended publication can reach its terminal even after
spending the run allowance. An implementing plan pull request does not
prove that the implementation itself ended.
"""
from __future__ import annotations

import importlib
import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import (
    _ISSUE_STATE_CLOSED,
    issue_is_closed,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    run_grant as _run_grant,
    run_limit as _run_limit,
    run_limit_state as _run_limit_state,
    run_limit_values as _run_limit_values,
    stage_targets as _stage_targets,
    terminal_reading as _terminal_reading,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


# What a pull request reads as once it is over, whichever way it ended. The
# run-limit hold asks for both together, because what it is deciding is
# whether the work is finished rather than which ending finished it.
_ENDED_PR_STATES = frozenset((_terminal_reading._MERGED, _ISSUE_STATE_CLOSED))


def _run_limit_holds_the_tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    ended: bool,
) -> bool:
    """Whether this issue has spent every agent run it is allowed to.

    True is the whole tick: no handler is called, so nothing is spawned,
    nothing is relabelled, and everything the issue was carrying when it ran
    out -- a locked session, a pull request, a branch, a manifest, a
    generation's record -- is left exactly where the park found it. A lifetime
    total is spent once and no clock returns it, so unlike every other park in
    this repository there is nothing to wait for here and no road below that
    could be right about the wait.

    Held once, here, rather than taught to each stage. The park is a claim
    about the ISSUE and not about any stage's road, while `awaiting_human`
    means something different on every one of those roads: `implementing`
    resumes a locked developer on the next trusted reply, the conversation
    stages read one as the answer their agent asked for, and the spent-budget
    holds wait on a command that buys another attempt. Each is right about the
    park it was written against; none of them buys back a run.

    Work that has ENDED is let past, and that exemption is the reason this is
    a question rather than a filter above the partition. What an ending
    reaches below is a terminal -- the merged, rejected, and human-closed
    finalizers, and the cleanup sweep that settles a generation ledger -- and
    every one of those ENDS the issue rather than spending anything on it.
    Refusing them would leave a spent issue permanently mid-ending: a pull
    request nothing finalizes, a receipt nobody posts, a ledger no sweep
    settles. And "permanently" is meant: a lifetime total buys no clock, so
    an issue held here is held until a human arrives, and an ending it never
    reaches is one nothing else will.

    `ended` is that question already answered, handed in rather than asked
    here: `_spent_work_has_ended` beside this owns the two facts it is read
    off and the order they cost anything in. What the answer buys is the tick
    reaching the stage its label names, whose own terminal does the ending --
    and nothing it lets through can spend a run, since the circuit every
    launch goes through reads the same ledger and refuses on it.

    The one thing that lifts it is asked here too, and asked nowhere else:
    a trusted `/orchestrator add-agent-runs N` widening what this issue may
    spend (`run_grant.py`). It belongs to the hold rather than to a stage for
    the same reason the park does -- the ledger is spent by every role at
    every stage, so no one handler is the place a human would say it -- and a
    command that lifts the park lets the tick go on to the stage its label
    names, which is the run the human just paid for.

    It is asked BEHIND the ending, and the order is the point: reading that
    command MUTATES -- it widens the allowance, clears this park, consumes
    the batch it read, posts an acknowledgement and records a phase. None of
    that is anything work a human has already merged or closed should earn.
    Asked first, a terminal issue would buy runs it will never spend, and a
    malformed request over one would collect a refusal receipt on a thread
    about to be finalized.

    The sentence the park owes the thread is replayed before the hold
    returns, because this is the road that strands it: nothing below runs, so
    a notice a refused post or an unreadable thread left owed would be owed
    for as long as the issue is parked. The refusal is recorded either way --
    a park nobody can see going on refusing is one an operator reads as a
    workflow that stopped for no reason.
    """
    if not _run_limit_state._park_stands(state) or ended:
        return False
    if _run_grant._lifts_the_park(gh, issue, state):
        return False
    log.info(
        "repo=%s issue=#%s has spent every agent run it is allowed; holding "
        "it for a human rather than dispatching it",
        spec.slug, issue.number,
    )
    _run_limit._replay_owed_notice(gh, issue, state)
    _run_limit._emit_phase(gh, issue, _run_limit_values.RunLimitPhase.STANDING)
    return True


def _spent_work_has_ended(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    label: str | None,
    observed_closed: bool,
) -> bool:
    """Whether the work a spent ledger would hold is already over.

    Asked BEHIND the park, and that is what keeps it cheap: the pull-request
    half below is a request, and an issue with runs left to spend has no hold
    for an ending to lift. So a tick that is not parked costs nothing here.

    The free fact comes first. A closed ISSUE is the object already in hand,
    and the poll's own reading counts beside it, since an issue closed when it
    was enumerated is one this tick was routed on the strength of. The PULL
    REQUEST behind it is the half the object cannot show.
    """
    if not _run_limit_state._park_stands(state):
        return False
    if observed_closed or issue_is_closed(issue):
        return True
    return _recorded_pr_has_ended(gh, issue, state, label)


def _recorded_pr_has_ended(
    gh: GitHubClient, issue: Issue, state: PinnedState, label: str | None,
) -> bool:
    """Whether the pull request this issue records has merged or been closed.

    The half of "is this work over" the issue's own flag cannot answer, and
    the reason the hold above asks a request at all: a merge leaves the issue
    open until a stage terminal reads it, and a close nobody merged leaves it
    open for good, so a spent issue behind either would sit on the park
    forever with the ending it is owed unreachable.

    Read fail-OPEN through the terminals' own guarded reading, which is where
    the shape of that read lives: a fetched pull request is lazy, so the
    lookup asks GitHub nothing and the request that can fail is the attribute
    access behind it. A reading that did not come back says nothing about
    whether the work is over, and answering True on one would lift a park on
    a request that failed -- so it leaves the hold exactly where it was and
    the next poll asks again.

    The `discussion` stage's PLAN is not an ending ON ONE STAGE, and that is
    why the LABEL decides it rather than the record alone. An issue relabelled
    out of `discussion` arrives on `workflow:implementing` still recording the
    plan's number, and merging that plan is an agreement -- the humans read a
    design and said build it -- so the stage that would receive this tick
    carries on rather than finalizing. Answered as an ending there, the hold
    would step aside every poll for an issue no terminal is going to finalize,
    and say in the log that it was letting one through.

    Everywhere else the same pull request is exactly the ending it looks like.
    `discussion` itself drains a settled plan through its own terminal, so a
    carve-out applied to that label stops the one stage the plan belongs to
    from ever ending -- and behind a permanent park there is no later tick to
    do it instead.

    Told apart off the SAME reading the state came from, through the owner
    that decides what a plan is, so the classification and the ending are
    about one snapshot rather than two.

    What a True buys is the tick reaching the stage the label names, whose
    own terminal does the ending. Nothing here finalizes anything itself.
    """
    linked = _terminal_reading._linked_pull_request(
        gh, issue, state, "checking whether its work has already ended",
    )
    if not linked.was_read or linked.state not in _ENDED_PR_STATES:
        return False
    if label == WorkflowLabel.IMPLEMENTING:
        implementing = importlib.import_module(_stage_targets._IMPLEMENTING_HANDLER_OWNER)
        if implementing._recorded_pr_is_the_plan(state, linked.head):
            return False
    log.info(
        "issue=#%s has spent every agent run it is allowed and records a pull "
        "request that has merged or been closed; letting the tick reach the "
        "terminal that ends it",
        issue.number,
    )
    return True
