# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recover or create the exact issue for one late-split manifest slice.

Resumed creation looks for the cycle receipt before opening an issue.
Ambiguous, closed, or already-started orphans are refused, and the close
latch is checked again after the repository lookup.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import issues as _github_issues
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
)
from orchestrator.workflow.stages.decomposition import (
    child_creation as _child_creation,
    late_child_content as _late_child_content,
    late_child_records as _late_child_records,
    late_owner as _late_owner,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

log = logging.getLogger("orchestrator.workflow")



class _StrandedChild(Exception):
    """An issue this walk found for a slice and may not take over.

    Carries the sentence the park is made of, because the two reasons a
    candidate is refused are different things to tell a human: one is an
    issue a human acted on, the other is an issue whose receipt does not say
    which slice it belongs to.
    """

    def __init__(self, number: int, described: str) -> None:
        super().__init__(described)
        self.number = number
        self.described = described


_STRANDED_CHILD = (
    "child #{number}, created by an earlier pass of this split and never "
    "recorded on this issue"
)

_AMBIGUOUS_RECEIPT = (
    "issue #{number}, which carries the receipt for slice {index} of this "
    "split beside another slice's -- so nothing here can say which slice it "
    "was created for, and adopting it would attribute one issue to two"
)


def _child_issue(
    context: _LateContext, walk: _late_child_records._ChildWalk, index: int, child: dict,
) -> Issue | None:
    """Adopt the child this index already has, or create it exactly once.

    Adoption is what keeps a retry from opening a second issue for a slice
    that already has one: the parent's own recorded list is the register, and
    it is written in the same durable step the creation is.

    None is "create nothing further", and the record says which of the two
    reasons it was: a park this step could not get past, or a cancellation a
    latched close earned while the lookup was running.
    """
    try:
        return _adopted_or_created(context, walk, index, child)
    except _StrandedChild as stranded:
        log.error(
            "issue=#%d may not take #%d over for slice %d: %s",
            context.issue.number, stranded.number, index, stranded.described,
        )
        _late_child_records._parked(context, stranded.described)
        return None
    except Exception:
        log.exception(
            "issue=#%d could not establish late split child %d (%r)",
            context.issue.number, index, child.get(_late_child_content._TITLE),
        )
        _late_child_records._parked(context, f"child {index} ({child.get('title')!r})")
        return None


def _adopted_or_created(
    context: _LateContext, walk: _late_child_records._ChildWalk, index: int, child: dict,
) -> Issue | None:
    """Return the child at this index, opening one only where none exists.

    Three answers in order, and the middle one is the whole point. A number
    this generation already recorded is the ordinary resume. A marker still
    on GitHub with no number beside it is the crash between the create and
    the write that would have recorded it -- adopted rather than duplicated,
    which is the only recovery for a create nothing outside GitHub knows
    about. Only past both is an issue actually opened.

    None is a fourth answer and it belongs to the create alone: the lookup
    above walks the repository, so the latch is asked again against the step
    that would open a real issue somebody then works. The mark it leaves is
    what tells the loop this was a cancellation rather than a park.
    """
    if index < len(walk.known):
        return context.gh.get_issue(walk.known[index])
    # Past here the first UNRECORDED index has been answered, so nothing an
    # earlier attempt made is left for the register to be missing.
    walk.past_the_unrecorded()
    orphan = _orphan_for(context, walk, index)
    if orphan is not None:
        log.warning(
            "issue=#%d adopting orphan child #%d for slice %d: it was created "
            "and never recorded",
            context.issue.number, orphan.number, index,
        )
        return orphan
    if _late_owner._latch_stops(context) is not None:
        log.warning(
            "issue=#%d was observed closed while slice %d was being looked "
            "up; opening no issue for it",
            context.issue.number, index,
        )
        return None
    return context.gh.create_child_issue(
        title=child[_late_child_content._TITLE],
        body=_late_child_content._child_body(context, child, walk.snapshot_ref, index),
        parent_number=context.issue.number,
        labels=_child_creation._child_initial_labels(),
    )


def _orphan_for(
    context: _LateContext, walk: _late_child_records._ChildWalk, index: int,
) -> Issue | None:
    """The issue an earlier pass created for this slice and never recorded.

    Asked only on a resumed pass. The lookup is a walk over the repository's
    issues in every state, which is what a marker nobody indexed costs -- and
    a first pass has nothing to find, since no earlier one has run. What says
    an earlier one did is the expected count already standing on the parent
    before this pass wrote its own.

    A candidate a human has since closed, or moved off the label a child is
    born on, is refused rather than adopted. Reopening or re-labelling it
    would undo a deliberate act on an issue this orchestrator had not even
    attributed yet, and creating a second one beside it would be worse -- so
    the transaction parks and lets them say which they meant.
    """
    if not walk.resumed:
        return None
    marker = _late_child_content._child_marker(context.generation, index)
    orphan = context.gh.find_issue_carrying(marker)
    if orphan is None:
        return None
    if not _sole_receipt(orphan, marker):
        raise _StrandedChild(
            orphan.number,
            _AMBIGUOUS_RECEIPT.format(number=orphan.number, index=index),
        )
    if _github_issues.issue_is_closed(orphan) or _moved_off_blocked(context, orphan):
        raise _StrandedChild(
            orphan.number, _STRANDED_CHILD.format(number=orphan.number),
        )
    return orphan


def _sole_receipt(orphan: Issue, marker: str) -> bool:
    """Whether this candidate carries THIS receipt and no other slice's.

    The lookup that found it matches a marker as a substring, which is all a
    body search can do -- and a body carries agent-declared scope above the
    marker this transaction stamped in. An issue whose body holds two child
    receipts answers the search for either slice, so adopting on the strength
    of the match alone lets one issue be recorded as two children of the same
    split, each seeded with the other's scope.

    Declared scope carrying a receipt is refused where it is declared, so this
    can only be an issue an older binary created or a human edited. It is
    still asked, because those are exactly the issues nothing else vouches
    for. A body that could not be read carries no receipt this can point at
    and is refused the same way.
    """
    body = getattr(orphan, "body", "") or ""
    return marker in body and body.count(_ancestry.CHILD_RECEIPT) == 1


def _moved_off_blocked(context: _LateContext, orphan: Issue) -> bool:
    """Whether somebody has taken this child off the label it was born on."""
    return context.gh.workflow_label(orphan) != _child_creation._child_initial_labels()[0]
