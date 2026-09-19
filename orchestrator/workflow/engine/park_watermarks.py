# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How far a park that ends an agent run may say this thread has been read.

A post can land above a human reply that arrived during the agent run. The
walk stops at the first comment the orchestrator id ledger does not claim, and
advances only through comments this tick actually posted and identified. It
never reads the thread's tip: a tip is where a comment nothing here has looked
at lands, and crossing one is the only failure on this road that a later poll
cannot undo.

It sits in the engine rather than in one stage because the park funnel in
`guards.py` beside it asks for it: `bounded=True` stamps this walk instead of
the id of the notice the park just posted. No stage passes that yet, and the
implementing stage's own `park_watermarks` keeps its tip fallback for the parks
that read it -- this owner is the bounded answer those parks are moved onto.

`guards.py` reads this owner rather than the other way round, so nothing here
may reach back for it: the park is built on the watermark, not beside it.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    prompt_delivery as _delivery,
)

log = logging.getLogger("orchestrator.workflow")


def _read_this_far(
    gh: GitHubClient, issue: Issue, state: PinnedState, said_before: set,
) -> int | None:
    """How far a park ending a RUN may record this thread as read, or None.

    Past every comment of ours above the watermark and past nothing else. A
    park's notice has to carry the watermark over itself, or the next tick
    reads our own sentence as somebody's fresh guidance and pays a developer
    to answer it. But the run this park ends took minutes, and a human writing
    in that window wrote something no reading here has looked at: carried to
    the thread's tip instead, the notice takes their comment with it and it is
    skipped for good.

    So the walk stops at the first comment that is not ours, which is the
    boundary between what this tick read and what landed behind its back.
    Which comments are ours is read off the ledger every post writes to, since
    that is the one record here that names them. The pinned state comment is
    left out of the read by its id and nothing else: read by its marker
    instead, a reply that merely quotes the marker is invisible to the walk,
    which then steps over it to the notice above and records it read.

    None -- the mark stays where it is -- answers three threads, and none of
    them may fall back to the tip:

    - A post this ledger did not gain. What may be advanced through is a
      comment actually posted and identified, and an id nothing read
      identifies none. Our own unrecorded sentence carries our marker with no
      ledger entry behind it, so every delivery reading refuses it as forged
      and the worst it costs is a poll rather than somebody's comment.
    - A thread with no watermark to walk from. The tip is where the comment
      written DURING the run is too, and nothing distinguishes the two by id.
    - A thread this call cannot re-read, which must not raise. Every caller
      asks this AFTER its notice is on the thread and BEFORE its own write
      records the park, so an exception here strands one notice said with
      nothing durable behind it, and the next poll reruns the agent the notice
      was about and says it again.
    """
    ours = _comments._orchestrator_ids(state)
    if ours == said_before:
        return None
    read_to = state.get(_delivery.PINNED_LAST_ACTION_COMMENT_ID)
    if not isinstance(read_to, int):
        return None
    try:
        thread = gh.comments_after(
            issue, read_to, state_comment_id=state.comment_id,
        )
    except Exception:
        log.exception(
            "issue=#%d could not be re-read for how far its park may record "
            "the thread as read; leaving the watermark where it was so the "
            "park itself is still recorded",
            issue.number,
        )
        return None
    for seen in sorted(thread, key=_comment_id):
        if _comment_id(seen) not in ours:
            break
        read_to = _comment_id(seen)
    return read_to


def _stamp_read_this_far(
    gh: GitHubClient, issue: Issue, state: PinnedState, said_before: set,
) -> None:
    """Record the bounded reading on the state, where there is one to record.

    The conditional IS the rule: an answer of None is a thread this tick may
    not claim to have read any further than it already had, so the mark is
    left exactly where it was.
    """
    read_to = _read_this_far(gh, issue, state, said_before)
    if read_to is not None:
        state.set(_delivery.PINNED_LAST_ACTION_COMMENT_ID, read_to)


def _comment_id(seen) -> int:
    """One comment's own address, or 0 for one nothing here can name."""
    identified = getattr(seen, "id", None)
    return identified if isinstance(identified, int) else 0
