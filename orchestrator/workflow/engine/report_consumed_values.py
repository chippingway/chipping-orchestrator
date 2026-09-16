# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The bookkeeping a recorded transaction may close, and what it may set it to.

A transaction that completes owes two kinds of write the run behind it can no
longer make: the watermarks over the input that run actually consumed, and the
route bookkeeping its own road closes. Both are recorded as
`[[field, value], ...]` and both are APPLIED to the pinned comment, so what
bounds them is not a type annotation but a table naming every field a recovered
record may write and what each one may hold.

The table is per KEY rather than per type, for the reason the held-pair
vocabulary beside it is. An arbitrary key is a write into any field the workflow
has -- a label, a park flag, another stage's watermark. A key with the wrong
SHAPE is the same damage one owner further on: `["pr_last_comment_id", "later"]`
passes any check that only asks whether a comment can carry the value, and fails
at the comparison a feedback scan makes, on a tick nobody is watching.

A group is read all or nothing. Half-applied is worse than none: the watermark
advances, the report it was advanced for is never published, and the feedback
that produced the report is skipped for good -- so one member that will not read
refuses the whole record, and the transaction is held rather than completed.

Watermarks may only go FORWARD, which is what makes replaying a settlement safe.
The keys are spelled as literals rather than imported from the stage packages
that own them, so this owner stays free of the packages that import it; a guard
test proves the two lists still agree.
"""
from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType

from orchestrator.workflow.late_split import formats as _formats

# How many members a recorded pair has: the field, and what it is set to.
_PAIR = 2


def _counted(consumed: object) -> bool:
    """Whether a watermark was recorded as a real, non-negative comment id.

    Zero is a real answer -- it is what an empty surface is seeded with, so
    that the legacy backfill cannot re-fire -- and a negative is a value
    nothing wrote.
    """
    return _formats.whole_number(consumed) and consumed >= 0


def _digest(consumed: object) -> bool:
    """Whether a requirements baseline was recorded as a whole digest.

    The one consumed input that is not an id. A truncated or hand-written
    value here would be compared against a freshly computed hash forever and
    report an edit on every tick, resuming a developer over a change nobody
    made.
    """
    return _formats.is_hex_of(consumed, _formats.DIGEST_LENGTHS)


# Every pinned field a completed transaction may advance on behalf of the run
# that consumed the input, with what each one may be set to. The three
# pull-request surfaces share the in_review scan's spellings, the issue-thread
# watermark is the one every park and resume ratchets, and the baseline is the
# requirements revision a drift resume refreshes.
_CONSUMABLE_FIELDS = MappingProxyType({
    "last_action_comment_id": _counted,
    "pr_last_comment_id": _counted,
    "pr_last_review_comment_id": _counted,
    "pr_last_review_summary_id": _counted,
    "user_content_hash": _digest,
})


# The fields themselves, for the guard that proves every watermark this
# workflow consumes is one this table knows.
CONSUMABLE_FIELDS = frozenset(_CONSUMABLE_FIELDS)


def consumable(pair: object) -> bool:
    """Whether one recorded pair is a watermark a completion may advance.

    Both halves, because the field is what says what the value MEANS: an id
    recorded as text is not a smaller claim than an unknown key, it is the same
    damage one owner further on -- written to the comment and then compared
    against by the scan that decides what feedback is fresh.
    """
    if not isinstance(pair, list) or len(pair) != _PAIR:
        return False
    consumed_field, consumed = pair
    allowed = _CONSUMABLE_FIELDS.get(consumed_field)
    return allowed is not None and allowed(consumed)


def recorded_pairs(
    raw: object, allowed: Callable[[object], bool],
) -> tuple | None:
    """Return one recorded `[[field, value], ...]` group, or None for damage.

    All or nothing, and None rather than an empty group, because the two mean
    opposite things: a record that owes nothing carries an empty group, while
    one whose group will not read owes something this build cannot say.
    Applied half-way, the round advances while the bookmark it was spent for
    stays pending, and the next re-entry reruns a developer over feedback that
    was already answered.

    An EMPTY list is the ordinary "nothing owed" -- an initial publication has
    no reviewer round behind it and no batch to consume -- and an absent or
    `null` group is damage. The encoder writes both arrays on every record, so
    a group that is not there was truncated or hand-edited, and reading it as
    an empty one would let that record publish while silently dropping the
    watermarks and the round it was supposed to close. The only legacy-safe
    absence is the whole additive record, which the reader above answers for.
    """
    if not isinstance(raw, list):
        return None
    if not all(allowed(pair) for pair in raw):
        return None
    return tuple((pair[0], pair[1]) for pair in raw)


def advance_consumed(state, pairs: tuple) -> None:
    """Advance the watermarks a completed transaction consumed, forward only.

    A ratchet rather than a write, because the record was made before the
    publication it describes and a human may well have commented since. Moved
    BACKWARDS, the watermark would hand that comment to the next scan as fresh
    feedback -- or, where the recorded value is the higher one, hand the scan a
    boundary past comments nobody has answered. Only a value that moves the
    boundary forward is applied, so replaying a settlement is a no-op.

    The one field that is not a boundary is the requirements baseline, which is
    a digest: there is no "forward" for it, and what a completed transaction
    consumed is exactly the revision its report was written against.
    """
    for consumed_field, consumed in pairs:
        prior = state.get(consumed_field)
        if isinstance(consumed, int) and isinstance(prior, int) and prior > consumed:
            continue
        state.set(consumed_field, consumed)


def close_bookkeeping(state, pairs: tuple) -> None:
    """Close the route bookkeeping a completed transaction owed.

    Applied from the pair the transaction froze rather than re-derived, which
    is what makes a replay count once: a round computed from the counter would
    be counted again by the tick that replays a settlement the crash hid, while
    re-applying a value already written is a no-op.
    """
    for owed_field, spent in pairs:
        state.set(owed_field, spent)
