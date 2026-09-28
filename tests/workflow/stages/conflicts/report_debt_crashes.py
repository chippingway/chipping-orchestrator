# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The windows a conflict round's hand to `validating` opens, driven as failures.

Past a landed push the round still has three durable steps to take: the gate's
own write, carrying the publication receipt and the settled round beside it;
the write that records the report debt; and the relabel with the tail's write
behind it. A process ending before any of them leaves the issue on
`workflow:resolving_conflict` for a later tick to finish, and the debt has to
survive every one of them -- the first included, where all that is durable is
the approval the gate took before its push.

A process ending is spelled as a raise the case swallows, so what a test reads
afterwards is exactly the durable state a crash would have left. A write the
comment has no room for is the other failure: a field nothing reads fills the
comment to the boundary a case names, and sizing it again is a human making room.
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.stages.implementing import late_push as _late_push
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.conflicts.report_debt_support import DEBT

# A field nothing reads, sized to fill the pinned comment to a boundary.
_FILLER = "operator_note"


class _Crashed(RuntimeError):
    """The process ending where a case says it ends."""


def leaving_room(github, issue_number: int, staged: dict, *, room: int) -> None:
    """Fill the pinned comment so `room` characters are left once `staged` is written onto it.

    Negative is a comment that write would overflow by that many. The filler
    is sized off the comment as it stands, with an empty filler counted, so
    the boundary is the one GitHub would hold the write to.
    """
    pinned = github.pinned_data(issue_number)
    taken = len(_pinned_state.pinned_state_body({**pinned, _FILLER: "", **staged}))
    pinned[_FILLER] = "x" * (_pinned_state.MAX_PINNED_BODY - taken - room)
    github.seed_state(issue_number, **pinned)


@contextlib.contextmanager
def dying_after_the_push(github):
    """A process that ends once the push has landed, before the gate writes what it paid.

    What survives is the approval the gate wrote ahead of the push: the
    commit, the head it was leased against, and the route's spends.
    """
    with patch.object(
        _late_push, "_publication_paid", side_effect=_Crashed,
    ), contextlib.suppress(_Crashed):
        yield


@contextlib.contextmanager
def dying_on_the_debt(github):
    """A process that ends on the write that would record a report debt.

    The push has landed and the gate's own write -- the publication receipt
    and the settled round beside it -- is down; nothing past it is.
    """
    with patch.object(
        github, "write_pinned_state", _DiesOnTheDebt(github),
    ), contextlib.suppress(_Crashed):
        yield


@contextlib.contextmanager
def dying_on_the_handoff(github):
    """A process that ends as the round is relabelled to `validating`."""
    with patch.object(
        github, "set_workflow_label", _DiesHandingOn(github.set_workflow_label),
    ), contextlib.suppress(_Crashed):
        yield


class _DiesOnTheDebt:
    """The pinned writes a tick makes, ending on the first that changes the debt."""

    def __init__(self, github) -> None:
        self._github = github
        self._writes = github.write_pinned_state

    def __call__(self, issue, state):
        standing = self._github.pinned_data(issue.number)
        if state.get(DEBT) != standing.get(DEBT):
            raise _Crashed
        return self._writes(issue, state)


class _DiesHandingOn:
    """The relabels a tick makes, ending on the one onto `validating`."""

    def __init__(self, relabel) -> None:
        self._relabel = relabel

    def __call__(self, issue, label, **options):
        if label == WorkflowLabel.VALIDATING:
            raise _Crashed
        return self._relabel(issue, label, **options)
