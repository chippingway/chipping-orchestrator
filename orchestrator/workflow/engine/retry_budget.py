# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The day's spawn budget an issue has, and the park an empty one leaves.

Every fresh agent spawn on an issue is charged to one per-issue budget --
implementing and decomposing share it, because both spend the same issue's day
of tokens -- and the whole point of a cap is that the issue STOPS when it is
out. Which is why nothing in the gate posts: deciding and telling a human are
two obligations with different failure modes, and an owner holding both has to
answer a refused comment either by failing a spawn it already allowed or by
saying the same sentence again on the next tick, forever.

So the gate answers and the caller acts. `_consume_retry_slot` reads the
accounting, charges an attempt it allows, and hands back what it decided.
Every durable consequence of a refusal -- the park, the stable reason under
it, the stage that ran out, and the sentence the thread is owed -- is staged
into the caller's own pinned state and rides out on the write that caller was
going to make anyway. A refusal writes nothing of its own, so a tick that dies
between the decision and that write leaves the budget exactly as it found it.

What a caller then DOES with a refusal is the one part that is not always its
own. A stage whose park has to carry state this owner never sees -- a live
late generation, its frozen pair, and the hold on the pull request its
candidate stands under -- stages the park itself, so the record and the reason
the record stopped moving land on one write. A stage whose park carries
nothing but the park takes `_charge_or_park` below, which is that same tail
written once rather than copied per stage: charge, stage, write, and say it
once. The gate is untouched either way -- it is the composition that writes,
and it writes before it posts.

The park is durable so that it can be recognized. `park_reason` says
`retry_cap` and `retry_cap_stage` says which stage ran out, which is what lets
a later tick tell an issue waiting on THIS from one waiting on an agent's
question -- and refuse the spawn from the flag rather than by re-deriving the
whole window. It is also what keeps the park exhausted: the 24h window is a
budget window, not a parole hearing, and a notice that asked for a human is
not answered by the clock passing it. While the park stands the window is
never renewed, however old it is. Renewal is one explicit step,
`_grant_continuation`, and what it hands back is a single attempt.

What the thread is owed is written down beside the park rather than assumed
said. The comment and the write that records it cannot be made one operation,
and the two readings of that gap fail in opposite directions: read as already
said, a refused comment leaves a human waiting on a sentence nothing will ever
say; read as still owed, a write that failed after a post that landed repeats
one comment. So the obligation is durable, the thread is asked before it is
repeated, and what a park says is said once per park rather than once per
tick.

The four audit phases are the same story from outside: what was said first,
what the thread was found to already carry, which ticks the park went on
refusing, and when a human bought another attempt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from github.Issue import Issue

from orchestrator.config import settings as config
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import authored_by_us
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards, usage as _usage

log = logging.getLogger("orchestrator.workflow")

# The durable reason an exhausted budget parks under. It is a wire string on
# live issues and the one thing that makes this park recognizable to the tick
# after it: a park with no reason is one nothing can tell from any other
# stage's, and the gate would go on re-deciding the same exhausted budget.
PARK_RETRY_CAP = "retry_cap"

# The sentence the standing park has still to say out loud. Held beside the
# flag, dropped only by a post that landed or by the park itself ending, and
# spelled without the mention the delivery prefixes -- what is durable is what
# the park has to explain, not how a thread was addressed.
RETRY_CAP_NOTICE = "retry_cap_notice"

# How many of the attempts a continuation bought are still unspent. Its
# PRESENCE is what says this issue runs on grants rather than on the setting:
# a human answered a park here, and what they answered it with is a count of
# attempts, not a licence to read whatever `MAX_RETRIES_PER_DAY` happens to
# say when the spawn is finally asked for. Stored as the count itself so it
# survives every change to that setting in both directions -- widened, and
# turned off. Written by the continuation, spent by the gate, dropped where
# the rest of the budget is: the publication that moves the issue on.
#
# Its ABSENCE is the only thing that means "no grant" -- an issue nobody has
# continued, or one the publication reset cleared back to null. Present, it
# governs: a real count is read into the range a continuation can produce (a
# bigger number a hand edit left buys the one attempt a continuation buys, a
# negative buys nothing), and a value that is not a number at all proves no
# attempt and so hands out none. Nothing a hand edit can leave here widens
# what this issue may spend.
RETRY_CAP_CONTINUED = "retry_cap_continued"

# What one continuation buys. Spelled here because it is the bound the notice
# quotes when the attempt is spent, as well as the number written down.
_GRANTED_ATTEMPTS = 1

# Which stage's fresh spawn ran out. The budget is shared, so the flag alone
# cannot say what the human is being asked about, and the audit records below
# would have no stage to report the park under once the label has moved on.
RETRY_CAP_STAGE = "retry_cap_stage"

_RETRY_CAP_EVENT = "retry_cap"

# What a thread read answers when the request itself failed. A sentinel rather
# than None, because None is the answer for a thread that was read and does
# not carry the notice -- and only that one may be posted over.
_UNREADABLE_THREAD = object()

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

_RETRY_WINDOW_START = "retry_window_start"

_RETRY_COUNT = "retry_count"

# The consumed-comment watermark a park's own mention ratchets, and only on a
# post that landed. That is what makes it the window an undelivered notice is
# looked for in: a sentence whose write failed sits ABOVE the mark its post
# should have moved, while one from a tick that completed sits at or below it.
_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# A fixed window per issue rather than a rolling one: enough to stop a stuck
# issue from burning a day of tokens, and cheap enough to read off two fields.
_WINDOW = timedelta(hours=24)


class RetryCapPhase(StrEnum):
    """Which step of a retry-cap park one audit record describes.

    The four are deliberately distinguishable. A delivery and a reconciliation
    both end with the thread carrying the notice, but only one of them paid a
    comment for it; a standing park and a continuation both follow an
    exhausted budget, but only one of them lets an agent run again.
    """

    DELIVERED = "delivered"
    RECONCILED = "reconciled"
    STANDING = "standing"
    CONTINUED = "continued"


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
class RetryDecision:
    """What one stage's fresh spawn was told, and the accounting behind it.

    Carried back rather than acted on here: the caller owns the park, the
    write under it, and the sentence it explains. `cap` and `window_start` are
    reported because the notice quotes both -- a human who is asked for manual
    intervention is owed the numbers the refusal was made on. `cap` is the
    bound that was actually in force, which is the configured one everywhere
    but on an issue a continuation has already had to buy.
    """

    allowed: bool
    stage: str
    cap: int
    spent: int
    window_start: str | None


def _consume_retry_slot(state: PinnedState, *, stage: str) -> RetryDecision:
    """Decide whether a fresh spawn may run, and charge it when it may.

    Only fresh spawns are counted. A resume on a human reply and a recovered
    worktree's push are an unblock signal and carried-over work, not retries.

    A standing retry-cap park is the first thing asked and it refuses on its
    own, ahead of the cap and ahead of the window. What stands there was
    announced as needing a human, and every other way of getting past it is
    something no human answered: the clock passing the window, and an operator
    widening `MAX_RETRIES_PER_DAY` or turning it off entirely -- a setting
    change is not the continuation the notice asked for, and reading it as one
    would resume the workflow silently. Only `_grant_continuation` lifts it.

    Below that park, an issue a continuation has bought attempts for is
    answered from those attempts and from nothing else. The setting is not
    consulted at all there: read at spend time it would make a grant worth
    whatever the cap had become in between -- nothing, once it is turned off,
    or several attempts once it is widened -- and what a human bought is one
    attempt whenever it is taken.

    An issue with no grant on it is answered by the setting. An unbounded
    budget (`MAX_RETRIES_PER_DAY <= 0`) allows everything and keeps no
    accounting -- and drops what it finds, so that turning it off is not a
    pause on a window nobody could spend while it was off. Kept, that window
    would refuse the first spawn after the budget came back, out of a count
    charged under a setting that has been changed twice since. A bounded
    budget opens its window at the first counted attempt and reopens it once
    24h have passed.

    A refusal writes nothing. Everything durable a refusal implies is staged
    by `_stage_retry_cap_park`, which the caller runs when it has decided this
    tick is the one that parks.
    """
    if _park_stands(state):
        return RetryDecision(
            False, stage, _bound_in_force(state),
            int(state.get(_RETRY_COUNT) or 0),
            state.get(_RETRY_WINDOW_START),
        )
    granted = _granted_attempts(state)
    if granted is not None:
        return _spend_granted_attempt(state, stage, granted)
    bound = config.MAX_RETRIES_PER_DAY
    if bound <= 0:
        state.data.pop(_RETRY_WINDOW_START, None)
        state.data.pop(_RETRY_COUNT, None)
        return RetryDecision(True, stage, bound, 0, None)
    if _window_is_over(state):
        state.set(_RETRY_WINDOW_START, _usage._now_iso())
        state.set(_RETRY_COUNT, 0)
    spent = int(state.get(_RETRY_COUNT) or 0)
    window_start = state.get(_RETRY_WINDOW_START)
    if spent >= bound:
        return RetryDecision(False, stage, bound, spent, window_start)
    state.set(_RETRY_COUNT, spent + 1)
    return RetryDecision(True, stage, bound, spent + 1, window_start)


def _stage_retry_cap_park(state: PinnedState, decision: RetryDecision) -> bool:
    """Record the park an exhausted budget takes, and what it owes a thread.

    In memory only, like every other field a refused tick stages: what makes
    it durable is the caller's own write, which is what keeps the park and the
    obligation it carries in one write rather than two.

    Returns whether the thread is now owed a sentence. A park already standing
    whose notice has been said is not announced again -- that repeat is the
    whole failure this protocol exists to stop, and the budget is re-decided
    on every eligible tick, so nothing else would ever stop it. Nor is such a
    park rewritten: the flag, the reason, and the stage under it are already
    what this refusal would say, and the refusal is the same one.

    A park whose sentence was never said is still owed it, and what it is owed
    is the sentence it was taken with -- kept verbatim rather than rewritten
    from this refusal. The obligation is a claim about a comment that may
    already be on the thread, and the thread is searched for exactly the text
    the park recorded: a sentence reworded by a later tick under a different
    stage or a retuned cap would find nothing, post a second notice, and
    attribute the park to a stage that did not take it. Only a standing park
    with no stage of its own -- an issue parked before this field, or hand
    edited out of it -- takes this refusal's, since a park nobody can name is
    worse than one named late.
    """
    if not _park_stands(state):
        state.set(_AWAITING_HUMAN, True)
        state.set(_PARK_REASON, PARK_RETRY_CAP)
        state.set(RETRY_CAP_STAGE, decision.stage)
        state.set(RETRY_CAP_NOTICE, _cap_message(decision))
        return True
    if _park_stage(state) is None:
        state.set(RETRY_CAP_STAGE, decision.stage)
    return _owed_notice(state) is not None


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
        f"{config.HITL_MENTIONS} {owed}",
        reason=PARK_RETRY_CAP,
    )
    state.set(_PARK_REASON, PARK_RETRY_CAP)
    _settle_notice(state)
    _emit_phase(gh, issue, state, RetryCapPhase.DELIVERED)
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
    nothing for the delivery below to do about it either.
    """
    owed = _owed_notice(state)
    if owed is None:
        return NoticeReading.SAID
    delivered = _delivered_id(gh, issue, state, owed)
    if delivered is _UNREADABLE_THREAD:
        return NoticeReading.UNREADABLE
    if delivered is None:
        return NoticeReading.UNSAID
    log.info(
        "issue=#%d already carries its retry-cap notice; recording it as "
        "said rather than saying it twice",
        issue.number,
    )
    _settle_notice(state)
    prior = state.get(_LAST_ACTION_COMMENT_ID)
    if not isinstance(prior, int) or delivered > prior:
        state.set(_LAST_ACTION_COMMENT_ID, delivered)
    _emit_phase(gh, issue, state, RetryCapPhase.RECONCILED)
    return NoticeReading.SAID


def _charge_or_park(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    *,
    stage: str,
) -> bool:
    """Gate a fresh agent spawn, and park the issue itself when it is refused.

    The parking form of the budget, for the stages whose park carries nothing
    of their own. Everything it decides is decided by `_consume_retry_slot`;
    what is here is the tail those callers would otherwise each have to write
    -- stage the park, settle the sentence it owes against the thread, and say
    it once.

    Returns True if the spawn is allowed (and the budget was charged); False
    if the budget is out. On that branch the park is made DURABLE here, before
    a word of it is said: a notice on a thread that no pinned state backs is
    the worst of both endings -- nothing reconciles it, because nothing knows
    it is owed, and the window under it rolls over a day later with the issue
    running again beneath a comment saying it had stopped. The caller's own
    write follows and carries whatever the delivery settled.

    A park already standing for an exhausted budget is re-taken silently: the
    budget is re-decided on every eligible tick, so announcing it again would
    say the same sentence to the same thread once a poll until a human
    arrived. The thread is asked before anything is said, so a comment that
    landed under a write that failed is recorded as said rather than repeated
    -- and a thread this tick could not read is said nothing to at all, since
    the sentence it may already carry is exactly the one about to go out.
    The park stands and the notice stays owed, so the next tick reads again.

    `stage` is required rather than defaulted. It is what the park is
    attributed to and what the notice quotes, the budget is shared, and a
    default here would be one stage's name answering for another's spawn.
    """
    decision = _consume_retry_slot(state, stage=stage)
    if decision.allowed:
        return True
    if not _stage_retry_cap_park(state, decision):
        _emit_phase(gh, issue, state, RetryCapPhase.STANDING)
        return False
    gh.write_pinned_state(issue, state)
    if _reconcile_notice(gh, issue, state) is NoticeReading.UNSAID:
        _deliver_notice(gh, issue, state)
    return False


def _replay_owed_notice(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Say what a standing retry-cap park is for, if nothing ever did.

    The retry the durable half of a park earns, and the reason the obligation
    is written down at all. A park is exactly the state that stops a tick
    reaching anything: the stages this budget gates route an awaiting-human
    issue to a resume or to nothing, and neither of those roads passes the
    gate that took the park -- so a sentence a refused post or an unreadable
    thread left owed would stay owed for as long as the issue is parked, which
    is unbounded. The human would be waiting on a comment nobody was ever
    going to write.

    So it is asked at the top of the tick, ahead of every gate a park routes
    past, and it is idempotent by what it clears: the obligation is dropped by
    the post that discharges it, so a notice reaches the thread once per park
    rather than once per tick. A thread that could not be read is left for the
    next tick rather than posted over.

    The write is taken here rather than left to the caller, because the caller
    is a tick that may be about to return without writing anything at all --
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


def _grant_continuation(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Clear a standing retry-cap park and buy it one more attempt.

    The renewal the park's own notice asks for, and the only one there is: the
    window reopens HERE, at a human's word, and what it holds is a single
    slot. A whole fresh day would let one reply spend the cap over again with
    nobody watching, which is the runaway the budget exists to bound; one
    attempt makes every retry past the cap a decision somebody took.

    What it grants is written down as a count of attempts rather than as a
    counter to compare against the setting later. The setting is a global an
    operator moves while issues are in flight, and a grant expressed against
    it is worth whatever it has become by the time the spawn is asked for:
    nothing at all once the budget is turned off, and several attempts once it
    is widened. One is one, so it is stored as one -- and from here to the
    spawn that spends it, nothing this issue is answered with reads the cap.

    Whether the caller is entitled to grant it -- that a park stands, and that
    the comment asking is a trusted `/orchestrator continue` -- is the
    caller's to establish. What is here is what granting one does.
    """
    _emit_phase(gh, issue, state, RetryCapPhase.CONTINUED)
    state.set(RETRY_CAP_CONTINUED, _GRANTED_ATTEMPTS)
    state.set(_RETRY_WINDOW_START, _usage._now_iso())
    state.set(_RETRY_COUNT, 0)
    state.set(_AWAITING_HUMAN, False)
    state.set(_PARK_REASON, None)
    state.data.pop(RETRY_CAP_STAGE, None)
    _settle_notice(state)


def _emit_phase(
    gh: GitHubClient, issue: Issue, state: PinnedState, phase: RetryCapPhase,
) -> None:
    """Record which step of a retry-cap park this tick took.

    The stage is read off the park rather than off the label, because the
    budget is shared and the label an issue wears while parked is not always
    the stage whose spawn ran out. A park carrying no readable stage reports
    none at all, which the record builder drops -- a phase with no stage is
    still countable, and a guessed one is worse than a missing one.
    """
    gh.emit_event(
        _RETRY_CAP_EVENT,
        issue_number=issue.number,
        stage=_park_stage(state),
        phase=phase,
    )


def _park_stands(state: PinnedState) -> bool:
    """Whether this issue is stopped, right now, on an exhausted budget.

    Both halves are asked. The flag alone is every stage's park, and the
    reason alone outlives the park a resume already cleared.
    """
    if not state.get(_AWAITING_HUMAN):
        return False
    return state.get(_PARK_REASON) == PARK_RETRY_CAP


def _spend_granted_attempt(
    state: PinnedState, stage: str, granted: int,
) -> RetryDecision:
    """Answer an issue that runs on what a continuation bought it.

    The grant is the whole budget while it lasts: no window is renewed under
    it and no cap is read, so an attempt a human paid for is worth exactly one
    spawn whenever it is taken and whatever the setting has become since.

    A grant with nothing left in it refuses, and the caller parks on it as it
    parks on any other exhausted budget -- which is what makes the next
    attempt a human's word again rather than the clock's. The ordinary counter
    is charged beside it so the spawn a grant pays for is reported like every
    other one.
    """
    spent = int(state.get(_RETRY_COUNT) or 0)
    window_start = state.get(_RETRY_WINDOW_START)
    if granted <= 0:
        return RetryDecision(
            False, stage, _GRANTED_ATTEMPTS, spent, window_start,
        )
    state.set(RETRY_CAP_CONTINUED, granted - 1)
    state.set(_RETRY_COUNT, spent + 1)
    return RetryDecision(
        True, stage, _GRANTED_ATTEMPTS, spent + 1, window_start,
    )


def _granted_attempts(state: PinnedState) -> int | None:
    """How many attempts a continuation still owes this issue, if it runs on
    one at all.

    Absent is the one answer that means "no grant": an issue nobody has
    continued carries nothing here, and the reset a publication writes spells
    the same thing as null. Both answer None and are decided by the configured
    budget, as every issue that never hit the cap is.

    Anything else PRESENT says this issue runs on grants, and from there the
    only question is how many it has left. A number is read into the range a
    continuation can produce: a bigger one a hand edit left buys the same
    single attempt, and a negative buys nothing. A value that is not a number
    at all -- `true`, `"1"`, a list -- proves no attempt, so it hands out
    none. Read instead as no grant, it would fall through to the setting and
    answer a renewal-shaped record with a whole window's worth of spawns, or
    with every spawn where the budget is off, off the strength of something
    somebody typed. `bool` is refused explicitly, since it is an `int` in this
    language and a `true` would otherwise read as an attempt still owed.

    Failing closed costs a park that asks a human, which is the same thing
    the field itself is there to ask for.
    """
    granted = state.get(RETRY_CAP_CONTINUED)
    if granted is None:
        return None
    if isinstance(granted, bool) or not isinstance(granted, int):
        return 0
    return min(max(granted, 0), _GRANTED_ATTEMPTS)


def _grant_is_unspent(state: PinnedState) -> bool:
    """Whether a continuation has bought an attempt nothing has taken yet.

    A claim about the ROAD the next agent run has to take, which is why it is
    asked outside this owner at all. What a continuation buys is a fresh
    spawn -- the only run the budget counts and the only one this gate is
    consulted for -- so every seam that would instead resume a locked session
    has to stand down while one is outstanding. A resume there would run the
    agent the human paid for and leave the grant on the issue unspent, ready
    to buy a second.

    Absent and exhausted answer the same way, since neither is an attempt
    somebody is still owed: an issue with no grant is decided by the
    configured budget, and one whose grant is spent is back to being decided
    by it at the next window.
    """
    granted = _granted_attempts(state)
    return granted is not None and granted > 0


def _bound_in_force(state: PinnedState) -> int:
    """How many fresh spawns this issue is allowed at all, for the record.

    What a refusal reports, so that the notice quotes the bound the issue was
    actually held to: the attempts a continuation bought where it runs on
    those, and the configured cap everywhere else.
    """
    if _granted_attempts(state) is None:
        return config.MAX_RETRIES_PER_DAY
    return _GRANTED_ATTEMPTS


def _park_stage(state: PinnedState) -> str | None:
    """Which stage's fresh spawn the standing park ran out of, if it says.

    An issue parked before this field existed, or hand-edited out of it,
    answers None -- the audit record drops the stage rather than reporting a
    guessed one, and the next refusal writes its own.
    """
    stage = state.get(RETRY_CAP_STAGE)
    return stage if isinstance(stage, str) and stage else None


def _owed_notice(state: PinnedState) -> str | None:
    """The sentence this park has still to say, if it has one.

    Anything but a non-empty string reads as nothing owed: an issue recorded
    before this field existed, and a hand-edited one, both leave a park that
    says nothing rather than a tick that raises over the shape of a note.
    """
    owed = state.get(RETRY_CAP_NOTICE)
    return owed if isinstance(owed, str) and owed else None


def _settle_notice(state: PinnedState) -> None:
    """Drop the obligation, however it ended.

    One name for both endings, because the field records an obligation rather
    than an event: a sentence posted to the thread and a park a continuation
    retired before anybody read it leave exactly nothing owed.
    """
    state.data.pop(RETRY_CAP_NOTICE, None)


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
            "issue=#%d could not be read for a retry-cap notice already "
            "posted; leaving it owed and saying nothing this tick rather "
            "than repeating a sentence the thread may already carry",
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


def _cap_message(decision: RetryDecision) -> str:
    """What the park explains to the humans it stops the issue for.

    The window it opened at is quoted because that is the fact the refusal was
    made on, and the one an operator needs to tell a budget that is genuinely
    spent from a counter something left behind.
    """
    return (
        f"hit retry cap ({decision.cap}/day) for {decision.stage}; "
        f"manual intervention needed. "
        f"Window opened at {decision.window_start}."
    )


def _window_is_over(state: PinnedState) -> bool:
    """Whether the standing window has run out, or was never readable.

    An absent, unparsable, or offset-free stamp answers True and a new window
    is opened over it: a budget nobody can account for is worse than one
    charged from now, and what stops a runaway is the park below rather than
    the clock. A naive stamp is refused rather than compared -- reading one as
    UTC would invent the very fact the comparison turns on, and no writer here
    produces one.
    """
    stamp = state.get(_RETRY_WINDOW_START)
    if not stamp:
        return True
    try:
        opened = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return True
    if opened.tzinfo is None:
        return True
    return datetime.now(UTC) - opened > _WINDOW
