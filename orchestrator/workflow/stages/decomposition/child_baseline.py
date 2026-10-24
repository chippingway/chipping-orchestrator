# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The requirements baseline a split's child is seeded with: what it was created saying, and nothing later.

A child's drift baseline is the `user_content_hash` its own drift check
compares the thread against, and a child is created to carry exactly the
requirements its split cut for it. So the baseline is taken off the create
itself (`at_creation`): the title and body GitHub answered the create with --
the declared slice, the receipt, any snapshot reuse instructions, and the
`Parent:` footer the client appends -- and no comment, since a child is born
with none, hashed by the one definition every drift check hashes by
(`engine/content_hash`). An edit landing after the create -- before the seed,
or while a recovery is due -- is never part of it: the drift check is what
meets that edit, as an edit.

The seed records it once (`seed`). A record already carrying a baseline keeps
it, so a seed retried over its own landed write, or over a record another
writer reached first, never replaces the one established. A seed with no
proof of the creation content records none: a receipt proves which slice a
child was cut for, not what it said, so a child seeded without the create's
answer in hand -- recovered, or adopted by its receipt -- is left with its
baseline missing, never given one hashed off what the child says by then.
What a missing baseline means is the drift check's to decide
(`engine/drift`); here it holds nothing, since no seed, admission, or release
reads it.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import content_hash as _content_hash, drift as _drift


def at_creation(created: Issue) -> str:
    """The drift baseline of a child as its create answered it.

    Asked of the create's own answer before anything else is asked about the
    child, so what it hashes is what GitHub stored when it opened the issue,
    exactly as the child's drift check will read it back while it is unedited.
    """
    title = created.title or ""
    return _content_hash._hash_requirements(title, created.body or "", (), set())


def seed(child_state: PinnedState, baseline: str | None) -> None:
    """Record `baseline` as the child's drift baseline, where one is proved and none is established yet.

    Established is what the drift check reads as a baseline: a string. None
    -- nothing proved the creation content -- records nothing.
    """
    if baseline is not None and not isinstance(child_state.get(_drift._USER_CONTENT_HASH), str):
        child_state.set(_drift._USER_CONTENT_HASH, baseline)
