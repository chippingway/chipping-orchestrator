# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dispatch hold on a split's child whose seed is not the one its receipt says it was owed.

Every stage that could run a child of an ordinary split reads its lineage off
the pinned seed: its own decomposition asks it how deep the child sits before
splitting it again, and its size gate mints the generation of a split of its
own from it. A seed that never landed, or lost or changed the late ancestry
it was written with, reads as an issue no split made -- a fresh root at depth
0 with room for generations past the bound -- or as one at another place in
the lineage. A hand relabel or an edit's reroute reaches the child's own
handler without its parent's walk, so this is the question a dispatcher asks
before any of them runs.

What the child was owed is read off the last receipt in its body (see
`split_receipts`), so the question costs no request. Only a receipt on an
issue this orchestrator opened counts, since a body is a field anyone can
paste into. The seed has to carry a `parent_number` that is exactly the
parent the receipt names, and the late ancestry group exactly as the receipt
owes it: none of it on a child owed none, and the whole group -- written back
exactly as the comment carries it, at that root, depth, parent, cycle, and
generation -- on one owed a lineage. A pointer is the one part a seed may
lack, because the child's own reuse guard takes the ref and its commit off
together once the ref is gone; a pointer it does carry has to be that pair
whole, naming the snapshot the parent's own split preserved under that
identity, since half of one names no commit or no ref to fetch it from.

A child held here is parked with the reason a split whose lineage cannot be
proved parks under, once: a park already standing keeps it held without the
notice being said again, and a reply to it is no seed. A pinned comment that
will not parse is held too, with nothing written and nothing said but the log
on every tick: it reads back empty, and the park's write would replace
whatever it carries with that substitute. A seed made whole -- by its
parent's recovery or by hand -- lets it run as usual. Its terminals are left
to their own no-op.

Dormant: no dispatcher asks this yet, and no split stamps the receipt it
reads, so nothing is held here.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.git.snapshots import namespace as _snapshot_namespace
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import authored_by_us
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import lineage as _lineage
from orchestrator.workflow.late_split.ancestry import LateAncestry
from orchestrator.workflow.stages.decomposition import (
    replacement_lineage as _replacement_lineage,
    split_receipts as _split_receipts,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The labels whose handlers run nothing, which the hold leaves to them.
_ENDED = frozenset((WorkflowLabel.DONE, WorkflowLabel.REJECTED))

_UNSEEDED = (
    "this issue was created by the split of #{parent}, and its pinned record is not the seed that split owes it: "
    "{lapse}. Decomposed or implemented like that, it would read as an issue no split made, or as one at another "
    "place in its lineage, and start whatever it creates there -- so it is held under every label and runs "
    "nothing while that stands. Let #{parent}'s recovery seed it, or write `parent_number` and the late lineage "
    "the receipt in this issue's body names onto its pinned record by hand."
)

_UNLINKED = "it carries no `parent_number` naming #{parent}"

_MISSING = "it carries none of the late lineage that split owes it"

_FOREIGN_POINTER = "its late ancestry points at `{ref}`, which is not the snapshot that split preserved"

_HALF_POINTER = (
    "its late ancestry carries half a snapshot pointer -- a ref without its commit, or a commit without its ref"
)


def holds_unseeded(gh: GitHubClient, issue: Issue, label: str | None, state: PinnedState) -> bool:
    """Whether this issue is a split's child whose seed is not what it was owed, held rather than dispatched.

    For an issue under any label but a terminal -- whose handler runs
    nothing -- ahead of the stage handler it names, answered off the issue
    and the record a dispatcher already holds.
    """
    ours = authored_by_us(issue, bot_login=getattr(gh, "_bot_login", None))
    if label in _ENDED or not ours:
        return False
    owed = _split_receipts.owed_by(getattr(issue, "body", None))
    if owed is None:
        return False
    if not state.parsed:
        log.error(
            "issue=#%s carries a receipt of #%s's split and a pinned comment that will not parse; "
            "holding it with nothing written over that comment", issue.number, owed.parent_issue,
        )
        return True
    lapse = _lapse(state, owed, issue.number)
    if lapse is None:
        return False
    if not state.get(_state._AWAITING_HUMAN):
        notice = _UNSEEDED.format(parent=owed.parent_issue, lapse=lapse)
        _replacement_lineage.park_unproved(gh, issue, state, notice)
    return True


def _lapse(state: PinnedState, owed: LateAncestry, number: int) -> str | None:
    """Why this child's seed is not the one `owed` describes, or None where it is.

    The recognition a recovery and a release hold a recorded child to, with
    the parent link required rather than left for a recovery to backfill --
    nothing here writes one -- and with a lineage owed required to be there.
    """
    if not _state._links_to(state.get(_state._PARENT_NUMBER), owed.parent_issue):
        return _UNLINKED.format(parent=owed.parent_issue)
    carried = any(state.carries(key) for key in _lineage.LATE_ANCESTRY_KEYS)
    if owed.is_present and not carried:
        return _MISSING
    unrecognized = _replacement_lineage._unrecognized(
        state, owed if owed.is_present else LateAncestry(), owed.parent_issue, number, promised=True,
    )
    return unrecognized or _pointer_lapse(state, owed)


def _pointer_lapse(state: PinnedState, owed: LateAncestry) -> str | None:
    """Why the pointer a recognized seed carries is not the one its split preserved, or None.

    Only a seed owed a lineage reaches here carrying any of the group, and the
    one ref that lineage could point at is the one its identity mints. The ref
    and its commit stand or go together: neither half is a pointer anything
    can fetch.
    """
    recorded = _lineage.read_late_ancestry(state)
    pair = (recorded.snapshot_ref, recorded.snapshot_sha)
    if not any(pair):
        return None
    if not all(pair):
        return _HALF_POINTER
    kept = _snapshot_namespace.snapshot_ref(
        issue_number=owed.parent_issue, cycle_id=owed.cycle_id, generation=owed.generation,
    )
    return None if recorded.snapshot_ref == kept else _FOREIGN_POINTER.format(ref=recorded.snapshot_ref)
