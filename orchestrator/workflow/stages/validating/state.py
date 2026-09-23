# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The wire strings and shared bounds the validating owners key on.

The pinned-state keys and the `park_reason` tokens beside them are part of the
JSON comment live issues already carry, and they outlive this stage: the
fixing handler dispatches its own recovery off `_REASON_PUSH_FAILED` /
`_REASON_AGENT_TIMEOUT`, and dashboards group parks by the same spellings. So
renaming one is a migration of every open issue rather than a refactor.

They sit in one module because the owner that writes a value is almost never
the owner that branches on it: the cap park stamps `review_cap` and the
awaiting-human route is what reads it back to honor
`/orchestrator add-review-rounds`; the dev-fix timeout stamps
`pre_dev_fix_sha` and the silent recovery is what compares HEAD against it.
The outcome tokens are the same shape one level up -- a helper returns
`"pushed"` / `"parked"` / `"cleared"` / `"stuck"` / `"return"` and a different
owner switches on it -- so the strings are declared once rather than spelled
twice.

`_OPEN_DRIFT`, `_REVIEWER_OWES_A_ROUND`, and `_CAP_GRANTED_ON` are the keys
here that outlive their own tick on purpose. A
requirements edit resumes the developer, and that resume can end without
answering it: a question, a timeout, a tree nobody could publish. The reply
that clears such a park is a continuation of the drift road rather than an
ordinary fix -- its report is the one the edit is owed -- so the road it
belongs to has to survive the park, and nothing else on the comment says which
road a park came off. Both review stages write it through the shared drift
disposition and `in_review` reads it for the budget a hand-back owes; it lives
exactly as long as the park it was written with, since the park clearing is
what answers it. Additive: an issue without it has no edit outstanding.

`_REVIEWER_OWES_A_ROUND` is the other, and it exists for the gap between a
reviewer-side park clearing and the round that clearing was for. The drift
check stands down for such a park because the reply -- or the silent recovery
-- belongs to the reviewer; the clear then goes out on a tick that runs no
round at all -- the recovery unparks and ends its tick, a report still owed
holds the reviewer behind it -- and the round it released runs on a later one.
The thread it releases has moved the requirements by then, so a tick reading
the park alone finds a plain edit and takes the developer's road ahead of the
reviewer the reply bought. Both roads write this down instead, and the round
that finally runs drops it -- and settles the reply where the value says one
bought it. Additive: an issue without it owes no round.

`_CAP_GRANTED_ON` is the third, and it is the one record that says a cap grant
took. The notice announcing it is posted before the reviewer runs while the
round reset it announces is staged for the reviewer's own write, so a launch
the run circuit refuses keeps the sentence and discards the reset -- and the
same command has to be honored again once an agent-run grant hands the park
back. Written beside the reset, it goes down or does not with it, which is
what tells a grant still owed from one already made and stops a command the
mark was held below resetting every cap the issue later reaches.

`_VERIFY_STATUS_TO_REASON` and `_VALIDATING_TRANSIENT_PARK_REASONS` are the
two groupings that decide behavior on their own: the first turns a verify
status into the durable tag a park is filed under, and the second is the set
a later tick is allowed to retry silently -- membership here is what says a
condition can resolve without anyone commenting.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any

_ReviewRoundsCommand = tuple[Any, int, str | None]

_ADD_REVIEW_ROUNDS_RE = re.compile(
    r"^\s*/orchestrator\s+add-review-rounds\s+(\d+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_PARK_REASON = "park_reason"

_PRE_DEV_FIX_SHA = "pre_dev_fix_sha"

_REVIEW_ROUND = "review_round"

_REASON_PUSH_FAILED = "push_failed"

_REASON_AGENT_TIMEOUT = "agent_timeout"

_REASON_REVIEWER_TIMEOUT = "reviewer_timeout"

_REASON_REVIEWER_FAILED = "reviewer_failed"

_REASON_REVIEW_CAP = "review_cap"

# What a squash that could not be finished is filed under. Durable rather than
# event-only, because the recovery ahead of the reviewer retries it on every
# tick -- a human told to reconcile the branch or repair the comment is
# answered by the retry getting further, not by a reply -- and the reason is
# what tells that park's own notice from one to post afresh.
_REASON_SQUASH_FAILED = "squash_failed"

_OUTCOME_PARKED = "parked"

_OUTCOME_CLEARED = "cleared"

_OUTCOME_PUSHED = "pushed"

# A resume that committed nothing and wrote a report: the report is recorded
# and bound to the head the pull request already carries, so the caller routes
# the head rather than parking on it as a question. A drift resume routes it as
# it routes an `ACK:` -- the same head, re-reviewed against the new
# requirements -- and a reviewer-requested round routes it as a landed fix,
# since the report is the handover that round made.
_OUTCOME_REPORTED = "reported"

# The fix-loop outcomes that can leave a recorded report for the caller to
# bind, once its own bookkeeping -- and its relabel, where it makes one -- is
# written.
_REPORTING_OUTCOMES = frozenset((_OUTCOME_PUSHED, _OUTCOME_REPORTED))

# Whether a requirements edit resumed the developer and that resume has not
# answered it yet. Written beside the park the resume ended on and read by the
# reply that clears it, which is then the drift resume's continuation.
_OPEN_DRIFT = "requirements_drift_open"

# Whether a reviewer round a deferral stood down for is still owed. Written by
# the drift check when it defers and by the road that clears a reviewer-side
# park into a round, carried by whichever write goes out first, and dropped by
# the reviewer round that runs.
_REVIEWER_OWES_A_ROUND = "validating_reviewer_owes_a_round"

# What that note holds where a REPLY bought the round rather than a silent
# recovery releasing one: the round owes those words a settlement wherever it
# finally runs, which is not necessarily the tick the park came off. `True` is
# the other shape -- an edit nobody delivered, which the round that discharges
# the note records nothing about.
_ROUND_BOUGHT_BY_A_REPLY = "bought_by_a_reply"

# The comment a review-cap grant was WRITTEN for. Staged beside the round
# reset it buys and carried by the same write, so it is durable exactly where
# that reset is. Additive: an issue without it has granted nothing.
_CAP_GRANTED_ON = "review_cap_granted_comment_id"

_OUTCOME_STUCK = "stuck"

# The recovery finished and the tick is over, without anything having healed.
# The size gate took the candidate the retry was about -- parked on a reading
# nobody could take, or handed the issue to the adjudication -- so the caller
# owes no follow-up, no park clear, and no relabel: it would be announcing a
# recovery that did not happen and moving a label the gate has just set.
_OUTCOME_HELD = "held"

_OUTCOME_RETURN = "return"

_SHORT_SHA_LEN = 12

_VALIDATING_TRANSIENT_PARK_REASONS = frozenset(
    (_REASON_PUSH_FAILED, _REASON_AGENT_TIMEOUT, _REASON_REVIEWER_TIMEOUT, _REASON_REVIEWER_FAILED)
)

_VERIFY_STATUS_TO_REASON = MappingProxyType({
    "failed": "verify_failed",
    "timeout": "verify_timeout",
    "dirty": "verify_dirty",
    "head_changed": "verify_head_changed",
})
