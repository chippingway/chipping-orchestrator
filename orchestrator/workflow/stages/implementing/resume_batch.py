# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One read of a parked thread, and everything a resume owes what it found.

An awaiting-human resume asks the same thread two questions -- what the
developer is handed, and what the issue may record as answered -- and the two
have to be about one batch. Read twice, a comment landing between the reads is
quoted to an agent and left unrecorded, or recorded and never quoted -- and on
`validating` the two questions are asked by different owners, the park-reason
decisions and the resume behind them, so the looser of two filters would
decide what a prompt carries. The read is taken HERE, once, and what it
produces is the batch both questions are answered from: the replies the prompt
quotes are exactly the inputs the record names, because the record is what the
prompt is built from.

Three filters decide what is in it, and none of them may be dropped. Untrusted
authors come out first, so nothing an outsider posts on a parked issue reaches
the prompt or the watermark. The orchestrator's own comments come out beside
them by the ledger of ids it recorded posting -- nothing this process wrote is
a human's guidance, and the default empty allowlist trusts every author, so a
park notice read back as somebody asking for a change is a developer paid to
answer the orchestrator talking to itself. And a body carrying the
orchestrator's marker that the ledger cannot vouch for is refused as forged:
the marker is an HTML comment anybody may paste, and the author login may be a
token shared with a reviewer whose real replies this must not swallow, so the
id is the whole of the evidence and a marker without one admits nothing.

What is settled is settled AFTER the run, from the frozen batch, and only for
an outcome that counts the input as delivered. There is no report transaction
on this road -- nothing here records one -- so the settlement is the ordinary
pinned one: `prompt_delivery` ratchets the consumed field forward and no
field it did not deliver against is touched. A run that was never invoked, one
a shutdown killed, and one a live pause withheld consume nothing at all: the
developer did not see the batch, and a watermark moved for them is a human
reply answered by nobody. A run that finished consumes it whatever it came
back with -- a commit, a timeout, or a question -- because the developer read
it, and the question the park then poses is preserved independently of that:
the batch says what was delivered, never that anything was resolved.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    conversation_prompts as _conversation_prompts,
    prompt_delivery as _delivery,
)
from orchestrator.workflow.stages.implementing import (
    late_command as _late_command,
    late_measurement_reply as _late_measurement_reply,
    state as _state,
)

# The excerpt bound this surface does not have. The followup quotes every reply
# it was handed, so a snapshot taken under a limit would record an omission the
# prompt never made -- and the watermark would then stop below a comment the
# developer read, handing it back as fresh guidance on the next poll.
_UNBOUNDED_EXCERPT = None

# What a batch nobody may consume carries in place of a delivery. Shared
# because it is the same absence every time: no input was evaluated, so there
# is no provenance to keep apart and nothing for a settlement to advance.
_DELIVERED_NOTHING = _delivery.create_prompt_delivery_snapshot(entries=())


@dataclass(frozen=True)
class _ReplyBatch:
    """The replies one resume delivers, and the record of that delivery.

    `comments` are the comment objects the prompt quotes and `delivery` is the
    snapshot naming the same ids; they are produced together and neither is
    re-derived, which is what makes "what the developer saw" and "what the
    issue records as answered" one fact rather than two readings that agree.

    `reserved` is a batch a command road owns. It is not an empty batch and
    must not be confused with one: there IS a reply, and what it says is a
    decision only the road that classifies this park may act on -- so the
    whole tick is handed back unconsumed rather than one reply held out of it.
    A watermark is one number and a resume is not the last thing to move it:
    the run it starts parks, and that park stamps the thread read to the notice
    it posts, which lands above the command and takes it for good.

    `state` is the pinned state the read was bounded by, carried rather than
    passed in again: what a settlement may advance is the cursor the batch was
    taken from, and a batch settled onto some other reading of the same issue
    would ratchet a watermark past comments it never saw.
    """

    state: PinnedState
    delivery: _delivery.PromptDeliverySnapshot
    comments: tuple
    reserved: bool = False

    @property
    def followup(self) -> str:
        """The resume prompt, quoting exactly the replies the record names."""
        return _conversation_prompts._build_human_reply_followup(
            list(self.comments),
        )

    def settle(self) -> tuple:
        """Record this batch as consumed, forward only and idempotently.

        The ordinary pinned settlement, which is the whole of what this road
        has: no run here records a report transaction, so there is nothing
        holding frozen watermarks for a later tick to apply. Only the surface
        this batch was read from advances -- the issue thread -- so unseen
        pull-request feedback below a consumed reply is left for the scan that
        owns it rather than skipped by a maximum taken across both.
        """
        return _delivery.settle_delivery(self.state, self.delivery)


def _freeze(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _ReplyBatch:
    """Read this parked thread once and freeze what a resume may do with it.

    The measurement park's reservation is asked of the trusted read BEFORE our
    own comments come out of it, because that is the read the retry itself
    takes: reserved off a narrower batch, this tick would defer what that road
    then refuses, and the two would hand the same thread back and forth
    forever.

    The authorization park's is asked of the LAST reply the ID LEDGER leaves,
    which is the batch that park's own road reads and reads it by: a command
    with guidance written over it has been replaced -- the safe reading of
    somebody who asked to publish and then asked for a change is the one that
    publishes nothing -- so that batch is an ordinary resume and the developer
    answers the change. Asked of the narrower DELIVERED replies instead, the
    two roads would disagree about which reply is last wherever a marker
    somebody pasted sits over the command, and each would hand the tick to the
    other: one refusing a command it does not see last, the other deferring to
    the road that refused it.
    """
    ours = _comments._orchestrator_ids(state)
    read = filter_trusted(gh.comments_after(
        issue, state.get(_state._LAST_ACTION_COMMENT_ID),
    ))
    if _late_measurement_reply._reserved_for_the_measurement_park(read, state):
        return _ReplyBatch(state, _DELIVERED_NOTHING, (), reserved=True)
    unclaimed = [seen for seen in read if seen.id not in ours]
    if unclaimed and _late_command._reserved_for_the_park(
        unclaimed[-1], state,
    ):
        return _ReplyBatch(state, _DELIVERED_NOTHING, (), reserved=True)
    delivery = _delivery.create_prompt_delivery_snapshot(
        issue_comments=unclaimed,
        max_chars=_UNBOUNDED_EXCERPT,
        retained_ids=frozenset(ours),
        state=state,
    )
    return _ReplyBatch(state, delivery, _quoted(read, delivery))


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
    batch through. A live pause stops before anything is persisted and the
    caller returns on the same flag, so a settlement here would be the one
    write that survived a tick deliberately abandoned. A shutdown-killed run
    has no trustworthy result at all. And a launch the run circuit turned away
    invoked no process, so there is nothing that could have been read.

    Everything else does, whatever it came back with. A timeout, an empty
    message, a question: the prompt carrying those replies reached an agent,
    and the park that ends such a run mentions a human about what the agent
    said rather than about the input it was given.
    """
    if paused or agent_result.interrupted:
        return False
    return agent_result.invoked
