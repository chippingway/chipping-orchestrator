# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one late field in a pinned comment reads back as.

The pinned comment is JSON a human can edit, an older binary may have written,
and a newer one has to survive reading, so nothing here trusts the type it
finds. Each reader answers with the field's own default instead of raising:
the late gate is entered by an issue that already has committed work, and a
`TypeError` out of a state read would strand that work behind a crash on every
poll rather than behind a decision somebody can act on.

Fail-closed is the rule for every reader, and each field is read for what it
actually is rather than for its Python type. A count that is negative is not a
measurement, an identity that is not positive is not an issue or a cycle, a
depth outside the lineage is not one, and a commit field that is not a whole
object id -- nor a fingerprint that is not a whole digest -- is not one -- every one of them reads back absent,
which downstream is "not measured", "not adjudicated", or "may not split", and
never a value a later tick would act on. The two flags are literal: only JSON
`true` is set, because a hand-edited "false" is a string, and reading it for
its truthiness would arm a cancellation or a pending restart nobody wrote.

The one thing this owner does not do is convert. A number is not made out of
something that was not one (the `formats` owner beside it is where that line
is drawn), so `True` is not cycle 1 and 2.9 is not depth 2. The two external
ledgers are read by the `ledgers` owner instead, because their answer to an
unreadable value is to preserve it rather than to default it.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.late_split.models import MAX_LINEAGE_DEPTH


def as_count(raw: Any) -> int | None:
    """Return a counted field, or None unless it is a real, non-negative one.

    A threshold, an additions total, and a generation counter are all counts:
    zero is a real answer, and a negative is a value nothing measured -- one
    that would otherwise make an unmeasured candidate report as oversized.
    """
    if not _formats.whole_number(raw) or raw < 0:
        return None
    return raw


def as_identity(raw: Any) -> int | None:
    """Return an identity field, or None unless it is a positive whole number.

    Cycles, issues, pull requests, and comment ids all start at 1: a zero or a
    negative is not one of them, and reading it as a live identity would put a
    record on an audit line nothing can be joined to.
    """
    number = as_count(raw)
    return number if number else None


def as_depth(raw: Any) -> int | None:
    """Return a lineage depth, or None unless it is one inside the bound.

    Unknown rather than clamped: a depth outside the lineage is a field this
    binary cannot act on, and answering with the root's 0 is exactly how a
    damaged field would buy a generation past the cap.
    """
    number = as_count(raw)
    if number is None or number > MAX_LINEAGE_DEPTH:
        return None
    return number


def as_hex(raw: Any, lengths: frozenset) -> str | None:
    """Return a hex field of exactly one of those lengths, or None.

    What keeps a commit field a commit and a fingerprint a fingerprint: the
    caller names the shape its own field has -- a whole object id for a frozen
    commit, a whole digest for a local fingerprint -- so text that is not one,
    an abbreviation included, is not a value to carry forward.
    """
    return raw if _formats.is_hex_of(raw, lengths) else None


def as_flag(raw: Any) -> bool:
    """Return a boolean field, set only by the literal this domain writes."""
    return raw is True


def as_text(raw: Any) -> str | None:
    """Return a free-text field, or None when it is absent or not a string.

    The fields read this way -- a declared scope, a held PR body, a stamp --
    are the ones no sink carries and no vocabulary bounds, so what they must
    be is a string and nothing more.
    """
    return raw if isinstance(raw, str) else None


def as_member[Member: StrEnum](members: type[Member], raw: Any) -> Member | None:
    """Return the vocabulary member a wire string names, or None.

    An unknown spelling is a field this binary cannot act on, and answering
    None is what routes it to the same place an absent field goes.
    """
    try:
        return members(raw)
    except (TypeError, ValueError):
        return None
