# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The question a recovery asks immediately before a captured completion is handed on or invalidated.

A capture's transfer into the delivery (`completion_handoff.transfer`) and its
guarded invalidation (`completion_checkpoint.retire`) each read the comment
afresh, and then send their edit through the guarded commit
(`pinned_commit.commit`), which reads it once more. A recovery owner finishing
an admitted capture on its stage's disposition has to have the capture's
admission read again behind every one of those requests too, and immediately
before the edit: a control applied, a relabel, a close, an edit, or a push
landing during any of them is a handoff or a retirement the issue no longer
admits. So the owner hands that question in here for the length of its
disposition, and the guarded commit asks it last of every edit, behind its own
reading and immediately before the edit goes out, over the comment it read and
the candidate it would leave. The question answers for the one write that
moves the pending capture it finishes -- its transfer, or its invalidation --
and lets every other through; an answer that the capture no longer stands
refuses the commit with nothing sent
(`pinned_commit_models.CommitRefusal.MOVED_BEHIND`).

Kept apart from the guarded commit so it needs no argument every disposition
between the owner and the write would have to thread through, and so the
engine asks a question its stages own without importing them. The value is
per execution context, so the threads a tick fans out across never see each
other's question, and a commit outside a recovery -- a live tick's, or the
dispatcher's own invalidation -- asks nothing.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

# A pinned comment as a commit reads it, or the candidate it would leave.
Spelling = Mapping[str, Any]

# A question over the comment a commit read and the candidate it would leave.
Question = Callable[[Spelling, Spelling], bool]

_QUESTION: ContextVar[Question | None] = ContextVar("completion_question", default=None)


@contextmanager
def asked_before_the_write(question: Question) -> Iterator[None]:
    """Have `question(read, candidate)` asked immediately before each guarded edit made inside the block."""
    token = _QUESTION.set(question)
    try:
        yield
    finally:
        _QUESTION.reset(token)


def stands(read: Spelling, candidate: Spelling) -> bool:
    """Whether an edit leaving `candidate` over the comment `read` may go out: True where no question stands."""
    question = _QUESTION.get()
    return question is None or question(read, candidate)
