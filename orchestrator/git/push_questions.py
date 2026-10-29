# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The question a caller asks immediately before a push leaves this host.

The push transport (`branch_transport._push_branch`) prepares every push the
same way -- the token, the refusal of a worktree whose own config could send
a token-bearing push somewhere else, the askpass session -- and each of those
runs after whatever the caller last established about the worktree. A caller
whose push is only right while the checkout is still the one it proved hands
that question in here for the length of the push; the transport asks it after
every preparation and immediately before `git push`, and whatever it raises
leaves nothing sent. A push leased explicitly takes no reading between the
two, so nothing but the command itself follows the answer.

Kept apart from the transport so the transport stays the one owner of how a
push is made, and so the question needs no argument every caller of the
transport would have to thread through. The value is per execution context,
so the threads a tick fans out across never see each other's question.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial

_QUESTION: ContextVar[Callable[[], object] | None] = ContextVar("push_question", default=None)


@contextmanager
def asked_before_the_push(question: Callable[..., object], *args, **kwargs) -> Iterator[None]:
    """Have `question(*args, **kwargs)` asked immediately before each push made inside the block."""
    token = _QUESTION.set(partial(question, *args, **kwargs))
    try:
        yield
    finally:
        _QUESTION.reset(token)


def _asks() -> None:
    """Ask the question a caller handed in for this push, where one stands."""
    question = _QUESTION.get()
    if question is not None:
        question()
