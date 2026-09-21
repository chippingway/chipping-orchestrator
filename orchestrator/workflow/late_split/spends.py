# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a hold's route bookkeeping may close, and what each field may take.

The vocabulary a restored spend is bounded by, kept apart from the pinned
round trip that carries one because what it decides is a CLAIM rather than a
field: whether the pair a comment came back with is one this workflow's routes
could have recorded at all.

The table is what turns a restored spend from "whatever the comment says" into
a bounded claim, and it is per KEY rather than per type because what comes back
is APPLIED to the pinned comment and then read by owners that know what each
field is. An arbitrary key is a write into any field the workflow has -- a
label, a watermark, a park flag. A key with the wrong SHAPE is the same damage
one step in: `["review_round", "later"]` passes any check that only asks
whether a comment can carry the value, and fails at the `int(...)` the cap is
counted with, on a tick nobody is watching.

The keys are spelled as literals rather than imported from the four stage
packages that own them: a stage's bookkeeping stays that stage's to describe
and this owner stays free of the packages that import it.
`tests/workflow/test_spend_vocabulary.py` proves the two lists agree, so a key
added to a route without being added here fails there rather than silently at
a retry.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any

from orchestrator.workflow.late_split import formats as _formats

# How many members a recorded spend pair has: the field and what it is set to.
_PAIR = 2

# How long an outcome a conflict round settles on may be. Every one this
# workflow writes is a short word; the bound is what keeps a hand-edited record
# from putting a body-sized string on the pinned comment through a retry.
_OUTCOME_LIMIT = 64


def _cleared(spent: Any) -> bool:
    """Whether a bookmark was recorded as CLEARED, which is all it may be."""
    return spent is None


def _counted(spent: Any) -> bool:
    """Whether a counter was recorded as a real, non-negative count."""
    return _formats.whole_number(spent) and spent >= 0


def _named_outcome(spent: Any) -> bool:
    """Whether an outcome was recorded as one bounded, single-line name."""
    return _formats.is_bounded_text(spent, _OUTCOME_LIMIT)


def _settled_commit(spent: Any) -> bool:
    """Whether a settled head was recorded as a commit, or as none at all."""
    return spent == "" or _formats.is_hex_of(spent, _formats.COMMIT_LENGTHS)


def _raised(spent: Any) -> bool:
    """Whether a mark was recorded as RAISED, which is all it may be.

    The mirror of `_cleared`: what clears one is the route that reads it, so a
    record may only ever put one up. `True` exactly -- `1` is an `int` that
    reads the same to a truth test and is not a flag this workflow writes.
    """
    return spent is True


# Every pinned field a hold's route bookkeeping may close, with what each one
# may be set TO.
_SPENDABLE_FIELDS = MappingProxyType({
    "review_round": _counted,
    "pending_fix_at": _cleared,
    "pending_fix_issue_max_id": _cleared,
    "pending_fix_review_max_id": _cleared,
    "pending_fix_review_summary_max_id": _cleared,
    "pending_fix_issue_ids": _cleared,
    "pending_fix_review_ids": _cleared,
    "pending_fix_review_summary_ids": _cleared,
    "pending_fix_reviewer_comment_id": _cleared,
    "fixing_round_settled": _raised,
    "conflict_settled_outcome": _named_outcome,
    "conflict_settled_sha": _settled_commit,
    "docs_settled_sha": _settled_commit,
})


# The fields themselves, for the guard that proves every route spends one this
# table knows.
SPENDABLE_FIELDS = frozenset(_SPENDABLE_FIELDS)


def spendable(pair: Any) -> bool:
    """Whether one recorded pair is a field a write may set, at a value it may.

    Both halves, because the field is what says what the value MEANS: a
    counter that came back as text is not a smaller claim than an unknown key,
    it is the same damage one owner further on -- applied to the comment and
    then read by the cap that counts rounds.
    """
    if not isinstance(pair, list) or len(pair) != _PAIR:
        return False
    field, spent = pair
    allowed = _SPENDABLE_FIELDS.get(field)
    return allowed is not None and allowed(spent)
