# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a manifest correction's launch and its answer are held to beyond the pinned comment.

The comment says whether the attempt still stands (`correction_standing`);
this says whether the issue still does, read afresh off GitHub rather than off
the dispatch's snapshot, which is as old as the tick: no `paused` or `backlog`
hold, still open, still the initial decomposition's on `workflow:decomposing`,
and its requirements -- title, body, and the human thread, fingerprinted as
the drift check fingerprints them -- still the revision the rejected run was
handed. That revision is met either by the whole thread or by the thread
through the reply boundary the run's own settlement recorded: a reply written
while a resumed run was out is past that boundary, the next resume's to
deliver, and no more an edit here than on the parked tick that froze its read
(`replies.py`), while a changed title, body, or comment the run had read
moves both. It is asked right behind the launch's charge (the circuit's
`OwedLaunch.resolves`), so a hold, a close, a relabel, or an edit landing while
the attempt was armed and charged invokes nothing, and again before anything is
made of the answer the correction returns, so none of them is answered with a
child, a split marker, a label, or a park. Each of those asks ends on the
issue fetched once more behind the thread's read (`controls`), whose controls
and title and body are the ones judged, and the circuit's judge of the pinned
reading its start is written over asks the whole of it again behind that
reading (`uncontrolled`), so a hold or an edit landing while an earlier request
of the check was out is met rather than read past.

The pinned comment is asked of the context the attempt was armed under before
anything is made of the correction's answer (`answers`), ahead of the issue
itself: a session, command, or baseline written there since is no
conversation that answer belongs to.

Four answers, since each is acted on differently. STANDS licenses the step.
HELD is a control a human applied: nothing moved, nothing is made, and the
attempt is left as it stands. MOVED is proof: the issue was closed, handed to
another label, or its requirements changed, so the answer is spent and the
change is the drift road's to route through a fresh decomposition. UNREAD is a
reading GitHub would not answer, which proves neither and licenses nothing.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from enum import StrEnum

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, content_hash as _content_hash
from orchestrator.workflow.stages.decomposition import (
    correction_records as _records,
    correction_standing as _standing,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


class Live(StrEnum):
    """What the issue, read afresh, says of a correction's launch or of acting on its answer."""

    STANDS = "stands"
    HELD = "held"
    MOVED = "moved"
    UNREAD = "unread"


def controls(gh: GitHubClient, issue: Issue) -> tuple[Live, Issue | None]:
    """What `issue`, fetched now, says of its controls and its owner, beside the issue fetched where it stands.

    HELD for a `paused` or `backlog` hold, MOVED for a close or a label other
    than `workflow:decomposing`, UNREAD where GitHub would not answer.
    """
    try:
        fresh = gh.get_issue(issue.number)
    except Exception:
        log.exception("issue=#%d could not be read for its manifest correction; holding it", issue.number)
        return Live.UNREAD, None
    if hard_skip_control_label(fresh) is not None:
        return Live.HELD, None
    if issue_is_closed(fresh) or gh.workflow_label(fresh) != WorkflowLabel.DECOMPOSING:
        return Live.MOVED, None
    return Live.STANDS, fresh


def reads(gh: GitHubClient, issue: Issue, state: PinnedState, source: _records.CorrectionSource) -> Live:
    """What `issue`, fetched now with its thread, says of the correction `source`'s rejected answer earned.

    `state` is the caller's record, whose ledger of our own posts is what keeps
    them out of the fingerprint, as the drift check keeps them out. The issue
    is fetched again behind the thread's read, last, and both its controls and
    the title and body the requirements are measured by are that fetch's, so a
    hold or an edit landing while the thread was read is met rather than read
    past.
    """
    first = controls(gh, issue)[0]
    if first is not Live.STANDS:
        return first
    try:
        thread = list(gh.comments_after(issue, None, state_comment_id=state.comment_id))
    except Exception:
        log.exception("issue=#%d its thread could not be read for its manifest correction; holding it", issue.number)
        return Live.UNREAD
    live, fresh = controls(gh, issue)
    if live is not Live.STANDS:
        return live
    return Live.STANDS if source.requirements in _revisions(fresh, state, thread) else Live.MOVED


def _revisions(fresh: Issue, state: PinnedState, thread: list) -> frozenset[str]:
    """The requirements `fresh` reads as over its whole `thread`, and over the stretch through `state`'s boundary."""
    ours = _comments._orchestrator_ids(state)
    floor = state.get(_state._LAST_ACTION_COMMENT_ID)
    if not isinstance(floor, int):
        floor = None
    read = [seen for seen in thread if floor is not None and seen.id <= floor]
    whole = _content_hash._compute_user_content_hash(fresh, ours, comments=thread)
    return frozenset((whole, _content_hash._compute_user_content_hash(fresh, ours, comments=read)))


def answers(gh: GitHubClient, issue: Issue, state: PinnedState, source: _records.CorrectionSource) -> Live:
    """What the pinned comment and then the issue, read afresh, say of making anything of `source`'s correction.

    The comment first: its requirements baseline and both decomposer pins as
    the source saved them (`correction_standing.moved`) -- a session or
    command a human pinned in their place, or a baseline moved, is MOVED, a
    conversation the answer no longer belongs to, and a comment nobody could
    read, or one proving neither, is UNREAD. Then the issue (`reads`), its
    controls and requirements read last.
    """
    try:
        reading = gh.read_pinned_state(issue)
    except Exception:
        log.exception("issue=#%d its pinned comment could not be read for its manifest correction", issue.number)
        return Live.UNREAD
    moved = _standing.moved(reading, source)
    if moved is _standing.Standing.STALE:
        return Live.MOVED
    if moved is not None:
        return Live.UNREAD
    return reads(gh, issue, state, source)


# The circuit's judge of one pinned reading, and the caller's question of the issue beyond it.
_Judge = Callable[[PinnedState], bool]
_Question = Callable[[], bool]


def uncontrolled(judged: _Judge, still: _Question, reading: PinnedState) -> bool:
    """Whether `judged` grants the launch on `reading` and the issue, read afresh behind it, `still` stands.

    The circuit's judge of each pinned reading it charges or starts the
    launch from (`OwedLaunch.stands`), asking the issue once more -- its
    controls, thread, and requirements, the issue fetched last (`resolves`) --
    behind the reading the start is written over, so a hold or an edit
    landing behind `resolves` while that reading was taken invokes nothing
    either.
    """
    return judged(reading) and still()


def resolves(gh: GitHubClient, issue: Issue, state: PinnedState, source: _records.CorrectionSource) -> bool:
    """Whether the correction's launch may start now: the circuit's question behind its charge (`reads`)."""
    live = reads(gh, issue, state, source)
    if live is Live.STANDS:
        return True
    log.info("issue=#%d reads %s behind its manifest correction's charge; launching nothing", issue.number, live.value)
    return False
