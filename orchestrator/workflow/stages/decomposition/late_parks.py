# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The decisions that take, stage, retire, or answer a late park.

A pre-run park stages its claim, commits it through ``late_park_state``, and
then asks ``late_park_delivery`` to say what is owed. A post-run caller stages
the same claim with its result but releases it only after its owner guard.
Keeping these calls ordered protects the result when a comment fails without
making delivery recovery another park decision.

A fresh attempt retires only the reasons it can answer. A human's answer
clears its own park and any notice that park still owed; neither path may
silently dismiss the other reasons that require a human decision.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.engine import retry_budget as _retry_budget
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_park_delivery as _late_park_delivery,
    late_park_state as _late_park_state,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext, _StagedPark

log = logging.getLogger("orchestrator.workflow")


def _park(context: _LateContext, message: str, *, reason: str) -> None:
    """Hand the issue back to a human now, and commit everything staged.

    The two halves below run back to back, which is what every exit taken
    BEFORE a run reaches for: nothing has been paid for yet, so there is no
    result a refused comment could take down with it and no owner read between
    the write and the notice.
    """
    _stage_park(context, message, reason=reason)
    _late_park_state._persist(context)
    _late_park_delivery._release_staged_park(context)


def _park_on_spent_budget(
    context: _LateContext, decision: _retry_budget.RetryDecision,
) -> None:
    """Stop this adjudication on a per-issue budget it cannot spend.

    The refusal the shared gate hands back, made durable here rather than
    beside the gate. Nothing has been paid for -- the whole point is that no
    agent started -- so this is the pre-run park shape: the write goes out and
    the sentence follows it immediately, with no owner read between them and
    no result a refused comment could take down with it.

    The write carries the generation this tick reached, which is the reason
    the park is staged through this owner at all: everything the refusal
    leaves standing -- the frozen pair, the phase, the hold on the pull
    request the candidate is on, the locked run and whatever it recorded -- is
    late state, and a park written past it would either lose that record or
    have to write it twice.

    The stage that ran out goes down beside the flag, unabbreviated by this
    mode. The budget is shared, so a park carrying no stage is one a later
    tick can neither attribute in an audit nor tell from another stage's --
    and the tick that meets this one next may well be an initial
    decomposition, on an issue whose generation has since been retired.

    What the park says is the gate's own sentence rather than a late-mode
    rewording of it. A human reading it is owed the bound the refusal was
    made on and the window it was made in, and an operator comparing two
    parked issues is owed the same words on both.
    """
    context.state.set(_retry_budget.RETRY_CAP_STAGE, decision.stage)
    _park(
        context,
        _retry_budget._cap_message(decision),
        reason=_late_park_state.PARK_RETRY_CAP,
    )


def _stage_park(context: _LateContext, message: str, *, reason: str) -> None:
    """Record the park in memory and hold its notice for the caller.

    The reason is written durably beside the flag, which the shared park
    deliberately clears: without it, an issue parked here is one nothing can
    tell from an issue parked by any other stage, and the next late attempt
    could neither retire its own park nor leave somebody else's alone.

    A park already standing for this same reason is not announced again. Every
    late failure is reconciled on each eligible tick -- that is what makes the
    retries idempotent -- so an unchanged one would otherwise say the same
    sentence to the same thread once a tick until a human arrived. The state
    is still written: what is suppressed is the notice, not the park -- which
    is why the suppression is decided HERE, before the flags it reads are
    overwritten.

    Nothing is said, and the sentence is recorded as owed rather than assumed
    delivered. It is staged beside the flag in the SAME memory the park is,
    so the write the park rides out on carries both -- and until a post
    actually lands, every reader of that flag can tell a human who has been
    told from one who has not.

    Every exit a COMPLETED run takes stages its park and lets the owner read
    that follows decide whether the notice may be posted at all, so the
    durable half rides whatever write comes next and no comment can be posted
    ahead of it.
    """
    repeated = _late_park_state._stands_already(context, reason)
    context.state.set(_late_park_state._AWAITING_HUMAN, True)
    context.state.set(_late_park_state._PARK_REASON, reason)
    if repeated:
        log.info(
            "issue=#%d is already parked as %s; not repeating the notice",
            context.issue.number, reason,
        )
        return
    context.staged_park = _StagedPark(message=message, reason=reason)
    _late_notice._owe_notice(context, context.staged_park)


def _release_unsuperseded_park(context: _LateContext) -> None:
    """Say what a staged park explains, if nothing else ever will.

    The counterpart to holding a notice back for a read that could not be
    taken. Holding one back is only ever a DEFERRAL, and it is a deferral
    exactly where a later attempt supersedes the park: that attempt re-takes
    it, and announces the reason it fails for then, which is the current one.

    A park no attempt supersedes has no such tick coming. It IS what the issue
    is waiting on, and its sentence is the only thing that will ever say what
    the human has to do -- so dropping it leaves an `awaiting_human` standing
    with nothing behind it, for as long as the read keeps failing, which is
    unbounded. A comment on a thread this tick could not prove is open costs
    less than that.

    Asked of what an earlier tick left owed as well as of what this one
    staged, because the two are the same obligation: a notice a refused
    comment stranded is exactly a sentence nothing else will ever say.
    """
    staged = context.staged_park or _late_notice._owed_notice(context)
    if staged is None or staged.reason in _late_park_state._SUPERSEDED_PARKS:
        return
    context.staged_park = staged
    _late_park_delivery._release_staged_park(context)


def _retire_park(context: _LateContext) -> bool:
    """Clear a late park this attempt has already answered.

    A park is a claim that the issue is waiting on a human. Once the step that
    failed has been reconciled the claim is stale, and leaving it standing is
    not harmless: the announcement a question earns is suppressed by exactly
    this flag, so a hold that failed once would silence a categorized question
    -- decided, durable, and never said out loud.

    Which is why this runs the moment the hold reconciles rather than beside
    the spawn. The question being silenced need not be one this tick produced:
    a run whose result persisted and whose comment then failed leaves an
    announcement owing, and a hold that failed in between would bury it under
    a park that has nothing to do with it.

    Only this mode's own parks, and only the ones an attempt answers. A park
    another stage left is not this one's to retire, and the question park is
    not stale: nothing here has answered it.

    Returns whether anything was retired. The write belongs to the caller,
    as it does for every other state this mode stages, and the caller that
    stages nothing else has to know it now owes one. What was retired is kept
    on the tick, so a park re-taken for the same reason is recognized as the
    one already announced rather than announced again -- and a park whose
    notice was never said is deliberately NOT kept, because "already
    announced" is the one thing it is not.

    The obligation goes with the park. Retiring one whose sentence is still
    owed is what makes it moot: the step it named has been reconciled, so
    what the sentence describes is over.
    """
    standing = context.state.get(_late_park_state._PARK_REASON)
    if standing not in _late_park_state._SUPERSEDED_PARKS:
        return False
    if _late_notice._owed_notice(context) is None:
        context.retired_park = standing
    _late_notice._notice_settled(context)
    context.state.set(_late_park_state._AWAITING_HUMAN, False)
    context.state.set(_late_park_state._PARK_REASON, None)
    return True


def _answer_park(context: _LateContext) -> None:
    """Clear the park a human has now answered.

    The counterpart to `_retire_park` for the parks no retry supersedes. Those
    stand until somebody says something, so what clears them is an answer
    rather than another attempt -- and the caller that took the answer is the
    only thing that knows one arrived.

    Deliberately NOT remembered on the tick the way a retirement is. That
    memory exists to recognize a park re-taken unchanged, and an answered park
    is never that: the human said something, something ran because they did,
    and whatever it parks on next is news even when it carries the same reason.
    A second question is a different question, and remembering the first would
    leave it recorded, durable, and never said out loud. The write belongs to
    the caller, as it does for every other state this mode stages.

    A sentence this park still owed is dropped with it. The human has spoken,
    which is more than being told what to speak about, and telling them now
    what the issue was waiting on would ask them for something they have
    already given.
    """
    _late_notice._notice_settled(context)
    context.state.set(_late_park_state._AWAITING_HUMAN, False)
    context.state.set(_late_park_state._PARK_REASON, None)
