# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The effects a settled decision licenses, in the order a crash is safe in.

The second half of the settlement, split from the first so each is one
crash-ordered sequence rather than one long one: what is durable before this
owner runs is the DECISION -- the exemption, and the commit a push is still
owed for beside it -- and what runs here are the effects that decision buys.

The push comes first, made where the verdict was measured. Then the label,
handed to the stage the record names rather than to `implementing`, because a
generation entered on the published side names the one stage whose completion
the candidate still owes. Only after that is the generation cleared: a
`decomposing` issue with no generation on it is one the INITIAL decomposer
would pick up and re-decompose, and an issue back on its own stage with a live
generation is one the relabel guard puts back and the settlement re-runs.

The window between the push and the label is the one the record alone cannot
answer, and the head proof one owner over is what recognizes it: the retry
comes back to a live generation whose pull request is standing on the accepted
candidate, which is this settlement's own push rather than somebody else's
movement, and the tick finishes the label and the retirement it never reached.

The retirement is the last place a latched close can still be answered, since
past it the record has no cycle identity at all and there is nothing left for a
cancellation to end. So the answer behind that write is a REINSTATEMENT rather
than a refusal -- the generation is still in this call's own memory -- and the
write and the barrier are held inside the observations owner's window, so a
poll reading the record between them is not told there is nothing to end.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.engine import (
    comments as _comments,
    observations as _observations,
)
from orchestrator.workflow.late_split import endings as _endings
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_verdict_push as _late_verdict_push,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateContext,
    _LateDisposition,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# Said by whoever the publication is owed to, which is an operator: a `single`
# on its own parks, so the only road that reaches this sentence is one a human
# authorized. Naming the adjudicator instead would credit the decision to the
# agent that is not allowed to make it.
_ACCEPTED_NOTICE = (
    ":white_check_mark: the committed candidate `{candidate}` was authorized "
    "to publish unsplit ({additions} added lines against a ceiling of "
    "{threshold}), so it publishes as it stands. Only that commit is exempt "
    "-- anything committed on top of it is measured again."
)


def _continued(context: _LateContext) -> _LateDisposition | None:
    """Publish where the verdict was measured, then hand the label on.

    Split from the exemption ahead of it so each half is one crash-ordered
    sequence rather than one long one: what is durable before this call is the
    decision, and what this call does is the effects the decision licenses.
    """
    if not _late_verdict_push._pushed_where_it_was_measured(context):
        return _LateDisposition.PARKED
    stopped = _late_owner._latch_stops(context)
    if stopped is not None:
        return stopped
    context.gh.set_workflow_label(context.issue, _continues_at(context))
    stopped = _late_owner._latch_stops(context)
    if stopped is not None:
        return stopped
    return _published(context)


def _continues_at(context: _LateContext) -> WorkflowLabel:
    """The state a settled adjudication puts this issue back into.

    The record's own answer where it has one. A generation entered on the
    published side names the stage the gate took the issue out of, and that
    stage is the only one whose completion the candidate still owes: a docs
    commit owes the watermark, the notice, and the `in_review` handoff; a
    conflict resolution owes its round; a fix owes the reviewer another look.
    Sending every one of them to `implementing` instead publishes the commit
    and then walks the issue back to a point in the pipeline it had already
    passed, skipping the bookkeeping the stage it came from is the only owner
    of.

    `implementing` is the answer for a candidate nothing had published, which
    is the only other kind: there is no other stage it could have come from.
    """
    if not context.generation.has_publication_context:
        return WorkflowLabel.IMPLEMENTING
    return context.generation.source_stage


def _published(context: _LateContext) -> _LateDisposition | None:
    """Say what was decided, and retire the generation that decided it.

    The two ledgers are the only thing carried across. An obligation the
    remote is owed does not stop being owed because the adjudication that
    recorded it ended well, so the write that drops the rest keeps them -- a
    record with no cycle identity writes exactly what the issue still owes and
    nothing else.

    The notice and the retirement land in one write, so the narrow window
    between them costs at most a repeated comment. The window ahead of them --
    a label already handed on with the generation still live -- costs a tick:
    the relabel guard puts the issue back and this reconciliation runs again,
    finding the hold already released and the exemption already recorded.

    Both of those steps are requests, though, and this is the last place a
    latched close can still be answered: past the retirement the record has no
    cycle identity at all, which is the one state the ending cannot be entered
    from. So the latch is asked between them, and asked again BEHIND the
    retirement -- where the answer is not a refusal but a reinstatement, since
    the generation it would have ended is still in memory.

    The write and that last barrier are held inside `retiring_cycle`, because
    "still in memory" is a claim about THIS thread and the poll runs beside
    it. A poll that reads the record between the two finds no cycle, and
    without the window it would answer "nothing to end", drop the observation,
    and leave the barrier below asking a latch nobody is holding any more.
    Inside it the record's silence proves nothing, the observation is kept,
    and the receipt the poll leaves on the thread is scoped to the cycle this
    window names.

    The window is memory, though, and the barrier behind the write is this
    process's. So the cycle being dropped is recorded in the same write that
    drops it, outside the group that write clears: a process that dies before
    the barrier runs leaves a receipt naming a cycle and a record that still
    says which cycle that was, which is all a later one needs to adopt it.
    """
    _comments._post_issue_comment(
        context.gh, context.issue, context.state,
        _ACCEPTED_NOTICE.format(
            candidate=context.generation.candidate_sha,
            additions=context.generation.additions,
            threshold=context.generation.threshold,
        ),
    )
    live = context.generation
    stopped = _late_owner._latch_stops(context)
    if stopped is not None:
        return stopped
    retiring = _observations.retiring(
        context.spec.slug, context.issue.number, live.cycle_id,
    )
    with retiring.held():
        context.generation = LateGeneration(
            resources=live.resources,
            consumers=live.consumers,
            opaque_resources=live.opaque_resources,
            opaque_consumers=live.opaque_consumers,
        )
        _endings.record_retired_cycle(context.state, live.cycle_id)
        _late_park_state._persist(context)
    return _reinstated(context, live, retiring)


def _reinstated(
    context: _LateContext,
    live: LateGeneration,
    retiring: _observations.RetiringCycle,
) -> _LateDisposition | None:
    """Put back a cycle the retirement write dropped a moment too early.

    That write is a request like every other, so a poll can observe the close
    inside it -- and what it leaves behind is a record with no cycle identity.
    Nothing can end that: the closed-owner sweep reads the cycle to decide
    anything is owed, and a receipt adopted from the thread has no generation
    to be adopted against, so the observation would be stranded for good.

    Asked OF the window rather than of the latch, and that is what makes it
    unmissable: the window decides what it observed as it closes, under the
    lock that closes it, so there is no interval between the answer and the
    exit for a poll to latch a close and post a receipt in. A barrier that
    read the latch itself would leave exactly one.

    The window is also what makes the question answerable at all: without it
    a poll racing the write would have read the retired record, called the
    reading spent, and cleared the very latch this asks about.

    The generation the publication was carrying is still in this call's own
    memory, which is the whole reason the answer here is a reinstatement
    rather than a refusal. It goes back exactly as it was and is cancelled
    from there, so what the ending reads is the cycle that actually ran.

    The published side of the tick is left standing: the exemption is
    recorded, the notice is said, and the label is handed on. None of the
    three is this owner's to take back, and what the ending does with the
    issue where it stands is the cancellation's own business.
    """
    if not retiring.observed:
        return None
    log.warning(
        "repo=%s issue=#%d was observed closed as its accepted candidate was "
        "published; putting cycle %d back on the record so the cancellation "
        "has something to end",
        context.spec.slug, context.issue.number, live.cycle_id,
    )
    context.generation = live
    return _late_owner._latch_stops(context)
