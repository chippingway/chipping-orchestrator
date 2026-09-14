# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one command that moves an issue off its spent agent-run ledger.

The park beside this owner is the whole ending of an issue that has spent its
lifetime: no clock returns a run, and every stage road below reads
`awaiting_human` as something else. What is left is a human deciding this
issue is worth more runs than it was allowed, and this is where that decision
is written down.

`/orchestrator add-agent-runs N` is that decision and nothing else. What the
words have to be before any of them read as a request -- a line of their own,
an exact positive count inside the bound -- is settled by
`run_grant_request.py` and handed here as one record that already knows
whether it buys anything. Everything else about the reading is decided here.
It is read only while the park stands, because the park is the only thing it
can lift: on a running issue it would be a ceiling nobody was held to, and on
any other park it would answer a question it was not asked. And it is read
only from a trusted author, because what it buys is agent time on somebody's
word -- the same allowlist every other workflow-driving comment on a public
thread goes through.

What a valid command buys is an allowance of exactly `used + N` -- the runs
already spent plus the ones just granted -- rather than a count added onto
whatever the field said before. Written that way it says the same thing
however often it is read: nothing spends a run while the park stands, so a
tick that dies between the receipt and the write grants the same ceiling again
on the next one rather than a second N on top of it.

Everything else is refused rather than acted on, and refused the same way: the
park stands, the ledger is left exactly where the request found it, and the
thread is told what a request has to say. Both answers carry a marker scoped
to the comment that asked, because a post and the write that consumes what it
answers cannot be made one operation -- so the thread is read before either
sentence is written again, exactly as every other receipt in this repository
is. An untrusted account is answered with nothing at all: a reply is a comment
somebody else's word paid for, and consuming the thread for one would spend
the watermark a trusted operator's command is read against.

Neither ending returns a run. What the ledger has spent is spent, and both
counts stay where they were: this widens what an issue may spend, and there is
nothing here that unspends anything.

Only the ending that moves the ceiling reaches the shared `agent_run_budget`
stream (`run_budget.py`), and only once the write that moves it has landed.
That is the transition an operator is counting: how often a deployment's limit
has to be bought past, and by how much. A refusal moved nothing, so it stays
where it already is -- on the park's own audit stream, beside the phase that
records the receipt it earned.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import settings as config
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import carries_own_marker, filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    run_budget as _run_budget,
    run_grant_request as _run_grant_request,
    run_ledger as _run_ledger,
    run_ledger_values as _run_ledger_values,
    run_limit as _run_limit,
)

log = logging.getLogger("orchestrator.workflow")

# Stamped on the answer one request earns, whichever answer it is, and scoped
# to the comment that carried it. A second request is a second decision and
# owes its own sentence, while an unscoped marker would read the first answer
# as the answer to every request after it. Both are HTML comments, so they are
# invisible in the rendered thread -- and both are what makes an answer
# idempotent: the comment and the write that consumes the request it answers
# cannot be made one operation, so the thread is read for the receipt before
# it is written a second time.
_REFUSED_MARKER = (
    "<!--orchestrator-add-agent-runs-refused"
    ":issue={issue}:comment={comment}-->"
)

_GRANTED_MARKER = (
    "<!--orchestrator-add-agent-runs-granted"
    ":issue={issue}:comment={comment}-->"
)

_REFUSAL_NOTICE = (
    "{mentions} that `/orchestrator add-agent-runs` request is not one this "
    "park can act on: it takes a whole number of runs from 1 to {maximum}, "
    "on a line of its own. Nothing moved -- this issue's allowance and the "
    "runs spent against it are exactly where they were, and it is still "
    "parked. Say it again with a count in that range.\n\n{marker}"
)

_GRANT_NOTICE = (
    ":arrows_counterclockwise: granting {added} more agent run(s): this "
    "issue's lifetime allowance is now {allowance}, against {used} already "
    "spent. What was spent stays spent -- this widens the ceiling rather than "
    "returning a run -- so the issue stops here again once it reaches "
    "it.\n\n{marker}"
)

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

_LAST_ACTION_COMMENT_ID = "last_action_comment_id"


def _lifts_the_park(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Whether a human has just bought this issue past its spent ledger.

    True means the park is down, the grant is durable, and the tick may go on
    to the stage its label names -- which is the point of answering here
    rather than leaving the command for the next poll: the run a human paid
    for is the one this issue was stopped for.

    False is every other reading, and the caller holds the tick on all of
    them: no command on the thread, an untrusted one, a request this park
    cannot act on (which earns its receipt on the way past), and a thread that
    could not be read at all. Those last two are not symmetric with a grant --
    a park held one poll too long is answered by the next read, while a grant
    handed out on a thread nobody could read buys runs no human asked for.

    The park is asked for again here rather than taken from the caller,
    because it is the whole of what this command may touch: what it lifts is
    an issue held on a spent ledger, and read anywhere else the same words
    would clear a park waiting for something they do not say -- or hand a
    running issue a ceiling nobody decided.

    A park that still owes the thread its sentence is left alone. The hold
    above says that sentence, and saying it moves the response boundary past
    everything written under the old one -- so a command read here would be a
    command written before the question was put, bought and then consumed by
    the notice explaining why the issue had stopped.
    """
    unanswerable = (
        not _run_limit._park_stands(state)
        or _run_limit._owed_notice(state) is not None
    )
    if unanswerable:
        return False
    try:
        thread = gh.comments_after(issue, state.get(_LAST_ACTION_COMMENT_ID))
    except Exception:
        log.exception(
            "issue=#%d could not be read for the command that buys it more "
            "agent runs; holding the park this tick",
            issue.number,
        )
        return False
    request = _run_grant_request._requested(filter_trusted(thread))
    if request is None:
        return False
    if request.added is None:
        _refuse_request(gh, issue, state, request, thread)
        return False
    _grant_runs(gh, issue, state, request, thread)
    return True


def _grant_runs(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    request: _run_grant_request._Request,
    thread: list,
) -> None:
    """Buy this issue the runs one request asks for, and take its park down.

    The allowance is written as the whole number this issue may spend rather
    than as an increment onto the field, because that is what the ledger holds
    and what makes a replayed grant harmless: the count spent has not moved
    while the park stood, so the same command read twice writes the same
    ceiling twice.

    Said once per REQUEST rather than once per tick, for the reason the
    refusal beside it is: the acknowledgement and the write that consumes the
    command cannot be made one operation, so a tick that died between them
    reads the same command again -- and the marker its own receipt carries is
    what keeps that second reading from saying the same sentence twice.

    An obligation is dropped on the way out. There is none to drop on a park
    whose sentence was said, which is the only kind that reaches this -- but a
    record left in a shape nothing can read is one the park it belonged to no
    longer has, and the park is what is ending here.

    The budget stream is told last, after the write that makes the wider
    ceiling durable, and that order is what makes the record a transition. A
    command re-read because a tick died between its receipt and its write is
    a grant that never landed, so the reading it reports is the one that
    finally did; a grant that landed takes its own park down, and nothing
    reaches this owner again to report it twice.

    Nothing gives a run back. What is spent stays spent, and the issue stops
    on this same park the moment it reaches the ceiling this bought it.
    """
    ledger = _run_ledger._read_ledger(state)
    allowance = ledger.used + request.added
    log.info(
        "issue=#%d was granted %d more agent run(s) by a trusted operator "
        "command; its lifetime allowance is now %d against %d spent",
        issue.number, request.added, allowance, ledger.used,
    )
    marker = _GRANTED_MARKER.format(
        issue=issue.number, comment=request.comment_id,
    )
    _said(gh, issue, state, thread, (marker, _GRANT_NOTICE.format(
        added=request.added,
        allowance=allowance,
        used=ledger.used,
        marker=marker,
    )))
    state.set(_run_ledger_values.AGENT_RUN_ALLOWANCE, allowance)
    state.set(_AWAITING_HUMAN, False)
    state.set(_PARK_REASON, None)
    _run_limit._settle_notice(state)
    _consumed(gh, issue, state, request, _run_limit.RunLimitPhase.GRANTED)
    _run_budget._emit_extension(gh, issue, _run_ledger._read_ledger(state))


def _refuse_request(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    request: _run_grant_request._Request,
    thread: list,
) -> None:
    """Tell the thread what a request has to say, once, and stay parked.

    Once per REQUEST rather than once per tick, by the same receipt the grant
    beside this one writes: the marker is scoped to the comment that asked,
    and the thread is read for it before the sentence is written again.

    Nothing is charged and nothing is bought. The allowance and the runs spent
    against it are exactly what they were, which is what the sentence tells a
    human: this is a request that was not acted on, rather than a grant of
    some other size.
    """
    log.info(
        "issue=#%d asked for more agent runs in a request this park cannot "
        "act on; leaving the ledger where it was and saying so",
        issue.number,
    )
    marker = _REFUSED_MARKER.format(
        issue=issue.number, comment=request.comment_id,
    )
    _said(gh, issue, state, thread, (marker, _REFUSAL_NOTICE.format(
        mentions=config.HITL_MENTIONS,
        maximum=_run_grant_request.MAX_RUNS_PER_COMMAND,
        marker=marker,
    )))
    _consumed(gh, issue, state, request, _run_limit.RunLimitPhase.REFUSED)


def _said(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    thread: list,
    said: tuple[str, str],
) -> None:
    """Write one answer to the thread, unless the thread already carries it.

    `said` is the marker that identifies this receipt and the body carrying
    it. Both answers this owner writes go through here, because both are the
    visible half of a step whose durable half is a separate write: a tick that
    posts and then fails to record what it posted reads the same request again
    on the next poll, and what stops it saying the same sentence twice is the
    receipt already on the thread.

    Both halves of "ours" are asked of that receipt -- the scoped marker and
    the author -- since a marker is plain text anybody may paste, and read
    from anybody it would silence the answer a human is owed.
    """
    marker, body = said
    if carries_own_marker(
        thread, marker, bot_login=getattr(gh, "_bot_login", None),
    ):
        return
    _comments._post_issue_comment(gh, issue, state, body)


def _consumed(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    request: _run_grant_request._Request,
    phase: _run_limit.RunLimitPhase,
) -> None:
    """Consume exactly what this tick read and answered, and record the tick.

    The mark moves to the last comment of the batch the request was read out
    of, and then over the answer written under it -- and no further. What it
    may never move over is a comment nobody here has seen: the thread is read
    once, the receipt is written after that read, and a human who commented in
    between would be marked answered by a tick that never looked at their
    words. A watermark is how every stage below decides what is still unread,
    so a comment swept under it is not delayed, it is lost.

    It is ratcheted rather than set, so a mark already past what this tick saw
    is left where it is.

    The write is taken here rather than left to the caller, because both
    endings leave the tick: one returns to a hold that dispatches nothing, and
    the other to a stage handler that reads this issue's state back from the
    pinned comment. A grant that is not durable by then is a park the next
    read puts straight back.
    """
    consumed = state.get(_LAST_ACTION_COMMENT_ID)
    answered = _answered_through(gh, issue, state, request)
    if not isinstance(consumed, int) or answered > consumed:
        state.set(_LAST_ACTION_COMMENT_ID, answered)
    _run_limit._emit_phase(gh, issue, phase)
    gh.write_pinned_state(issue, state)


def _answered_through(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    request: _run_grant_request._Request,
) -> int:
    """The last comment this tick may claim to have answered.

    The batch the request was read out of, extended over the receipts written
    under it, and stopped by the first comment that is neither. Both halves
    matter. Without the extension the answer just posted stays unread, and the
    road a grant opens would find the orchestrator's own acknowledgement where
    it looks for a human's words. Without the stop, a comment somebody wrote
    between the read and the post -- the one window in which the thread can
    grow under this owner -- would be marked answered by a tick that never
    read it.

    Ours is settled by the id ledger the post itself records and, failing
    that, by the marker every comment this orchestrator writes carries, since
    a write that never landed leaves the id nowhere. Anything else stops the
    walk, whoever wrote it: what is at stake is somebody's unread comment, and
    a mark that stops one comment short costs a tick rather than a word.

    A thread that cannot be read answers with the batch alone. The receipt is
    then read back as a fresh comment by a later tick, which is what its
    marker and the id ledger are there to settle -- and far cheaper than a
    mark past comments nobody has read.
    """
    answered = request.consumed
    try:
        written = gh.comments_after(issue, answered)
    except Exception:
        log.exception(
            "issue=#%d could not be re-read for the answer just written to "
            "it; consuming the batch the command was read out of and leaving "
            "that answer for the next tick",
            issue.number,
        )
        return answered
    recorded = _comments._orchestrator_ids(state)
    bot_login = getattr(gh, "_bot_login", None)
    for posted in written:
        if posted.id not in recorded and not carries_own_marker(
            (posted,), _comments._ORCH_COMMENT_MARKER, bot_login=bot_login,
        ):
            break
        answered = posted.id
    return answered
