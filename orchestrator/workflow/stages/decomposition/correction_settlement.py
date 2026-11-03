# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a manifest correction's answer is allowed to come to, and the exhaustion that spends its attempt.

The answer goes through every disposition an ordinary decomposer answer does
-- the holds, the timeout, the read-only checkout, the interruption, the
manifest parser -- save one: it earns no correction of its own. Each
disposition decides what the attempt is left as.

- A park -- a timeout, a dirty checkout, a question, silence, or a second
  invalid manifest -- is taken only over an issue that still stands, read
  afresh (`parks`): a close, a relabel, or an edit since spends the attempt
  and parks nothing on an owner the answer no longer belongs to, and a hold
  or an unread issue parks and spends nothing. A park taken lands first, with
  the attempt still pending on the state it writes, and the attempt is
  exhausted behind it only where that write landed
  (`correction_notices.recorded`, `spends_behind_park`), naming the
  correction's own invocation. A park standing over a pending attempt is the
  one a lost exhaustion, or a park write landing unconfirmed, leaves, which the
  next tick spends with no second notice (`correction_reconcile`); an
  exhaustion landing ahead of a lost park would leave an issue nobody was told
  about.
- A usable manifest is acted on only once the issue, read afresh, still stands
  where the rejected run left it (`correction_live`), the attempt is exhausted,
  and the issue, read afresh again behind that write, still stands (`clears`):
  the exhaustion lands before the first child, split marker, or label, so a
  split whose transaction a crash interrupts is the split recovery's, never an
  attempt still pending beside its children. A close, a relabel, or an edit
  since spends the attempt and makes nothing of the answer, the edit left for
  the drift reset's fresh decomposition; a hold or a reading GitHub would not
  answer makes nothing of it and spends nothing -- save one landing behind the
  exhaustion, which leaves the attempt spent for the next tick to park over
  (`correction_reconcile.recovers_park`).
- A hold, an unresolved accounting, or an interruption leaves the attempt
  pending with its start on the ledgers -- never launched again -- for the
  next tick to give up behind a human park.

An exhaustion that does not land is said locally and grants nothing: the
attempt is left pending and started, and no write here retries it. One that
lands, and a retirement that lands, drop a park notice the record still held
for the attempt (`discards`): a move or a close took that park away, so nothing
will post it, and it would otherwise sit on the comment through every stage
behind.

An attempt whose context moved -- an edit's reset or a continuation retiring
the session it was saved under -- is retired (`retires`) before any decomposer
is charged behind it, the tick's own reset landed first where only it shows the
move, and only over the comment the retirement read, so the resolution covers
no run the fresh decomposition makes and puts back nothing written meanwhile;
a retirement that does not land holds the tick with the attempt pending.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import record_admission as _record_admission
from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_commits as _commits,
    correction_live as _live,
    correction_notices as _notices,
    correction_records as _records,
    correction_standing as _standing,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.models import _DecomposerRunPlan

log = logging.getLogger("orchestrator.workflow")

# What a live reading answers that spends the attempt it was asked for: a move
# of its requirements or saved context, or of the issue's owner.
_SPENDING = frozenset((_live.Live.MOVED, _live.Live.DISOWNED))


def spends(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    attempt: _records.CorrectionAttempt,
    correction: AgentInvocation | None = None,
) -> bool:
    """Exhaust `attempt`, naming `correction` where its launch returned one; whether the record now reads it spent.

    A notice still held for it is dropped behind an exhaustion that landed
    (`discards`); one that did not land keeps both.
    """
    spent = _checkpoint.exhaust(gh, issue, state, attempt, correction)
    if not spent.settled:
        log.warning(
            "issue=#%d its manifest correction could not be recorded spent (%s); it stays pending and grants nothing",
            issue.number, getattr(spent.refusal, "value", spent.status.value),
        )
        return False
    discards(gh, issue, state, attempt)
    return True


def discards(
    gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt | None = None,
) -> bool:
    """Drop the park notice held for `attempt` -- or any, where None -- that no park will say; whether none stands.

    A park that landed dropped its notice in its own write, so what is left
    here is a notice whose park the attempt's move or close took away --
    spent or retired over it -- which nothing will ever post, and which would
    otherwise sit on the comment through every stage behind. Asked again
    before a later tick's run over an attempt already resolved, or none at
    all, so a drop an earlier tick could not land is taken then, whatever that
    tick left of the attempt (`correction_reconcile.reconciles`). Written only
    over the comment the tick last synced with
    (`record_admission.strictly_written`), so a field written meanwhile is
    never put back and a write that does not land leaves the caller's state
    withheld; a notice held for another attempt than the one named is left as
    it stands.
    """
    if attempt is None:
        held = state.carries(_state._DECOMPOSER_CORRECTION_NOTICE)
    else:
        held = _notices.owed(state, attempt) is not None
    if not held:
        return True
    state.state_data.pop(_state._DECOMPOSER_CORRECTION_NOTICE, None)
    if _record_admission.strictly_written(gh, issue, state):
        return True
    log.warning("issue=#%d its spent manifest correction's held notice could not be dropped", issue.number)
    return False


def settles_park(
    gh: GitHubClient, issue: Issue, state: PinnedState, reading: _standing.CorrectionReading, parked: _live.Live,
) -> bool:
    """Whether a tick may go on behind the park it owed `reading`'s attempt, that park having answered `parked`.

    A hold, an unread reading, or a withheld state ends the tick with the
    attempt as it stands. Otherwise the park stands, or a move or a close took
    it away, and the attempt is spent behind it -- an exhausted one already is,
    so only a notice still held for it is dropped (`discards`) -- and the tick
    goes on only where that landed, so no resume or fresh decomposer is charged
    beside an attempt still pending, and only on an issue still this label's.
    """
    answered = parked is _live.Live.STANDS or parked in _SPENDING
    if not answered or state.withheld:
        return False
    resolve = discards if reading.standing is _standing.Standing.EXHAUSTED else spends
    if not resolve(gh, issue, state, reading.attempt):
        return False
    return parked is not _live.Live.DISOWNED and not state.withheld


def spends_behind_park(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run_plan: _DecomposerRunPlan,
    given_up: _records.CorrectionAttempt | None = None,
) -> None:
    """Exhaust the attempt a park its caller just wrote stands over, where one does.

    The attempt `run_plan`'s own run answers, naming that run; else
    `given_up`, an attempt armed for the run that granted no launch, naming
    none. A plan answering no attempt, with none given up, spends nothing.
    """
    if run_plan.correction is not None:
        spends(gh, issue, state, run_plan.correction, run_plan.agent_result.invocation)
    elif given_up is not None:
        spends(gh, issue, state, given_up)


def clears(gh: GitHubClient, issue: Issue, state: PinnedState, run_plan: _DecomposerRunPlan) -> bool:
    """Whether the usable manifest `run_plan`'s run answered may be acted on now.

    Every run's but a correction's may. A correction's only where the issue
    still stands as its rejected run left it, its attempt reads spent over a
    write that left the caller's state its own -- one landing over a comment
    moved since the caller read it withholds that state, and no whole-state
    write a split or a decision makes could land -- and, behind that write, the
    issue, read afresh once more, still stands and its pinned comment still
    carries the session, command, and baseline the attempt was armed under: a
    hold, a close, a relabel, an edit, or a pin moved meanwhile makes nothing
    of the answer either, the attempt left spent for the next tick to park
    over or to answer as moved.
    """
    attempt = run_plan.correction
    if attempt is None:
        return True
    live = _live.reads(gh, issue, state, attempt.source)
    if live in {_live.Live.HELD, _live.Live.UNREAD}:
        log.info("issue=#%d its corrected manifest reads %s; acting on nothing", issue.number, live.value)
        return False
    spent = spends(gh, issue, state, attempt, run_plan.agent_result.invocation)
    if live in _SPENDING or not spent or state.withheld:
        log.info("issue=#%d its corrected manifest is acted on nothing: it reads %s", issue.number, live.value)
        return False
    behind = _live.answers(gh, issue, state, attempt.source)
    if behind is not _live.Live.STANDS:
        log.info("issue=#%d reads %s behind its correction's exhaustion; acting on nothing", issue.number, behind.value)
    return behind is _live.Live.STANDS


def parks(gh: GitHubClient, issue: Issue, state: PinnedState, run_plan: _DecomposerRunPlan) -> bool:
    """Whether the park `run_plan`'s run reached may be taken on the issue now.

    Every run's may but a correction's, which only where the pinned comment
    and then the issue, read afresh, still stand as its rejected run left them
    (`correction_live.answers`): a session, command, or baseline pinned in
    place of the saved ones, a close, a relabel, or an edit since spends the
    attempt and parks nothing on an owner or a conversation the answer no
    longer belongs to -- the edit left for the drift reset's fresh
    decomposition -- while a hold, or an issue GitHub would not answer for,
    parks and spends nothing, the attempt left started for a later tick to
    park over. The comment is read back first (`correction_checkpoint.read_back`),
    so one another road or a human wrote since the tick read it withholds the
    tick's state and nothing is parked over it: the park's whole-state writes
    would put back what that write replaced.
    """
    attempt = run_plan.correction
    if attempt is None:
        return True
    _checkpoint.read_back(gh, issue, state)
    live = _live.answers(gh, issue, state, attempt.source)
    if live in _SPENDING:
        spends(gh, issue, state, attempt, run_plan.agent_result.invocation)
    if live is not _live.Live.STANDS or state.withheld:
        log.info("issue=#%d reads %s as its manifest correction returns; parking nothing", issue.number, live.value)
        return False
    return True


def retires(gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt) -> bool:
    """Retire a moved `attempt`; whether the tick may go on to the fresh decomposition the move buys.

    A retirement refused for want of evidence is one whose move is this
    tick's in memory alone -- the drift reset's -- so that state is written
    first, only over the very comment the retirement read
    (`record_admission.strictly_written`), and the retirement asked again over
    it: a session a human pinned, a claim edited, or anything else written
    since is never put back, and the tick holds with the caller's state
    withheld. Only a retirement that settled lets the tick go on: one refused
    for any other reason -- a charge count nobody can read among them --
    leaves the attempt pending, so no fresh decomposer is charged behind an
    attempt nobody could resolve.
    """
    retired = _checkpoint.retire(gh, issue, state, attempt)
    if retired.refusal is _commits.CorrectionRefusal.NO_EVIDENCE and _record_admission.strictly_written(
        gh, issue, state,
    ):
        retired = _checkpoint.retire(gh, issue, state, attempt)
    if not retired.settled:
        log.warning(
            "issue=#%d its moved manifest correction could not be retired (%s); holding the tick",
            issue.number, getattr(retired.refusal, "value", retired.status.value),
        )
        return False
    return discards(gh, issue, state, attempt) and not state.withheld
