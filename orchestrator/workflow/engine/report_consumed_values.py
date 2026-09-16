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
That shape check comes before the table is asked, because a table is a mapping
and the recorded field name JSON hands it may be an array: looked up, it raises
out of the state read instead of reading back as the damage it is.

Watermarks may only go FORWARD, which is what makes replaying a settlement safe
-- and what makes their ceiling load-bearing, since a boundary nothing can pass
is one no later comment is ever fresh against.

The watermark half of the table is not spelled here at all: it is BUILT from
`prompt_delivery`'s own `WATERMARK_FIELDS` and `PINNED_USER_CONTENT_HASH`, the
owner that produces the pairs a transaction freezes. Two lists would be two
lists, and the failure a drifted one causes is silent at exactly the wrong
moment: a producer surface this table had never heard of makes one member
unreadable, which refuses the WHOLE group, which holds a transaction whose
report is written and whose feedback is already answered. Read off the
producer, that cannot happen -- and what each field may hold still belongs
here, because a key names a shape this domain has to bound.
"""
from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType

from orchestrator.workflow.engine import (
    prompt_delivery as _delivery,
    report_record_values as _record_values,
)
from orchestrator.workflow.late_split import formats as _formats

# How many members a recorded pair has: the field, and what it is set to.
_PAIR = 2


def _counted(consumed: object) -> bool:
    """Whether a watermark was recorded as a real comment id, inside its range.

    Zero is a real answer -- it is what an empty surface is seeded with, so
    that the legacy backfill cannot re-fire -- and a negative is a value
    nothing wrote.

    The ceiling is the one every recorded identity is held to, and it matters
    more here than anywhere else in this domain: a watermark is APPLIED, and
    the ratchet that applies it only ever moves forward. A value past every id
    GitHub will ever issue is one no later comment can pass, so the scan that
    decides what feedback is fresh finds none again for the life of the issue --
    every human reply read as already answered, with nothing on the thread to
    say why.
    """
    if not _formats.whole_number(consumed) or consumed < 0:
        return False
    return consumed <= _record_values.MAX_RECORDED_NUMBER


def _digest(consumed: object) -> bool:
    """Whether a requirements baseline was recorded as a whole digest.

    The one consumed input that is not an id. A truncated or hand-written
    value here would be compared against a freshly computed hash forever and
    report an edit on every tick, resuming a developer over a change nobody
    made.
    """
    return _formats.is_hex_of(consumed, _formats.DIGEST_LENGTHS)


# Every pinned field a completed transaction may advance on behalf of the run
# that consumed the input, with what each one may be set to. The fields are the
# producer's -- one cursor per delivery surface, plus the requirements revision
# the same snapshot settles -- so a surface added there is consumable here on
# the commit that adds it rather than on the tick that refuses a record for it.
_CONSUMABLE_FIELDS = MappingProxyType({
    **dict.fromkeys(_delivery.WATERMARK_FIELDS, _counted),
    _delivery.PINNED_USER_CONTENT_HASH: _digest,
})


# The fields themselves, for the guard that holds this table to the producer
# and the producer's spellings to the live pinned fields they name.
CONSUMABLE_FIELDS = frozenset(_CONSUMABLE_FIELDS)


def names_a_field(pair: object) -> bool:
    """Whether one recorded pair is shaped like a field and what it is set to.

    Asked before either vocabulary is, because a vocabulary is a mapping and a
    mapping is asked with a KEY: JSON carries arrays and objects, so a recorded
    `[[], 1]` reaches the lookup as an unhashable field name and raises out of
    a state read. Answered here, that record reads back as no record -- which
    is what every other damaged member here reads back as, and what keeps an
    issue carrying committed work behind something somebody can act on rather
    than behind a crash on every poll.
    """
    if not isinstance(pair, list) or len(pair) != _PAIR:
        return False
    return isinstance(pair[0], str)


def consumable(pair: object) -> bool:
    """Whether one recorded pair is a watermark a completion may advance.

    Both halves, because the field is what says what the value MEANS: an id
    recorded as text is not a smaller claim than an unknown key, it is the same
    damage one owner further on -- written to the comment and then compared
    against by the scan that decides what feedback is fresh.
    """
    if not names_a_field(pair):
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

    The shape is proved before the vocabulary is asked, and for every group
    rather than only this owner's: the caller names which table bounds its
    members, and a table is a mapping that would raise on a recorded field name
    JSON is free to have written as an array.
    """
    if not isinstance(raw, list):
        return None
    if not all(names_a_field(pair) and allowed(pair) for pair in raw):
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
