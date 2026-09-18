# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist and report the park a spent lifetime launch allowance requires.

The supplied ledger decides exhaustion. This owner records the park before
its budget event and notice, reconciles bot-authored delivery on the thread,
and replays an owed notice without granting or spending any additional run.
Every one of those records the thread read only through our own identified
comments: a refused launch is often a resume whose frozen replies sit below
the notice, and crossing them would spend input no agent ever read."""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import authored_by_us
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    park_watermarks as _park_watermarks,
    run_budget as _run_budget,
    run_budget_models as _run_budget_models,
    run_limit_state as _run_limit_state,
    run_limit_values as _run_limit_values,
)
from orchestrator.workflow.engine.run_ledger_models import AgentRunLedger
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")


def _park_exhausted(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    ledger: AgentRunLedger,
    launch: _run_budget_models.AgentRunLaunch,
) -> None:
    """Stop this issue on its spent ledger, and say so once.

    The whole durable half goes down BEFORE a word of it is said: a notice on
    a thread that no pinned state backs is the worst of both endings -- nothing
    reconciles it, because nothing knows it is owed, and the next tick runs
    the issue again beneath a comment saying it had stopped. The caller's own
    write follows and carries whatever the delivery settled.

    A park already standing and already explained is re-taken silently, and
    recorded as standing rather than said again: the ledger is re-read on
    every tick that reaches a spawn, so announcing it again would say the same
    sentence to the same thread once a poll until a human arrived.

    The budget stream is told by the tick that TAKES the park, on the write
    that makes it durable, and by no other. A park is met again by every
    launch the issue has left, so a record per meeting would report one ending
    as a stream of them -- and the phase beside it on this owner's own stream
    is already what says a park went on holding. The launch travels into that
    record because it is the work the ceiling stopped, which is the one thing
    a park cannot say about itself: the ledger is spent by every role, so the
    refusal names the role and the stage it was actually taken from.

    The thread is asked before anything is said, so a comment that landed
    under a write that failed is recorded as said rather than repeated -- and
    a thread this tick could not read is said nothing to at all, since the
    sentence it may already carry is exactly the one about to go out. The park
    stands and the notice stays owed, so the next tick reads again.
    """
    taken = not _run_limit_state._park_stands(state)
    if not _run_limit_state._stage_park(state, ledger):
        _emit_phase(gh, issue, _run_limit_values.RunLimitPhase.STANDING)
        return
    gh.write_pinned_state(issue, state)
    if taken:
        _run_budget._emit_exhaustion(gh, issue, ledger, launch)
    if _reconcile_notice(gh, issue, state) is _run_limit_values.NoticeReading.UNSAID:
        _deliver_notice(gh, issue, state)


def _deliver_notice(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Say what a standing park is for, if the thread has not been told.

    Idempotent by what it clears rather than by how often it is called: the
    obligation is dropped by the post that discharges it, so a notice reaches
    the thread once per park.

    The obligation is dropped between the post and the caller's write, which
    is the only order that fails the right way: a crash in that window leaves
    a sentence owed by a thread that already has it, which the reconciliation
    below settles, rather than dropping one nobody ever said.

    The mention and the watermark go through the shared park, and the park is
    BOUNDED: the thread is recorded read through our own identified comments
    and no further. The launch this notice explains is very often a resume
    handed a frozen reply batch -- the guidance a human wrote on a parked issue
    -- and the circuit refused it before any agent read a word. Those replies
    sit below the notice, so the notice-id stamp would mark them answered by a
    run that never happened, and after the grant the road that would have
    delivered them would find nothing to deliver. That helper clears
    `park_reason` by contract, so the stable reason is re-stamped after it.
    """
    owed = _run_limit_state._owed_notice(state)
    if owed is None:
        return False
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} {owed.message}",
        reason=_run_limit_values.PARK_AGENT_RUN_LIMIT,
        bounded=True,
    )
    state.set(_run_limit_values._PARK_REASON, _run_limit_values.PARK_AGENT_RUN_LIMIT)
    _run_limit_state._settle_notice(state)
    _emit_phase(gh, issue, _run_limit_values.RunLimitPhase.DELIVERED)
    return True


def _reconcile_notice(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _run_limit_values.NoticeReading:
    """Discharge an obligation the thread shows was already discharged.

    Asked before anything acts on the obligation, because a pinned write that
    failed after a post that landed claims the opposite of what the issue
    holds -- and the issue is the one of the two that cannot be wrong about
    what was said. What that write was carrying is put back: the sentence is
    marked said, the comment that carried it enters the id ledger it was never
    written to, and the watermark is walked the way the delivery would have
    walked it -- through our own identified comments and no further. Ratcheted
    straight to the notice instead, it would cross the replies a refused
    resume was handed, which sit below the notice and which no agent ever
    read.

    Nothing is posted and nothing is decided. A notice the thread does not
    carry is left exactly as it was, for the delivery to say -- and a thread
    that could not be read is reported as exactly that, since a caller told
    "not there" would say a sentence the issue may already carry.

    An obligation nobody holds reads as `SAID`: there is nothing owed, and
    nothing for the delivery above to do about it either.
    """
    owed = _run_limit_state._owed_notice(state)
    if owed is None:
        return _run_limit_values.NoticeReading.SAID
    delivered = _delivered_id(gh, issue, state, owed.message)
    if delivered is _run_limit_values._UNREADABLE_THREAD:
        return _run_limit_values.NoticeReading.UNREADABLE
    if delivered is None:
        return _run_limit_values.NoticeReading.UNSAID
    log.info(
        "issue=#%d already carries its agent-run-limit notice; recording it "
        "as said rather than saying it twice",
        issue.number,
    )
    _run_limit_state._settle_notice(state)
    said_before = _comments._orchestrator_ids(state)
    _comments._track_orchestrator_comment(state, delivered)
    _park_watermarks._stamp_read_this_far(gh, issue, state, said_before)
    _emit_phase(gh, issue, _run_limit_values.RunLimitPhase.RECONCILED)
    return _run_limit_values.NoticeReading.SAID


def _replay_owed_notice(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Say what a standing park is for, if nothing ever did.

    The retry the durable half of a park earns, and the reason the obligation
    is written down at all. This park is exactly the state that stops a tick
    reaching anything: it is held ahead of every stage handler, so no road the
    issue has left passes the spawn that took it -- and a sentence a refused
    post or an unreadable thread left owed would stay owed for as long as the
    issue is parked, which is for good. The human would be waiting on a
    comment nobody was ever going to write.

    So it is asked by the hold itself, ahead of the handler a label names, and
    it is idempotent by what it clears: the obligation is dropped by the post
    that discharges it, so a notice reaches the thread once per park rather
    than once per tick. A thread that could not be read is left for the next
    tick rather than posted over.

    The write is taken here rather than left to the caller, because the caller
    is a hold that is about to return without dispatching anything at all --
    which is exactly how the sentence was stranded. It rides the same mention
    and watermark every park in this repository does, so what it consumes is
    what a park taken now would have consumed.
    """
    if not _run_limit_state._park_stands(state) or _run_limit_state._owed_notice(state) is None:
        return False
    reading = _reconcile_notice(gh, issue, state)
    if reading is _run_limit_values.NoticeReading.UNREADABLE:
        return False
    if reading is _run_limit_values.NoticeReading.UNSAID:
        _deliver_notice(gh, issue, state)
    gh.write_pinned_state(issue, state)
    return True


def _emit_phase(
    gh: GitHubClient, issue: Issue, phase: _run_limit_values.RunLimitPhase,
) -> None:
    """Record which step of an agent-run-limit park this tick took.

    The stage is the label the issue is wearing, because that is the whole of
    what this park can say about where the issue stopped: the ledger is spent
    by every role at every stage, so there is no one stage that ran out of it.
    """
    gh.emit_event(
        _run_limit_values._RUN_LIMIT_EVENT,
        issue_number=issue.number,
        stage=stage_name(gh.workflow_label(issue)),
        phase=phase,
    )


def _delivered_id(
    gh: GitHubClient, issue: Issue, state: PinnedState, message: str,
) -> int | None | object:
    """The id of this notice's own comment on the thread, if it is there.

    The whole sentence is matched rather than a marker, because this notice
    carries none of its own and the mention prefixed to it is not part of what
    was recorded. The highest match is reported, so the watermark is repaired
    to the last thing said rather than the first.

    And the receipt has to be OURS. The sentence is plain text on a public
    thread, so anybody can write it -- and read from anybody, it would
    discharge an obligation nobody discharged: the park would stand with its
    notice marked said, the watermark would be dragged past whatever else was
    written under it, and the human the park was taken for would never be
    told. So the author is checked through the same owner every other receipt
    this repository reads off a thread goes through
    (`github.comments.authored_by_us`), and a client with no authenticated
    login of its own to compare against falls back to the text alone exactly
    as those do.

    A read that could not be taken answers `_UNREADABLE_THREAD`, which is a
    different thing from finding nothing: the notice stays owed either way,
    but only one of the two licenses a comment. Read as a miss, a request that
    failed inside the very window where the sentence is already on the thread
    would post it a second time.
    """
    try:
        thread = gh.comments_after(issue, state.get(_run_limit_values._LAST_ACTION_COMMENT_ID))
    except Exception:
        log.exception(
            "issue=#%d could not be read for an agent-run-limit notice "
            "already posted; leaving it owed and saying nothing this tick "
            "rather than repeating a sentence the thread may already carry",
            issue.number,
        )
        return _run_limit_values._UNREADABLE_THREAD
    bot_login = getattr(gh, "_bot_login", None)
    said = [
        issue_comment.id
        for issue_comment in thread
        if message in (issue_comment.body or "")
        and authored_by_us(issue_comment, bot_login=bot_login)
    ]
    return max(said) if said else None
