# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned-state fields this stage reads and writes, and how it names children.

Every owner in the package keys the same durable fields, so they are spelled
once here: a typo in a key is a silently-lost park or a parent that forgets its
children, and neither surfaces until an issue is already stuck. `_issue_ref_list`
sits with them because it is the one rendering of those recorded numbers -- the
held-dependency log line, the rejected- and closed-child parks, and the drift
notice all quote children the same way.
"""
from __future__ import annotations

from typing import Any

from orchestrator.workflow.late_split import formats as _formats

_AWAITING_HUMAN = "awaiting_human"

_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

_CHILDREN = "children"

_UMBRELLA = "umbrella"

# Which CYCLE's consumer ledger is FINAL. Written only where the loop stopped
# because that cycle was cancelled and every child that exists is already on
# the register, which is the one state in which a ledger short of the count
# the transaction wrote is complete rather than mid-flight.
#
# The cycle rather than a flag, because the seal outlives the attempt that
# wrote it: no write that ends a generation drops this key, so a bare "yes"
# would be read by the NEXT cycle on the same issue as proof about a register
# it says nothing about -- and a later split stopped mid-loop would authorize
# the delete of the very ref its unrecorded children were cut from.
_SPLIT_LEDGER_SEALED = "split_ledger_sealed"

# When an umbrella's terminal became durable. Read by two owners rather than
# one: the terminal writes it in the same pinned write that retires the cycle,
# and the closed-owner sweep reads it to tell an umbrella whose label a crash
# took away from one a human closed mid-cycle.
_UMBRELLA_RESOLVED_AT = "umbrella_resolved_at"

_PARK_REASON = "park_reason"

_PARENT_NUMBER = "parent_number"

_CREATED_AT = "created_at"

_DONE = "done"

_HeldChild = tuple[int, list[int]]


def _ledger_is_sealed(sealed: Any, cycle_id: int) -> bool:
    """Whether a recorded seal is this cycle's own final register.

    Spelled once because the loop that writes it and the reclamation rule
    that reads it are two owners, and only an exact match between them is
    proof: a seal naming another cycle is a fact about a split this one never
    ran, and a value no attempt could have written -- a bare flag, a
    hand-edited field, a number that is not an identity -- names no cycle at
    all and is read as no seal, which holds the ref rather than releasing it.
    """
    if not _formats.whole_number(sealed) or sealed <= 0:
        return False
    return sealed == cycle_id


def _links_to(linked: Any, parent: int) -> bool:
    """Whether a recorded `parent_number` is exactly `parent`'s issue number.

    Spelled once because recovery, recognition, and release all take the link
    as proof of parentage, and only an issue number proves it: JSON carries
    `41.0` and `true` as values Python compares equal to 41 and 1, and neither
    is one any writer here produced, so each names no parent at all.
    """
    return _formats.whole_number(linked) and linked > 0 and linked == parent


def _issue_ref_list(numbers: list) -> str:
    """Render issue/child numbers as a `#a, #b` comma-joined reference list."""
    return ", ".join(f"#{number}" for number in numbers)
