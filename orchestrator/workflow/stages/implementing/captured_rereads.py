# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The admission a recovery reads again immediately before a captured report is handed on or withdrawn.

A recovery owner finishes an admitted capture through its stage's existing
disposition, and that disposition takes readings of its own before the report
is handed to the delivery or withdrawn ahead of a park: a pull request
fetched, a watermark carry over both comment surfaces, a remote fetch proving
the tip a publication replaces. Each is a request a human can land a move
behind -- a control applied, a relabel, a close, an edit, a push -- and the
capture may be handed on or retired only over readings that still admit it.
So the owner runs its disposition inside `rereads(admitted)`, and the
capture-aware recorder (`captured_report`) asks `holds` immediately before
the transfer and before a withdrawal: every reading a handoff's effect stands
on is taken again (`completion_effect.admitted_again`), and anything but
APPLICABLE withholds the state and holds the tick with nothing written, for
the next dispatch to decide afresh.

Outside a recovery nothing is asked: a live tick honors the hold its run's
return read, whatever a later fetch sees. Kept apart from the recorder so
the question needs no argument every disposition between the owner and the
recorder would have to thread through, and per execution context, so the
threads a tick fans out across never see each other's admission.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_effect as _effect,
    completion_records as _records,
    completion_recovery_models as _recovery_models,
)

log = logging.getLogger("orchestrator.workflow")

_ADMITTED: ContextVar[_recovery_models.AdmittedCompletion | None] = ContextVar("admitted_capture", default=None)


@contextmanager
def rereads(admitted: _recovery_models.AdmittedCompletion) -> Iterator[None]:
    """Have `admitted` read again immediately before its capture is handed on or withdrawn inside the block."""
    token = _ADMITTED.set(admitted)
    try:
        yield
    finally:
        _ADMITTED.reset(token)


def holds(state: PinnedState, pending: _records.CompletionCapture) -> bool:
    """Whether the recovery finishing `pending` no longer stands on readings that admit it; `state` withheld if so.

    False outside a recovery of that very capture, and where every reading
    a handoff's effect stands on answers as the admission read it.
    """
    admitted = _ADMITTED.get()
    if admitted is None or admitted.capture.invocation != pending.invocation:
        return False
    again = _effect.admitted_again(admitted)
    if again.standing is _recovery_models.Standing.APPLICABLE:
        return False
    state.withheld = True
    log.warning(
        "issue=#%d moved behind the readings its captured completion's recovery took (%s: %s); handing on "
        "and withdrawing nothing, for a later dispatch to decide",
        admitted.issue.number, again.standing, again.reason,
    )
    return True
