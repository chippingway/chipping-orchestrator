# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dispatch hold on a split's child whose seed is not the one its receipt says it was owed.

Every stage that could run a child of an ordinary split reads its lineage off
the pinned seed: its own decomposition asks it how deep the child sits before
splitting it again, and its size gate mints the generation of a split of its
own from it. A seed that never landed, or lost or changed the late ancestry
it was written with, reads as an issue no split made -- a fresh root at depth
0 with room for generations past the bound -- or as one at another place in
the lineage. The parent's walk refuses to release such a child, but a hand
relabel or an edit's reroute reaches the child's own handler without that
walk, so the dispatcher asks here before any of them runs -- pickup of a child
whose label was taken off included, the adjudication of a candidate of the
child's own too, and ahead of the reuse guard, which would otherwise ask the
remote about a pointer this refuses to believe.

What the child was owed is read off the last receipt in its body
(`owed_by`, over the receipt `split_receipts` writes), so the question costs
no request. Only a receipt on an
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
whatever it carries with that substitute. A tick that finds the seed whole
-- written by its parent's recovery, which lifts the park with the seed, or by
hand -- dispatches it as usual. Its terminals are left to their own no-op.

The seed outlives the child's own cycles for the same reason: an operator's
restart of a cycle the child's close cancelled keeps it (`carried_seed`),
since a restarted child is still the split's child its receipt names. And
because this hold reads the receipt, a recovery and a release ask the other
half before they seed or start a child (`stamp_lapse`): the receipt itself has
to be the one the split stamped for the child's slot, or the child would be
seeded or released there and held here.
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

_DUPLICATED = "child #{child} is not recorded exactly once in this split's register"

_MISSTAMPED = (
    "child #{child} carries a receipt that is not the one this split stamped for its slice -- another split's, "
    "another slice's, or one owing a lineage this split does not owe it"
)

# What a split writes onto its child's pinned record, and so what the receipt
# in that child's body holds the record to.
_SEED_KEYS = (_state._PARENT_NUMBER, *_lineage.LATE_ANCESTRY_KEYS)


def holds_unseeded(gh: GitHubClient, issue: Issue, label: str | None, state: PinnedState) -> bool:
    """Whether this issue is a split's child whose seed is not what it was owed, held rather than dispatched.

    Asked by the dispatcher of an issue under any label but a terminal --
    whose handler runs nothing -- ahead of the stage handler it names, and
    answered off the issue and the record the dispatcher already holds.
    """
    owed = None if label in _ENDED else _owed(gh, issue)
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


def carried_seed(gh: GitHubClient, issue: Issue, state: PinnedState) -> dict[str, object]:
    """The seed fields a split's receipted child carries, kept across a restart; none for any other issue.

    A restart keeps what is true about the issue rather than the attempt that
    ended, and a split's child's seed is that: where it sits in its tree, held
    to its receipt on every later dispatch. Kept exactly as carried -- the
    pointer too, which the reuse guard checks the body's instructions by --
    and nothing of the cycle that ended: no candidate or authorization.
    """
    if _owed(gh, issue) is None:
        return {}
    return {key: state.get(key) for key in _SEED_KEYS if state.carries(key)}


def stamp_lapse(
    gh: GitHubClient, parent: Issue, state: PinnedState, child: Issue, owed: LateAncestry | None,
) -> str | None:
    """Why a recorded child of `parent` is not the slice its receipt says it is, as a refusal notice; or None.

    Asked by a recovery and a release before they seed or start a child,
    since this hold later holds its seed to the receipt: its last whole
    receipt has to be exactly the one stamped for the slot the register names
    it in, once -- this parent, the recorded attempt, that slice, and `owed`.
    A child with no receipt (an older binary's split) answers the rest alone.
    """
    register = state.get(_state._CHILDREN) or []
    if register.count(child.number) != 1:
        return _replacement_lineage._CHILD_NOTICE.format(reason=_DUPLICATED.format(child=child.number))
    attempt = state.get(_state._SPLIT_ATTEMPT)
    stamped = None
    if isinstance(attempt, str):
        stamped = _split_receipts.receipt(parent.number, attempt, register.index(child.number), owed)
    if _owed(gh, child) is None:
        return None
    if _split_receipts.final_receipt(child.body) == stamped:
        return None
    return _replacement_lineage._CHILD_NOTICE.format(reason=_MISSTAMPED.format(child=child.number))


def owed_by(body: object) -> LateAncestry | None:
    """The lineage the last whole receipt in a body says its split owed, or None where it carries none.

    The last, because the split writes the receipt after the declared slice
    and nothing but reuse instructions after it, and an ordinary manifest's
    slice may quote the body of a parent that was itself a split's child --
    receipt and all -- so the first could be the parent's own.

    Its `parent_issue` is the parent that receipt names; a split that owed no
    lineage answers that parent and nothing else, which `is_present` reads
    as no lineage at all.
    """
    read = _split_receipts._RECEIPT_READING.fullmatch(_split_receipts.final_receipt(body))
    if read is None:
        return None
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


def _owed(gh: GitHubClient, issue: Issue) -> LateAncestry | None:
    """The lineage the last receipt in this issue's body says its split owed it, or None.

    Only on an issue this orchestrator opened, since a body is a field anyone
    can paste a receipt into.
    """
    if not authored_by_us(issue, bot_login=getattr(gh, "_bot_login", None)):
        return None
    return owed_by(getattr(issue, "body", None))


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
