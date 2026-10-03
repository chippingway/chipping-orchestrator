# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The receipt an ordinary split would stamp into each child, and the adoption it lets a recovery make.

A split records each child on its parent in the write right behind the create
that opened it, and a process can die between the two. The issue then exists
and nothing outside GitHub knows its number, so the only way back to it is
something the split put IN it: a hidden marker naming the parent, the split
attempt, and the slice. The attempt is minted for each split and belongs on
the parent's `split_attempt` in the same write as the expected count and the
dependency graph -- ahead of the first child -- so a receipt an earlier split
of the same issue stamped is never read as this one's.

A recovery that finds the parent short of its count looks for the one slice a
crash can leave unrecorded: the next one, since the loop records each child
before it creates another. An issue this orchestrator opened whose last
whole receipt is that one, open and still on the label a child is born with,
is recorded on the parent -- and, in that same write, on the consumer ledger of
the snapshot the parent's proved lineage points its children at, exactly as
the write the crash lost would have recorded it. The entitlement comes from
that lineage rather than from the child's text, which anyone may have edited
since. One closed or relabelled is something a human acted on, and one
ending on another receipt -- or on none whole -- is one nothing can
attribute, so it is neither adopted nor reported as absent: the answer names
it for a park. A parent with no attempt
this binary minted -- one an older binary split -- leaves nothing to look for.

The receipt also names the lineage the split owed its child -- root, depth,
cycle, and generation under the parent it names, or none -- decided off the
parent's record before the child existed. The last whole receipt in a body is
the one that counts, since the split stamps it after the declared slice and a
slice may quote another child's body, receipt and all, ahead of it.
`split_seeds` holds a child's pinned seed to it.

Dormant: no split mints an attempt or stamps a receipt yet, and no recovery
adopts, so every child is still created with neither and a short register
still parks as it always has.
"""
from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split.ancestry import LateAncestry
from orchestrator.workflow.stages.decomposition import (
    child_creation as _child_creation,
    replacement_lineage as _replacement_lineage,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_RECEIPT = "<!--orchestrator-split-child:"

_BODY = "body"

# What the child cut for one slice of one split is looked up by: everything
# ahead of the lineage, which closes the index so slice 1 never reads as 10.
_LOOKUP = f"{_RECEIPT}issue={{issue}}:attempt={{attempt}}:index={{index}}:lineage="

# The lineage a receipt says its split owed the child: root, depth, cycle, and
# generation under the parent the receipt names, or `none` for a split that
# owed it none.
_OWED = "{root}-{depth}-{cycle}-{generation}"

_NONE = "none"

# What `mint_attempt` writes, and so the only attempt a receipt is looked up
# by: a hand-edited value names no split this binary minted.
_ATTEMPT = re.compile("[0-9a-f]{16}")

_STRANDED = (
    "issue #{number} carries the receipt for slice {index} of this split and {why}, so it is neither adopted nor "
    "created again"
)

_CLOSED = "was closed before the split recorded it"

_MOVED = "was moved off the label a child is born with"

_UNATTRIBUTED = "its last whole receipt is not that one"

# A receipt read whole, exactly as `receipt` writes one: anything else -- a
# placeholder in prose quoting the format, a number edited out -- is no
# receipt, and claims no parent and no lineage.
_RECEIPT_READING = re.compile(
    rf"{re.escape(_RECEIPT)}issue=(?P<parent>\d+):attempt=[0-9a-f]{{16}}:index=\d+:lineage="
    rf"(?:{_NONE}|(?P<root>\d+)-(?P<depth>\d+)-(?P<cycle>\d+)-(?P<generation>\d+))-->",
)


@dataclass(frozen=True)
class Adoption:
    """The children a recovery holds a split to, and why an unrecorded one could not join them."""

    children: list
    stranded: str | None = None


def mint_attempt() -> str:
    """A fresh identity for one split, which no other split's receipt carries."""
    return secrets.token_hex(8)


def receipt(issue: int, attempt: str, index: int, owed: LateAncestry | None) -> str:
    """The hidden receipt the child cut for one slice of one split would be created carrying.

    `owed` is the lineage the split would seed that child with, its pointer
    aside, or None -- or the empty ancestry -- for a split that seeds none.
    """
    lineage = _NONE if owed is None or not owed.is_present else _OWED.format(
        root=owed.root_issue, depth=owed.lineage_depth, cycle=owed.cycle_id, generation=owed.generation,
    )
    return f"{_LOOKUP.format(issue=issue, attempt=attempt, index=index)}{lineage}-->"


def stamped(
    children: list, issue_number: int, attempt: str, lineage: _replacement_lineage.ReplacementLineage,
) -> list:
    """Every declared child with its receipt after its body, and any reuse instructions after that."""
    receipted = []
    for index, child in enumerate(children):
        stamp = receipt(issue_number, attempt, index, lineage.ancestry)
        sections = (child[_BODY], stamp, lineage.instructions)
        receipted.append({**child, _BODY: "\n\n".join(filter(None, sections))})
    return receipted


def owed_by(body: object) -> LateAncestry | None:
    """The lineage the last whole receipt in a body says its split owed, or None where it carries none.

    The last, because `stamped` writes the receipt after the declared slice
    and nothing but reuse instructions after it, and an ordinary manifest's
    slice may quote the body of a parent that was itself a split's child --
    receipt and all -- so the first could be the parent's own.

    Its `parent_issue` is the parent that receipt names; a split that owed no
    lineage answers that parent and nothing else, which `is_present` reads
    as no lineage at all.
    """
    if not isinstance(body, str):
        return None
    readings = list(_RECEIPT_READING.finditer(body))
    if not readings:
        return None
    read = readings[-1]
    parent = int(read["parent"])
    if read["root"] is None:
        return LateAncestry(parent_issue=parent)
    return LateAncestry(
        root_issue=int(read["root"]),
        lineage_depth=int(read["depth"]),
        parent_issue=parent,
        cycle_id=int(read["cycle"]),
        generation=int(read["generation"]),
    )


def adopt_unrecorded(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, recorded: list,
) -> Adoption:
    """Record the child a crash left created and unrecorded, where there is one to find.

    For a parent short of its expected count. The lookup walks the
    repository's issues in every state, the price of a marker nobody indexed,
    so a recovery would ask it once: the answer either completes the register
    or parks the split. The adopted child is recorded -- and protected, where the
    lineage asked off the parent's record now points its children at a
    snapshot -- in its own parent write, so a crash behind it leaves a
    register the next recovery reads as complete and a ref kept for the child
    it names. A lineage that no longer points, or no longer proves, protects
    nothing here; the recovery that follows seeds or refuses the child on it.
    """
    attempt = state.get(_state._SPLIT_ATTEMPT)
    if not isinstance(attempt, str) or _ATTEMPT.fullmatch(attempt) is None:
        return Adoption(list(recorded))
    lookup = _LOOKUP.format(issue=issue.number, attempt=attempt, index=len(recorded))
    orphan = gh.find_issue_carrying(lookup)
    if orphan is None:
        return Adoption(list(recorded))
    stranded = _unadoptable(gh, orphan, lookup, len(recorded))
    if stranded is not None:
        return Adoption(list(recorded), stranded)
    log.warning(
        "issue=#%s adopting child #%s for slice %d: it was created and never recorded",
        issue.number, orphan.number, len(recorded),
    )
    adopted = [*recorded, orphan.number]
    state.set(_state._CHILDREN, adopted)
    _replacement_lineage.read_replacement_lineage(state, issue, spec).protect(state, orphan.number)
    gh.write_pinned_state(issue, state)
    return Adoption(adopted)


def _unadoptable(gh: GitHubClient, orphan: Issue, lookup: str, index: int) -> str | None:
    """Why this candidate may not be taken over as slice `index`'s child, said for the park, or None.

    The lookup matches a receipt as a substring, so it finds a body quoting
    that receipt as readily as one stamped with it, and a receipt cut short as
    readily as a whole one. Attribution is the last whole receipt, read as
    `owed_by` reads it: the split stamps its own after the slice, so one the
    slice quoted ahead of it is not a second claim, while one appended behind
    it, or a body ending on no whole receipt, names nothing this split can
    vouch for. A closed candidate, or one moved off the label it was born on,
    is one a human acted on before anything here attributed it: reopening or
    relabelling it would undo that, and creating a second beside it is worse.
    """
    body = getattr(orphan, _BODY, "") or ""
    readings = list(_RECEIPT_READING.finditer(body))
    final = readings[-1].group(0) if readings else ""
    why = None
    if not final.startswith(lookup):
        why = _UNATTRIBUTED
    elif issue_is_closed(orphan):
        why = _CLOSED
    elif gh.workflow_label(orphan) != _child_creation._child_initial_labels()[0]:
        why = _MOVED
    if why is None:
        return None
    return _STRANDED.format(number=orphan.number, index=index, why=why)
