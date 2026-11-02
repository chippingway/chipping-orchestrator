# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One read of a parked decomposition's thread, and everything its resume owes it.

A parked `decomposing` tick asks its thread three questions -- whether the
requirements moved under the park, what the locked decomposer session is
handed, and how far the issue may record the thread as answered -- and the
three have to be about one read. Read apart, a reply landing between two of
them is quoted and left unrecorded, recorded and never quoted, or measured as
an edit by the drift check while the resume beside it delivers it as an
answer. So the thread is read here, once, before drift is decided
(`run._prepare_decomposer_run`), and every answer is cut from that read.

What the park had already read -- the comments at or below
`last_action_comment_id` -- is what the drift check measures the requirements
by (`answered`). A reply past it is the park's answer, delivered to the session
that asked; counted as an edit it would retire that session and re-decompose
the issue from scratch. Only a change the replies do not explain -- the title,
the body, a comment the park had already read -- is drift, and that keeps the
fresh decomposition whatever reply arrived beside it.

The replies past the boundary are cut by `prompt_delivery`'s own classification:
an untrusted author, the pinned comment by its id, our own posts by recorded
id, and a body carrying our marker the id ledger cannot vouch for all come out.
So does a bare `/orchestrator add-agent-runs`, a control the dispatcher's
run-limit hold answered and whose grant may leave it past the boundary above the
reply its refusal interrupted. Nothing else is classified here: a bare
`/orchestrator continue` is the way a human retries a timed-out or silent
decomposer, and is delivered as the reply it is. What is left is quoted whole
and is exactly what the delivery record names, since the prompt is that
record's own rendering.

Settlement waits for the run, and only a run that read the prompt counts: the
caller answers a refused launch, an unresolved accounting, and a live hold
before it asks, and a shutdown-killed one reads nothing either. It records the
reply boundary through the last reply delivered and, as `user_content_hash`,
the fingerprint of this read through that reply -- so a delivered reply is
never met again as an edit, on this stage or on `ready`, where a `single`
decision hands the issue.

An edit the read shows takes the fresh decomposition instead, and that spawn is
handed the same read (`conversation`): what the park had already read as the
excerpt every decompose prompt quotes, and the replies past its boundary whole,
as a resume quotes them. A reply cut by the excerpt would hold the boundary
below it while the baseline counts it, and the next reply would then read as an
edit nobody made. It is settled the same way -- the read's whole fingerprint as
the baseline, which the reset leaves to it -- so its boundary moves only over
replies its prompt quoted, and only a run that read the edit answers it.

A tick spending an attempt a retry-cap continuation bought reads its thread
the same way, parked or not (`reads_the_thread`). The continuation moves no
boundary, so the replies a bounded park held under its notice and the words
that bought the attempt are still past it, and the fresh spawn the attempt
pays for is handed them as an edit's spawn is (`conversation`) -- whole, and
settled only where its run read them, on whichever tick spends the attempt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from github.Issue import Issue

from orchestrator.agents.models import AgentResult, is_shutdown_sweep_interrupted
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    prompt_context as _prompt_context,
    prompt_delivery as _delivery,
    retry_ledger as _retry_ledger,
    run_grant_request as _run_grant_request,
)
from orchestrator.workflow.stages.decomposition import state as _state

log = logging.getLogger("orchestrator.workflow")

# The excerpt bound this followup does not have. It quotes every reply it
# delivers, so a record taken under a limit would name an omission the prompt
# never made and stop the reply boundary below a reply the decomposer read.
_UNBOUNDED_EXCERPT = None

# Between the conversation a fresh spawn is quoted and the replies beside it,
# as between any two comments a prompt quotes.
_SECTION_BREAK = "\n\n"


@dataclass(frozen=True)
class DecomposerReplies:
    """One frozen read of a parked thread: what the park answered, and what it is answered with.

    `read` is the whole thread less the pinned comment and `floor` the reply
    boundary it was read under. `delivery` records the replies past that
    boundary a resume hands the decomposer, and its `rendered_text` is the
    prompt, so what the decomposer saw and what the issue records as answered
    are one fact rather than two readings that agree.
    """

    read: tuple
    floor: int | None
    delivery: _delivery.PromptDeliverySnapshot

    @property
    def answered(self) -> tuple:
        """The comments at or below the boundary: the thread the park had already read.

        No boundary is a park that has read nothing.
        """
        if not isinstance(self.floor, int):
            return ()
        return tuple(seen for seen in self.read if seen.id <= self.floor)

    @property
    def followup(self) -> str | None:
        """The resume prompt, or None where nothing past the boundary is a reply to deliver."""
        if not self.delivery.delivered_inputs(_delivery.SURFACE_ISSUE_THREAD):
            return None
        return self.delivery.rendered_text

    @property
    def pending(self) -> tuple:
        """The comments past the boundary: the thread the park has not read yet, whoever wrote them."""
        answered = {seen.id for seen in self.answered}
        return tuple(seen for seen in self.read if seen.id not in answered)

    def conversation(self, issue: Issue, state: PinnedState) -> DecomposerReplies:
        """This read as the fresh decomposition an edit buys is handed it: the conversation, then the pending replies.

        What the park had already read is cut to the bound every decompose
        prompt quotes its thread under; what is past the boundary is quoted
        whole, as the resume quotes it. Both are recorded as delivered by the
        same classification, our own posts kept by their recorded ids, so the
        settlement moves the boundary through every reply the read holds --
        which is what the reset's baseline, this read's fingerprint, counts.
        A reply cut there would hold the boundary below it under a baseline
        that counts it, and the next reply would leave neither the whole
        thread nor the answered part matching that baseline: an edit nobody
        made, resetting the session this spawn opens.

        It is this read rather than one taken beside it for the same reason
        from the other side: a reply written behind the read would otherwise
        be quoted under a baseline that never counted it.

        The baseline is that read's whole fingerprint, carried as the
        delivery's requirements revision: the reset that buys this spawn
        records none, so the edit is answered only once a run that read it
        settles (`settle`), and a run that read nothing leaves it owed.
        """
        earlier = _quoted(self.answered, state)
        replies = _quoted(self.pending, state, max_chars=_UNBOUNDED_EXCERPT)
        return replace(self, delivery=_delivery.create_prompt_delivery_snapshot(
            entries=earlier.entries + replies.entries,
            rendered_text=_SECTION_BREAK.join(text for text in (earlier.rendered_text, replies.rendered_text) if text),
            requirements_revision=_content_hash._compute_user_content_hash(
                issue, _comments._orchestrator_ids(state), comments=list(self.read),
            ),
            state=state,
        ))

    def settle(self, state: PinnedState, agent_result: AgentResult) -> None:
        """Record these replies answered where the run handed them read them, forward only.

        Asked of a run the caller already found invoked, accounted, and
        unheld, and ahead of any park that run earns, so the park's walk starts
        from the last reply delivered. A shutdown-killed run is the last that
        read nothing: a park its worktree earns leaves the replies for the
        next resume to deliver.
        """
        if not is_shutdown_sweep_interrupted(agent_result):
            _delivery.settle_delivery(state, self.delivery)


def freeze(gh: GitHubClient, issue: Issue, state: PinnedState) -> DecomposerReplies | None:
    """Read the parked thread once and freeze what drift and the resume may do with it; None where it cannot be read.

    An unreadable thread answers nothing, and the caller holds the tick on it:
    neither the drift reset nor a launch is decided on a read that established
    nothing, and the next tick reads again.
    """
    try:
        thread = tuple(gh.comments_after(issue, None, state_comment_id=state.comment_id))
    except Exception:
        log.exception(
            "issue=#%d its parked decomposition thread could not be read; "
            "holding the tick with nothing reset, resumed, or spawned",
            issue.number,
        )
        return None
    replies = _replies_past(thread, state)
    delivery = _delivery.create_prompt_delivery_snapshot(
        issue_comments=replies,
        max_chars=_UNBOUNDED_EXCERPT,
        retained_ids=frozenset(_comments._orchestrator_ids(state)),
        state=state,
        state_comment_id=state.comment_id,
    )
    if replies:
        delivery = replace(delivery, requirements_revision=_revision_through(issue, state, thread, replies))
    return DecomposerReplies(read=thread, floor=state.get(_state._LAST_ACTION_COMMENT_ID), delivery=delivery)


def parked(state: PinnedState) -> bool:
    """Whether the issue stands on a park whose thread a reply may answer."""
    return bool(state.get(_state._AWAITING_HUMAN))


def reads_the_thread(state: PinnedState) -> bool:
    """Whether this tick decides on one frozen read of its thread (`freeze`).

    A park a reply may answer does, and so does an attempt a continuation
    bought that no run has spent yet: the continuation leaves the replies the
    retry-cap park held past the boundary, beside the words that bought it,
    and the fresh decomposition it pays for is handed them through the same
    read -- quoted whole, and settled only by a run that read them -- on
    whichever tick spends it.
    """
    return parked(state) or _retry_ledger._grant_is_unspent(state)


def _replies_past(thread: tuple, state: PinnedState) -> list:
    """The comments past the reply boundary a human wrote to the park, in thread order."""
    floor = state.get(_state._LAST_ACTION_COMMENT_ID)
    return [
        seen for seen in _delivery.human_replies(
            [seen for seen in thread if not isinstance(floor, int) or seen.id > floor],
            frozenset(_comments._orchestrator_ids(state)),
            state_comment_id=state.comment_id,
        )
        if not _run_grant_request._is_bare_command(seen)
    ]


def _quoted(comments: tuple, state: PinnedState, **bound) -> _delivery.PromptDeliverySnapshot:
    """One stretch of this read as a decompose prompt quotes it, our own posts kept by recorded id.

    Under the excerpt bound every decompose prompt quotes its thread under,
    save where `bound` says otherwise.
    """
    return _prompt_context._thread_delivery(
        comments,
        retained_ids=frozenset(_comments._orchestrator_ids(state)),
        state_comment_id=state.comment_id,
        state=state,
        **bound,
    )


def _revision_through(issue: Issue, state: PinnedState, thread: tuple, replies: list) -> str:
    """The requirements fingerprint of this read through the last reply it delivers.

    Taken off the frozen read rather than the live thread, so the baseline the
    settlement records describes exactly the replies the decomposer was handed
    and nothing written after them.
    """
    through = max(seen.id for seen in replies)
    return _content_hash._compute_user_content_hash(
        issue, _comments._orchestrator_ids(state), comments=[seen for seen in thread if seen.id <= through],
    )
