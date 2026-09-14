# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hold failed measurements, retry transport misses quietly, and announce each standing failure once.

The recorded candidate and failure determine whether a notice is owed.
A changed frozen base is persisted even while a repeat stays quiet, and
the retry bound determines when a new transport failure becomes a park.
An unreadable candidate retains any resolved object id so its retry stays
bound to the same work.
"""
from __future__ import annotations

import logging

from orchestrator.config import settings as config
from orchestrator.git.measurement import (
    models as _measurement,
)
from orchestrator.workflow.late_split import (
    events as _events,
    models as _late_models,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_measurement_state as _late_measurement_state,
    late_park_notices as _late_park_notices,
    late_park_retirement as _late_park_retirement,
    late_park_state as _late_park_state,
    late_records as _records,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

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


def _unmeasured(
    gate: _late_gate_models._Gate, generation: _late_models.LateGeneration, failure,
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
    gate: _late_gate_models._Gate, generation: _late_models.LateGeneration, failure,
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
    described = _late_park_notices._described(failure, detail)
    if described:
        refused = f"{refused}\n\n{described}"
    return _late_park_notices._parked(
        gate, _late_measurement_state._announced(generation, failure), failure, refused, detail,
    )


def _repeats_a_notice(
    gate: _late_gate_models._Gate, generation: _late_models.LateGeneration, failure,
) -> bool:
    """Whether the thread has already been told THIS about THIS pair.

    Both halves are required and each rules out a different way of swallowing
    a notice nobody has made. The park has to be one somebody is still waiting
    behind and taken over this very pair, which `_stands_over` answers; and
    the step has to be the one that park's own notice named, which only a road
    that announced something ever wrote down. A record that says nothing is a
    pair nobody has been told about, so it is told.
    """
    if not _late_measurement_state._stands_over(gate, generation):
        return False
    recorded = _late_state.read_late_generation(gate.state)
    return recorded.measurement_failure == failure


def _held_quietly(
    gate: _late_gate_models._Gate, generation: _late_models.LateGeneration, failure,
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
        _late_park_state._persisted(gate, generation)
    _late_park_notices._emit(gate, generation, _events.measurement_failure_event(failure, detail))
    return True


def _records_the_notice(
    gate: _late_gate_models._Gate, generation: _late_models.LateGeneration, failure,
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
    _late_park_state._persisted(gate, _late_measurement_state._announced(generation, failure))


def _lost_reading(
    gate: _late_gate_models._Gate, generation: _late_models.LateGeneration, failure,
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
    if _late_measurement_state._stands_over(gate, generation):
        return _unmeasured(gate, generation, failure, detail)
    # Nobody is waiting on this pair, so no park may outlive the miss about to
    # be counted: a reason standing with its latch already spent -- what a
    # resume leaves -- still freezes the branch out of base sync and still
    # tells every announce-once guard a human has been notified.
    _late_park_retirement._retire_spent_park(gate.state)
    missed = _late_measurement_state._one_more_miss(generation, failure)
    announcing = not _late_measurement_state._retries_quietly(missed, failure)
    if announcing:
        missed = _late_measurement_state._announced(missed, failure)
    _late_park_state._persisted(gate, missed)
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
    _late_park_notices._emit(gate, missed, _events.measurement_failure_event(failure, detail))
    return True


def _unnameable(
    gate: _late_gate_models._Gate,
    recorded: _late_models.LateGeneration,
    candidate: _measurement.FrozenCommit,
) -> _late_gate_models._GateVerdict:
    """Park a candidate nobody could freeze, under the id it did name.

    A reading can fail with an id in hand, and the commonest one does: a
    revision that resolved and would not peel -- an object a prune took, or
    work made on a host this one is not -- comes back carrying the id it
    resolved to. That id is the only record of which commit the attempt was
    about, so it goes down with the park rather than being reported and
    dropped. Recorded, the retry asks for that exact object, the pre-tick base
    refresh holds the branch still around it, and the reconciliation ahead of
    the next spawn proves it before anything runs. Reported and dropped, none
    of those three has anything to act on: the branch is rebased under the
    park and the next reading proves whatever the checkout points at by then,
    which is how base or somebody else's work is measured and published as
    this issue's implementation.

    A revision that would not resolve at all names nothing, and there the park
    itself is the record: no pair was frozen, so nothing may be reconciled
    against one and the retry says so rather than taking a first reading of a
    head it cannot tie to this issue.
    """
    named = _records._named(gate, recorded, candidate.sha)
    if named.candidate_sha and named.candidate_sha != recorded.candidate_sha:
        _late_park_state._persisted(gate, named)
    _unmeasured(gate, named, candidate.failure, candidate.detail)
    return _late_gate_models._HELD
