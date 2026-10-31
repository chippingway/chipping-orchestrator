# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The question a recovery asks immediately before a captured completion is handed on or invalidated.

A capture's transfer into the delivery (`completion_handoff.transfer`) and its
guarded invalidation (`completion_checkpoint.retire`) each read the comment
afresh, and a transfer may read the repository a verification names, before
the commit it sends. A recovery owner finishing an admitted capture on its
stage's disposition has to have the capture's admission read again behind
every one of those requests too, and immediately before the write: a control
applied, a relabel, a close, an edit, or a push landing during any of them is
a handoff or a retirement the issue no longer admits. So the owner hands that
question in here for the length of its disposition, and both writes ask it
last, after every reading of their own and immediately before their commit;
an answer that the capture no longer stands refuses the write with nothing
sent (`completion_commits.CheckpointRefusal.MOVED_BEHIND`).

Kept apart from the two writers so neither needs an argument every
disposition between the owner and the write would have to thread through,
and so the engine asks a question its stages own without importing them.
The value is per execution context, so the threads a tick fans out across
never see each other's question, and a write asked outside a recovery --
a live tick's, or the dispatcher's own invalidation -- asks nothing.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from orchestrator.agents.models import AgentInvocation

_QUESTION: ContextVar[Callable[[AgentInvocation], bool] | None] = ContextVar("completion_question", default=None)


@contextmanager
def asked_before_the_write(question: Callable[[AgentInvocation], bool]) -> Iterator[None]:
    """Have `question(invocation)` asked immediately before each handoff or invalidation made inside the block."""
    token = _QUESTION.set(question)
    try:
        yield
    finally:
        _QUESTION.reset(token)


def stands(invocation: AgentInvocation) -> bool:
    """Whether the capture of `invocation` may still be written over: True where no question stands."""
    question = _QUESTION.get()
    return question is None or question(invocation)
