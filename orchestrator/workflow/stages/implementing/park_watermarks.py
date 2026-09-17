# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reply watermark a park can advance past its own recorded notices.

A post can land above a human reply that arrived during the agent run. The
walk stops at the first comment the orchestrator id ledger does not claim, and
advances only through comments this tick actually posted and identified; only
a missing prior watermark uses the thread tip.

Every park that ends a RUN stamps through `_stamp_read_this_far`: the parks
that post for themselves call it directly, and the two timeout parks hand it to
`engine/guards.py`'s shared funnel as its `watermark` hook, so they keep the
one place failed-run parks are correlated from while still refusing that
funnel's own notice-id stamp. That stamp is right where no agent ran under it
-- the window it covers is the moment between its own post and its own write,
not minutes -- and wrong after a run, where the notice lands above the comment
a human wrote while the agent was out.

The hook's shape is this module's, not the funnel's: `(gh, issue, state,
said_before)`, taking the id ledger as it stood before the funnel's post.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.implementing import (
    state as _state,
)


def _read_this_far(
    gh: GitHubClient, issue: Issue, state: PinnedState, said_before: set,
) -> int | None:
    """How far a park ending a RUN may record this thread as read.

    Past every comment of ours above the watermark and past nothing else. A
    park's notice has to carry the watermark over itself, or the next tick
    reads our own sentence as somebody's fresh guidance and pays a developer
    to answer it. But the run this park ends took minutes, and a human writing
    in that window wrote something no reading here has looked at: carried to
    the thread's TIP instead, the notice takes their comment with it and it is
    skipped for good. On this stage that comment can be the
    `/orchestrator authorize-oversized` an adjudicated candidate is waiting
    for, and the only road that could act on it never sees it.

    So the walk stops at the first comment that is not ours, which is the
    boundary between what this tick read and what landed behind its back.
    Which comments are ours is read off the ledger every post writes to, since
    that is the one record here that names them.

    A post this ledger did not gain moves the watermark NOWHERE, and that is
    the same rule rather than an exception to it: what may be advanced through
    is a comment actually posted and identified, and an id nothing read
    identifies none. Left where it is, the mark is the one the resume settled
    to the reply the developer was handed, and the notice above it is refused
    by the very reading that would have answered it -- the frozen reply batch
    drops a body carrying our marker that the ledger cannot vouch for, so our
    own unrecorded sentence reaches no prompt and buys no developer. Taking
    the tip instead would buy that safety with the one thing this bound exists
    to keep: the comment a human wrote while the agent ran.

    One answer still falls back to the tip, and it is the lesser of what is
    left. A watermark that was never set is a tick with nothing to bound: the
    spawn behind it quoted the whole thread to the agent, so the comments
    below have been answered rather than missed, while a mark left unset would
    hand every one of them back as fresh guidance on the next poll.
    """
    ours = _comments._orchestrator_ids(state)
    if ours == said_before:
        return None
    read_to = state.get(_state._LAST_ACTION_COMMENT_ID)
    if not isinstance(read_to, int):
        return gh.latest_comment_id(issue)
    for seen in sorted(gh.comments_after(issue, read_to), key=_comment_id):
        if _comment_id(seen) not in ours:
            break
        read_to = _comment_id(seen)
    return read_to


def _stamp_read_this_far(
    gh: GitHubClient, issue: Issue, state: PinnedState, said_before: set,
) -> None:
    """Record the bounded reading on the state, where there is one to record.

    One helper rather than the same two lines at every park that ends a run --
    and the shape `engine/guards.py`'s `watermark` hook is called with, so the
    two timeout parks name this instead of writing the mark themselves.

    The conditional IS the rule: an answer of None is a thread this tick may
    not claim to have read any further than it already had, so the mark is
    left exactly where the resume settled it.
    """
    read_to = _read_this_far(gh, issue, state, said_before)
    if read_to is not None:
        state.set(_state._LAST_ACTION_COMMENT_ID, read_to)


def _comment_id(seen) -> int:
    """One comment's own address, or 0 for one nothing here can name."""
    identified = getattr(seen, "id", None)
    return identified if isinstance(identified, int) else 0
