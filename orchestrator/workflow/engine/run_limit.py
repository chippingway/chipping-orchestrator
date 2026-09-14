# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where an issue stops once its lifetime agent-run ledger is spent.

The ledger beside this one answers what an issue may spend and what it has
spent. This owner is what happens when those two meet: the issue stops, a
human is told once, and nothing but a human moves it again. A lifetime total
is spent once and no clock returns it, so unlike the day's spawn budget there
is no window here to elapse: what the park waits for is one bounded command
from a trusted operator (`workflow/engine/run_grant.py`) widening the ceiling
this issue is held to, and nothing else on the thread is an answer to it.

The park is durable so that it can be RECOGNIZED. `awaiting_human` alone is
every stage's park, and a tick reading that flag has no way to tell an issue
waiting on an agent's question from one that has run out of runs for good. So
the reason is written beside it and it is stable: `agent_run_limit` is a wire
string on live issues, and it is what lets the dispatcher hold an exhausted
issue ahead of every stage's own awaiting-human road -- each of which is right
about the park it was written against and wrong about this one. A reply is the
answer to a question an agent asked; it buys no runs an issue has already
spent, and neither does the command that lifts this park -- what that widens
is what the issue may still spend.

What the thread is owed is written down rather than assumed said. The comment
and the write that records it cannot be made one operation, and the two
readings of that gap fail in opposite directions: read as already said, a
refused comment leaves a human waiting on a sentence nothing will ever say;
read as still owed, a write that failed after a post that landed repeats one
comment. So the obligation is durable, the thread is asked before it is
repeated, and what a park says is said once per park rather than once per
tick.

That obligation is scoped to the exhaustion that minted it. The reason under
this park never varies -- there is one way to run out of a lifetime -- so the
reason cannot tell one refusal from another, and the sentence quotes numbers
that can: the allowance in force and the runs spent against it. A record
naming the reading the notice was written for is one a later tick can hold up
against the ledger it reads now, which is what keeps a sentence quoting a
ceiling the issue is no longer held to from being the sentence a human is
finally shown. Same reading, same sentence, kept verbatim: the thread is
searched for exactly the text the park recorded, so a notice reworded between
the post and the write that records it would find nothing and say it twice.

Nothing here decides that an issue is out. The ledger is read by whoever is
about to spend a run, and this owner is handed the reading -- so a park is
taken on the numbers the refusal was actually made on, and the sentence under
it quotes those rather than whatever the setting has become since.

The five audit phases are the same story from outside: what was said first,
what the thread was found to already carry, which ticks the park went on
holding, and how the command beside it ended -- one ceiling wider, or one
request this park could not act on.

The moment the park is TAKEN is a sixth thing, and it is reported somewhere
else: `run_budget.py`'s shared `agent_run_budget` stream, which carries it
beside the charges the same launches paid, on both sinks and with the whole
ledger reading under it. The five phases above are about a notice and a
command; that one is about a lifetime ending, and an operator counts it
against the runs that spent it rather than against the sentences that
explained it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from github.Issue import Issue

from orchestrator.config import settings as config
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import authored_by_us
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    run_budget as _run_budget,
    run_budget_models as _run_budget_models,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.engine.run_ledger_models import AgentRunLedger
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")

# The durable reason a spent lifetime ledger parks under. It is a wire string
# on live issues and the one thing that makes this park recognizable to the
# tick after it: a park with no reason of its own is one nothing can tell from
# an agent's question, and every stage's awaiting-human road would answer it.
PARK_AGENT_RUN_LIMIT = "agent_run_limit"

# The sentence the standing park has still to say out loud, and the reading it
# was written for. Held beside the flag, dropped only by a post that landed,
# and spelled without the mention the delivery prefixes -- what is durable is
# what the park has to explain, not how a thread was addressed.
AGENT_RUN_LIMIT_NOTICE = "agent_run_limit_notice"

_NOTICE_MESSAGE = "message"

_NOTICE_ALLOWANCE = "allowance"

_NOTICE_SPENT = "spent"

_RUN_LIMIT_EVENT = "agent_run_limit"

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

# The consumed-comment watermark a park's own mention ratchets, and only on a
# post that landed. That is what makes it the window an undelivered notice is
# looked for in: a sentence whose write failed sits ABOVE the mark its post
# should have moved, while one from a tick that completed sits at or below it.
_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# What a thread read answers when the request itself failed. A sentinel rather
# than None, because None is the answer for a thread that was read and does
# not carry the notice -- and only that one may be posted over.
_UNREADABLE_THREAD = object()


class RunLimitPhase(StrEnum):
    """Which step of an agent-run-limit park one audit record describes.

    The five are deliberately distinguishable. A delivery and a
    reconciliation both end with the thread carrying the notice, but only one
    of them paid a comment for it; a park that holds a later tick is neither,
    and it is the record that keeps an operator from reading a workflow
    stopped for good as one that stopped for no reason. A grant and a refusal
    are the two endings of the one command that answers this park, and only
    one of them lets an agent run again.
    """

    DELIVERED = "delivered"
    RECONCILED = "reconciled"
    STANDING = "standing"
    GRANTED = "granted"
    REFUSED = "refused"


class NoticeReading(StrEnum):
    """What a thread was found to say about a notice a park still owes.

    Three answers rather than two, because the two ways of not finding it are
    not the same thing. A thread that does not carry the sentence is owed it.
    A thread nobody could read says nothing at all -- and the sentence may
    already be on it, posted by a tick whose pinned write then failed, which
    is the exact state this reconciliation exists for. Read as a miss, a
    request that failed would post the duplicate the protocol is here to
    stop, so it is its own answer and the delivery stands down for the tick.
    """

    SAID = "said"
    UNSAID = "unsaid"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class OwedNotice:
    """One sentence a park still owes, and the exhaustion it explains.

    The pair of counts is the scope. They are what the sentence quotes, so a
    notice carrying a reading the issue is no longer at is one that would tell
    a human the wrong numbers -- and they are the only thing that can say so,
    since every park this owner takes carries the same reason.
    """

    message: str
    allowance: int
    spent: int

    def explains(self, ledger: AgentRunLedger) -> bool:
        """Whether this sentence is about the exhaustion the ledger reads."""
        return self.allowance == ledger.allowance and self.spent == ledger.used


def _park_stands(state: PinnedState) -> bool:
    """Whether this issue is stopped, right now, on a spent lifetime ledger.

    Both halves are asked. The flag alone is every stage's park, and the
    reason alone outlives a park something has already taken down.
    """
    if not state.get(_AWAITING_HUMAN):
        return False
    return state.get(_PARK_REASON) == PARK_AGENT_RUN_LIMIT


def _stage_park(state: PinnedState, ledger: AgentRunLedger) -> bool:
    """Record the park a spent ledger takes, and what it owes a thread.

    In memory only, like every other field a refused tick stages: what makes
    it durable is the caller's own write, which is what keeps the park and the
    obligation it carries in one write rather than two.

    Returns whether the thread is now owed a sentence. A park already standing
    whose notice has been said is not announced again -- that repeat is the
    whole failure this protocol exists to stop, and nothing else would stop
    it, since a park is re-asked on every tick that reaches it. Nor is such a
    park rewritten: the flag and the reason under it are already what this
    refusal would say.

    A park whose sentence was never said keeps that sentence verbatim for as
    long as it is about the reading the ledger still shows. The obligation is
    a claim about a comment that may already be on the thread, and the thread
    is searched for exactly the text the park recorded, so a sentence reworded
    by a later tick would find nothing and post a second notice. A sentence
    about some other reading is the one thing worth replacing: it quotes an
    allowance or a spend this issue has moved off, and a human shown those
    numbers is being asked about a state that is over.
    """
    if not _park_stands(state):
        state.set(_AWAITING_HUMAN, True)
        state.set(_PARK_REASON, PARK_AGENT_RUN_LIMIT)
        _owe_notice(state, ledger)
        return True
    owed = _owed_notice(state)
    if owed is None:
        return False
    if not owed.explains(ledger):
        _owe_notice(state, ledger)
    return True


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
    taken = not _park_stands(state)
    if not _stage_park(state, ledger):
        _emit_phase(gh, issue, RunLimitPhase.STANDING)
        return
    gh.write_pinned_state(issue, state)
    if taken:
        _run_budget._emit_exhaustion(gh, issue, ledger, launch)
    if _reconcile_notice(gh, issue, state) is NoticeReading.UNSAID:
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

    The mention and the watermark ratchet go through the shared park so this
    notice moves the response boundary every other park in this repository
    moves -- a comment written before it would otherwise read as an answer to
    it. That helper clears `park_reason` by contract, so the stable reason is
    re-stamped after it.
    """
    owed = _owed_notice(state)
    if owed is None:
        return False
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} {owed.message}",
        reason=PARK_AGENT_RUN_LIMIT,
    )
    state.set(_PARK_REASON, PARK_AGENT_RUN_LIMIT)
    _settle_notice(state)
    _emit_phase(gh, issue, RunLimitPhase.DELIVERED)
    return True


def _reconcile_notice(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> NoticeReading:
    """Discharge an obligation the thread shows was already discharged.

    Asked before anything acts on the obligation, because a pinned write that
    failed after a post that landed claims the opposite of what the issue
    holds -- and the issue is the one of the two that cannot be wrong about
    what was said. Both halves that write was carrying are put back: the
    sentence is marked said, and the watermark is ratcheted to the comment
    that actually carried it.

    Nothing is posted and nothing is decided. A notice the thread does not
    carry is left exactly as it was, for the delivery to say -- and a thread
    that could not be read is reported as exactly that, since a caller told
    "not there" would say a sentence the issue may already carry.

    An obligation nobody holds reads as `SAID`: there is nothing owed, and
    nothing for the delivery above to do about it either.
    """
    owed = _owed_notice(state)
    if owed is None:
        return NoticeReading.SAID
    delivered = _delivered_id(gh, issue, state, owed.message)
    if delivered is _UNREADABLE_THREAD:
        return NoticeReading.UNREADABLE
    if delivered is None:
        return NoticeReading.UNSAID
    log.info(
        "issue=#%d already carries its agent-run-limit notice; recording it "
        "as said rather than saying it twice",
        issue.number,
    )
    _settle_notice(state)
    prior = state.get(_LAST_ACTION_COMMENT_ID)
    if not isinstance(prior, int) or delivered > prior:
        state.set(_LAST_ACTION_COMMENT_ID, delivered)
    _emit_phase(gh, issue, RunLimitPhase.RECONCILED)
    return NoticeReading.SAID


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
    if not _park_stands(state) or _owed_notice(state) is None:
        return False
    reading = _reconcile_notice(gh, issue, state)
    if reading is NoticeReading.UNREADABLE:
        return False
    if reading is NoticeReading.UNSAID:
        _deliver_notice(gh, issue, state)
    gh.write_pinned_state(issue, state)
    return True


def _emit_phase(
    gh: GitHubClient, issue: Issue, phase: RunLimitPhase,
) -> None:
    """Record which step of an agent-run-limit park this tick took.

    The stage is the label the issue is wearing, because that is the whole of
    what this park can say about where the issue stopped: the ledger is spent
    by every role at every stage, so there is no one stage that ran out of it.
    """
    gh.emit_event(
        _RUN_LIMIT_EVENT,
        issue_number=issue.number,
        stage=stage_name(gh.workflow_label(issue)),
        phase=phase,
    )


def _owed_notice(state: PinnedState) -> OwedNotice | None:
    """The sentence this park has still to say, and what it is about.

    Anything but a whole record reads as nothing owed: an issue recorded
    before this field existed, and a hand-edited one, both leave a park that
    says nothing rather than a tick that raises over the shape of a note. The
    counts are part of that record rather than decoration -- a sentence with
    no reading behind it is one nothing can hold up against the ledger, so it
    is no obligation this owner can honor.
    """
    owed = state.get(AGENT_RUN_LIMIT_NOTICE)
    if not isinstance(owed, dict):
        return None
    message = owed.get(_NOTICE_MESSAGE)
    allowance = _run_ledger_values._counted(owed.get(_NOTICE_ALLOWANCE))
    spent = _run_ledger_values._counted(owed.get(_NOTICE_SPENT))
    if not isinstance(message, str) or not message:
        return None
    if allowance is None or spent is None:
        return None
    return OwedNotice(message=message, allowance=allowance, spent=spent)


def _owe_notice(state: PinnedState, ledger: AgentRunLedger) -> None:
    """Record this park's sentence, and the reading it was written for."""
    state.set(AGENT_RUN_LIMIT_NOTICE, {
        _NOTICE_MESSAGE: _limit_message(ledger),
        _NOTICE_ALLOWANCE: ledger.allowance,
        _NOTICE_SPENT: ledger.used,
    })


def _settle_notice(state: PinnedState) -> None:
    """Drop the obligation, however it ended.

    One name for both endings, because the field records an obligation rather
    than an event: a sentence posted to the thread and one a park retired
    before anybody read it leave exactly nothing owed.
    """
    state.data.pop(AGENT_RUN_LIMIT_NOTICE, None)


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
        thread = gh.comments_after(issue, state.get(_LAST_ACTION_COMMENT_ID))
    except Exception:
        log.exception(
            "issue=#%d could not be read for an agent-run-limit notice "
            "already posted; leaving it owed and saying nothing this tick "
            "rather than repeating a sentence the thread may already carry",
            issue.number,
        )
        return _UNREADABLE_THREAD
    bot_login = getattr(gh, "_bot_login", None)
    said = [
        issue_comment.id
        for issue_comment in thread
        if message in (issue_comment.body or "")
        and authored_by_us(issue_comment, bot_login=bot_login)
    ]
    return max(said) if said else None


def _limit_message(ledger: AgentRunLedger) -> str:
    """What the park explains to the humans it stops the issue for.

    Both numbers are quoted because they are the facts the refusal was made
    on, and because the allowance is not always the setting: an issue may
    carry one of its own, and a human reading a ceiling they did not
    configure needs to see the one this issue was actually held to.
    """
    return (
        f"spent this issue's lifetime agent-run allowance "
        f"({ledger.used}/{ledger.allowance} runs); manual intervention "
        f"needed. A lifetime total is spent once, so no window reopens it."
    )
