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

`_OPEN_DRIFT` is the one key here that outlives its own tick on purpose. A
requirements edit resumes the developer, and that resume can end without
answering it: a question, a timeout, a tree nobody could publish. The reply
that clears such a park is a continuation of the drift road rather than an
ordinary fix -- its report is the one the edit is owed -- so the road it
belongs to has to survive the park, and nothing else on the comment says which
road a park came off. Both review stages write it through the shared drift
disposition and `in_review` reads it for the budget a hand-back owes; it lives
exactly as long as the park it was written with, since the park clearing is
what answers it. Additive: an issue without it has no edit outstanding.

`_VERIFY_STATUS_TO_REASON` and `_VALIDATING_TRANSIENT_PARK_REASONS` are the
two groupings that decide behavior on their own: the first turns a verify
status into the durable tag a park is filed under, and the second is the set
a later tick is allowed to retry silently -- membership here is what says a
condition can resolve without anyone commenting.
"""
from __future__ import annotations

import re
from types import MappingProxyType

_ReviewRoundsCommand = tuple[int, str | None]

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

# A requirements-drift resume that committed nothing and wrote a report: the
# report is recorded and bound to the head the pull request already carries,
# so the caller routes it as it routes an `ACK:` -- the same head, re-reviewed
# against the new requirements -- rather than as a question.
_OUTCOME_REPORTED = "reported"

# The drift outcomes that can leave a recorded report for the caller to bind,
# once its own bookkeeping -- and on `in_review` its relabel -- is written.
_REPORTING_OUTCOMES = frozenset((_OUTCOME_PUSHED, _OUTCOME_REPORTED))

# Whether a requirements edit resumed the developer and that resume has not
# answered it yet. Written beside the park the resume ended on and read by the
# reply that clears it, which is then the drift resume's continuation.
_OPEN_DRIFT = "requirements_drift_open"

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
