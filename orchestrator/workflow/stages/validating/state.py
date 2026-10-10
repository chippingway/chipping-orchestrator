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
bought it. Additive: an issue without it owes no round. Where a reply bought
the round, the note is joined by the requirements revision of the thread
through that reply, which is what the round is due to hand its reviewer, and
`_discharges_the_owed_round` is the one place both are dropped together.

`_CAP_GRANTED_ON` is the third, and it is the one record that says a cap grant
took. The notice announcing it is posted before the reviewer runs while the
round reset it announces is staged for the reviewer's own write, so a launch
the run circuit refuses keeps the sentence and discards the reset -- and the
same command has to be honored again once an agent-run grant hands the park
back. Written beside the reset, it goes down or does not with it, which is
what tells a grant still owed from one already made and stops a command the
mark was held below resetting every cap the issue later reaches.

`_VERIFY_STATUS_TO_REASON`, `_VALIDATING_TRANSIENT_PARK_REASONS`, and
`_REVIEWER_SIDE_PARK_REASONS` are the three groupings that decide behavior on
their own: the first turns a verify status into the durable tag a park is
filed under, the second is the set a later tick is allowed to retry silently
-- membership here is what says a condition can resolve without anyone
commenting -- and the third is the set whose reply belongs to a fresh reviewer
rather than to the developer, which the drift check stands down for as well.
Three of those never retry themselves: an approval parked without valid
evidence (`reviewer_unverified`) and a verdict parked without room to be
recorded (`reviewer_unrecorded`) wait for exactly that reply, and a reviewer
its provider's usage limit stopped (`reviewer_usage_limit`) waits for a
narrower one still -- the operator's `/orchestrator continue`, since only a
human can say the quota has reset.

`_BOTH_MOVES` is the fourth. A write laid over the pinned comment as it stands
keeps what another road wrote there and what this tick staged, and where both
moved one field it is membership here that decides whether both moves are
kept -- a usage total adding up the runs each folded in, the cost tags beside
it joining, a comment-id watermark keeping whichever reading went further --
or the field is one road's to say, as every other field both moved is. Both
are kept only over values spelled as the field's writers spell them: a flag
where a count belongs, or a word where a list of them does, is a hand edit
nobody can add to, and that move is one road's to say too.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from types import MappingProxyType
from typing import Any, NamedTuple

from orchestrator.github.pinned_state import PinnedState

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

# What an approval that relies on no valid verification evidence parks under.
# Durable rather than transient: a reviewer that approved without the evidence
# will not produce it by being spawned again unasked, so the park waits for a
# human, and the reply to it buys the fresh reviewer that owes the evidence.
_REASON_REVIEWER_UNVERIFIED = "reviewer_unverified"

# What a returned reviewer's verdict parks under where the pinned comment has no
# room to persist it, or it would not read back as written: acted on unrecorded,
# it would be answered again by a second reviewer the moment the tick died.
# Durable for the same reason as the one above, and answered the same way.
_REASON_REVIEWER_UNRECORDED = "reviewer_unrecorded"

# What a reviewer its provider's usage limit stopped parks under. Durable
# rather than transient: the quota has not reset because another poll ran, so
# no idle tick may spend a launch finding that out. And unlike the two above,
# a reply does not answer it either -- only the operator's own
# `/orchestrator continue`, written once the quota has reset, releases it into
# a fresh reviewer. Nothing parks under it yet: recognizing the provider's stop
# on a reviewer's result is the road that will.
_REASON_REVIEWER_USAGE_LIMIT = "reviewer_usage_limit"

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

# The requirements revision a round a reply bought is due to hand its reviewer:
# the thread fingerprinted through the last reply that bought it. Written beside
# the note above and dropped with it, so the round can tell that reply -- which
# is the reviewer's to read -- from words written after it, which are a
# requirements change the developer has not answered. Additive: a round bought
# before it existed has none, and is held to the drift baseline instead.
_ROUND_BOUGHT_THROUGH = "validating_reviewer_round_requirements"

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

# The reading of the BRANCH is what withheld the clear, so the park stands
# exactly as it was filed. Spelled apart from `stuck` because that word is what
# licenses the fixing stage's worktree-drift reroute, and the claim here is a
# different one: a condition that keeps failing may really be a base advance
# nobody synced, while a checkout nothing could place, or one proved to be
# carrying a commit no report describes, is a branch whose publication is the
# very thing being withheld. Rerouted on either, the park comes down and that
# checkout is published by a road staging no report debt for the head it leaves.
_OUTCOME_UNSETTLED = "unsettled"

# The recovery outcomes that heal nothing: the caller clears no park, posts no
# follow-up, and moves no label on any of them. One grouping rather than a
# tuple spelled at each road, since a caller naming only the words it knows
# reads a later addition as a recovery that happened.
_RECOVERY_HOLDS_THE_PARK = frozenset((
    _OUTCOME_STUCK, _OUTCOME_HELD, _OUTCOME_UNSETTLED,
))

_OUTCOME_RETURN = "return"

_SHORT_SHA_LEN = 12

_VALIDATING_TRANSIENT_PARK_REASONS = frozenset(
    (_REASON_PUSH_FAILED, _REASON_AGENT_TIMEOUT, _REASON_REVIEWER_TIMEOUT, _REASON_REVIEWER_FAILED)
)

# The parks whose round is the reviewer's to redo rather than a developer's to
# answer: a reviewer that timed out, crashed, or ran out of provider quota, and
# a returned verdict parked without its evidence or without room to be
# recorded. A reply to any of them buys a fresh reviewer -- for the quota park,
# only a reply carrying `/orchestrator continue` -- and the drift check stands
# down for one rather than resuming the developer on an edit made under it.
_REVIEWER_SIDE_PARK_REASONS = frozenset((
    _REASON_REVIEWER_TIMEOUT,
    _REASON_REVIEWER_FAILED,
    _REASON_REVIEWER_UNVERIFIED,
    _REASON_REVIEWER_UNRECORDED,
    _REASON_REVIEWER_USAGE_LIMIT,
))

_VERIFY_STATUS_TO_REASON = MappingProxyType({
    "failed": "verify_failed",
    "timeout": "verify_timeout",
    "dirty": "verify_dirty",
    "head_changed": "verify_head_changed",
    "tree_changed": "verify_tree_changed",
})


def _is_amount(written: Any) -> bool:
    """Whether `written` is a cost total as its writer spells it: a number, and no flag."""
    return not isinstance(written, bool) and isinstance(written, (int, float))


def _is_whole(written: Any) -> bool:
    """Whether `written` is a count or a comment id as its writers spell it: a whole number, and no flag."""
    return not isinstance(written, bool) and isinstance(written, int)


def _adds_up(ours: Any, theirs: Any, since: Any) -> Any:
    """A total both roads folded runs into: the other road's, with this tick's own fold added."""
    return theirs + ours - (since or 0)


def _is_tag_list(written: Any) -> bool:
    """Whether `written` is the cost tags as their writer spells them: a list of words."""
    if not isinstance(written, list):
        return False
    return all(isinstance(tag, str) for tag in written)


class _BothMoves(NamedTuple):
    """How a pinned field keeps this tick's move beside another road's, and the shape it keeps them in."""

    # Whether one value is spelled as the field's writers spell it.
    shaped: Callable[[Any], bool]
    # The value both moves leave: from this tick's value, the other road's,
    # and the one both moved from.
    kept: Callable[[Any, Any, Any], Any]

    def spelled(self, ours: Any, theirs: Any, since: Any) -> bool:
        """Whether both moves, and the value they moved from where there was one, are spelled as written."""
        if since is not None and not self.shaped(since):
            return False
        return self.shaped(ours) and self.shaped(theirs)


# Each pinned field a write keeps both moves of. A usage total adds up the runs
# each road folded in -- the run and token counts as whole numbers, the cost as
# any number -- and the cost tags beside those totals join. A comment-id
# watermark keeps whichever reading went further: moved back past what the
# other road read, it would hand a comment already answered to the next reader
# as new, and neither reading went past a comment it had not read.
_BOTH_MOVES = MappingProxyType({
    **dict.fromkeys(("issue_agent_runs", "issue_total_tokens"), _BothMoves(_is_whole, _adds_up)),
    "issue_total_cost_usd": _BothMoves(_is_amount, _adds_up),
    "issue_cost_sources": _BothMoves(
        _is_tag_list, lambda ours, theirs, _since: sorted({*ours, *theirs}),
    ),
    **dict.fromkeys(
        ("last_action_comment_id", "pr_last_comment_id", "pr_last_review_comment_id", "pr_last_review_summary_id"),
        _BothMoves(_is_whole, lambda ours, theirs, _since: max(ours, theirs)),
    ),
})


def _discharges_the_owed_round(state: PinnedState) -> None:
    """Drop the note that a reviewer round is owed, and what it was due to hand.

    Together, since the revision is about that note's round and no other: left
    behind, it would hold some later round to a reply that round never bought.
    It is dropped only where it is set, so an issue that never carried it is
    not given the key.
    """
    state.set(_REVIEWER_OWES_A_ROUND, None)
    if state.get(_ROUND_BOUGHT_THROUGH) is not None:
        state.set(_ROUND_BOUGHT_THROUGH, None)


def _keeps_both_moves(state: PinnedState, field: str, read: dict, since: dict) -> bool:
    """Keep on `state` both moves of `field`: this tick's, and another road's to what the comment `read` holds.

    Both moved from what `since`, the comment as read before, held. True where
    the field is one of `_BOTH_MOVES` and every value is spelled as its writers
    spell it (`_BothMoves.spelled`); False, `state` left as it is, for any
    other field, and for a value the field never records -- a hand edit, a
    flag where a count belongs, a word where a list of them does -- whose move
    is one road's to say like any other field's.
    """
    both = _BOTH_MOVES.get(field)
    moves = (
        state.get(field), read.get(field), since.get(field),
    )
    if both is None or not both.spelled(*moves):
        return False
    state.set(field, both.kept(*moves))
    return True
