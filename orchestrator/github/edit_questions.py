# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The question a caller asks immediately before a strict rewrite of the pinned comment leaves this host.

The strict editor (`pinned_state.GitHubStateMixin.edit_pinned_state`) walks
the thread to the comment it rewrites, and that walk is the last reading
before the edit. A caller whose edit is only right while what it read
elsewhere still stands -- a recovery finishing a captured completion, whose
issue a human can pause, relabel, close, edit, or push to while any request
ahead of the edit is out, the walk included -- hands that question in here for
the length of its work. The editor asks it behind its walk, over the comment
that walk read and the state it would send, and immediately before the edit;
an answer that the edit no longer stands sends nothing
(`pinned_state.PinnedEdit.HELD`).

Kept apart from the editor so the editor stays the one owner of how a pinned
comment is rewritten, so the question needs no argument every caller between
the asker and the edit would have to thread through, and so this client asks
a question the workflow owns without importing it. The value is per execution
context, so the threads a tick fans out across never see each other's
question, and an edit made outside one asks nothing.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

# A pinned comment as the editor's walk read it, or the state it would send.
Spelling = Mapping[str, Any]

# A question over the comment the walk read and the state the edit would send.
Question = Callable[[Spelling, Spelling], bool]

_QUESTION: ContextVar[Question | None] = ContextVar("edit_question", default=None)


@contextmanager
def asked_before_the_edit(question: Question) -> Iterator[None]:
    """Have `question(read, candidate)` asked immediately before each strict edit made inside the block."""
    token = _QUESTION.set(question)
    try:
        yield
    finally:
        _QUESTION.reset(token)


def stands(read: Spelling, candidate: Spelling) -> bool:
    """Whether an edit sending `candidate` over the comment `read` may go out: True where no question stands."""
    question = _QUESTION.get()
    return question is None or question(read, candidate)
