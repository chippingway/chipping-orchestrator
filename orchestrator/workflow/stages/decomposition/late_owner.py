# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The fresh read that stands between a finished run and what it earns.

Every other guard in this mode is about the candidate. This one is about the
issue the candidate belongs to, and it exists because of how long a late run
takes: the issue was fetched when the tick began, the adjudicator or the
developer then ran for minutes to hours, and everything a completed run leads
to -- publishing an accepted candidate, taking a snapshot, superseding the
pull request its work is on, activating children -- is an effect on an issue
somebody may
have closed in the meantime. The snapshot in hand cannot say so, so the owner
is read again, once, after the result is durable and before any of it happens.

EVERY completion, not only the ones that decided something. A question, a
timeout, an unusable reply, and a developer reconciliation that could not be
made are all runs the issue paid for, and a closure during any of them strands
the same generation and the same hold as a closure during a `single`
would. So the read is taken on each of them, and what differs is only what the
answer is allowed to change.

Three answers, and each is a different obligation.

**Open** is the only one that lets the tick carry on, and it is also where a
pending check from an earlier tick is retired.

**Closed** ends the cycle rather than the tick. The generation is marked
cancelled and the mark is irreversible within it -- a human who reopens the
issue afterwards gets a fresh cycle, not this one resumed, because the moment
the cleanup obligation was taken on is not a thing a later reading may move.
Nothing is reclaimed here: what the remote is owed is recorded on the
generation, and the cleanup path is what settles it. Marking is the whole job,
and it is durable before the record of it is emitted.

**Unreadable** leaves the check owed, on the generation itself. That marker is
the load-bearing half, because nothing else would bring a tick back to this
read: a revision that came back under the ceiling is not adjudicable, and an
issue already parked for a human is not going anywhere either, so a retry that
hung off either would never run. It is written BEFORE the read rather than
after it fails, because a read that fails is not the only one that does not
come back -- a process killed mid-read would leave nothing at all behind, and
that is precisely a tick whose obligation nobody can reconstruct.

The park beside it is the visible half, and it is taken only when the issue is
not ALREADY stopped on something a human has to answer -- replacing a question
or a stalled revision with "the owner could not be read" would swap out the
thing the human is being asked.

The retry costs no agent. The run has already been paid for and its result is
already recorded, so what failed is a single GitHub read: the pending check is
reconciled at the very top of the next eligible tick, ahead of the size gate,
the hold, and any spawn, and the recorded result is what answers the
candidate afterwards.

The claim is not made here, though, and that is the point of it. It rides the
COMPLETION's own write -- the one `late_outcome` makes as the last step of
every finished run, carrying the recorded verdict or the park a timeout, an
unusable reply, an unrecordable outcome, a moved candidate, or a reconciliation
nobody could make earned. Taking it a step later, on the way into this read,
would mean a tick that died in between left nothing at all: no park, no claim,
and a generation still reading as `adjudicating`, so the next tick would pay
for another agent against a candidate this one already answered. What this
owner does with the claim is ask whether it is standing, and read only past it.

That same write is what every notice a completion staged rides out on: the
park is durable, and the sentence is said out loud once the read comes back
open -- so a comment GitHub refuses can no longer take a finished run's result
with it, and nothing is announced ahead of the read that would have told this
tick whether anybody is still listening.

Holding a sentence back is a DEFERRAL, though, and only where something will
say it instead. A park a later attempt supersedes is re-taken and re-announced
by that attempt; a park no attempt supersedes is what the issue is waiting on,
and its sentence is the only thing that will ever say what the human has to
do. So an unreadable owner releases that one anyway: a comment on a thread
nobody could prove is open costs less than an `awaiting_human` standing
unexplained for as long as the read keeps failing.

A park that clears itself owes the thread one sentence, for the reason every
self-healing park in this repository does: the last thing said on the issue
mentioned a human and asked them to look, and leaving that as the final word
costs somebody a visit to an issue that has moved on. Unless there was no such
word: a park whose own notice GitHub refused told nobody anything, so it is
retired in silence and the follow-up is skipped -- a recovery message for a
failure the thread never heard about is the first thing the episode would have
said. What that park still owes is said instead by the read that fails AGAIN,
which is the only tick on which it is still true. It is posted BEFORE the
write that clears the park, so the window a crash can land in loses the write
and not the sentence -- and "at most once" is answered from the thread rather
than from pinned state, because the post and the clear cannot be made one
operation. The follow-up carries its own marker and the next attempt looks for
one among the comments past `last_action_comment_id`, the id the park's own
mention stamped, which is what scopes the search to THIS episode.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.workflow.engine import comments as _comments, observations as _observations, usage as _usage
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
    LatePhase,
)
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_outcome as _late_outcome,
    late_park_delivery as _late_park_delivery,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateContext,
    _LateDisposition,
    _OwnerState,
)

log = logging.getLogger("orchestrator.workflow")

# The two states a GitHub issue reports. Anything else -- a shape with no
# state on it, an attribute that raised -- is a read that established nothing,
# which is not the same claim as "open".
_OPEN = "open"
_CLOSED = "closed"

_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# Stamped on every follow-up so a later tick recognizes one it posted even
# when the pinned write that was supposed to record it never landed. This
# mode's own, not the validating route's: a follow-up from another episode
# must not be able to silence this one. An HTML comment, so it is invisible in
# the rendered thread.
_RECOVERY_FOLLOWUP_MARKER = "<!--orchestrator-late-owner-recovery-->"

_RECOVERED_FOLLOWUP = (
    ":arrows_counterclockwise: Recovered automatically: this issue's own "
    "state could not be read when the adjudication finished, and now can; "
    "processing resumed. No action needed.\n\n"
    f"{_RECOVERY_FOLLOWUP_MARKER}"
)

_UNREADABLE_PARK = (
    "this issue's oversized committed candidate has been adjudicated, but "
    "whether the issue itself is still open could not be read from GitHub -- "
    "so nothing was published, superseded, or created. The result is "
    "recorded: the next tick takes the same read again without re-running any "
    "agent, and says so here when it succeeds."
)


def _reconcile_pending_owner_check(
    context: _LateContext,
) -> _LateDisposition | None:
    """Take again the owner read an earlier tick could not, if one is owed.

    The first thing a tick asks, ahead of the live-generation gate and the
    hold, because the marker it reads is exactly the state those two
    would route past: a revised candidate that came back under the ceiling is
    not adjudicable and an issue parked for a human is not adjudicating, and
    on either of them a pending read would otherwise stand for good.

    Answers None when there is nothing owed, and also when the read succeeded
    -- the tick carries on with the park cleared and its follow-up said. A
    closed owner and one that still cannot be read are the whole of what the
    tick did.
    """
    generation = context.generation
    if not generation.is_present or generation.cancelled:
        return None
    if not generation.owner_check_pending:
        return None
    reading = _guarded_owner(context)
    if reading == _OwnerState.CLOSED:
        return _LateDisposition.CANCELLED
    if reading == _OwnerState.UNREADABLE:
        return _LateDisposition.PARKED
    return None


def _still_wanted(context: _LateContext) -> _LateDisposition | None:
    """Whether the split may take its next irreversible step, or why not.

    None is the only answer that lets one happen. Asked immediately before
    each of them rather than once for all of them, because the steps are not
    one moment: a push and a fetch stand between the verdict and the first
    child, and a create, a record, and a seed stand between every child and
    the next, so a human can close the issue inside any of those gaps.

    What makes asking necessary at all is who else could see the close. A
    poll that observes one while this worker holds the issue cannot hand it
    anywhere -- the scheduler admits no second worker for an issue one is
    already running -- so the observation is deferred to a later tick, and
    until that tick comes THIS run is the only thing standing between a
    closed issue and another real issue created against it.

    The three answers are the guard's own, unchanged. A closed owner is
    marked and the cycle ends where it stands, with everything already put on
    the remote left on the ledger for the cleanup path. An unreadable one
    parks: a read that established nothing is not "still open", and the read
    stays owed on the record, which is what brings the next tick back to it
    ahead of anything else it would do.
    """
    reading = _guarded_owner(context)
    if reading == _OwnerState.OPEN:
        return None
    if reading == _OwnerState.CLOSED:
        return _LateDisposition.CANCELLED
    return _LateDisposition.PARKED


def _guarded_owner(context: _LateContext) -> _OwnerState:
    """Read this generation's owner fresh, and record what the answer costs.

    The one call every completed late run passes through before it is acted
    on, and it is entered PAST a claim rather than making one. The obligation
    is written by the completion itself, in the same write that recorded what
    the run left, so a process that dies anywhere between the run and this
    read -- inside it, or before a line of it has run -- leaves an issue that
    still owes the read and a park a human can already see. Deriving the
    obligation from the failure would mean a read that never came back left
    nothing behind at all, and taking it here would mean a tick that died on
    the way here left nothing either.

    Asked rather than assumed all the same, because "claimed" is the one thing
    the read may not be taken without: a caller whose own write did not carry
    it gets the claim here, which costs a write and is not the same as reading
    an owner nothing would bring a tick back to.

    Each answer then persists what it means before anything external happens:
    an open owner drops the claim and releases what was staged, a closed one
    persists the cancellation, and an unreadable one leaves the claim exactly
    where it was written.
    """
    if not _already_claimed(context.generation):
        _late_outcome._completed(context)
    reading = _read_owner(context)
    if reading == _OwnerState.CLOSED:
        _cancelled(context)
    elif reading == _OwnerState.UNREADABLE:
        _unreadable(context)
    else:
        _cleared(context)
        _late_park_delivery._release_staged_park(context)
    context.staged_park = None
    return reading


def _already_claimed(generation: LateGeneration) -> bool:
    """Whether the read this guard is about to take is already owed durably.

    The precondition every caller is supposed to arrive having met, asked
    rather than assumed. A completion writes its own result and this claim as
    one thing -- that write is what a crash before the read leaves behind, and
    what stops the next tick paying for an agent that already answered -- and
    a reconciliation of an owed read is here BECAUSE the claim is standing.

    So the answer is normally yes and the guard writes nothing. It is asked at
    all because "claimed" is the thing the read may not be taken without, and
    a caller whose own write did not carry it gets the claim here rather than
    a read nobody would come back to. The phase is part of the question for
    the same reason it is part of the claim: a generation that recorded the
    obligation at an earlier boundary still owes this one its name.

    Which phases those are is the completion's own answer, not a single one.
    A claim never writes over a boundary the split transaction owns -- doing
    so would tell the reclamation that nothing had been cut from the ref yet
    -- so a transaction re-entered after a crash carries its claim under the
    boundary it interrupted, and that is as standing a claim as `owner_check`.
    """
    return (
        generation.owner_check_pending
        and generation.phase in _late_outcome._CLAIM_PHASES
    )


def _read_owner(context: _LateContext) -> _OwnerState:
    """Say which of the three answers this issue gives, latch read first.

    The latch is asked ahead of GitHub because it holds the one reading GitHub
    cannot give back: a poll that found this issue closed while this very
    worker held it could hand that reading to nobody -- the scheduler admits
    no second worker for an issue one is already running -- and a human who
    reopened it in the meantime has taken it off the remote for good. Asking
    costs no request, so every barrier in this mode gets it.

    Otherwise re-fetched rather than read off the snapshot the tick opened
    with, which is the whole point: that snapshot is as old as the run that
    has just finished. The fetch and the state read share one guard, because a
    PyGithub issue is lazy and the request that can fail is as likely to be
    the attribute as the fetch.

    Fails closed twice over. An exception is unreadable, and so is a state
    that is neither of the two GitHub reports -- a shape with no state on it
    would otherwise default to "open" and let the tick publish on the strength
    of a read that established nothing.
    """
    if _latched_close(context):
        return _OwnerState.CLOSED
    try:
        owner_state = _owner_state(context)
    except Exception:
        log.exception(
            "issue=#%d could not be re-read after its late run finished; "
            "not acting on the verdict this tick",
            context.issue.number,
        )
        return _OwnerState.UNREADABLE
    if owner_state == _OPEN:
        return _OwnerState.OPEN
    if owner_state == _CLOSED:
        return _OwnerState.CLOSED
    log.error(
        "issue=#%d reported no readable state after its late run finished; "
        "not acting on the verdict this tick",
        context.issue.number,
    )
    return _OwnerState.UNREADABLE


def _latched_close(context: _LateContext) -> bool:
    """Whether a poll observed this issue closed and nothing has settled it.

    Said out loud when it answers, because it is the one closed reading that
    no request of this run's would ever show and an operator reading the log
    would otherwise see a cycle end against an issue GitHub reports open.
    """
    if not _observations.close_observed(
        context.spec.slug, context.issue.number,
    ):
        return False
    log.warning(
        "repo=%s issue=#%d was observed closed by a poll that could hand the "
        "reading to no worker; ending cycle %d here rather than asking "
        "GitHub, which a reopen since would answer differently",
        context.spec.slug, context.issue.number, context.generation.cycle_id,
    )
    return True


def _latch_stops(context: _LateContext) -> _LateDisposition | None:
    """Whether a latched close forbids the step that is about to happen.

    The barrier for every irreversible step whose own moment is too tight for
    a request: the create at the bottom of the child loop, the spawn, the
    write that erases a settled cycle. It is the LATCH alone rather than the
    whole guard, because those steps sit where a claim would be wrong -- a
    claim names `owner_check`, and writing it over whatever boundary the tick
    actually reached is the rewind the record refuses -- and because it costs
    nothing: no request, and no write at all on an issue still reading open.

    A cycle already cancelled answers None, because there is nothing left
    here to end and the gate above routes it to its ending anyway.
    """
    if not context.generation.is_present or context.generation.cancelled:
        return None
    if not _latched_close(context):
        return None
    _cancelled(context)
    return _LateDisposition.CANCELLED


def _still_activating(context: _LateContext) -> _LateDisposition | None:
    """Whether the children this transaction made may be started.

    The last gap of all and the only one past the retirement, so it is asked
    without the claim every earlier barrier takes: the generation now stands
    at `cleaning_up`, and a claim writes `owner_check` over that -- the very
    boundary the whole-ledger rule reads to decide whether a ref may go.

    Three answers still, and the two that stop are not the same stop. A closed
    owner -- latched, or reported so by GitHub between the retirement write
    and this read -- ends the cycle: the mark goes down, no child is started,
    and the ending settles what the transaction already put on the remote. An
    unreadable one starts nothing and ends nothing; the umbrella's own walk
    takes the same reading on its next tick, which is the retry the activation
    always had.
    """
    reading = _read_owner(context)
    if reading == _OwnerState.OPEN:
        return None
    if reading == _OwnerState.CLOSED:
        _cancelled(context)
        return _LateDisposition.CANCELLED
    log.warning(
        "issue=#%d could not be re-read before its children were started; "
        "leaving them where they are for the umbrella's own walk",
        context.issue.number,
    )
    return _LateDisposition.SETTLED


def _owner_state(context: _LateContext) -> str:
    """The state GitHub reports for this issue right now.

    Both shapes the workflow sees are honored, exactly as the dispatcher's own
    closed check honors them: PyGithub's `state`, and the `closed` flag the
    in-memory double carries. The flag is asked first and only when it is set,
    so a shape that merely lacks it does not read as open on its own.
    """
    owner = context.gh.get_issue(context.issue.number)
    if getattr(owner, "closed", False):
        return _CLOSED
    return getattr(owner, "state", "")


def _cleared(context: _LateContext) -> None:
    """Drop the claim this read answered, saying so if a park is being retired.

    The follow-up goes out BEFORE the write that clears the park, so a crash
    between them costs the write rather than the sentence -- the next tick
    finds the claim still standing, finds its own follow-up already on the
    thread, and clears without repeating it.

    Only a park THIS guard filed is retired or announced. An issue stopped on
    a question or a stalled revision was never told anything by this guard, so
    there is nothing to take back and nothing of somebody else's to clear.

    Retired whether or not it was ever announced, and announced only if it
    was: a park whose own notice GitHub refused told nobody anything, so there
    is no alarming last word to take back and a follow-up would be the first
    this episode said -- a recovery message for a failure the thread never
    heard about.

    "Was it announced" is asked of the obligation, which is safe HERE and only
    here: the tick reconciles that obligation against the issue before any of
    this runs, so a notice the thread carries has already been discharged from
    what GitHub holds. Without that step the question would answer itself from
    a record, and a post that landed beside a write that did not would read as
    a silence -- costing the human the one sentence this park promises them.
    """
    if _late_park_state._stands_for(context, _late_park_state.PARK_OWNER_UNREADABLE):
        if _late_notice._owed_notice(context) is None:
            _announce_recovery(context)
        _late_parks._answer_park(context)
    context.generation = replace(
        context.generation, owner_check_pending=False,
    )
    _late_park_state._persist(context)


def _cancelled(context: _LateContext) -> None:
    """Mark this cycle cancelled for the cleanup that has to settle it.

    Irreversible within the cycle: the stamp is kept from the first marking,
    so a later tick that finds the issue reopened re-marks the same
    cancellation rather than moving the moment the obligation was taken on.

    The pending marker goes with it. What it exists for is bringing a tick
    back to this read, and this read has now been taken.

    A park notice still owed goes with it too. Every sentence this mode owes
    a human explains a candidate under adjudication, and a cancelled cycle
    has none: saying one now would ask somebody to settle a question about an
    issue they have already closed.

    Durable before it is reported, like every other record in this mode. What
    the remote still owes is already on the generation and is not touched
    here -- reclaiming it is the cleanup path's job, and this is the mark that
    path reads.

    Recorded and reported ONCE per cycle. Several barriers can reach a closed
    reading in one run -- the read taken between two children, the one taken
    before the activation -- and a record that already carries the mark is
    left exactly where the FIRST one put it: the stamp, the boundary, and the
    `late_cancellation` a sink is handed all belong to that marking, and
    repeating them would put one record per barrier on a cycle that ended at
    the first. The claim the repeat's own read was taken under is still
    dropped, because that read has now been taken.
    """
    if context.generation.cancelled:
        _claim_dropped(context)
        return
    log.warning(
        "issue=#%d was closed while its oversized candidate %s was being "
        "adjudicated; cancelling cycle %d",
        context.issue.number,
        context.generation.candidate_sha,
        context.generation.cycle_id,
    )
    context.generation = replace(
        context.generation.cancel(_usage._now_iso()),
        phase=LatePhase.CANCELLING,
        owner_check_pending=False,
    )
    _late_notice._notice_settled(context)
    _late_park_state._persist(context)
    _late_outcome._emit_cancellation(context)


def _claim_dropped(context: _LateContext) -> None:
    """Take the owner-read obligation off a cycle already marked over.

    What the claim exists for is bringing a tick back to a read of this
    issue, and the read that reached this has been taken. Written only where
    one is actually standing: a repeat that owes nothing writes nothing, so
    a cancelled cycle costs a pinned write on the barrier that marked it and
    on none of the barriers after it.
    """
    if not context.generation.owner_check_pending:
        return
    context.generation = replace(
        context.generation, owner_check_pending=False,
    )
    _late_park_state._persist(context)


def _unreadable(context: _LateContext) -> None:
    """Leave the claim standing, and park unless something else already does.

    Nothing durable is written here: the claim the read was taken under IS the
    retry obligation, and it went out before the read. What is left to decide
    is only whether a human is told, which is the park.

    The park is skipped for an issue already handed back to one -- that issue
    is stopped either way, and overwriting the reason it was stopped for would
    cost the human the question they were actually asked.

    What happens to the notice that park staged depends on whether anything
    will ever say it instead. A park a later attempt supersedes is re-taken
    and re-announced by that attempt, so holding its sentence back costs a
    tick; a park no attempt supersedes -- a stalled revision waiting to be
    told what a dirty checkout now means -- has no such tick coming, and
    dropping its sentence would leave a human looking at an `awaiting_human`
    with nothing saying what to do about it for as long as the read kept
    failing. That one is said, on a thread this tick could not prove is open,
    because silence there is unbounded and a stray comment is not.
    """
    _late_outcome._emit_failure(context, LateFailure.OWNER_READ_FAILED)
    if _late_park_state._stands_parked(context):
        log.info(
            "issue=#%d is already parked; leaving the owner read owed rather "
            "than replacing what it is parked on",
            context.issue.number,
        )
        _late_parks._release_unsuperseded_park(context)
        return
    _late_parks._park(
        context,
        _UNREADABLE_PARK,
        reason=_late_park_state.PARK_OWNER_UNREADABLE,
    )


def _announce_recovery(context: _LateContext) -> None:
    """Retire the alarming last word the park this tick answered left behind.

    The thread is read rather than a receipt remembered, because the comment
    and the write that clears the park cannot be one operation. Scoped to this
    episode by the park's own mention id, so an older follow-up sitting below
    the watermark cannot silence a later park's, and a park with no mention
    behind it says nothing at all -- nobody was pinged, so there is nothing to
    take back.
    """
    if context.state.get(_LAST_ACTION_COMMENT_ID) is None:
        return
    if _episode_already_announced(context):
        return
    _comments._post_issue_comment(
        context.gh, context.issue, context.state, _RECOVERED_FOLLOWUP,
    )


def _episode_already_announced(context: _LateContext) -> bool:
    """Whether this park episode's follow-up is already on the thread."""
    watermark = context.state.get(_LAST_ACTION_COMMENT_ID)
    return any(
        _RECOVERY_FOLLOWUP_MARKER in (issue_comment.body or "")
        for issue_comment in context.gh.comments_after(
            context.issue, watermark,
        )
    )
