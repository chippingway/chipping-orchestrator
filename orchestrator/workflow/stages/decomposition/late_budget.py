# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Declared child addition budgets and the bounds required by fresh replies.

The scalar reader accepts only a positive whole-line count. A fresh split
reply requires one for every child and checks it strictly below the frozen
threshold; older recorded children can still carry no declared budget.
"""
from __future__ import annotations

from typing import Any

from orchestrator.workflow.late_split import formats as _formats

# The manifest key a proposed child declares its budget under. The prompt
# spells it from here and so does the parser, so the number an agent is asked
# for is the number the reply is read for.
ESTIMATE = "estimated_added_lines"

# The smallest budget a slice may claim. A child of an oversized candidate
# that adds nothing is not a slice of it.
MIN_ESTIMATE = 1


def declared_budget(child: Any) -> int | None:
    """Return the lines this child claims it will add, or None for no claim.

    None for everything that is not a count as well as for a child that
    declared nothing, since a caller that told the two apart would be acting
    on a number nobody wrote.
    """
    if not isinstance(child, dict):
        return None
    estimated = child.get(ESTIMATE)
    if not _formats.whole_number(estimated) or estimated < MIN_ESTIMATE:
        return None
    return estimated

_NO_ESTIMATE = (
    f"child {{0}} needs an `{ESTIMATE}` of at least one whole line"
)

_ESTIMATE_PAST_CEILING = (
    f"child {{0}} declares an `{ESTIMATE}` of {{1}}, which is not "
    "below the {2}-line ceiling this split has to get under"
)


def _estimates_error(
    children: tuple, threshold: int | None,
) -> str | None:
    """Return the first child whose declared addition budget is not one.

    What a budget IS is the shared owner's, since the record this reply
    becomes and the child issue it creates both read one back. What an absent
    one costs is this owner's alone: a fresh reply that declared no size for a
    slice is refused, because a proposal nobody sized can still be re-asked
    for the price of the run that is already over.

    A number at or past the ceiling is refused beside it, because a child that
    big is this same adjudication again with an issue number in front of it.
    """
    for child_index, child in enumerate(children):
        estimated = declared_budget(child)
        if estimated is None:
            return _NO_ESTIMATE.format(child_index)
        if threshold is not None and estimated >= threshold:
            return _ESTIMATE_PAST_CEILING.format(
                child_index, estimated, threshold,
            )
    return None
