# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Lifetime run-limit notice records, audit phases, and pinned park fields.

`DisplacedPark` is the park a run-limit park goes up in front of, in the pinned
shape a grant would put back; nothing records or restores one yet."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.workflow.engine.run_ledger_models import AgentRunLedger

# The durable reason a spent lifetime ledger parks under. It is a wire string
# on live issues and the one thing that makes this park recognizable to the
# tick after it: a park with no reason of its own is one nothing can tell from
# an agent's question, and every stage's awaiting-human road would answer it.
PARK_AGENT_RUN_LIMIT = "agent_run_limit"

# The sentence the standing park has still to say out loud, and the reading it
# was written for. Held beside the flag, dropped only by a post that landed,
# and spelled without the mention the delivery prefixes -- what is durable is
# what the park has to explain, not how a thread was addressed.
AGENT_RUN_LIMIT_NOTICE = "agent_run_limit_notice"

# The park a spent ledger takes the issue off, for the grant that takes the
# run-limit park down to put back. A refused launch is very often a resume of
# that park -- a developer handed the reply a human wrote on it -- and the
# circuit refuses on the DURABLE state, before the road that launched has
# written anything, so this is exactly the park the run the human paid for was
# stopped on. Cleared instead, the tick the grant hands on takes the stage's
# ordinary road: a fresh spawn quoting the reply with no record that it was
# delivered, or a reviewer where a developer was owed it.
AGENT_RUN_LIMIT_DISPLACED = "agent_run_limit_displaced"

_DISPLACED_AWAITING = "awaiting_human"

_DISPLACED_REASON = "park_reason"

_NOTICE_MESSAGE = "message"

_NOTICE_ALLOWANCE = "allowance"

_NOTICE_SPENT = "spent"

_RUN_LIMIT_EVENT = "agent_run_limit"

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

# The consumed-comment watermark a park's own mention ratchets, and only on a
# post that landed. That is what makes it the window an undelivered notice is
# looked for in: a sentence whose write failed sits ABOVE the mark its post
# should have moved, while one from a tick that completed sits at or below it.
_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# What a thread read answers when the request itself failed. A sentinel rather
# than None, because None is the answer for a thread that was read and does
# not carry the notice -- and only that one may be posted over.
_UNREADABLE_THREAD = object()


class RunLimitPhase(StrEnum):
    """Which step of an agent-run-limit park one audit record describes.

    The five are deliberately distinguishable. A delivery and a
    reconciliation both end with the thread carrying the notice, but only one
    of them paid a comment for it; a park that holds a later tick is neither,
    and it is the record that keeps an operator from reading a workflow
    stopped for good as one that stopped for no reason. A grant and a refusal
    are the two endings of the one command that answers this park, and only
    one of them lets an agent run again.
    """

    DELIVERED = "delivered"
    RECONCILED = "reconciled"
    STANDING = "standing"
    GRANTED = "granted"
    REFUSED = "refused"


class NoticeReading(StrEnum):
    """What a thread was found to say about a notice a park still owes.

    Three answers rather than two, because the two ways of not finding it are
    not the same thing. A thread that does not carry the sentence is owed it.
    A thread nobody could read says nothing at all -- and the sentence may
    already be on it, posted by a tick whose pinned write then failed, which
    is the exact state this reconciliation exists for. Read as a miss, a
    request that failed would post the duplicate the protocol is here to
    stop, so it is its own answer and the delivery stands down for the tick.
    """

    SAID = "said"
    UNSAID = "unsaid"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class OwedNotice:
    """One sentence a park still owes, and the exhaustion it explains.

    The pair of counts is the scope. They are what the sentence quotes, so a
    notice carrying a reading the issue is no longer at is one that would tell
    a human the wrong numbers -- and they are the only thing that can say so,
    since every park this owner takes carries the same reason.
    """

    message: str
    allowance: int
    spent: int

    def explains(self, ledger: AgentRunLedger) -> bool:
        """Whether this sentence is about the exhaustion the ledger reads."""
        return self.allowance == ledger.allowance and self.spent == ledger.used


@dataclass(frozen=True)
class DisplacedPark:
    """The park a spent ledger's park went up in front of.

    Read off the state the circuit refused on, which is the durable one: the
    launch it turned away wrote nothing first, so what the issue was waiting
    on when the run was asked for is what the flag and the reason say then. A
    reason that is the run-limit park's own is no park to go back to -- it is
    a flag a road took down and left its reason behind -- so it reads as none.

    A record that is missing or malformed -- a park taken before the field
    existed, or a hand-edited one -- reads as no park at all, which is what a
    grant puts back where there is no record to read.
    """

    awaiting: bool = False
    reason: str | None = None

    @classmethod
    def standing(cls, state) -> DisplacedPark:
        """The park this state is waiting on right now."""
        reason = state.get(_PARK_REASON)
        if reason == PARK_AGENT_RUN_LIMIT or not isinstance(reason, str):
            reason = None
        return cls(awaiting=bool(state.get(_AWAITING_HUMAN)), reason=reason)

    @classmethod
    def recorded(cls, record) -> DisplacedPark:
        """The park one record names, or no park at all."""
        if not isinstance(record, dict):
            return cls()
        awaiting = record.get(_DISPLACED_AWAITING) is True
        reason = record.get(_DISPLACED_REASON)
        return cls(
            awaiting=awaiting,
            reason=reason if awaiting and isinstance(reason, str) else None,
        )

    def as_record(self) -> dict:
        """The pinned shape of this park."""
        return {
            _DISPLACED_AWAITING: self.awaiting,
            _DISPLACED_REASON: self.reason,
        }
