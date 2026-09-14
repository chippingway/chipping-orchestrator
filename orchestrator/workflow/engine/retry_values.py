# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retry decisions, notice phases, and pinned keys for the daily retry budget."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

# The durable reason an exhausted budget parks under. It is a wire string on
# live issues and the one thing that makes this park recognizable to the tick
# after it: a park with no reason is one nothing can tell from any other
# stage's, and the gate would go on re-deciding the same exhausted budget.
PARK_RETRY_CAP = "retry_cap"

# The sentence the standing park has still to say out loud. Held beside the
# flag, dropped only by a post that landed or by the park itself ending, and
# spelled without the mention the delivery prefixes -- what is durable is what
# the park has to explain, not how a thread was addressed.
RETRY_CAP_NOTICE = "retry_cap_notice"

# How many of the attempts a continuation bought are still unspent. Its
# PRESENCE is what says this issue runs on grants rather than on the setting:
# a human answered a park here, and what they answered it with is a count of
# attempts, not a licence to read whatever `MAX_RETRIES_PER_DAY` happens to
# say when the spawn is finally asked for. Stored as the count itself so it
# survives every change to that setting in both directions -- widened, and
# turned off. Written by the continuation, spent by the gate, dropped where
# the rest of the budget is: the publication that moves the issue on.
#
# Its ABSENCE is the only thing that means "no grant" -- an issue nobody has
# continued, or one the publication reset cleared back to null. Present, it
# governs: a real count is read into the range a continuation can produce (a
# bigger number a hand edit left buys the one attempt a continuation buys, a
# negative buys nothing), and a value that is not a number at all proves no
# attempt and so hands out none. Nothing a hand edit can leave here widens
# what this issue may spend.
RETRY_CAP_CONTINUED = "retry_cap_continued"

# What one continuation buys. Spelled here because it is the bound the notice
# quotes when the attempt is spent, as well as the number written down.
_GRANTED_ATTEMPTS = 1

# Which stage's fresh spawn ran out. The budget is shared, so the flag alone
# cannot say what the human is being asked about, and the audit records below
# would have no stage to report the park under once the label has moved on.
RETRY_CAP_STAGE = "retry_cap_stage"

_RETRY_CAP_EVENT = "retry_cap"

# What a thread read answers when the request itself failed. A sentinel rather
# than None, because None is the answer for a thread that was read and does
# not carry the notice -- and only that one may be posted over.
_UNREADABLE_THREAD = object()

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

_RETRY_WINDOW_START = "retry_window_start"

_RETRY_COUNT = "retry_count"

# The consumed-comment watermark a park's own mention ratchets, and only on a
# post that landed. That is what makes it the window an undelivered notice is
# looked for in: a sentence whose write failed sits ABOVE the mark its post
# should have moved, while one from a tick that completed sits at or below it.
_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# A fixed window per issue rather than a rolling one: enough to stop a stuck
# issue from burning a day of tokens, and cheap enough to read off two fields.
_WINDOW = timedelta(hours=24)


class RetryCapPhase(StrEnum):
    """Which step of a retry-cap park one audit record describes.

    The four are deliberately distinguishable. A delivery and a reconciliation
    both end with the thread carrying the notice, but only one of them paid a
    comment for it; a standing park and a continuation both follow an
    exhausted budget, but only one of them lets an agent run again.
    """

    DELIVERED = "delivered"
    RECONCILED = "reconciled"
    STANDING = "standing"
    CONTINUED = "continued"


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
class RetryDecision:
    """What one stage's fresh spawn was told, and the accounting behind it.

    Carried back rather than acted on here: the caller owns the park, the
    write under it, and the sentence it explains. `cap` and `window_start` are
    reported because the notice quotes both -- a human who is asked for manual
    intervention is owed the numbers the refusal was made on. `cap` is the
    bound that was actually in force, which is the configured one everywhere
    but on an issue a continuation has already had to buy.
    """

    allowed: bool
    stage: str
    cap: int
    spent: int
    window_start: str | None
