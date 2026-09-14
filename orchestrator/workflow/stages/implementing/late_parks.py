# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a refusal costs, and the two sinks every one of them reaches.

One park shape for every reading the size gate could not take, because the
recovery is the same for all of them: the issue is handed back with the step
that failed named, the typed failure goes to the audit and analytics streams,
and a trusted bare `/orchestrator continue` re-reads rather than re-running
anything. The writes those steps ride out on are here too, since a park and a
persisted record are the two durable things this domain does.

What reaches those streams is the same three things the thread is told, and
for the same reason: the family says a reading did not happen, the member
beside it says which step stopped, and the line the step wrote says why. An
operator holding only the stream would otherwise have `measurement_failed` for
a remote that was throttling, a checkout that is gone, and a diff nothing can
pin, and no way to count one apart from the others.

Two of the steps a reading stops at get a bounded number of tries before that
happens, and they are the two that name the transport rather than the work: a
remote that would not answer for the base branch, and a fetch that did not
bring the base object back. Those clear themselves -- a network, a token, a
host that was down -- so the first few are counted on the record and nothing
else is done at all, and only a pair that has lost the last of them is worth a
human's attention. Every other member still parks on its first miss, because
re-reading a candidate this host does not hold or a diff nothing can pin buys
exactly the same answer.

Past ANY of those parks the pair is still read on every poll -- the
post-publication reconciliation takes that reading ahead of every handler --
and what those readings owe the thread is one sentence per thing there is to
say rather than one per poll. So the member a notice named is recorded, and it
is recorded by the roads that announce and by no other: a quiet miss tells
nobody anything, and a step written down by one would be a notice the guard
thinks was made. A reading stopping at the recorded member repeats a sentence
already on the issue and is held silently -- reported to the log and to both
sinks, said to no one. One stopping somewhere else is a different next move
for whoever is holding the issue, and nothing else would ever tell them, so it
is announced once and takes the recorded member's place.

What each member means to that person is spelled out here too. The vocabulary
is written for the code that branches on it, and a park that named only the
member would leave a human to work out for themselves whether they are looking
at a remote, a token, a checkout, or something planted in one.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from enum import StrEnum
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import settings as config
from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.github import (
    client as _client,
    comments as _github_comments,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    guards as _guards,
    messages as _messages,
)
from orchestrator.workflow.late_split import (
    events as _events,
    exemption as _exemption,
    formats as _formats,
    models as _late_models,
    payloads as _payloads,
    state as _late_state,
    telemetry as _telemetry,
)
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    late_records as _records,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

PARK_MEASUREMENT_FAILED = "late_measurement_failed"


class LateApprovalBasis(StrEnum):
    """What one approval on this issue rests on, said by the owner granting it.

    A bounded vocabulary rather than a flag, because the readers ask different
    questions of it and a boolean would have to be renamed the first time a
    third road approved anything.

    `READING` is this gate's own count coming back at or below the ceiling.
    `UNMEASURED` is a publication that skipped the count on a record this
    workflow made for itself and can re-derive: a rewrite permit, a
    switched-off candidate, a receipt already on the remote. Each of those
    answers for its own bypass on the next tick, so nothing about the debt
    they leave has to be revalidated before it is spent.

    The other two are the ones an operator's authorization stands behind, and
    they are apart from `READING` for exactly that reason: an approval is
    spent by the tick that comes back after a crash, and one that RESTS on an
    authorization may only be spent while that authorization can still be
    read. `ADJUDICATION` is the publication debt an authorized settlement
    records beside the exemption it writes. `AUTHORIZATION` is the debt a
    candidate past the ceiling earns when an operator authorizes it at the
    gate itself -- the count behind it was this gate's own, so recording it as
    a reading would be true and useless: what let it through was the human,
    and a record damaged before the push would have it publish unmeasured.

    A value from anywhere else, and an approval an older binary wrote with no
    basis at all, read back as no basis -- and what a reader does with that is
    fall back to the exemption, which is the only evidence such a record left.
    """

    READING = "reading"
    UNMEASURED = "unmeasured"
    ADJUDICATION = "adjudication"
    AUTHORIZATION = "authorization"


# The two an operator's gesture is behind, which may be spent only while that
# gesture can still be read. Named as a group because that is the question a
# reader has of the basis -- whether a debt has to be revalidated, rather than
# which owner granted it -- so the membership is stated once here instead of
# being re-derived by each of them, and it is the whole of what the two share.
AUTHORIZED_BASES = frozenset((
    LateApprovalBasis.ADJUDICATION,
    LateApprovalBasis.AUTHORIZATION,
))

# The steps a lost reading is retried quietly for, and the only two. Both name
# the transport between this host and the base -- a remote that would not
# answer for the branch, and a fetch that did not bring the object back -- and
# a transport fault is the one thing in this vocabulary that clears itself
# while nobody is watching. Every other member names something a second
# reading cannot change: a candidate this host does not hold, a diff nothing
# here can pin. Re-reading those buys the same answer, so they park on the
# first miss and ask a human for the one thing that would change it.
_TRANSPORT_STEPS = frozenset((
    MeasurementFailure.BASE_UNREADABLE,
    MeasurementFailure.BASE_ABSENT,
))

_UNMEASURED_PARK = (
    "{mentions} this issue's committed implementation could not be measured "
    "({failure}), so it has not been published: a candidate whose size is "
    "unknown is not a small one, and pushing it would publish an "
    "implementation nobody adjudicated. Nothing was discarded -- the commit "
    "is still in the worktree, and the exact pair this attempt froze is "
    "recorded. Fix what the reading needs, then reply `/orchestrator "
    "continue` and the same commit is measured again without re-running the "
    "developer."
)

# The same refusal where the work already has a pull request. It is worded
# apart because both halves of the recovery differ: nothing is waiting to be
# published for the first time, and a bare continue on these stages resumes
# the developer rather than re-reading a pair -- so the notice says what is
# true here and asks for nothing that would spend an agent.
_UNMEASURED_PUBLISHED_PARK = (
    "{mentions} what this issue's pull request would come to could not be "
    "measured ({failure}), so the commit in the worktree has not been pushed "
    "to it: a candidate whose cumulative size is unknown is not a small one, "
    "and pushing it would grow a pull request nobody adjudicated. Nothing was "
    "discarded -- the commit is still in the worktree, the pull request still "
    "stands where it did, and the exact pair this attempt froze is recorded. "
    "Fix what the reading needs and the same pair is measured again."
)

# What each step means to the operator who has to clear it, one line apiece.
# The member is what code branches on and what the record and the streams
# carry, and on a thread it says nothing: `candidate_absent` names a host to
# bring a commit to and `diff_unpinnable` names a checkout to clean, and the
# difference between them is the whole of somebody's next move. The lines are
# here rather than beside the vocabulary because they are addressed to the
# human on this issue -- what was refused, and what would change it -- rather
# than to the step that stopped.
_FAILURE_LINES = MappingProxyType({
    MeasurementFailure.BASE_UNREADABLE: (
        "The `git ls-remote` this reading takes against the base branch never "
        "came back with a commit, so there was no base to diff against: a "
        "remote that could not be reached or was throttling the request, or a "
        "token that has expired or cannot see this repository. Three retries "
        "have already been taken quietly, one per tick, and the same pair "
        "goes on being re-read on every tick after this notice -- so a "
        "transport that comes back settles this with no reply at all. The "
        "invocation that failed is logged under `orchestrator.git_plumbing`."
    ),
    MeasurementFailure.BASE_ABSENT: (
        "The remote named the base commit and a fetch did not bring that "
        "object to this host, so there was nothing here to take the diff "
        "against: a base branch rewritten under this clone, an object a prune "
        "took, or a fetch that could not finish. It is retried on the same "
        "quiet bound as `base_unreadable` and re-read on every tick after "
        "this notice, and the fetch is logged under "
        "`orchestrator.git_plumbing`."
    ),
    MeasurementFailure.CANDIDATE_UNREADABLE: (
        "The commit this issue is about does not resolve in the worktree on "
        "this host -- a checkout that was rebuilt, reset, or reaped out from "
        "under the record. Restore the checkout that holds it, or commit the "
        "work again; another reading of the same worktree answers the same "
        "way."
    ),
    MeasurementFailure.CANDIDATE_ABSENT: (
        "The revision resolved to an object id this host cannot read as a "
        "commit -- work made on a host this one is not, or an object a prune "
        "took. The commit has to be here before any reading of it can be "
        "taken."
    ),
    MeasurementFailure.DIFF_UNPINNABLE: (
        "The checkout carries configuration that would decide what counts as "
        "text -- a repository diff driver, or a planted `info/attributes` "
        "file -- and no override this reading takes reaches either, so a "
        "count taken under it could be made to read as a small candidate. "
        "Clear it in the worktree before the pair is measured again."
    ),
    MeasurementFailure.DIFF_FAILED: (
        "`git diff` over the two frozen commits exited non-zero, so no count "
        "came back at all. The invocation and what it wrote are logged under "
        "`orchestrator.git_plumbing`."
    ),
    MeasurementFailure.DIFF_UNREADABLE: (
        "`git diff --numstat` answered with a record this build cannot count, "
        "so no number could be taken from it. The invocation is logged under "
        "`orchestrator.git_plumbing`."
    ),
})

# What the step said for itself, where it said anything. Free text a human
# reads rather than anything to branch on, and scrubbed of the credential by
# the transport long before it reaches here.
_REPORTED_DETAIL = "The step reported: {detail}"


def _described(failure, detail: str) -> str:
    """The line an operator acts on, and what the step said for itself.

    The member alone is a contract term: it tells the reading what to do and
    tells the person holding the issue nothing about what to fix. So the
    notice carries the sentence written for them, and the transport's own line
    after it where there is one -- by the time a human reads this the process
    that saw that stderr is minutes and a tick gone, and nothing else kept it.

    Empty for a member no line covers, which is what keeps the notice's own
    sentences the contract: a park says what was refused whether or not this
    table has caught up with the vocabulary.
    """
    described = _FAILURE_LINES.get(failure, "")
    if not detail:
        return described
    reported = _REPORTED_DETAIL.format(detail=detail)
    return f"{described} {reported}" if described else reported


def _parked(
    gate: _records._Gate,
    generation: _late_models.LateGeneration,
    failure,
    message: str,
    detail: str = "",
) -> bool:
    """Record the typed failure on both sinks, then hand the issue back.

    Every reading that did not happen is reported, which is why the generation
    reaching here is one a caller has already made reportable: a candidate the
    gate could not even name has no record of its own yet, and the identity
    minted for it is what lets the failure be joined to the cycle a later
    freeze writes under the same number.

    `failure` is whatever the caller stopped at, and the roads in do not agree
    about what that is: the ones a reading refused name a member, while the
    ones a RECORD refused -- a pinned comment too damaged to act on, a debt no
    push can pay -- name the repair in their own words, because the whole
    point of those parks is telling a human which part to fix. The record
    keeps the member where there is one and says nothing where there is not,
    so a step nobody reached is never reported as one that was.
    """
    log.error(
        "issue=#%d committed work could not be measured (%s); parking rather "
        "than publishing an unadjudicated candidate",
        gate.issue.number, failure,
    )
    _emit(gate, generation, _events.measurement_failure_event(failure, detail))
    _guards._park_awaiting_human(
        gate.gh, gate.issue, gate.state, message,
        reason=PARK_MEASUREMENT_FAILED,
    )
    gate.state.set(_state._PARK_REASON, PARK_MEASUREMENT_FAILED)
    return True


def _unmeasured(
    gate: _records._Gate, generation: _late_models.LateGeneration, failure,
    detail: str = "",
) -> bool:
    """Park a candidate nobody could measure, loudly and with its reason.

    Never "small". What a failed `git` invocation writes to stdout is nothing,
    which is what a candidate that changes nothing writes too, so publishing
    on that reading is precisely how an unadjudicated implementation goes out.

    The step is named twice over: as the member every other surface carries,
    and as the line an operator acts on. A notice that named only the member
    would hand somebody a term this vocabulary owns and leave them to guess
    which of a remote, a token, a checkout, or a planted attribute file the
    next move is about.

    Loudly ONCE per cause, and this is the one place that can be decided:
    every reading refused for a typed step reaches a human through here, and
    the pair behind a park is re-read on every poll after it. Said again each
    time, a base nobody can fetch or a diff nothing can pin would mention the
    same people once a poll, for as long as it takes them to fix it -- which
    is a notification channel nobody can answer faster by reading twice. So a
    refusal a standing park has already announced is held instead: reported to
    the log and to both sinks like every other reading that did not happen,
    and said to no one. A refusal that stops SOMEWHERE ELSE is not a repeat --
    it is a different next move for whoever is holding the issue, and nothing
    else would ever tell them -- so it is said, and takes the announced
    member's place.

    The road that spends the bounded retry says its own notice directly,
    because it has already decided that question: it writes the member down in
    the same write as the count that ran out, so asking the record afterwards
    would find the step it is about to announce and read its own write as
    somebody else's sentence.
    """
    if _repeats_a_notice(gate, generation, failure):
        return _held_quietly(gate, generation, failure, detail)
    return _announces(gate, generation, failure, detail)


def _announces(
    gate: _records._Gate, generation: _late_models.LateGeneration, failure,
    detail: str = "",
) -> bool:
    """Say this refusal to the thread, and park the issue under it.

    The half of the notice above that is not the announce-once question, split
    out for the one caller that has answered that question already. Nothing
    here asks whether the sentence is owed: reached at all, it is.
    """
    _records_the_notice(gate, generation, failure)
    unmeasured = _UNMEASURED_PARK
    if gate.entry is not None:
        unmeasured = _UNMEASURED_PUBLISHED_PARK
    refused = unmeasured.format(
        mentions=config.HITL_MENTIONS, failure=failure,
    )
    described = _described(failure, detail)
    if described:
        refused = f"{refused}\n\n{described}"
    return _parked(
        gate, _announced(generation, failure), failure, refused, detail,
    )


def _repeats_a_notice(
    gate: _records._Gate, generation: _late_models.LateGeneration, failure,
) -> bool:
    """Whether the thread has already been told THIS about THIS pair.

    Both halves are required and each rules out a different way of swallowing
    a notice nobody has made. The park has to be one somebody is still waiting
    behind and taken over this very pair, which `_stands_over` answers; and
    the step has to be the one that park's own notice named, which only a road
    that announced something ever wrote down. A record that says nothing is a
    pair nobody has been told about, so it is told.
    """
    if not _stands_over(gate, generation):
        return False
    recorded = _late_state.read_late_generation(gate.state)
    return recorded.measurement_failure == failure


def _held_quietly(
    gate: _records._Gate, generation: _late_models.LateGeneration, failure,
    detail: str = "",
) -> bool:
    """Report a refusal a human has already been sent, and tell them nothing.

    Silent to the THREAD and to nothing else. The typed failure goes to both
    sinks here as it does on every other reading that did not happen: the
    published road deliberately re-reads this pair on every poll, so the
    stream is the only place those readings exist at all, and a hold that
    reported none of them would make a pair nobody can measure look
    indistinguishable from one nobody is looking at.

    What the reading LEARNED is written down even here, and one thing can be
    learned past a park: the base's identity. A remote that would not answer
    records no base at all, so the first pass that finally gets an id for one
    is what gives every retry after it an exact object to ask for -- dropped
    here, the next pass asks the remote again and freezes whatever the branch
    has moved to since, which is a different pair under the same generation.

    Nothing else is written and nothing is counted. The bound is spent, so a
    count past it measures nothing, and a record that says what it already
    said is a pinned write bought for no reader.
    """
    log.warning(
        "issue=#%d still cannot measure its committed candidate %s (%s); "
        "holding the tick without a second notice",
        gate.issue.number, generation.candidate_sha, failure,
    )
    if _late_state.read_late_generation(gate.state).base_sha != (
        generation.base_sha
    ):
        _persisted(gate, generation)
    _emit(gate, generation, _events.measurement_failure_event(failure, detail))
    return True


def _records_the_notice(
    gate: _records._Gate, generation: _late_models.LateGeneration, failure,
) -> None:
    """Write the member a notice is about to name, before it is said.

    That order is what makes the notice the only one: every tick is a fresh
    process, so a member said and not written down is one the next poll says
    again, once a poll, for as long as the transport or the checkout stays
    where it is.

    A record already naming it pays no write -- the road that spends the bound
    puts the member down with the count, in the one write that carries both --
    and a refusal that froze no candidate writes nothing at all: a pinned
    cycle with no commit under it freezes nothing, reconciles nothing, and is
    read as a live cycle by the guard that ends one when the issue closes.
    Nothing re-enters such a park either, so there is no second notice for it
    to suppress.
    """
    if not generation.candidate_sha:
        return
    if _late_state.read_late_generation(
        gate.state,
    ).measurement_failure == failure:
        return
    _persisted(gate, _announced(generation, failure))


def _lost_reading(
    gate: _records._Gate, generation: _late_models.LateGeneration, failure,
    detail: str = "",
) -> bool:
    """Count one reading the transport lost, and end the tick either way.

    The bounded road into the park above, taken by the two steps that reach a
    base rather than read one. It is bounded rather than absent because those
    steps clear themselves: a remote that would not answer and a fetch that
    brought nothing back are a network, a token, or a host that was down, and
    the next tick is very often the whole of the fix. Spending a human on the
    first of them spends them on something nobody had to do.

    So a miss inside the bound does exactly one thing -- it goes on the record
    -- and deliberately does nothing else: no `awaiting_human`, no reason, and
    no comment, which leaves the pinned pair exactly as a retry finds it and
    lets the next tick re-enter that same pair on both roads with no agent
    behind it. Past the bound the ordinary park takes it, because a base still
    unreachable that many readings later is not one this process is going to
    reach, and committed work is waiting behind a reading that will not
    happen.

    The count goes down BEFORE anything is reported or said, and that order is
    the bound itself: every tick is a fresh process, so a miss lost to a crash
    in that window is a miss nothing remembers -- and a retry that cannot
    remember is not bounded at all. What is written always names a candidate,
    since both callers reach here holding the pair they froze.

    A park this owner already took OVER THIS PAIR ends the counting outright:
    the bound is spent, the human it asked has been asked, and the reading is
    retried each tick only so the transport coming back settles it without
    one. The reading is still reported, and whether it is also SAID is the
    announce-once guard above rather than this road's: a step that park
    already named is a repeat, and one it did not is a notice nobody has made.
    What clears the park is a reading that succeeds, or the human's own bare
    continue, which drops the reason before the gate is entered and so buys
    exactly one more counted attempt.

    The member that goes on the record is the one a notice NAMED, and the
    reading that spends the bound writes it in the same write as the count:
    the two are one fact -- this reading ran the retries out and is about to
    be said -- so a crash between them would leave a mention nothing could
    tell from a repeat. A quiet miss writes only the count, because it says
    nothing to anybody: the step it stopped at recorded there would be a
    notice the guard thinks was made, and the miss that finally spends the
    bound would find its own step already down and hand the issue over
    without a word.

    A park standing over some OTHER pair is a spent one, and it is retired
    here rather than obeyed. The commonest way to reach one is the opposite
    reply to that continue: a human answers the park with guidance, the
    developer is resumed, and what it commits is a fresh candidate this park
    was never about. Read as this pair's, the miss over that new commit would
    be dropped on the floor -- nothing persisted, nothing reported, and the
    pinned record still naming work the branch has moved past for the next
    tick to reconcile against.
    """
    if _stands_over(gate, generation):
        return _unmeasured(gate, generation, failure, detail)
    # Nobody is waiting on this pair, so no park may outlive the miss about to
    # be counted: a reason standing with its latch already spent -- what a
    # resume leaves -- still freezes the branch out of base sync and still
    # tells every announce-once guard a human has been notified.
    _retire_spent_park(gate.state)
    missed = _one_more_miss(generation, failure)
    announcing = not _retries_quietly(missed, failure)
    if announcing:
        missed = _announced(missed, failure)
    _persisted(gate, missed)
    if announcing:
        return _announces(gate, missed, failure, detail)
    log.warning(
        "issue=#%d could not reach the base its committed candidate %s is "
        "measured against (%s); re-reading the same pair on the next tick "
        "(%d of %d readings lost)",
        gate.issue.number, missed.candidate_sha, failure,
        missed.measurement_miss_count,
        _state._MEASUREMENT_MISSES_BEFORE_PARK,
    )
    _emit(gate, missed, _events.measurement_failure_event(failure, detail))
    return True


def _stands_over(
    gate: _records._Gate, generation: _late_models.LateGeneration,
) -> bool:
    """Whether a human is still waiting on a notice about THIS pair.

    The pair has to be the one the park was taken over, read off the pinned
    record, since a candidate the branch has moved past is work that park was
    never about -- the fresh start owes its own bounded retry rather than
    inheriting one already spent.

    Past that the question is which park this call is standing under, and
    there are two answers because there are two roads in. On the ordinary one
    the park is the record's own: the LATCH says somebody is still waiting,
    not the reason beside it, since a resume consumes the latch and leaves the
    reason standing, and a human who answered with guidance has spent the
    notice they were sent rather than still being owed it.

    The other is a handoff made UNDER a park, and there the flags cannot
    answer at all: the park held across the call is put back after it whatever
    the seam refused for, so a measurement park taken in here never survives
    the tick that took it. What does survive is the member the notice named,
    which is written by the two roads that tell somebody and by nothing else
    -- so under a held park that is the whole of the question, and the
    operator waiting behind the park being restored is the human still owed
    nothing further.
    """
    recorded = _late_state.read_late_generation(gate.state)
    if recorded.candidate_sha != generation.candidate_sha:
        return False
    if _under_a_held_park(gate.state):
        return bool(recorded.measurement_failure)
    if not gate.state.get(_state._AWAITING_HUMAN):
        return False
    return gate.state.get(_state._PARK_REASON) == PARK_MEASUREMENT_FAILED


def _under_a_held_park(state: _pinned_state.PinnedState) -> bool:
    """Whether this call was entered under a park that will be put back.

    Written before the handoff and dropped after it, so it is on the record
    for exactly the calls the rollback covers -- and for the poll after a
    crash inside one, which puts the park back before any gate is entered
    again. One road writes it, under one park: the operator authorization an
    adjudicated candidate is waiting for.
    """
    held = state.get(_state._HELD_PARK)
    return isinstance(held, dict) and bool(held.get(_state._AWAITING_HUMAN))


def _announced(
    generation: _late_models.LateGeneration, failure,
) -> _late_models.LateGeneration:
    """The record a notice naming this step leaves behind.

    The field is what the thread has been TOLD, so it is written by the two
    roads that tell somebody and by nothing else. Read that way it answers the
    only question the retry after it has: does the sentence already on this
    issue cover the step this reading stopped at?
    """
    return replace(generation, measurement_failure=failure)


def _one_more_miss(
    generation: _late_models.LateGeneration, failure,
) -> _late_models.LateGeneration:
    """The record one lost reading leaves, where the bound counts it.

    A step outside the bound is handed on untouched. The count is what says
    how close this pair is to being handed to a human, so a failure nothing
    retries may not spend one of the readings a transport fault is owed.

    The count and nothing beside it. What a quiet miss stopped at is said to
    the log and to both streams and to no human at all, and the member on the
    record is the one a human was TOLD -- so writing this reading's step there
    would leave the announce-once guard reading a notice nobody made.
    """
    if failure not in _TRANSPORT_STEPS:
        return generation
    return replace(
        generation,
        measurement_miss_count=generation.measurement_miss_count + 1,
    )


def _retries_quietly(missed: _late_models.LateGeneration, failure) -> bool:
    """Whether this miss is one the next tick takes again without a human."""
    return (
        failure in _TRANSPORT_STEPS
        and missed.measurement_miss_count
        <= _state._MEASUREMENT_MISSES_BEFORE_PARK
    )


def _reached(
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """The record a base this host really holds leaves: no miss outstanding.

    A freeze that succeeded is what the count exists to be ended by, and the
    end has to be recorded rather than assumed. Carried past it, readings lost
    to a transport that has since recovered would be spent on the next fault
    instead: a pair that lost three of them and then measured would hand the
    issue to a human on the first hiccup after that.

    The count and only it. Reaching the base is not the end of the steps a
    reading can stop at -- the diff still has to be pinned, taken and read --
    and the member beside the count is what a NOTICE named, so dropping it
    here would lose the record of what a human was told on the very tick that
    reaches the base, and the diff failure behind it would be announced afresh
    on every poll for as long as the base stayed reachable. `_measured` is
    where it goes, once the reading it describes has actually happened.
    """
    return replace(generation, measurement_miss_count=0)


def _measured(
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """The record a reading that HAPPENED leaves: nothing outstanding at all.

    The end of every step a measurement can stop at, which is the first point
    a member on this record describes a refusal that is over. So it goes here,
    before the verdict settles on the record -- and the count with it, since
    the same reading ended the row of lost ones.

    Before this and not after: the settlement WRITES this record, and an
    oversized candidate's survives the write to be adjudicated from. Cleared
    afterwards instead, the pinned comment would carry a step a human was told
    about into an adjudication where nothing is refusing anything, and the
    announce-once guard would read it as a sentence still standing on a thread
    whose park was retired by this very verdict.
    """
    return replace(
        generation, measurement_miss_count=0, measurement_failure=None,
    )


def _retire_spent_park(state: _pinned_state.PinnedState) -> None:
    """Drop a measurement park this attempt is the answer to, latch and all.

    The reason is durable and so is the flag beside it, so without this a park
    a fresh reading has superseded travels on -- into the stage the
    publication hands the issue to, where it is state describing a step
    nothing is waiting on.

    Called by the two owners that ANSWER the question it was taken for -- the
    verdict a count settles, and the verdict a commit this workflow already
    decided about needs no count for -- rather than by the gate they sit
    behind. Entering the gate is not an answer: the reading can miss again,
    and a retirement taken on the way in is one a durable write in that window
    makes permanent, leaving an unparked issue whose reading still has not
    happened and whose next miss starts the bound over. Every other exit
    either takes a park of its own with the reason it fails for NOW or leaves
    this one standing because it is still true.

    The LATCH goes with the reason, and it is the half that decides whether
    the reading was worth taking. A reconciliation the dispatcher drives has
    no run behind it to clear the flag, so a pair that measured small would
    retire its record, record the commit as owed a push, and hand the tick to
    a source stage that reads `awaiting_human` and takes its parked road --
    waiting for a reply to a question this very tick answered, while the
    approved commit sits unpushed.

    ONE park is retired here, and every other is left exactly where it
    stands -- a question, a dirty tree, a timeout, and above all the park an
    adjudicated candidate takes when nobody has authorized it. That one is
    waiting on a PERSON rather than on a reading, so nothing a reading does
    answers it: a road that lost the base and is counting a quiet miss would
    unpark an issue whose operator has not replied, and the exemption nobody
    stands behind would publish on the next poll with no authorization
    recorded anywhere. It comes off where a publication under it actually
    happens, and nowhere else.
    """
    if state.get(_state._PARK_REASON) == PARK_MEASUREMENT_FAILED:
        state.set(_state._PARK_REASON, None)
        state.set(_state._AWAITING_HUMAN, False)


def _retire_authorized_park(state: _pinned_state.PinnedState) -> None:
    """Drop the authorization park a publication under it is the answer to.

    The park an adjudicated candidate takes when nobody has authorized it,
    taken down by both of the answers that publish one from under it without
    asking anybody. One is the unmeasured road, where the record answers the
    park's own question -- an override that now covers the commit, or the
    bookkeeping owed for one its own pull request already stands on. The other
    is a fresh count the ceiling lets through, which answers something else
    entirely: nobody's permission was ever needed for a change this size, so
    the candidate is not this park's to hold. Neither reads the thread, so
    nothing else on either would take the flag off, and a published commit
    would leave an issue still saying a human is holding it, with the source
    stage's parked road stopping on every poll after.

    Retired where the publication is DECIDED rather than on the way into the
    gate, which is the whole of what keeps it apart from the measurement park
    beside it. What this park waits for is a person, and no reading answers a
    person: a tick that lost the base, or one a close ends, would otherwise
    unpark an issue whose operator has not replied, and the exemption nobody
    stands behind would publish on the next poll under nobody's authority at
    all.
    """
    if state.get(_state._PARK_REASON) == _command.PARK_UNAUTHORIZED_EXEMPTION:
        state.set(_state._PARK_REASON, None)
        state.set(_state._AWAITING_HUMAN, False)


def _retire_settled_park(
    state: _pinned_state.PinnedState, recorded: _late_models.LateGeneration,
) -> bool:
    """Drop a measurement park a settled split's own record provoked.

    True where one was standing, so the caller knows it owes the write. Left
    to the caller for the reason `_retire_spent_park` leaves it there: the
    tick that clears a park has its own write to ride out on, and this domain
    does not put two where one will do.

    The park is this domain's, and on a record whose candidate has already
    become children it is this domain's own false positive: the group the
    retirement keeps is there for the releases and the branch delete the
    umbrella still owes, not for a reading anybody is waiting on. Left
    standing it is an issue reading as parked for a human with nothing for a
    human to answer -- and the reason is durable, so the pre-tick base refresh
    goes on holding the branch it names for as long as the flag does.

    Only the measurement park is retired, for the reason every other
    retirement of it gives: a question, a rejected child, or a child somebody
    closed by hand is a park with an answer still owed, and this record says
    nothing about any of them.
    """
    if not recorded.split_has_settled:
        return False
    if state.get(_state._PARK_REASON) != PARK_MEASUREMENT_FAILED:
        return False
    _retire_spent_park(state)
    return True


def _retire_superseded_park(state: _pinned_state.PinnedState) -> None:
    """Drop a park the adjudication is taking the issue out of.

    A hold hands every later tick to the late coordinator, and what the issue
    is waiting on from that moment is a verdict rather than whatever the park
    asked a human about. Left standing the flag reaches the coordinator as an
    issue already parked -- its own parked dispatch fires on a mention nobody
    made about the question now open -- and the reason beside it describes a
    step no one is retrying. Every road into a hold either had no park or has
    one this hold supersedes, so the clear is unconditional.
    """
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)


def _recorded_candidate(state: _pinned_state.PinnedState) -> str:
    """The commit this issue's record names, or "" where none does.

    Published for the disposition beside this owner, which needs the floor a
    park left on the branch: commits already there when a resumed run started
    are not that run's, and reading them as its own would publish work an
    agent's clarifying question was asked INSTEAD of.
    """
    return _late_state.read_late_generation(state).candidate_sha


# Everything one standing debt goes down as, taken as one group: the commit a
# push is owed for, the head that push is pinned to, and the grounds the debt
# rests on. Spelled once so the reader that refuses a half-written group and
# the write that ends one cannot come to disagree about what the group is.
_APPROVAL_KEYS = (
    _state._APPROVED_SHA, _state._APPROVED_LEASE, _state._APPROVED_BASIS,
)


def _approved_commit(state: _pinned_state.PinnedState) -> str:
    """The commit an approval owes a publication for, or "" where none does.

    Published for every owner that has to know a commit is already DECIDED.
    An approval -- the retirement a small candidate earns, the exemption a
    `single` verdict records -- drops the generation that named the commit
    and licenses a push that has not run yet, so between the two this is what
    says which commit the issue is still waiting on. Read fail-closed like
    every other late commit field: only a whole object id is one, so a
    hand-edited value is no approval rather than an unmeasured publication.
    """
    return _payloads.as_hex(
        state.get(_state._APPROVED_SHA), _formats.COMMIT_LENGTHS,
    ) or ""


def _approved_lease(state: _pinned_state.PinnedState) -> str:
    """The head a published approval was frozen against, or "" where none was.

    The other half of an approval taken on the published side, and the half
    the retry after a failed push cannot re-derive: the generation that froze
    the pull request's head was retired by the write that approved the
    commit, and re-reading the pull request answers with wherever it has
    moved to since. Read fail-closed like every other late commit field.

    Empty is the ordinary answer and means a pre-publication approval -- what
    every implementing-seam approval is -- whose push correctly takes its own
    reading of the remote.
    """
    return _payloads.as_hex(
        state.get(_state._APPROVED_LEASE), _formats.COMMIT_LENGTHS,
    ) or ""


def _approved_basis(state: _pinned_state.PinnedState) -> str:
    """What the standing approval rests on, or "" where the record cannot say.

    Read fail-closed like every other late field: only a value this build's
    own vocabulary carries reads back, so a hand edit and a spelling from
    somewhere else are both "no basis" rather than a basis nothing checked.

    "" is also what an approval an older binary wrote reads back as, which
    carried no basis at all -- and a reader that acts on the two ALIKE is the
    one thing this may not be used for. `_unreadable_basis` beside it is what
    tells them apart, because only the absent one earns the compatibility.
    """
    written = state.get(_state._APPROVED_BASIS)
    if written in tuple(LateApprovalBasis):
        return str(written)
    return ""


def _unreadable_basis(state: _pinned_state.PinnedState) -> bool:
    """Whether the record CARRIES a basis this build cannot read.

    Presence and truth asked together, because the answer is the gap between
    them, and it is a gap a reader has to act on differently at each end. An
    approval an older binary wrote carries no field at all: there the
    exemption beside it is the only evidence there ever was, and reading it is
    the compatibility this domain owes live issues. One whose field a hand
    edit or a half-written crash left unreadable is the opposite record -- it
    CLAIMS grounds and cannot say which -- and reading that as the absence
    above hands a bypass to the one shape an attacker or an accident reaches
    by touching the single field the fallback turns on.

    So this is what the readers key the fail-closed road on, and the absence
    keeps the fallback to itself. `None` is asked beside the key because the
    payload is JSON and a field can be present and null, which is an older
    binary's value or a hand edit and is an absence either way.
    """
    if not state.carries(_state._APPROVED_BASIS):
        return False
    if state.get(_state._APPROVED_BASIS) is None:
        return False
    return not _approved_basis(state)


def _unreadable_approval(state: _pinned_state.PinnedState) -> bool:
    """Whether this comment CLAIMS a debt it cannot show whole.

    Presence rather than truth, and the question a caller asks before it acts
    on a debt having been PAID. The readers above answer "nothing owed" for a
    group a hand edit or a half-written crash left unreadable exactly as
    readily as for one the write that pays a debt blanked -- which is the
    right answer for a road deciding whether to spend an approval, and the
    wrong one for a road deciding whether the write that should have settled a
    publication landed at all. Read as the absence, a group standing over a
    commit nobody can name would pass as a debt somebody paid.

    Three shapes count, and each is the group disagreeing with itself. A
    member carrying something beside a commit this build cannot read is one:
    the debt names no commit and the record is still claiming one. A lease
    present that is not a commit is another, since the head a published
    approval was frozen against is what its retry is pinned to and a value
    nothing can read is no pin. And a basis the record carries and cannot name
    is the third, on the terms `_unreadable_basis` beside it already states.

    False for the ordinary comment, which carries a group of nulls: the write
    that ends a debt blanks these fields rather than removing them, so all
    three absent is the record nobody wrote.
    """
    if all(state.get(key) is None for key in _APPROVAL_KEYS):
        return False
    if not _approved_commit(state):
        return True
    leased = state.get(_state._APPROVED_LEASE) is not None
    if leased and not _approved_lease(state):
        return True
    return _unreadable_basis(state)


def _approve(
    state: _pinned_state.PinnedState,
    candidate_sha: str,
    lease: str,
    basis: LateApprovalBasis | str | None,
) -> None:
    """Record the commit a publication is owed, what pins it, and its grounds.

    The three are written together because they are spent together and mean
    nothing apart: a lease with no approval names a head nobody owes a push
    for, an approval whose lease was dropped is the one that force-pushes over
    whatever the pull request has become, and one whose basis was dropped is a
    debt a later tick has to GUESS the provenance of -- which is the guess
    that publishes an adjudication's debt as though this gate had counted it.

    The basis is handed in rather than derived, because the owner granting an
    approval is the only one that knows: the records standing around it are
    the same on every road, and a reader can tell them apart only if the
    writer said so.

    `None` is a caller that has an approval to re-record and NO grounds to
    record for it, which is the shape an older build left. It goes down as an
    absence rather than as a value, because the two say opposite things to the
    reader: a basis names a decision, while an absence hands the question to
    the exemption beside it -- and a caller inventing one here would answer a
    question it was never in a position to.

    A bare string is the third of those and is written back unchanged: a
    caller carrying forward a basis this build cannot read is preserving the
    record's own claim to grounds it cannot name, which the readers fail
    closed on. Turned into either of the two above it would become a decision
    nobody made or an absence the exemption answers for.
    """
    state.set(_state._APPROVED_SHA, candidate_sha)
    state.set(_state._APPROVED_LEASE, lease or None)
    state.set(_state._APPROVED_BASIS, None if basis is None else str(basis))


def _owes_a_publication(
    state: _pinned_state.PinnedState, candidate_sha: str,
) -> None:
    """Record that this commit is owed a push, on whatever grounds it has.

    The write for a caller holding one commit and no lease, which is the
    implementing seam: nothing froze a publication head there because there is
    no pull request yet, and the push that opens one reads the remote for
    itself. The gate's own debt writer declines for exactly that reason, so
    this seam mints its own -- and it has two callers, since the publication
    that normally does it is skipped whenever the checkout stopped being the
    commit that was approved.

    The grounds are CARRIED where an approval already stands for this very
    commit, since nothing about a checkout that moved changes what the
    publication was allowed on -- and an approval that never said what it
    rested on is carried as saying nothing, not upgraded. An older build wrote
    exactly that shape, and what a reader owes it is the exemption beside it
    rather than a claim this write invented: turned into `unmeasured` here, a
    legacy record would stop being read as unknown and become debt this
    workflow owns, which is a bypass nobody would ever revalidate.

    Where no approval stands for the commit, the grounds are the record's.
    The exemption CLAIM decides -- presence, not readability, since a field a
    hand edit truncated still says an adjudication happened and only fails to
    say which commit -- so a comment carrying one leaves the adjudication's
    debt, to be revalidated like every other debt a human's gesture is behind.
    A comment carrying none leaves `unmeasured`, which is what every road
    reaching here on such an issue is: a receipt the remote already carries, a
    permit, a candidate the switch kept out of the gate -- records this
    workflow made for itself and re-derives on the next tick, so each answers
    for its own bypass.

    The whole group goes down either way rather than the commit alone. A
    commit with a lease left over from some other attempt beside it is the
    pair disagreeing with itself, which the reconciliation ahead of the next
    handler reads as damage.
    """
    if _approved_commit(state) == candidate_sha:
        _approve(state, candidate_sha, "", _standing_basis(state))
        return
    _approve(state, candidate_sha, "", _minted_basis(state))


def _minted_basis(state: _pinned_state.PinnedState) -> LateApprovalBasis:
    """What a debt this seam mints for a commit no approval names rests on.

    Read off the exemption CLAIM rather than off the commit it names, and
    conservatively: an issue that never entered an adjudication carries no
    such field, while one whose field is unreadable carries the claim that one
    happened and no way to say what it was about. Read alike, the second is
    how an adjudication's publication debt comes to be recorded as this
    workflow's own -- the one write a later reader spends without asking
    anybody.

    What the conservative answer costs is a measurement on an issue whose
    adjudication is long over and whose candidate this gate really did admit
    for itself. What the other answer costs is the bypass.
    """
    if state.carries(_exemption.LATE_EXEMPT_SHA):
        return LateApprovalBasis.ADJUDICATION
    return LateApprovalBasis.UNMEASURED


def _standing_basis(
    state: _pinned_state.PinnedState,
) -> LateApprovalBasis | str | None:
    """What the standing approval rests on, exactly as the record holds it.

    The debt a caller re-records is the one that was already there -- the same
    commit, now the head the pull request stands on -- so what it rests on is
    whatever granted it. Carried forward rather than re-decided, since nothing
    about a checkout that stopped being what went out changes the grounds a
    publication was allowed on.

    None where the record never said, which is the shape an older build left
    and the one the exemption beside it answers for. Answered `unmeasured`
    instead, an unknown would be promoted to a decision nobody made: the
    reader would stop falling back, and a legacy `late_approved_sha` standing
    over the very commit an exemption names would read as debt this workflow
    owns and be spent without anybody being asked.

    A value this build cannot read is handed back VERBATIM rather than as
    either of those. It is neither a decision nor an absence -- it is a record
    claiming grounds it cannot name -- and the readers fail closed on exactly
    that shape. Rewritten as an absence here, one carry-forward would launder
    the damage into the legacy road and the next tick would spend the debt
    without asking anyone.
    """
    standing = _approved_basis(state)
    if standing:
        return LateApprovalBasis(standing)
    if _unreadable_basis(state):
        return state.get(_state._APPROVED_BASIS)
    return None


def _forget_approval(state: _pinned_state.PinnedState) -> None:
    """Drop a debt that is paid, superseded, or being adjudicated instead.

    What the route still owed goes with it. Those obligations outlive the
    generation that froze them only so the tick that finally lands this commit
    can close them; past that push there is nothing left to close, and a group
    left standing would be restored by the next approval on this issue and
    applied to a round it was never owed for.
    """
    for key in _APPROVAL_KEYS:
        state.set(key, None)
    _late_state.write_late_spends(state, ())


def _spends_a_held_reading(state: _pinned_state.PinnedState) -> None:
    """Consume the thread to the boundary a publication handoff staged.

    The other half of what an authorization handoff leaves in flight, and it
    is spent HERE -- in the write that ends this stage's hold on the issue --
    for the reason the park beside it is dropped here. Past that write nothing
    under the new label spends what implementing left behind and this stage
    never sees the issue again, so a boundary applied after the call is one a
    crash in that window loses for good.

    What it answers is a command the seam published on without ever reading
    the thread: a candidate the ceiling now lets through settles on its own
    count, and one an authorization already on the record covers publishes as
    decided. Neither consumes the reply that ended the park, and a reply left
    above the watermark is read on the next stage as somebody's fresh
    feedback -- a developer paid to answer a command nothing there can act on,
    over an implementation that is already published.

    Never past what that reading LOOKED at, which is what the boundary
    records: a tick consuming past whatever the tip has become since would
    swallow a reply posted in between, a retraction of the very command being
    published on included.

    Dropped whether it was spent or not. A boundary already behind the
    watermark is one the seam consumed for itself on the road that reads the
    thread, and one left standing would be applied to whatever this issue
    parks over next.
    """
    boundary = _payloads.as_identity(state.get(_state._HELD_COMMAND))
    state.set(_state._HELD_COMMAND, None)
    if boundary is None:
        return
    reached = _payloads.as_identity(
        state.get(_state._LAST_ACTION_COMMENT_ID),
    ) or 0
    if boundary <= reached:
        return
    log.info(
        "issue candidate published under an authorization the seam never "
        "read; consuming the thread to %d so the command is not taken for "
        "fresh feedback on the stage this issue moves to", boundary,
    )
    state.set(_state._LAST_ACTION_COMMENT_ID, boundary)


def _published_commit(state: _pinned_state.PinnedState) -> str:
    """The commit this stage last pushed, or "" where none was.

    Published beside the approval for the owner that has to tell a candidate
    nobody has ruled on from one this stage already put on a pull request. The
    two are the same window read from its two ends: the approval says a push
    is owed, and this says one was made, so between the push and the relabel
    the second is what says the size question has been answered AND acted on.
    Read fail-closed like every other late commit field, so a hand-edited
    value is no publication rather than an unmeasured one.
    """
    return _payloads.as_hex(
        state.get(_state._PUBLISHED_SHA), _formats.COMMIT_LENGTHS,
    ) or ""


def _published_lease(state: _pinned_state.PinnedState) -> str:
    """The head the recorded publication replaced, or "" where none is named.

    What scopes the receipt beside it to one publication attempt. A receipt is
    never cleared, so on its own it goes on naming a commit this stage pushed
    rounds ago and answers "this tick's push landed" for any pull request
    somebody rewound onto it. The head it REPLACED is the fact that dates it,
    and a caller that froze its own head is what compares the two.

    Read fail-closed like every other late commit field, and empty is a
    receipt that vouches for no moved head at all -- an initial publication,
    which froze no head, or one written before this pair was recorded.
    """
    return _payloads.as_hex(
        state.get(_state._PUBLISHED_LEASE), _formats.COMMIT_LENGTHS,
    ) or ""


def _recorded_pull_request(state: _pinned_state.PinnedState) -> int:
    """The pull request this ISSUE records, or 0 where none is readable.

    The publication a stage is working on, as against the one a receipt is
    about: the two agree on every ordinary tick and the receipt's own is what
    a landed push is proved by. This is for the caller that has to say which
    pull request it is PROVING against and holds no frozen entry to read one
    off -- the squash resume, and the accepted settlement whose reconciliation
    proved this very number on its way in.

    Read fail-closed like every other late identity.
    """
    return _payloads.as_identity(state.get(_state._PR_NUMBER)) or 0


def _published_pull_request(state: _pinned_state.PinnedState) -> int:
    """The pull request the recorded publication went onto, or 0 for none.

    The third member of the receipt group, and the one the bookkeeping behind
    a landed push is bound by: the commit says what reached a remote, the head
    it replaced dates that to one attempt, and this says which pull request
    now carries it.

    Read fail-closed like every other late identity, so a hand-edited or
    truncated value is no pull request rather than one nothing checked. What a
    reader does with 0 is refuse -- there is no second place to look that is
    not a search, and a search by branch answers with whatever is open on the
    ref rather than with the publication this receipt is about.
    """
    return _payloads.as_identity(state.get(_state._PUBLISHED_PR)) or 0


def _claims_a_value(state: _pinned_state.PinnedState, key: str) -> bool:
    """Whether the record CARRIES something at `key` rather than an absence.

    `None` and `""` are the only two values read as an absence, and they are
    named rather than tested for falsehood. The payload is JSON, so a field
    can hold anything a hand edit or a half-written crash leaves -- `false`,
    `0`, `[]`, `{}` -- and every one of those is falsy in Python while being
    exactly the damage the reader below exists to catch. Written as "empty
    means absent" that refusal is bypassed by the shapes nobody wrote on
    purpose, which is the one set it most has to answer for.
    """
    if not state.carries(key):
        return False
    written = state.get(key)
    return written is not None and written != ""


# The publication receipt group, in the order a refusal names its members:
# the commit that reached a remote, the head that push replaced, and the pull
# request it went onto. Each is read fail-closed by the owner beside it, so a
# member that CARRIES a value and reads back empty is one this build cannot
# use -- which is the gap `_damaged_receipt` is the whole of.
_RECEIPT_GROUP = (
    (_state._PUBLISHED_SHA, _published_commit),
    (_state._PUBLISHED_LEASE, _published_lease),
    (_state._PUBLISHED_PR, _published_pull_request),
)


def _damaged_receipt(state: _pinned_state.PinnedState) -> str:
    """Which member of the receipt group claims a publication it cannot name.

    Asked of all three at once, because the three are ONE record: `_record_
    publication` writes every member on every receipt and clears every member
    on none, so a group that reads back partial is not a record with a gap in
    it but one nothing here produced. Every other reader in this domain is
    fail-CLOSED and so reads a partial group as an absence -- right for one
    deciding "may this commit publish", and exactly wrong for one deciding
    whether the record is SOUND. Told "no receipt", that second reader
    measures the candidate and publishes: the branch is force-pushed, a second
    pull request is opened over whatever the first may already carry, and the
    write behind that push puts a fresh group down over the damaged one, which
    destroys the evidence an operator would have repaired it from.

    Three shapes are damage, and `_missing_member` and `_unusable_member`
    below own them in that order. A KEY that is not there while its siblings
    are is the first, and telling it from the `null` an initial publication
    writes is the whole reason presence is asked of every member rather than
    of the commit alone: the write puts all three keys down, so one that has
    gone is a hand edit or a half-written record and the group can no longer
    say what it is about. A member that carries a VALUE this build cannot read
    is the second, and it is named so the park can tell a human which field to
    repair. An ORPHAN is the third -- a lease or a pull request with no
    readable commit beside it, which claims this stage published and cannot
    say what.

    An empty MEMBER is not damage where its key is there: `null` is what an
    initial publication records for the head it froze none of, and what an
    install writing no identity records for the number. The delivery proof
    refuses the second on its own terms, with a remedy of its own.

    Answers with the member to repair, and "" for a group that is whole and
    for an issue that never published at all.
    """
    return _missing_member(state) or _unusable_member(state)


def _missing_member(state: _pinned_state.PinnedState) -> str:
    """The member whose KEY is gone while the rest of the group is there.

    Presence alone, which is the one question the value readers cannot ask:
    a member holding `null` and a member that is not on the comment read back
    identically to every one of them, and only the first is something a write
    of this build's ever produced.

    "" for a record carrying no member at all, which is an issue that never
    published and has nothing to be partial about.
    """
    present = [member for member, _ in _RECEIPT_GROUP if state.carries(member)]
    if not present:
        return ""
    absent = [
        member for member, _ in _RECEIPT_GROUP if member not in present
    ]
    return absent[0] if absent else ""


# The two members a group that claims anything has to fill. A publication is
# a commit that reached a remote and the pull request that now carries it, and
# neither is derivable from the other: a receipt with no commit cannot say
# what was published, and one with no number leaves the recovery behind it a
# branch to search rather than an identity to prove. The LEASE is not among
# them -- an initial publication froze no head, records `null`, and is the
# commonest sound group there is.
_REQUIRED_MEMBERS = (_state._PUBLISHED_SHA, _state._PUBLISHED_PR)


def _unusable_member(state: _pinned_state.PinnedState) -> str:
    """The member of a whole group that cannot say what it claims to.

    Two shapes over the same gap between "carries a value" and "carries one
    this build can use". A member holding something no reader here will type
    answers for itself. And a group that claims ANYTHING while one of the two
    members a publication is named by stands empty answers with the member it
    is missing: a lease or a number with no commit beside it claims this stage
    published and cannot say what, and a commit with no number cannot say
    where it went -- which leaves every reader behind it a lookup by branch,
    and that answers with whatever is open on the ref.

    An empty LEASE is sound, and is why the two are named rather than the
    whole group being required: the initial publication froze no head to be
    pinned to and records none.
    """
    unreadable = [
        member for member, read_member in _RECEIPT_GROUP
        if _claims_a_value(state, member) and not read_member(state)
    ]
    if unreadable:
        return unreadable[0]
    claimed = [
        member for member, _ in _RECEIPT_GROUP
        if _claims_a_value(state, member)
    ]
    if not claimed:
        return ""
    missing = [
        member for member in _REQUIRED_MEMBERS if member not in claimed
    ]
    return missing[0] if missing else ""


def _publication_from(
    state: _pinned_state.PinnedState, head: str, pull_request: int,
) -> str:
    """The commit recorded as pushed FROM this head onto this pull request.

    The whole receipt group asked as the one question every caller of it
    actually has: is the publication this record names the one I am about to
    act on? No member answers it alone. A receipt is never cleared, so by
    itself it goes on naming a commit this stage pushed rounds ago and vouches
    for any pull request somebody rewound onto it; a head with no receipt
    beside it names no push at all; and the two together still say nothing
    about WHICH publication received the commit -- so a branch that has been
    pushed from this head before, onto a pull request since closed and
    replaced, answers yes to both.

    All three date one push to one attempt, and the caller supplies both of
    the facts it is proving against: the head it froze, and the pull request
    it froze that head on. A receipt naming another number is an earlier
    publication of this issue's, and one naming none is a record this build
    cannot tie to any publication at all -- both answer "" rather than being
    taken at their word, since what the answer licenses is a carve-out from
    the refusal that catches somebody else's branch move.

    A caller with no head of its own is claiming nothing here, and gets "".
    """
    if not head or _published_lease(state) != head:
        return ""
    if not pull_request or _published_pull_request(state) != pull_request:
        return ""
    return _published_commit(state)


def _record_publication(
    state: _pinned_state.PinnedState,
    published: str,
    superseded: str,
    pull_request: int = 0,
) -> None:
    """Record the commit a push put on the remote, and the head it replaced.

    The pair is written together for the reason the approval's is, and the
    danger is the mirror image: a receipt whose head was dropped is the one
    that vouches for a publication somebody else moved, so the second half is
    written on EVERY receipt -- cleared where there is no head to name rather
    than left for the next receipt to inherit from the last.

    The pull request travels with them for the same reason and answers the
    question neither of them does: which publication now carries the commit.
    Left to the relabel that records `pr_number`, it is missing for exactly
    the window the receipt exists for -- a push that landed and a process that
    died before that write -- and a reader with no identity there falls back
    to a lookup by branch, which a replacement somebody opened over the same
    ref satisfies. Cleared with the rest where a caller names none, never
    inherited from the receipt before.
    """
    state.set(_state._PUBLISHED_SHA, published)
    state.set(_state._PUBLISHED_PR, pull_request or None)
    state.set(_state._PUBLISHED_LEASE, superseded or None)


def _persisted(
    gate: _records._Gate, generation: _late_models.LateGeneration,
) -> None:
    """Write the generation this step reached, and the state around it.

    What the caller's hold owes rides the same write, because the freeze is
    durable and the count that follows it is not: a tick that dies in between
    leaves a pair for the reconciliation ahead of the next handler to answer,
    and that tick has no run behind it to re-derive a reviewer round, a
    cleared bookmark, or a stage tail from. Written after the generation and
    inside its own key group, so the retirement that ends the pair drops it in
    the same write.

    Only while the pair still AWAITS its count, which is exactly the window it
    pays for. A record carrying a number has been answered -- the routed hold
    that carries it spent this on the way past -- and rewriting it there would
    leave a spent claim on the comment for a later reader to apply twice.

    A measurement park the new record moves PAST goes out in this same write,
    because the two are read as one afterwards: a later tick asks whether the
    park standing is the one this pair was parked for, and answers by
    comparing it against the recorded candidate. Left to the verdict alone,
    the window between this write and that one is a crash away from a park
    taken over one commit sitting beside a record naming another -- which the
    next tick reads as that pair's own, holding every later reading of it
    silently, counting none of them, and never reaching the notice a human is
    owed. Bound here, the comment can never say two things at once.
    """
    _unbound_park(gate.state, generation)
    _late_state.write_late_generation(gate.state, generation)
    if generation.additions is None:
        _late_state.write_late_spends(gate.state, gate.spends.fields)
    gate.gh.write_pinned_state(gate.issue, gate.state)


def _unbound_park(
    state: _pinned_state.PinnedState, generation: _late_models.LateGeneration,
) -> None:
    """Retire a measurement park the record being written moves past.

    Only a park over some OTHER candidate: one taken over the pair still being
    written is exactly the park that has to survive, since the reading it was
    taken for still has not happened. A record that names no candidate at all
    is no claim about which pair is parked, so it leaves the park alone.
    """
    if not generation.candidate_sha:
        return
    if state.get(_state._PARK_REASON) != PARK_MEASUREMENT_FAILED:
        return
    if _late_state.read_late_generation(state).candidate_sha == (
        generation.candidate_sha
    ):
        return
    _retire_spent_park(state)


def _emit(
    gate: _records._Gate,
    generation: _late_models.LateGeneration,
    event: _events.LateEvent,
) -> None:
    """Report one late event from the stage the measurement happened in.

    Which stage that is comes off the entry the call was taken on rather than
    off this package's own name: the same gate runs at the seam that publishes
    a pull request for the first time and at the one that pushes to a pull
    request the remote already carries, and a record filed under
    `implementing` for a reading taken in `fixing` would put a measurement in
    a stage no developer of it ever ran under.
    """
    stage = _state._IMPLEMENTING_STAGE
    if gate.entry is not None:
        stage = gate.entry.stage
    _telemetry.emit_late_event(gate.gh, event, generation, stage=stage)


def _answers_the_measurement_park(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState,
) -> list:
    """The bare continues a human has written on a measurement park, if any.

    Empty for everything else, and each exclusion is its own answer. An issue
    parked for another reason is not this park's to retry; a thread with
    nothing new on it is a human who has not replied yet; and a reply carrying
    real words is guidance, which belongs to the ordinary resume that feeds it
    to the developer rather than to a reading taken behind their back.

    A bare `/orchestrator continue` is the one reply that means "the step you
    could not take, take again": the failure was a reading rather than a
    question, so what it earns is the same pair measured once more and no
    agent at all.

    Which batch that is, the reader below decides -- so the two roads that
    would otherwise spend one of these answer the same question off the same
    shape of read, and a command landing between two of them is deferred to
    the poll that can act on it rather than consumed by one that cannot.
    """
    if state.get(_state._PARK_REASON) != PARK_MEASUREMENT_FAILED:
        return []
    if not state.get(_state._AWAITING_HUMAN):
        return []
    replies = _github_comments.filter_trusted(
        gh.comments_after(issue, state.get(_state._LAST_ACTION_COMMENT_ID)),
    )
    return replies if _reserved_for_the_measurement_park(replies, state) else []


def _reserved_for_the_measurement_park(replies: list, state) -> bool:
    """Whether this batch is one only this park's own road may consume.

    Every road that reads a parked thread reads it again after the road above
    it handed the tick back, and the time in between is time an operator can
    write in. A bare continue landing there is in a later road's batch and in
    nobody else's, and both of the roads behind this one would SPEND it: the
    parked-continue classifier reads a command on a park that is not a session
    failure as one carrying no answer, refuses it, and consumes the thread
    past its own refusal; the generic resume reads it as guidance, pays for a
    developer to answer it, and consumes it too. Either way the operator's
    retry is gone and the reading they asked for is one nothing will ever
    take.

    So while this park stands, a batch this road would act on belongs to it,
    and the two behind it hand the whole TICK back rather than sparing the one
    reply. A watermark is one number and neither of them is the last thing to
    move it: the run a resume starts parks, and that park stamps the thread
    read to the notice it posts, which lands above the command and takes it.
    Deferred entire, nothing is lost -- the next poll reads the same batch and
    re-measures the pair on it.

    ALL of them, which is this park's own rule rather than the last-reply one
    the authorization command is read by. A reading is retried by a reply that
    asks for nothing else; a batch carrying real words is guidance, and the
    ordinary resume feeding it to the developer is exactly what it is owed.

    Asked only while the park is standing, and only of a batch read the way
    this owner reads one. A comment of ours above the watermark is in that
    read, so it is in this one: reserved off a narrower batch, a tick would
    defer what the road it deferred to then refuses, and the two would hand
    the same thread back and forth forever.
    """
    if state.get(_state._PARK_REASON) != PARK_MEASUREMENT_FAILED:
        return False
    if not state.get(_state._AWAITING_HUMAN):
        return False
    if not _messages._parse_orchestrator_continue(replies):
        return False
    return all(
        _messages._is_bare_orchestrator_continue(reply) for reply in replies
    )
