# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Walk a late-split manifest while guarding each child creation and seeding step.

The owner is read before each slice. Each created child is recorded before
the close latch is checked again, so cancellation cannot strand an unnamed
issue or seed one its owner stopped wanting.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.workflow.stages.decomposition import (
    late_child_adoption as _late_child_adoption,
    late_child_records as _late_child_records,
    late_owner as _late_owner,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.models import _SplitPlan

log = logging.getLogger("orchestrator.workflow")


def _create_late_children(
    context: _LateContext, manifest: tuple, snapshot_ref: str,
) -> _SplitPlan | None:
    """Create or adopt every child of this split, in the crash-safe order.

    Returns the populated plan, or None when the loop stopped early -- a
    child that could not be created, recorded, or seeded, or an owner the
    close-check below found closed or unreadable. Either way the caller
    creates nothing further; which of the two it was is on the record.

    The owner is re-read before every child, the first included, because a
    create, a record, and a seed stand between each child and the next -- and
    the write that forces this issue to be an umbrella stands ahead of the
    first -- so a human can close the issue in any of those gaps. A close
    observed by the poll while this worker holds the issue reaches no other
    pass -- the scheduler admits no second worker for it -- so this loop is
    what stops the next child being opened against an issue somebody has
    ended.

    The read at the top of each turn is not the last word, either. Adopting
    a slice that was created and never recorded means walking the whole
    repository for its marker, which is minutes of remote work on a resumed
    pass, so the latch is asked ONE more time immediately before the create
    itself -- the one step here nothing takes back.
    """
    # Read before `_prepared` writes it: a count already there is the only
    # evidence a previous pass got as far as creating anything, and it is what
    # decides whether the orphan lookup below is worth a repository walk.
    resumed = context.state.get(_late_child_records._EXPECTED_CHILDREN) is not None
    _late_child_records._prepared(context, manifest)
    walk = _late_child_records._ChildWalk(
        plan=_SplitPlan.start(list(manifest), True),
        known=context.generation.split_children,
        snapshot_ref=snapshot_ref,
        resumed=resumed,
    )
    for index, child in enumerate(manifest):
        # Index 0 gets its own reading too, rather than borrowing the
        # caller's: `_prepared` above is a remote write, and a close landing
        # inside it would otherwise still open the first child.
        if _stopped(context, index):
            _late_child_records._sealed(context, walk)
            return None
        if not _placed(context, walk, index, child):
            _late_child_records._sealed(context, walk)
            return None
    return walk.plan


def _placed(
    context: _LateContext, walk: _late_child_records._ChildWalk, index: int, child: dict,
) -> bool:
    """Establish one slice's child, in the order a crash in it is safe in.

    Create or adopt, then record, then seed -- and False anywhere means the
    loop creates nothing further, with the record saying whether that was a
    park or the cancellation a latched close earned.
    """
    created = _late_child_adoption._child_issue(context, walk, index, child)
    if created is None:
        return False
    if not _late_child_records._recorded(context, walk, index, created, child):
        return False
    if _stopped_seeding(context, created):
        return False
    return _late_child_records._seeded(context, walk, created, child)


def _stopped_seeding(context: _LateContext, created: Issue) -> bool:
    """Whether a close latched inside the create stops this child's seed.

    The create is a request, so the close can land inside it -- and what it
    leaves is a real issue on GitHub. Recording that issue is not optional
    and is not touching it: the parent's own account is what makes the child
    reclaimable at all, and a child nothing names is the one state no pass
    can clean up. The SEED is a write to the child, and a cancelled cycle
    owes its children nothing -- they are not closed, not relabelled, and not
    written to, because what happens to them next is a human's decision.

    A child recorded and never seeded is a state the record already
    describes: the body carries the marker the create stamped into it, and
    the child's pinned comment carries nothing.
    """
    if _late_owner._latch_stops(context) is None:
        return False
    log.warning(
        "issue=#%d was observed closed while child #%d was being created; "
        "recording it and writing nothing to it",
        context.issue.number, created.number,
    )
    return True


def _stopped(context: _LateContext, index: int) -> bool:
    """Whether this issue has stopped wanting the children from here on.

    The reading is the guard's own and so is what it writes: a closed owner
    is marked cancelled where the loop stands, an unreadable one parks with
    the read owed, and only an open one lets the next child be opened.
    """
    if _late_owner._still_wanted(context) is None:
        return False
    log.warning(
        "issue=#%d is no longer known to want its split; creating none of "
        "its children from slice %d on", context.issue.number, index,
    )
    return True
