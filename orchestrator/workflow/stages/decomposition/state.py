# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned-state fields this stage reads and writes, and how it names children.

Every owner in the package keys the same durable fields, so they are spelled
once here: a typo in a key is a silently-lost park or a parent that forgets its
children, and neither surfaces until an issue is already stuck. `_issue_ref_list`
sits with them because it is the one rendering of those recorded numbers -- the
held-dependency log line, the rejected- and closed-child parks, and the drift
notice all quote children the same way. `_links_to` sits with them because a
recorded `parent_number` is proof of parentage only as an exact issue number,
and every reader that takes it as proof has to refuse the same values.
`_split_rationale_text` sits with them because a split's rationale is read by
one rule twice -- off the manifest it arrives in and off the record it is kept
in -- so what a split writes is what `_recorded_split_rationale` hands back to
every later reader: the summary a split or its recovery posts, and the
developer prompts of a parent's own pass. `_READY_REROUTE` is spelled here
because two owners key it: `ready` writes it with its reset, and the
`decomposing` tick that reroute hands the issue to drops it.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.stages.decomposition import late_result_payloads as _late_result_payloads

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

# Which ordinary split the parent's markers belong to: minted for each split
# and written in the same write as the expected count, ahead of the first
# child, so the receipt each child carries names this attempt and no earlier
# split of the same issue. Read by `split_receipts`, dropped with the manifest
# a drift reset discards, and dropped by a `blocked` parent once every child
# it names has resolved, in a write ahead of its flip back to its own work.
_SPLIT_ATTEMPT = "split_attempt"

# The decomposer's own account of an ordinary split: why it split, and on a
# parent that is no umbrella, the work it kept for the parent's own pass.
# Written in the same write as the expected count, ahead of the first child,
# so a split a crash or a failed create stops short of still holds it through
# its recovery, with no decomposer run to recover it from. Every split writes
# it over -- `None` where its manifest gave no usable text -- so no split is
# read back with an earlier one's account. Whatever supersedes the split
# clears it the same way -- a `single` decision, an edit's reset of the
# manifest, a pre-implementation reroute -- and a restart's projection drops
# it, while the handoff back to the parent's own work once every child is
# done keeps it as the scope that work was left -- the scope that work's
# developer prompts quote off this record
# (`engine/decomposition_prompts._handed_split_rationale`).
_SPLIT_RATIONALE = "split_rationale"

_CREATED_AT = "created_at"

# A reroute `ready` landed and still owes its relabel to `decomposing`: the
# children its reset stopped tracking, for the notice that names them, whether
# the baseline it compared against was missing rather than moved, and the
# receipt that notice carries, so a later `ready` tick finds it rather than
# saying it twice.
# Written in the same checkpoint as the reset it describes, so a `ready` tick
# reading it knows the reset is already in place -- its baseline included, which
# would otherwise read as requirements nobody changed -- and finishes the
# relabel rather than handing the issue to implementation. Dropped by the
# `decomposing` tick ahead of its drift check, recovery, and decomposer, so no
# later entry to `ready` reads it (`stages/decomposition/ready.py`).
_READY_REROUTE = "ready_reroute"

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


def _names_an_issue(linked: Any) -> bool:
    """Whether a recorded `parent_number` is an issue number at all.

    Spelled once because recovery, recognition, release, and the hold on a
    child its split never seeded all take the link as proof of parentage, and
    only an issue number proves it: JSON carries `41.0` and `true` as values
    Python compares equal to 41 and 1, and neither is one any writer here
    produced, so each names no parent at all.
    """
    return _formats.whole_number(linked) and linked > 0


def _links_to(linked: Any, parent: int) -> bool:
    """Whether a recorded `parent_number` is exactly `parent`'s issue number."""
    return _names_an_issue(linked) and linked == parent


def _split_rationale_text(raw: Any) -> str | None:
    """The text a split's rationale field carries, or None where it carries none a reader can use.

    Read as absent rather than refused, because a rationale decides nothing: a
    missing, null, blank, or non-string value leaves an otherwise valid split
    valid, and a record an older binary or a hand edit left that way reads back
    as no rationale. Kept stripped, and cut to the bound and marker a late
    record keeps a decomposer's rationale at, since it sits in the pinned
    comment every stage shares and a write past that comment's size would
    refuse the split it explains.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    return _late_result_payloads._bounded_rationale(raw.strip())


def _recorded_split_rationale(state: PinnedState) -> str | None:
    """The rationale this parent's latest split recorded, or None where it recorded none a reader can use."""
    return _split_rationale_text(state.get(_SPLIT_RATIONALE))


def _issue_ref_list(numbers: list) -> str:
    """Render issue/child numbers as a `#a, #b` comma-joined reference list."""
    return ", ".join(f"#{number}" for number in numbers)
