# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The trusted replies an adjudication still owes a whole quote.

The late adjudicator reads the conversation through the bounded excerpt every
conversation-carrying prompt shares, and that excerpt keeps the thread's TAIL.
Two roads consume a reply on the adjudicator's behalf -- the answer that
reopens a categorized question, and the words beside the continue that lifts
a spent budget -- and both consume it ahead of the spawn gates, into every
baseline, `user_content_hash` included. A reply longer than the excerpt, or
one followed by enough conversation, would then be recorded as answered while
the agent it was spent on read only its end; a run a gate refused would have
read nothing of it at all.

So those roads record what they spent as OWED, by comment id, on the
generation itself. Every late run quotes the owed replies whole beside the
excerpt until one has actually answered them: an adjudicator whose verdict is
recorded over them, or a developer revision whose reconciliation re-measures
a candidate off a run that neither timed out nor stopped before it worked.
Nothing short of that repays them -- a run refused at a spawn gate, paused,
or killed; one stopped by its timeout; one whose CLI stopped on its quota
before it said a word; a reply nothing could parse; a revision whose
reconciliation parked, a question over an unchanged commit among them -- so
the replies stay owed for the run that does.
"""
from __future__ import annotations

from dataclasses import replace

from github.Issue import Issue

from orchestrator.workflow.engine import prompt_context as _prompt_context
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

_OWED_HEADER = (
    "Replies this adjudication has to answer, quoted whole -- the "
    "conversation above is only its most recent part:"
)


def _owe(context: _LateContext, replies) -> None:
    """Record these replies as owed a whole quote, beside any already owed.

    In memory only, like the consumption it rides: the caller's own write is
    what makes the debt durable, in the same write as the baselines that now
    count the replies as read.
    """
    owed = context.generation.owed_replies
    added = tuple(reply.id for reply in replies if reply.id not in owed)
    if added:
        context.generation = replace(
            context.generation, owed_replies=owed + added,
        )


def _repaid(context: _LateContext) -> None:
    """Record that the run whose answer is being recorded has answered every owed reply.

    In memory as well: it lands with the write that records that answer, so a
    run nobody reconciles -- one a pause or a shutdown ended -- leaves the debt
    exactly where it was. A run that answered nothing is never asked about
    here -- a timeout, a quota stop, a refused verdict, a revision that
    parked -- so its debt stands too.
    """
    if context.generation.owed_replies:
        context.generation = replace(context.generation, owed_replies=())


def _conversation(generation: LateGeneration, issue: Issue) -> str:
    """The conversation an adjudicator is handed: the excerpt, then what is owed.

    One read of the thread for both, so a reply quoted whole is the same
    comment the excerpt was cut from. Each owed reply goes through the same
    trust filter the excerpt applies, so an author the allowlist has dropped
    since is not quoted on the strength of an id recorded before.
    """
    read = list(issue.get_comments())
    excerpt = _prompt_context._thread_text(read)
    owed = [
        _prompt_context._prompt_comment_chunk(issue_comment)
        for issue_comment in read
        if issue_comment.id in generation.owed_replies
    ]
    quoted = [chunk for chunk in owed if chunk is not None]
    if not quoted:
        return excerpt
    return _prompt_context._SECTION_SEP.join((excerpt, _OWED_HEADER, *quoted))
