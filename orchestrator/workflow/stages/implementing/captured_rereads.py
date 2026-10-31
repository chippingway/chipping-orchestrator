# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The admission a recovery reads again immediately before a captured report is handed on or withdrawn.

A recovery owner finishes an admitted capture through its stage's existing
disposition, and that disposition takes readings of its own before the report
is handed to the delivery or withdrawn ahead of a park: a pull request
fetched, a watermark carry over both comment surfaces, a remote fetch proving
the tip a publication replaces -- and then the write's own read of the
comment. Each is a request a human can land a move behind -- a control
applied, a relabel, a close, an edit, a push -- and the capture may be handed
on or retired only over readings that still admit it. So the owner runs its
disposition inside `rereads(admitted)`, which hands the engine the question
the guarded commit asks last of every edit, behind its own reading and
immediately before the edit goes out (`engine/completion_questions`): an
edit moving the pending capture `admitted` finishes -- its transfer, or its
invalidation -- has every reading a handoff's effect stands on taken again
(`completion_effect.admitted_again`), and anything but APPLICABLE refuses
the commit with nothing sent, the caller's state withheld and the tick held
for the next dispatch to decide afresh. Every other edit goes through.

Outside a recovery nothing is asked: a live tick honors the hold its run's
return read, whatever a later fetch sees.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial

from orchestrator.workflow.engine import (
    completion_effect as _effect,
    completion_questions as _questions,
    completion_records as _records,
    completion_recovery_models as _recovery_models,
    completion_spelling as _spelling,
)

log = logging.getLogger("orchestrator.workflow")


@contextmanager
def rereads(admitted: _recovery_models.AdmittedCompletion) -> Iterator[None]:
    """Have `admitted` read again immediately before its capture is handed on or withdrawn inside the block."""
    with _questions.asked_before_the_write(partial(_stands, admitted)):
        yield


def _stands(
    admitted: _recovery_models.AdmittedCompletion, read: _questions.Spelling, candidate: _questions.Spelling,
) -> bool:
    """Whether an edit leaving `candidate` over `read` may go out, read again where it moves `admitted`'s capture.

    True for an edit that leaves that pending capture as `read` carries it,
    and where every reading a handoff's effect stands on answers as the
    admission read it.
    """
    captured = read.get(_records.DEVELOPER_COMPLETION)
    if captured == candidate.get(_records.DEVELOPER_COMPLETION):
        return True
    if _spelling.read_record(captured) != admitted.capture:
        return True
    again = _effect.admitted_again(admitted)
    if again.standing is _recovery_models.Standing.APPLICABLE:
        return True
    log.warning(
        "issue=#%d moved behind the readings its captured completion's recovery took (%s: %s); handing on "
        "and withdrawing nothing, for a later dispatch to decide",
        admitted.issue.number, again.standing, again.reason,
    )
    return False
