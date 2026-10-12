# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The account-quota stop that retires a developer conversation, decided as each attempt returns.

`session_retirement` keeps the record of a conversation retired as failed and
decides nothing about THAT one failed. This owner decides it for an exhausted
account quota, and it is asked at the one boundary every developer launch
returns through -- each attempt `execution._DevRunCoordinator` makes, so the
first spawn, an ordinary resume, a rotated or poisoned-session fresh spawn, and
the one continuation an AGY run that stopped mid-command earns all alike. A
backend can keep handing the same stale quota terminal back on a conversation
that hit one, whatever a later turn did, so the next permitted developer run
has to be a fresh conversation over the same worktree, branch, and issue
context, under the pinned `dev_agent` command.

The verdict is the normalized one on the run's failure record
(`AgentResult.terminal_failure.quota_exhausted`), which only Antigravity fills;
a Claude quota notice in the final message is a stop its conversation resumes
past once the quota resets, so it retires nothing. The conversation is the one
the run names, or the one the attempt was launched to resume where the failure
named none. The retirement is landed as the attempt returns, through the
guarded commit (`session_retirement._commit_dev_session_retirement`), rather
than left to the tick's own write: every caller that sees a live pause or a
refused disposition returns without writing, and a commit the run left can
carry the tick into publication, which resets every counter a rotation reads.
A shutdown-sweep kill is the one stop left alone, since its result is no
trustworthy outcome and the durable state is the next process's to re-run from
(`guards._ignore_if_interrupted`).

A retirement that commit did not confirm -- refused over a comment another
writer moved, unreadable, or sent and never answered -- is not left to the
tick's whole-state write either: that write would put back everything the other
writer landed. The tick's state is withheld (`PinnedState.withheld`) and the
attempt answers held, which its caller honors as it honors a live pause:
nothing disposed, nothing written. The obligation is kept on the host instead
(`quota_record`), from before the launch that could owe it: each Antigravity
launch is armed first (`_armed`), and a launch the host will not arm is not
made. The launch's return settles it where no quota stopped it, and a quota
stop resolves it to the conversation that must be retired, so no write that
fails once the failure is known can lose it, and a poller restarted on this
host reads it as surely as the one that wrote it. An arming nothing resolved
-- a poller killed mid-run, a resolution the host would not take before a
restart -- names no conversation anyone can land, so it holds every launch
until the poller holding its resolution writes it or an operator does. A
resolved one is landed again ahead of the next resume's plan (`_reconcile`)
and ahead of every developer launch (`_holds_the_launch`), which is refused
until it lands and the host owes nothing more -- so a landed record is never
landed again over a conversation pinned after it -- and refused on a tick
whose state is withheld even where a later attempt lands it, since that state
can record nothing the launch leads to. A record that will not read has lost
the conversation it named, so it is never landed either, and a tick whose
resume was planned over one, or over an unresolved arming, launches nothing,
whatever becomes of the record before its launch.

Nothing here launches, parks, or schedules anything: the quota park and its
notice are `parks`'s, the continuation a human buys is `continue_command`'s,
and the retry, pause, close, and run-budget gates in front of the next launch
are untouched.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.agents.models import AgentResult, is_shutdown_sweep_interrupted
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit_models as _commit_models
from orchestrator.workflow.stages.implementing import (
    quota_record as _quota_record,
    session_retirement as _session_retirement,
)

log = logging.getLogger("orchestrator.workflow")

# Why the record says the conversation was retired: the event reason the quota
# park reports itself by.
_QUOTA_REASON = "agent_session_limit"


def _quota_failure(agent_result: AgentResult) -> bool:
    """True iff the run's failure record names an exhausted account quota, whatever else it left."""
    failure = agent_result.terminal_failure
    return failure is not None and failure.quota_exhausted


def _armed(gh: GitHubClient, issue: Issue, launched: str | None) -> bool:
    """Owe, on the host, the retirement of the conversation an Antigravity launch runs; whether it may be made.

    Asked after every hold in front of the launch, so nothing is owed then.
    `launched` is the conversation it resumes, None for a fresh spawn. The
    record stands until the launch comes back (`_retire_quota_conversation`),
    so the obligation a quota stop leaves is on the host before the stop is
    known; a host that will not take it holds the launch, whose stop would
    otherwise be kept by this process alone.
    """
    if _quota_record._OwedRetirement.armed(gh, issue, launched):
        return True
    log.warning(
        "issue=#%d this host keeps no record of the retirement an AGY launch of dev session %r "
        "could owe; holding the launch",
        issue.number, launched,
    )
    return False


def _retire_quota_conversation(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
    launched: str | None,
) -> bool:
    """Retire the conversation a quota-stopped attempt ran as, durably; whether the tick may go on.

    `launched` is the conversation the attempt was launched to resume, None
    for a fresh spawn, and stands in for an id the failed run omitted. A fresh
    spawn that named none retires every conversation pinned then, by name, in
    its place (`session_retirement._retire_dev_session`), and the record owes
    a fresh conversation, so the pin of whatever it returns next is refused
    unless it is one with an id of its own. An attempt no quota stopped -- a
    shutdown-sweep kill included -- settles what its launch armed, and goes on
    whether or not the record takes that: an arming it leaves standing holds
    every later developer launch (`_holds_the_launch`), not the disposition of
    this one, its publication included.

    True for an attempt no quota stopped, and for a retirement the commit
    landed and the host settled; False holds the tick, for a retirement it
    could not confirm or one the host still records owed once it landed.
    """
    if not _quota_failure(agent_result) or is_shutdown_sweep_interrupted(agent_result):
        _quota_record._OwedRetirement.cleared(gh, issue)
        return True
    session_id = agent_result.session_id or launched
    log.info(
        "issue=#%d dev session %r stopped on an exhausted account quota; retiring it so the "
        "next developer run starts a fresh conversation",
        issue.number, session_id,
    )
    return _landed(gh, issue, state, _quota_record._OwedRetirement.owed(gh, issue, session_id))


def _reconcile(gh: GitHubClient, issue: Issue, state: PinnedState) -> None:
    """Land the retirement an earlier attempt could not confirm, where one is owed, ahead of a resume's plan.

    Asked before a resume is planned, so a retirement that lands now is one
    the plan already reads, and the resume opens a fresh conversation. One
    that will not land withholds the state (`_landed`), and so does a record
    that names no retirement -- one that will not read, or an arming nothing
    resolved: the plan is then made over a pin that record may stand for, so
    the launch behind it is not made (`_holds_the_launch`) even where an
    operator writes the record again, or settles it, before then.
    """
    owed = _quota_record._OwedRetirement.recorded(gh, issue)
    if owed is not None and owed.legible:
        _landed(gh, issue, state, owed)
    elif owed is not None:
        state.withheld = True


def _holds_the_launch(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Whether a developer launch has to wait for a retirement an earlier attempt left owed.

    It waits while one is owed that will not land or stays owed on the host
    once it lands, while the record names no retirement anyone can land --
    it will not read, or the launch it was armed for never resolved it --
    and on any tick whose state is withheld,
    which could write nothing the launch leads to -- even once the retirement
    lands on it: an earlier attempt in the tick -- the one ahead of a resume's
    plan, which is how a launch planned over the unretired pin reaches here --
    could not land it or found it unreadable. The record stays owed for as
    long as that tick lasts (`_landed`), so every later launch in it waits
    too, and the next tick plans over the landed record.
    """
    owed = _quota_record._OwedRetirement.recorded(gh, issue)
    if owed is not None and not owed.legible:
        log.error(
            "issue=#%d its quota retirement record at %s names no retirement this poller can land -- it "
            "will not read, or the AGY launch it was armed for never resolved it; holding every developer "
            "launch until an operator writes the retirement it owes or settles it",
            issue.number, owed.path,
        )
        return True
    if owed is not None and not _landed(gh, issue, state, owed):
        return True
    return state.withheld


def _landed(gh: GitHubClient, issue: Issue, state: PinnedState, owed: _quota_record._OwedRetirement) -> bool:
    """Commit the `owed` retirement over `state`; whether it landed and the host owes it no more.

    One that did not land withholds `state` from the whole-state writer for
    the rest of the tick: the comment is not, or may not be, the one that
    state was read from. One that lands over a state already withheld keeps
    its record all the same, so the tick that state belongs to, which can
    write nothing a launch leads to, launches nothing however often it asks;
    the next tick that can write lands it again -- a commit that sends
    nothing, the comment already reading as its candidate -- and drops it.
    One the host will not drop once it lands is still owed: landed again
    while nothing a launch could pin has come after it, it changes nothing,
    so every launch waits until it can be dropped.
    """
    outcome = _session_retirement._commit_dev_session_retirement(
        gh, issue, state, owed.session_id, _QUOTA_REASON,
    )
    if outcome.status is not _commit_models.CommitStatus.COMMITTED:
        state.withheld = True
        log.warning(
            "issue=#%d could not land the retirement of dev session %r (%s); holding every "
            "developer launch and writing nothing over the comment until it lands",
            issue.number, owed.session_id, (outcome.refusal or outcome.status).value,
        )
        return False
    if state.withheld or owed.settle():
        return True
    log.warning(
        "issue=#%d landed the retirement of dev session %r, but this host still records it owed at %s; "
        "holding every developer launch until it can be cleared",
        issue.number, owed.session_id, owed.path,
    )
    return False
