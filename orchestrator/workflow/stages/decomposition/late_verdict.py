# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One finished reply, read and recorded as the verdict it decided.

What a late run's answer MEANS, split from the completion bookkeeping
`late_outcome` owns beside it the way `outcomes.py` is split from `run.py`.
What is here is the reading, the bound a split is refused at, the record it
becomes, and the one sentence a question owes the issue; what a completion
writes and hands back, and the emissions that report it, are that owner's.

The ordering rule the exits here obey is the one `late_park_state` owns -- the
durable write goes out before the external effect, never after -- and a
completed adjudication is what makes it worth obeying. The agent has already
been paid for by the time a reply is read, so a crash between reading it and
recording it costs a second run of an agent that already answered. The result
is therefore written and persisted BEFORE anything is posted, and the
announcement a question owes the issue is reconciled from that record on a
later tick rather than being the only place the outcome exists. What the
narrow crash window between the post and the write can still cost is one
repeated comment -- the same window every park in this repository has -- and
never the run.

`_announce` is published for the same reason it is not called from the step
that records an outcome: the owner guard runs between the record and anything
said out loud, so what posts a question is the step past that guard rather
than the step that wrote it down.

The lineage bound is enforced here rather than in the parser, because it is a
property of the generation and not of the reply. A structurally valid split
proposed at the bound is recorded as the categorized question it actually is:
the workflow is asking a human, the recorded outcome says so, and the next
tick does not pay for another agent to propose the same forbidden split.

What this owner deliberately does NOT do is act on the verdict it recorded.
Restoring or superseding the held pull request, creating children, and pushing
an accepted candidate all belong to the steps the guard hands a verdict on to.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split import events as _events
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_reply as _late_reply,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudication,
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
)

log = logging.getLogger("orchestrator.workflow")

_UNPARSED_PARK = (
    "the late decomposer did not return a usable "
    "`orchestrator-late-manifest` block ({reason}), so nothing was decided "
    "about this issue's oversized committed candidate."
)

_QUESTION_PARK = ":mag: the late decomposer is asking ({category}): {asked}"

_UNRECORDABLE_PARK = (
    "the late decomposer decided something this issue's pinned state cannot "
    "hold -- a question, an explanation of what stopped a split, or a child "
    "manifest past the size one orchestrator comment may carry. Nothing was "
    "recorded and nothing was published, because half an outcome is not one. "
    "This oversized candidate needs a human to split it by hand."
)

# What a split proposed at the lineage bound is recorded as. The bound is a
# safety invariant, so the outcome is not the split the agent asked for; it is
# the categorized question the workflow now owes a human, recorded as one so a
# later tick asks the human rather than the agent.
_AT_BOUND_QUESTION = _LateAdjudication(
    verdict=LateVerdict.QUESTION,
    category=_events.LateVerdictCategory.LINEAGE_BOUND,
    question=(
        "the late decomposer proposed splitting this issue, but its lineage "
        "is already as deep as automatic splitting goes. It has to land as "
        "one change or be split by hand."
    ),
)


def _decide(
    context: _LateContext, last_message: str,
) -> _LateAdjudicationRun:
    """Read the reply, refuse a split the lineage forbids, and record it.

    The reply is read against THIS generation's ceiling, which is the number
    its own prompt stated: a child sized against anything else would be
    judged by a bound the agent was never given.
    """
    adjudication, parse_error = _late_reply._parse_late_reply(
        last_message, context.generation.threshold,
    )
    if adjudication is None:
        _late_parks._stage_park(
            context,
            _UNPARSED_PARK.format(reason=parse_error),
            reason=_late_park_state.PARK_UNPARSED,
        )
        _late_outcome._completed(context)
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    if (
        adjudication.verdict == LateVerdict.SPLIT
        and not context.generation.may_split
    ):
        adjudication = _AT_BOUND_QUESTION
    return _recorded(context, adjudication)


def _recorded(
    context: _LateContext, adjudication: _LateAdjudication,
) -> _LateAdjudicationRun:
    """Persist one completed adjudication, then say what it decided.

    The persist is first and unconditional. Everything after it -- the two
    sinks, and the comment a question owes the issue -- is an external effect
    that a crash may repeat, and repeating one of those costs a duplicate
    record or a duplicate comment. Repeating what comes before it would cost
    another agent run against a candidate that has already been adjudicated,
    and a second run is free to decide differently.

    An outcome the record could not hold is the one case that never becomes
    an answer at all: nothing durable stands behind it, so acting on it would
    leave the issue decided in a way no later tick could see. It parks
    instead, and the park is staged BEFORE the write rather than after it, so
    the one write carries whichever of the two this run produced.

    Size is the only thing asked, and it is asked of the COMMENT. How an
    explanation will render on the thread is not a reason to refuse the
    verdict that carries it: this park is superseded by the next attempt, so a
    refusal here buys another agent run against a candidate that has already
    been adjudicated -- and a `single` refused that way never reaches the
    durable park a human's decision is owed on. What the sentence does with an
    explanation it cannot block off is `late_notice`'s own answer, and it
    keeps every word of it.

    What it deliberately does NOT do is announce. The announcement is an
    external effect on the issue, and whether the issue is still there is the
    owner guard's question -- which is asked between this write and anything
    said out loud, so a question is not posted to a thread somebody closed
    while the agent was answering it.
    """
    kept = _late_session._record_late_result(context.state, adjudication)
    if not kept:
        log.error(
            "issue=#%d the late outcome does not fit the pinned comment; "
            "refusing to record part of it",
            context.issue.number,
        )
        _late_parks._stage_park(
            context, _UNRECORDABLE_PARK, reason=_late_park_state.PARK_UNRECORDABLE,
        )
    _late_outcome._completed(context)
    _late_outcome._emit_verdict(context, adjudication)
    if not kept:
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    return _late_outcome._finished(
        context, _LateDisposition.DECIDED, adjudication,
    )


def _announce(
    context: _LateContext, adjudication: _LateAdjudication,
) -> None:
    """Post the question this outcome owes the issue, if it owes one.

    Called past the owner guard rather than beside the record, so a question
    is never posted to a thread this tick could not prove is still open. The
    park it goes through commits everything staged with it, so a caller has
    nothing left to write afterwards.

    Read off the adjudication rather than off the record, so what the issue
    is told is what the agent actually wrote. The two agree -- an outcome is
    refused rather than shortened -- but the announcement is not the record's
    to paraphrase.

    A verdict that asks nothing announces nothing, and a question the issue is
    already waiting on a human for is not repeated -- which is what a recorded
    question reaching this a second time relies on.
    """
    if not adjudication.question or _late_park_state._stands_parked(context):
        return
    _late_parks._park(
        context,
        _QUESTION_PARK.format(
            category=adjudication.category, asked=adjudication.question,
        ),
        reason=_late_park_state.PARK_QUESTION,
    )
