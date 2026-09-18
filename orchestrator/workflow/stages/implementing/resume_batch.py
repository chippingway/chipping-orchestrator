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

Who OWNS the batch is decided off that same filtered list. A parked thread is
read by command roads as well -- the measurement park's retry, the parked
`/orchestrator continue` -- and each of them asks whether every fresh reply is
a bare command. Asked of the raw read they see our own park notice standing
above the reply a human wrote while the agent was out, call the batch mixed,
and pass it through; the delivery then drops the notice and hands the bare
command to a developer as prose, with the watermark moved past the words that
asked for the retry. One list, and the answer is the same on both sides of it
-- which is why the cut is `parked_replies`' and not this owner's: the roads
ahead of this one read the thread through it, and this batch is cut by it.

The re-grounding conversation comes out of that same read, through the same
classification, and it has to on both counts. A resume whose session was
retired -- the resume budget, the silent-park streak, a transcript GitHub lost
-- is a FRESH spawn with no transcript to continue, so its prompt carries the
whole trusted thread beside the followup. Read again at spawn time that text is
a second reading minutes newer than the batch: a comment written in between
enters the prompt while the settlement stops below it, and the next poll hands
the developer the same words again. Rendered by a looser filter it is the same
hole one step over -- the forged marker this owner refuses would reach the
agent through the conversation block while staying out of everything that
records what was delivered. So both come off one snapshot each, over one read,
built by the owner that decides what a prompt may carry.

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
from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
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

# What a batch nobody may consume carries in place of a delivery. Shared
# because it is the same absence every time: no input was evaluated, so there
# is no provenance to keep apart and nothing for a settlement to advance.
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
    It is also the list the command roads are asked about, so who owns a batch
    and what a batch delivers are one reading too.

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

    `regrounding` is the whole conversation as of that same read, classified
    the same way and bounded to the excerpt a prompt carries, for the fresh
    spawn a retired session turns this resume into: that prompt quotes the
    thread rather than continuing a transcript. It is a snapshot rather than
    the rendered string because it is delivered input like any other, and the
    provenance of what reached an agent is not a thing to keep in two shapes.
    Our own comments stay IN it, by the recorded ids -- the preamble rebuilds
    a conversation this orchestrator is half of, and an agent reading the
    answers without the questions is being re-grounded on half a thread. A
    bare `/orchestrator add-agent-runs` stays OUT of it, as it stays out of
    the delivery: it is a control the run-limit hold answered, not anything
    said to the developer.

    `retrying` is the same conversation less the replies this batch would
    deliver, for the explicit `/orchestrator continue` retry: that road
    consumes the batch -- every reply in it a bare continue, which is the
    retry's own precondition -- and hands the developer the orchestrator's
    retry prompt instead of the operator's words. A retry whose session is
    missing or retired is a fresh spawn too, so it is re-grounded off THIS
    read rather than one taken at spawn time: a comment written between the
    two would reach the agent while the retry records the thread read only
    through the commands, and the next poll would hand it over again -- and
    the command it consumed would be quoted to the agent as the last thing a
    human said.
    """

    state: PinnedState
    delivery: _delivery.PromptDeliverySnapshot
    comments: tuple
    regrounding: _delivery.PromptDeliverySnapshot = _DELIVERED_NOTHING
    reserved: bool = False
    retrying: _delivery.PromptDeliverySnapshot = _DELIVERED_NOTHING

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

    @classmethod
    def delivering(
        cls,
        state: PinnedState,
        delivery: _delivery.PromptDeliverySnapshot,
        quoted: tuple,
        *,
        thread: list,
        ours: frozenset,
    ) -> _ReplyBatch:
        """This batch, with the conversation it re-grounds a fresh spawn with.

        Both ways round: whole for a resume, whose followup quotes the
        delivered replies beside it, and less those replies for the explicit
        retry, which consumes them and quotes none. Both off the one read the
        batch came from, and both without an answered run-grant command,
        which no road here hands a developer.
        """
        spoken = _parked_replies._answering(thread)
        delivered_ids = {seen.id for seen in quoted}
        regrounding, retrying = (
            _prompt_context._thread_delivery(
                conversation, retained_ids=ours, state_comment_id=state.comment_id,
            )
            for conversation in (
                spoken,
                [seen for seen in spoken if seen.id not in delivered_ids],
            )
        )
        return cls(state, delivery, quoted, regrounding, retrying=retrying)

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
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    *,
    continue_claimed: bool = False,
) -> _ReplyBatch:
    """Read this parked thread once and freeze what a resume may do with it.

    ONE fetch, for the whole thread, and everything below is cut from it: the
    fresh replies past the watermark, the conversation a fresh spawn is
    re-grounded with, and the record the settlement is taken from. A second
    fetch is a second moment, and every pair of readings minutes apart is a
    comment delivered but unrecorded or recorded but never delivered.

    The delivery is cut FIRST, and the reservations are asked of it. Which
    batch a command road owns is the same question as which batch a developer
    would be handed, so the two are answered off one list: a park notice of
    ours standing above a bare command, or a marker somebody pasted over one,
    is out of the delivered replies, and a classifier reading it as prose
    would pass the command through to a resume that spends it as guidance.
    Deferring the tick costs a poll; spending it costs the retry the operator
    bought and the watermark stops above the words that asked for it.

    The measurement park's and the parked-`/orchestrator continue`
    classifier's are the two roads that read this batch, and each reads it the
    same way, which is what keeps the deferral from being a loop: reserved off
    a batch the road behind it does not recognize, this tick would defer what
    that road then refuses and the two would hand the same thread back and
    forth forever.

    The continue classifier's is asked only where the caller says that road
    has already looked -- `continue_claimed`. It is the same window the
    measurement park's has: the classifier ran in the preflight and handed the
    tick back, so a bare command landing since is in this batch and in nobody
    else's, and fed to a developer as prose the explicit retry (or the refusal
    a park needing real guidance earns) is gone. A batch carrying real
    guidance beside the command is `passthrough` there and an ordinary resume
    here, which is the same answer read off the same words. The auto-rebase
    reasons are excluded because that classifier excludes them: those parks
    own their operator's retry comment, so deferring to a road that declines
    it would defer forever. Not asked at all on `validating`, whose
    awaiting-human road classifies the command itself rather than ahead of
    itself -- off this same delivered batch.

    A bare `/orchestrator add-agent-runs` is left out of the delivery, and so
    out of what the command roads classify. It is a control the run-limit hold
    has already answered, with its receipt on the thread, and the one road
    that acts on it reads it only while that park stands. It can still be
    above the mark: the grant that answers it may not consume a reply the park
    interrupted, and a watermark is one number, so the command above that
    reply is left unread with it. Handed on, it would reach a developer as
    prose nobody meant as requirements -- the same reason the content hash
    does not count it. And it has to be out of the preflight's read exactly
    as it is out of this one, which is why both take it out through
    `parked_replies`: counted there, a later bare continue is mixed with it
    and passed through; dropped here, the same continue is bare and reserved,
    and the park stands with nothing retried, refused, or said.

    The pinned state comment is taken out of that read by its IDENTITY, and
    only it. The thread reader's other answer -- the state marker in a body --
    also hides a human reply that quotes the marker, and the roads beside this
    one read by identity: the authorization park's own reading would count
    that reply as the last word while this batch dropped it and found the
    command below it last, and each road would hand the tick to the other for
    good. So the read, the delivery record, and the re-grounding conversation
    all name the pinned comment by id, and a reply quoting its marker is a
    reply like any other.

    The authorization park's is the third, and the one asked of a different
    batch: the LAST reply the ID LEDGER leaves, less an answered run-grant
    command, which is what that park's own road reads and reads it by. A command with guidance written over it has
    been replaced -- the safe reading of somebody who asked to publish and
    then asked for a change is the one that publishes nothing -- so that batch
    is an ordinary resume and the developer answers the change. Asked of the
    delivered replies instead, the two roads would disagree about which reply
    is last wherever a marker somebody pasted sits over the command, and each
    would hand the tick to the other: one refusing a command it does not see
    last, the other deferring to the road that refused it. The grant command
    comes out of both through the same `parked_replies` cut for the same
    reason: left last on one side alone, a command written above it is
    reserved by nobody and delivered to a developer as prose.
    """
    ours = frozenset(_comments._orchestrator_ids(state))
    thread = gh.comments_after(issue, None, state_comment_id=state.comment_id)
    unclaimed = [
        seen for seen in filter_trusted(_since(thread, state))
        if seen.id not in ours
    ]
    delivery = _delivery.create_prompt_delivery_snapshot(
        issue_comments=_parked_replies._answering(unclaimed),
        max_chars=_UNBOUNDED_EXCERPT,
        retained_ids=ours,
        state=state,
        state_comment_id=state.comment_id,
    )
    quoted = _quoted(unclaimed, delivery)
    if _reserved_elsewhere(quoted, state, continue_claimed=continue_claimed):
        return _ReplyBatch(state, _DELIVERED_NOTHING, (), reserved=True)
    if _last_word_reserved(unclaimed, state):
        return _ReplyBatch(state, _DELIVERED_NOTHING, (), reserved=True)
    return _ReplyBatch.delivering(
        state, delivery, quoted, thread=thread, ours=ours,
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

    Both answers are read off the DELIVERED batch -- the replies a developer
    would be handed -- because that is the batch the delivery beside this one
    would spend, and the two have to be one reading. Asked of the raw trusted
    read instead, a park notice of ours standing above a bare command makes
    both classifiers see a batch that is not all bare continues and pass it
    through, while the delivery drops the notice and feeds the command to a
    developer as prose: the explicit retry is gone and the watermark moves
    past the words that asked for it. A forged marker somebody pasted over the
    command is the same mismatch one step over.

    The roads this defers to read the batch the same way, which is what keeps
    the deferral from being a loop: a tick that reserved off a batch the road
    behind it does not recognize would defer what that road then refuses, and
    the two would hand the same thread back and forth forever.
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
    command, which is the reading that road takes: a grant left last on one
    side alone would put a command above it in nobody's hands.
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
