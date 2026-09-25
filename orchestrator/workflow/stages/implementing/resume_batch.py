# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One read of a parked thread, and everything a resume owes what it found.

An awaiting-human resume asks the same thread two questions -- what the
developer is handed, and what the issue may record as answered -- and the two
have to be about one batch. Read twice, a comment landing between the reads is
quoted to an agent and left unrecorded, or recorded and never quoted. So the
read is taken here, once, and what it produces is the batch both questions are
answered from: the replies the prompt quotes are exactly the inputs the record
names, because the record is what the prompt is built from.

Every `implementing` and `validating` awaiting-human resume reads it. On
`validating` the park-reason decisions and the resume behind them are
different owners, so the batch is built once with the awaiting context and
handed to both; the non-agent routes there consume exactly this batch too.

Three filters decide what is in the batch, and none may be dropped. Untrusted
authors come out first, so nothing an outsider posts reaches the prompt or the
watermark. The orchestrator's own comments come out by the ledger of ids it
recorded posting -- the default empty allowlist trusts every author, so a park
notice read back as guidance is a developer paid to answer the orchestrator
talking to itself. And a body carrying the orchestrator's marker that the
ledger cannot vouch for is refused as forged: the marker is an HTML comment
anybody may paste, and the login may be a token shared with a human whose real
replies must not be swallowed, so the id is the whole of the evidence.

Who OWNS the batch is decided off that same filtered list, and so are the
conversations a fresh spawn is re-grounded with: one snapshot each, over the
one read, built by the owner that decides what a prompt may carry.

What is settled is settled AFTER the run, from the frozen batch, and only for
an outcome that counts the input as delivered. The report transaction a run
may record carries no consumed watermarks, so the settlement is the ordinary
pinned one: `prompt_delivery` ratchets the issue-thread watermark forward and
touches no field it did not deliver against.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from github.Issue import Issue

from orchestrator.agents.models import AgentResult, is_shutdown_sweep_interrupted
from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    conversation_prompts as _conversation_prompts,
    messages as _messages,
    prompt_context as _prompt_context,
    prompt_delivery as _delivery,
)
from orchestrator.workflow.stages.implementing import (
    late_command as _late_command,
    late_measurement_reply as _late_measurement_reply,
    parked_replies as _parked_replies,
    state as _state,
)

# The excerpt bound this surface does not have. The followup quotes every reply
# it was handed, so a snapshot taken under a limit would record an omission the
# prompt never made -- and the watermark would then stop below a comment the
# developer read, handing it back as fresh guidance on the next poll.
_UNBOUNDED_EXCERPT = None

# What a batch nobody may consume carries in place of a delivery: no input was
# evaluated, so there is nothing for a settlement to advance.
_DELIVERED_NOTHING = _delivery.create_prompt_delivery_snapshot(entries=())

# What `_continue_command_action` answers for a batch the retry classifier
# leaves to the ordinary resume: no command on it, or a command somebody wrote
# real guidance beside.
_PASSTHROUGH = "passthrough"


@dataclass(frozen=True)
class _ReplyBatch:
    """The replies one resume delivers, and the record of that delivery.

    `comments` are the comment objects the prompt quotes and `delivery` is the
    snapshot naming the same ids; they are produced together and neither is
    re-derived, which is what makes "what the developer saw" and "what the
    issue records as answered" one fact rather than two readings that agree.

    `reserved` is a batch a command road owns. It is not an empty batch: there
    IS a reply, and what it says is a decision only the road that classifies
    this park may act on -- so the whole tick is handed back unconsumed rather
    than one reply held out of it.

    `state` is the pinned state the read was bounded by, carried rather than
    passed in again: a batch settled onto some other reading of the same issue
    would ratchet a watermark past comments it never saw.

    `regrounding` is the whole conversation as of that same read, for the
    fresh spawn a retired session turns a resume into. Our own comments stay
    in it by recorded id -- an agent reading the answers without the questions
    is re-grounded on half a thread -- and a bare `/orchestrator add-agent-runs`
    stays out of it, as it stays out of the delivery. `retrying` is the same
    conversation less the replies this batch delivers, for the explicit
    `/orchestrator continue` retry: that road consumes the bare commands and
    hands the developer the orchestrator's retry prompt instead, so quoting
    them would hand the agent the command as the last thing a human said.

    `read` is that one read itself and `floor` the watermark it was bounded
    by, kept for the drift check a parked tick asks before any road spends
    the batch (`answered`).
    """

    state: PinnedState
    delivery: _delivery.PromptDeliverySnapshot
    comments: tuple
    regrounding: _delivery.PromptDeliverySnapshot = _DELIVERED_NOTHING
    reserved: bool = False
    retrying: _delivery.PromptDeliverySnapshot = _DELIVERED_NOTHING
    read: tuple = ()
    floor: int | None = None

    @property
    def followup(self) -> str:
        """The resume prompt, quoting exactly the replies the record names."""
        return _conversation_prompts._build_human_reply_followup(
            list(self.comments),
        )

    @property
    def thread_text(self) -> str:
        """The re-grounding conversation, as the snapshot rendered it."""
        return self.regrounding.rendered_text

    @property
    def retry_thread_text(self) -> str:
        """The re-grounding conversation an explicit retry is handed."""
        return self.retrying.rendered_text

    @property
    def answered(self) -> tuple:
        """What the park had already read: the comments at or below `floor`.

        The drift check measures a parked issue's requirements by this rather
        than by the live thread, because the replies past the floor are this
        batch's to deliver -- counted as an edit, they would take the drift
        road, whose own excerpt quotes what this batch reserves and refuses,
        and whose settlement records a delivery this batch never made. No
        floor is a park that has read nothing.
        """
        if not isinstance(self.floor, int):
            return ()
        return tuple(seen for seen in self.read if seen.id <= self.floor)

    @classmethod
    def delivering(
        cls,
        state: PinnedState,
        delivery: _delivery.PromptDeliverySnapshot,
        quoted: tuple,
        *,
        thread: list,
        issue: Issue,
    ) -> _ReplyBatch:
        """This batch, with both conversations a fresh spawn is re-grounded on.

        Both off the one read the batch came from, through the same
        classification, and both without a command only a park's own road
        may act on (`for_the_developer`).

        The delivery record names the requirements revision it answers as
        well: the fingerprint of this read through the last reply it
        delivers, which its settlement records as `user_content_hash`.
        Otherwise those replies move the hash the moment they are consumed,
        and the next drift check -- on this stage or the one a handoff reaches
        -- answers them again as an edit to the issue.
        """
        spoken = cls.for_the_developer(thread, state)
        delivered_ids = {seen.id for seen in quoted}
        regrounding, retrying = (
            _prompt_context._thread_delivery(
                conversation,
                retained_ids=frozenset(_comments._orchestrator_ids(state)),
                state_comment_id=state.comment_id,
            )
            for conversation in (
                spoken,
                [seen for seen in spoken if seen.id not in delivered_ids],
            )
        )
        through = max(delivered_ids, default=0)
        return cls(
            state,
            replace(delivery, requirements_revision=_content_hash._compute_user_content_hash(
                issue,
                _comments._orchestrator_ids(state),
                comments=[seen for seen in thread if seen.id <= through],
            )) if delivered_ids else delivery,
            quoted,
            regrounding,
            retrying=retrying,
            read=tuple(thread),
            floor=state.get(_state._LAST_ACTION_COMMENT_ID),
        )

    @classmethod
    def for_the_developer(cls, read: list, state: PinnedState) -> list:
        """The comments of one read a developer may be handed as prose.

        `parked_replies`' cut, less the command that ends a standing
        authorization park. That command is a control only the park's own
        road may act on: left last it reserves the whole batch for that road,
        and anywhere else something written after it demoted it -- guidance,
        which is what the developer is owed instead, or a pasted marker the
        delivery refuses, which leaves the developer nothing at all. Either
        way the command itself reaches no prompt.
        """
        return [
            seen for seen in _parked_replies._answering(read)
            if not _late_command._reserved_for_the_park(seen, state)
        ]

    def settle(self) -> tuple:
        """Record this batch as consumed, forward only and idempotently.

        Only the surface this batch was read from advances -- the issue
        thread -- so unseen pull-request feedback is left for the scan that
        owns it rather than skipped by a maximum taken across both.
        """
        return _delivery.settle_delivery(self.state, self.delivery)


def _freeze(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    *,
    continue_claimed: bool = False,
) -> _ReplyBatch:
    """Read this parked thread once and freeze what a resume may do with it.

    ONE fetch, for the whole thread, and everything below is cut from it: the
    fresh replies past the watermark, the conversations a fresh spawn is
    re-grounded with, and the record the settlement is taken from. The
    pinned state comment is taken out of that read by its IDENTITY, so a reply
    quoting its marker is a reply like any other.

    The delivery is cut FIRST, and the reservations are asked of it. Which
    batch a command road owns is the same question as which batch a developer
    would be handed: a park notice of ours standing above a bare command, or a
    marker somebody pasted over one, is out of the delivered replies, and a
    classifier reading it as prose would pass the command through to a resume
    that spends it as guidance.

    The measurement park's retry is always asked. The parked-continue
    classifier's is asked only where the caller says that road already looked
    at an EARLIER read -- `continue_claimed` -- since a bare command landing
    after it is in this batch and in nobody else's; the auto-rebase reasons are
    excluded as that classifier excludes them. Neither stage's handler passes
    it: each freezes once and classifies this very batch. The authorization park's is asked of the
    LAST reply the id ledger leaves, which is how that park reads its thread:
    a marker somebody pasted over the command is still a reply that demotes
    it. A bare `/orchestrator add-agent-runs` is out of every one of these
    lists, since it is a control the run-limit hold has already answered --
    and while the authorization park stands its own command is out of what a
    developer is handed as well, so a command something demoted is neither
    acted on nor delivered as prose.
    """
    ours = frozenset(_comments._orchestrator_ids(state))
    thread = gh.comments_after(issue, None, state_comment_id=state.comment_id)
    unclaimed = [
        seen for seen in filter_trusted(_since(thread, state))
        if seen.id not in ours
    ]
    delivery = _delivery.create_prompt_delivery_snapshot(
        issue_comments=_ReplyBatch.for_the_developer(unclaimed, state),
        max_chars=_UNBOUNDED_EXCERPT,
        retained_ids=ours,
        state=state,
        state_comment_id=state.comment_id,
    )
    quoted = _quoted(unclaimed, delivery)
    if (
        _reserved_elsewhere(quoted, state, continue_claimed=continue_claimed)
        or _last_word_reserved(unclaimed, state)
    ):
        return _ReplyBatch(
            state, _DELIVERED_NOTHING, (), reserved=True,
            read=tuple(thread), floor=state.get(_state._LAST_ACTION_COMMENT_ID),
        )
    return _ReplyBatch.delivering(
        state, delivery, quoted, thread=thread, issue=issue,
    )


def _since(thread: list, state: PinnedState) -> list:
    """The slice of one whole-thread read that is past the park's watermark."""
    watermark = state.get(_state._LAST_ACTION_COMMENT_ID)
    if not isinstance(watermark, int):
        return list(thread)
    return [seen for seen in thread if seen.id > watermark]


def _reserved_elsewhere(
    quoted: tuple, state: PinnedState, *, continue_claimed: bool,
) -> bool:
    """Whether a road other than this resume owns the whole of this batch.

    Read off the DELIVERED batch, because that is the batch the delivery
    beside this one would spend, and the two have to be one reading.
    """
    replies = list(quoted)
    if _late_measurement_reply._reserved_for_the_measurement_park(replies, state):
        return True
    park_reason = state.get(_state._PARK_REASON)
    if not continue_claimed or park_reason in _base_sync_state._AUTO_REBASE_PARK_REASONS:
        return False
    return _messages._continue_command_action(replies, park_reason) != _PASSTHROUGH


def _last_word_reserved(unclaimed: list, state: PinnedState) -> bool:
    """Whether the authorization park's own road owns the last reply here.

    Asked of the replies the ID LEDGER leaves less an answered run-grant
    command: a grant left last would hide a command written above it.
    """
    spoken = _parked_replies._answering(unclaimed)
    return bool(spoken) and _late_command._reserved_for_the_park(spoken[-1], state)


def _quoted(
    read: list, delivery: _delivery.PromptDeliverySnapshot,
) -> tuple:
    """The comments behind the delivered half of one snapshot, in thread order.

    Selected by the ids the snapshot recorded rather than re-filtered, so the
    prompt cannot quote a reply the record left out or omit one it names.
    """
    delivered_ids = {
        entry.id
        for entry in delivery.delivered_inputs(_delivery.SURFACE_ISSUE_THREAD)
    }
    return tuple(seen for seen in read if seen.id in delivered_ids)


def _counts_as_delivered(agent_result: AgentResult, paused: bool) -> bool:
    """Whether this outcome counts the batch it was resumed on as delivered.

    Three outcomes never do, and each is a run the developer never read the
    batch through: a live pause, which stops before anything is persisted; a
    shutdown-killed run, which has no trustworthy result; and a launch the run
    circuit turned away, which invoked no process at all.

    Everything else does, whatever it came back with -- a timeout, an empty
    message, a question -- because the prompt carrying those replies reached an
    agent. The batch says what was delivered, never that anything was resolved.
    """
    if paused or is_shutdown_sweep_interrupted(agent_result):
        return False
    return agent_result.invoked
