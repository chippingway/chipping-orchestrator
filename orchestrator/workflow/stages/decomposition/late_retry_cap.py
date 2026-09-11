# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The spent-budget park a late adjudication meets, and what lifts it.

A late adjudication spends the same per-issue day of tokens every other agent
run does, so the gate in front of its fresh spawn is the shared one on
`workflow/engine/retry_budget.py`. What is here is the half that gate
deliberately does not own: the park a refusal takes, the sentence it owes the
thread, and the one reply that buys another attempt.

The park is staged through this mode's own park owner rather than through
the shared parking form beside the gate. That is not a preference: everything
a late tick holds is durable state under a live generation -- the frozen pair,
the phase the record reached, the hold standing on the pull request the
candidate is on, the locked run and whatever verdict it recorded -- and the
shared form writes pinned state itself, on its own schedule, with none of that
in hand. Staged here, the park rides the write the generation rides, and what
the thread is owed rides it too (`late_park_notice`), which is what gives this
refusal the same persist-before-effect delivery, failed-delivery retry, and
post-crash reconciliation every other late park has.

Nothing supersedes it. The parks a late attempt retires are the ones a retry
answers -- a hold that failed is reconciled again, a worktree that was gone is
back -- and a budget nobody has renewed is answered by neither. So the park is
asked at the top of the adjudication, ahead of the evidence probe, the hold,
and the content settlement, and while it stands the tick ends there having
written nothing, spawned nothing, and said nothing. What that keeps is
everything the issue arrived with: the generation and its frozen candidate,
the pull request still wearing the adjudication notice, the pinned run, the
recorded result, and the fingerprints the next content read is measured
against.

The one thing that lifts it is a trusted `/orchestrator continue`: the renewal
the notice itself asks for, and the only reading of a thread that means "spend
another attempt on this candidate". An edited body is not one -- drift is a
question about the requirements, and this park is a question about the
budget -- nor is "any update?", nor is an untrusted account's copy of the
command, since what it would buy is agent time on somebody else's word.

What one command buys is one attempt. The grant is durable before the spawn
and the spend is not, so a tick that dies -- or a run a mid-run `paused` or a
shutdown declines -- leaves the attempt where the human put it, unspent.
"""
from __future__ import annotations

import logging

from orchestrator.github.comments import filter_trusted
from orchestrator.workflow.engine import (
    messages as _messages,
    retry_budget as _retry_budget,
)
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

log = logging.getLogger("orchestrator.workflow")

_DECOMPOSING_STAGE = "decomposing"

_LAST_ACTION_COMMENT_ID = "last_action_comment_id"


def _park_owns_the_tick(context: _LateContext) -> bool:
    """Whether a standing retry-cap park stops this adjudication where it is.

    True is the whole tick: the caller returns having neither proved the
    frozen pair, reconciled the hold on the pull request, read what the
    humans have said since the candidate was frozen, nor reused a recorded
    answer. False means either that this issue is not parked on its budget at
    all, or that a human has just bought it another attempt -- and on that
    second answer the grant is already durable, so the spawn below spends
    something the next tick would find again if this one dies before reaching
    it.

    What runs AHEAD of this question is what is owed whether or not a park
    stands: the reconciliation of a notice already on the thread, the owner
    read the generation still records, and the redelivery of a sentence a
    refused comment stranded. The last of those is what says what THIS park is
    for, which is why the park is not asked before it.

    A park that still owes the thread its sentence is held before anything on
    that thread is read as an answer. Saying the sentence moves the response
    boundary past everything written under the old one, so while the
    obligation stands a command is one written before the question was asked.
    The redelivery leaves it standing for exactly one reason, a thread nobody
    could read, and a second read taken here is as likely to succeed as the
    first was to fail: read clean, it would buy an attempt with words nobody
    wrote in reply and consume the notice they were owed on the way out.

    The refusal is recorded either way, because a park nobody can see going on
    refusing is one an operator reads as an adjudication that stopped for no
    reason.
    """
    if not _retry_budget._park_stands(context.state):
        return False
    if _park_is_explained(context):
        if _continuation_is_bought(context):
            _late_park_state._persist(context)
            return False
        log.info(
            "issue=#%d stands on a spent spawn budget; holding its late "
            "adjudication until a trusted /orchestrator continue buys "
            "another attempt",
            context.issue.number,
        )
    _retry_budget._emit_phase(
        context.gh, context.issue, context.state,
        _retry_budget.RetryCapPhase.STANDING,
    )
    return True


def _charge_fresh_spawn(context: _LateContext) -> bool:
    """Gate the one fresh spawn a late adjudication makes, and park if refused.

    The decision is the shared gate's and nothing here re-derives it. What is
    here is what a refusal MEANS on this road: the issue is stopped, the stage
    that ran out is recorded so a later tick can tell this park from another
    stage's, and the sentence explaining it is staged beside the flag rather
    than assumed said.

    Reached only with no park standing -- the hold above is what makes that
    true -- so every refusal it takes is a fresh one, taken with an attempt
    the issue has genuinely run out of rather than with the one it was already
    stopped on.

    Nothing is written by the refusal itself. The park below is what writes,
    and it writes the generation this tick reached in the same breath, so the
    record and the reason the record stopped moving land together.
    """
    decision = _retry_budget._consume_retry_slot(
        context.state, stage=_DECOMPOSING_STAGE,
    )
    if decision.allowed:
        return True
    log.info(
        "issue=#%d has no spawn budget left for its late adjudication; "
        "parking with the frozen candidate and its hold untouched",
        context.issue.number,
    )
    _late_parks._park_on_spent_budget(context, decision)
    return False


def _park_is_explained(context: _LateContext) -> bool:
    """Whether the thread has been told what this park is for.

    Asked before the thread is read for an answer, because an unsaid sentence
    means the question has not been put yet -- and what the delivery does when
    it finally lands is move the response boundary past every comment written
    under the old one. Read for a command first, the same words would buy an
    attempt and then be consumed by the notice explaining why the issue had
    stopped.

    BOTH fields answer it, because a `retry_cap` park under this label can
    have been taken by either owner. This mode's own park records the sentence
    on `late_park_notice`; one the shared parking form took before an issue
    entered the size gate -- or before this owner existed -- records it on
    `retry_cap_notice`, and that one is said by the stage-entry replay rather
    than by the redelivery above. The replay stands down for exactly one
    reason, a thread it could not read, and this owner is the very next step:
    reading only its own field there would find the park explained, take a
    second read that may well succeed where the first failed, and buy an
    adjudication with words written before the question was ever asked. So an
    obligation on either field holds the tick, and whichever owner owes it
    says it on a later one.
    """
    owed = _late_notice._owed_notice(context) or _retry_budget._owed_notice(
        context.state,
    )
    if owed is None:
        return True
    log.info(
        "issue=#%d has still to be told what its retry-cap park is for; "
        "holding it rather than reading a command written before the "
        "question as an answer to it",
        context.issue.number,
    )
    return False


def _continuation_is_bought(context: _LateContext) -> bool:
    """Renew the budget if the thread carries the command that renews it.

    The command is looked for across the whole unread batch rather than in one
    comment of it, and the comment carrying it may carry words too: a decision
    that arrives with an explanation is still the decision, and the
    explanation reaches the fresh adjudicator through the late prompt's own
    comment context.

    A grant consumes the batch it was read out of, up to the last TRUSTED
    comment, exactly as every other reply this mode acts on does -- and
    through the shared watermark, so the comments this park spent are not
    handed to the content read below as fresh guidance or to the later
    validating -> in_review handoff as fresh PR feedback. What is left
    unconsumed is an outsider's, which the next tick filters out again.

    No session is retired with the park, and that is this road's own answer
    rather than an omission. The record a late run is started under drops the
    pinned session for every run that is not continuing a question the human
    has answered, and it is written before the spawn -- so the attempt this
    buys already opens the fresh conversation the budget refused.

    Mutates in memory only. The caller writes, so the grant and the watermark
    that says which words bought it land in one write rather than two.
    """
    answered = _trusted_replies(context)
    if not _messages._parse_orchestrator_continue(answered):
        return False
    log.info(
        "issue=#%d was continued by a trusted operator command; granting one "
        "more late adjudication attempt", context.issue.number,
    )
    _late_park_state._mark_replies_read(
        context, max(reply.id for reply in answered),
    )
    _late_parks._answer_park(context)
    _retry_budget._grant_continuation(
        context.gh, context.issue, context.state,
    )
    return True


def _trusted_replies(context: _LateContext) -> list:
    """What trusted humans have said since this park consumed the thread.

    A read that could not be taken answers nothing said, which holds the park
    for the tick. The two failures are not symmetric: a park held one poll too
    long is answered by the next read, while a grant handed out on a thread
    nobody could read would spend an attempt no human asked for.
    """
    try:
        thread = context.gh.comments_after(
            context.issue, context.state.get(_LAST_ACTION_COMMENT_ID),
        )
    except Exception:
        log.exception(
            "issue=#%d could not be read for the command that lifts a "
            "retry-cap park; holding the park this tick",
            context.issue.number,
        )
        return []
    return filter_trusted(thread)
