# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reply watermark a park can advance past its own recorded notices.

A post can land above a human reply that arrived during the agent run. The
walk stops at the first comment the orchestrator id ledger does not claim;
only a missing ledger update or missing prior watermark uses the thread tip.
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

    Two answers fall back to the tip, and each is the lesser of what is left.
    A post whose id nothing could read adds nothing to that ledger, so no walk
    could pass our own notice and every tick after would answer it as
    guidance. And a watermark that was never set is a tick with nothing to
    bound: the spawn behind it quoted the whole thread to the agent, so the
    comments below have been answered rather than missed.
    """
    latest = gh.latest_comment_id(issue)
    ours = _comments._orchestrator_ids(state)
    read_to = state.get(_state._LAST_ACTION_COMMENT_ID)
    if ours == said_before or not isinstance(read_to, int):
        return latest
    for seen in sorted(gh.comments_after(issue, read_to), key=_comment_id):
        if _comment_id(seen) not in ours:
            break
        read_to = _comment_id(seen)
    return read_to


def _comment_id(seen) -> int:
    """One comment's own address, or 0 for one nothing here can name."""
    identified = getattr(seen, "id", None)
    return identified if isinstance(identified, int) else 0
