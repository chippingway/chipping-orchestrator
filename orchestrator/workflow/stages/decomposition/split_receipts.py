# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The receipt an ordinary split stamps into each child, and the adoption it lets a recovery make.

A split records each child on its parent in the write right behind the create
that opened it, and a process can die between the two. The issue then exists
and nothing outside GitHub knows its number, so the only way back to it is
something the split put IN it: a hidden marker naming the parent, the split
attempt, and the slice. The attempt is minted for every split and written on
the parent in the same write as the expected count and the dependency graph --
ahead of the first child -- so a receipt an earlier split of the same issue
stamped is never read as this one's, and the slice a recovered child was cut
for still has its dependencies on record.

A recovery that finds the parent short of its count looks for the one slice a
crash can leave unrecorded: the next one, since the loop records each child
before it creates another. An issue this orchestrator opened carrying that
receipt and no other, open and still on the label a child is born with, is
recorded on the parent -- and, in that same write, on the consumer ledger of
the snapshot the parent's proved lineage points its children at, exactly as
the write the crash lost would have recorded it. The entitlement comes from
that lineage rather than from the child's text, which anyone may have edited
since: every child of a split that points is owed the pointer. From there it
is a recorded child like any other, held to the recovery's recognition and
seeded before anything finalizes the split. One closed, relabelled, or carrying a second
receipt is something a human acted on or nothing can attribute, so it is
neither adopted nor created again: the split parks. A split an older binary
prepared minted no attempt, which leaves nothing to look for.

Until its seed lands, a child carrying a receipt is held from running
anything of its own. A split that parks short of its count leaves the child it
adopted recorded and unseeded, and an edit can route that child into its own
decomposition -- where a pinned comment with no ancestry and no parent link
reads as an ordinary issue, and the children it splits into would start a
lineage over at depth 0. The parent link is the seed's own mark: a split
writes it together with whatever lineage the child is owed, so a receipt with
no link beside it is a child whose lineage nothing has proved yet.
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
from orchestrator.workflow.stages.decomposition import (
    child_creation as _child_creation,
    replacement_lineage as _replacement_lineage,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_RECEIPT = "<!--orchestrator-split-child:"

_BODY = "body"

_MARKER = f"{_RECEIPT}issue={{issue}}:attempt={{attempt}}:index={{index}}-->"

# What `mint_attempt` writes, and so the only attempt a receipt is looked up
# by: a hand-edited value names no split this binary minted.
_ATTEMPT = re.compile("[0-9a-f]{16}")

_STRANDED = (
    "issue #{number} carries the receipt for slice {index} of this split and {why}, so it is neither adopted nor "
    "created again"
)

_CLOSED = "was closed before the split recorded it"

_MOVED = "was moved off the label a child is born with"

_AMBIGUOUS = "carries another receipt beside it"

# The parent a receipt names, which the hold's notice points a human at.
_RECEIPT_PARENT = re.compile(rf"{re.escape(_RECEIPT)}issue=(\d+):")

_UNSEEDED = (
    "this issue was created by the split of #{parent}, and the seed that split owes it -- `parent_number` and any "
    "late lineage it inherits -- never landed. Decomposed or implemented like that, it would read as an issue no "
    "split made and start a lineage over at depth 0, so it is held here and runs nothing while that stands. Let "
    "#{parent}'s recovery seed it, or seed both on this issue's pinned record by hand."
)


@dataclass(frozen=True)
class Adoption:
    """The children a recovery holds a split to, and why an unrecorded one could not join them."""

    children: list
    stranded: str | None = None


def mint_attempt() -> str:
    """A fresh identity for one split, which no other split's receipt carries."""
    return secrets.token_hex(8)


def child_marker(issue: int, attempt: str, index: int) -> str:
    """The hidden receipt the child cut for one slice of one split is created carrying."""
    return _MARKER.format(issue=issue, attempt=attempt, index=index)


def stamped(children: list, issue_number: int, attempt: str, reuse: str) -> list:
    """Every declared child with its receipt after its body, and any reuse instructions after that."""
    receipted = []
    for index, child in enumerate(children):
        sections = (child[_BODY], child_marker(issue_number, attempt, index), reuse)
        receipted.append({**child, _BODY: "\n\n".join(filter(None, sections))})
    return receipted


def adopt_unrecorded(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, recorded: list,
) -> Adoption:
    """Record the child a crash left created and unrecorded, where there is one to find.

    Asked only of a parent short of its expected count. The lookup walks the
    repository's issues in every state, the price of a marker nobody indexed,
    and a recovery asks it once: the answer either completes the register or
    parks the split. The adopted child is recorded -- and protected, where the
    lineage asked off the parent's record now points its children at a
    snapshot -- in its own parent write, so a crash behind it leaves a
    register the next recovery reads as complete and a ref kept for the child
    it names. A lineage that no longer points, or no longer proves, protects
    nothing here; the recovery that follows seeds or refuses the child on it.
    """
    attempt = state.get(_state._SPLIT_ATTEMPT)
    if not isinstance(attempt, str) or _ATTEMPT.fullmatch(attempt) is None:
        return Adoption(list(recorded))
    orphan = gh.find_issue_carrying(child_marker(issue.number, attempt, len(recorded)))
    if orphan is None:
        return Adoption(list(recorded))
    why = _unadoptable(gh, orphan)
    if why is not None:
        stranded = _STRANDED.format(number=orphan.number, index=len(recorded), why=why)
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


def holds_unseeded(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Whether this issue is a split's child its seed never reached, held rather than decomposed.

    Asked of an issue about to decompose, ahead of the kill switch's hand-off
    to implementation and of the decomposer: either would run a child whose
    lineage nothing has proved. Parked with the reason a split whose lineage
    cannot be proved parks under, and only where it is not already awaiting a
    human: a park already standing -- this one, or the one its own blocked
    poll took -- keeps it held without the notice being said again, and a
    reply to it is no seed. A tick that finds it seeded -- by its parent's
    recovery, which lifts the park with the seed, or by hand -- lets the
    decomposition go on.
    """
    body = getattr(issue, _BODY, "") or ""
    claimed = _RECEIPT_PARENT.search(body)
    if claimed is None or _state._names_an_issue(state.get(_state._PARENT_NUMBER)):
        return False
    if not state.get(_state._AWAITING_HUMAN):
        notice = _UNSEEDED.format(parent=claimed.group(1))
        _replacement_lineage.park_unproved(gh, issue, state, notice)
    return True


def _unadoptable(gh: GitHubClient, orphan: Issue) -> str | None:
    """Why this candidate may not be taken over as the slice's child, or None.

    The lookup matches a receipt as a substring, and a body carrying two
    answers for either -- adopting it would attribute one issue to two
    slices. A closed candidate, or one moved off the label it was born on, is
    one a human acted on before anything here attributed it: reopening or
    relabelling it would undo that, and creating a second beside it is worse.
    """
    body = getattr(orphan, _BODY, "") or ""
    if body.count(_RECEIPT) != 1:
        return _AMBIGUOUS
    if issue_is_closed(orphan):
        return _CLOSED
    if gh.workflow_label(orphan) != _child_creation._child_initial_labels()[0]:
        return _MOVED
    return None
