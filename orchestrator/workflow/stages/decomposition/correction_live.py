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
moves both. It is asked ahead of the launch's charge, behind the pinned
comment (`answers`), and again right behind that charge (the circuit's
`OwedLaunch.resolves`), so a hold, a close, a relabel, or an edit landing
while the attempt was armed and charged invokes nothing; and again before
anything is made of the answer the correction returns
(`correction_settlement`), so none of them is answered with a child, a split
marker, a label, or a park. Each of those asks ends on the issue fetched once
more behind the thread's read (`controls`), whose controls and title and body
are the ones judged, and the circuit's judge of the pinned reading its start
is written over asks the whole of it again behind that reading
(`uncontrolled`), so a hold or an edit landing while an earlier request of the
check was out is met rather than read past.

The pinned comment is asked of the context the attempt was armed under ahead
of the issue itself, and read once more behind the issue's requests
(`answers`): a session, command, or baseline written there since is no
conversation the launch, or its answer, belongs to.

Five answers, since each is acted on differently. STANDS licenses the step.
HELD is a control a human applied: nothing moved, nothing is made, and the
attempt is left as it stands. MOVED is proof the requirements or the saved
context changed, so the attempt is no longer the tick's to launch, its answer
is spent, and the change is the drift road's to route through a fresh
decomposition. DISOWNED is proof the issue was closed or handed to another
label, so the answer is spent and the tick ends there: no road of this label's
has anything left to do on it. UNREAD is a reading GitHub would not answer,
which proves nothing and licenses nothing.
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
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    record_admission as _record_admission,
)
from orchestrator.workflow.stages.decomposition import (
    correction_commits as _commits,
    correction_records as _records,
    correction_standing as _standing,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# What a reading of the attempt says where it is no longer the tick's to answer
# for: another record's or cycle's, a claim nobody can read, or none at all.
_NOT_ITS_OWN = frozenset((_standing.Standing.DISPLACED, _standing.Standing.DAMAGED, _standing.Standing.ABSENT))


class Live(StrEnum):
    """What the issue, read afresh, says of a correction's launch or of acting on its answer."""

    STANDS = "stands"
    HELD = "held"
    MOVED = "moved"
    DISOWNED = "disowned"
    UNREAD = "unread"


def controls(gh: GitHubClient, issue: Issue) -> tuple[Live, Issue | None]:
    """What `issue`, fetched now, says of its controls and its owner, beside the issue fetched where it stands.

    HELD for a `paused` or `backlog` hold, DISOWNED for a close or a label
    other than `workflow:decomposing`, UNREAD where GitHub would not answer.
    """
    try:
        fresh = gh.get_issue(issue.number)
    except Exception:
        log.exception("issue=#%d could not be read for its manifest correction; holding it", issue.number)
        return Live.UNREAD, None
    if hard_skip_control_label(fresh) is not None:
        return Live.HELD, None
    if issue_is_closed(fresh) or gh.workflow_label(fresh) != WorkflowLabel.DECOMPOSING:
        return Live.DISOWNED, None
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
    """The requirements `fresh` reads as over its whole `thread`, and over the stretch through `state`'s boundary.

    The stretch only where a boundary stands: a thread with none names no
    stretch a run settled, so every comment on it is one the requirements are
    measured by, and a reply written while a run was out is an edit for the
    drift road rather than a comment past a boundary nobody recorded.
    """
    ours = _comments._orchestrator_ids(state)
    whole = _content_hash._compute_user_content_hash(fresh, ours, comments=thread)
    floor = state.get(_state._LAST_ACTION_COMMENT_ID)
    if not isinstance(floor, int):
        return frozenset((whole,))
    read = [seen for seen in thread if seen.id <= floor]
    return frozenset((whole, _content_hash._compute_user_content_hash(fresh, ours, comments=read)))


def answers(gh: GitHubClient, issue: Issue, state: PinnedState, source: _records.CorrectionSource) -> Live:
    """What the pinned comment and then the issue, read afresh, say of making anything of `source`'s correction.

    The comment first, read as the tick's own (`CorrectionCommit.fresh`): one
    another road or a human wrote since the tick last synced with it -- a
    cycle moved, a pin changed -- withholds the tick's state, so no
    whole-state write puts back what it replaced, and is UNREAD, holding the
    tick; so is one that no longer carries `source`'s attempt bound to its
    record and cycle, and one nobody could read. Then its requirements
    baseline and both decomposer pins as the source saved them
    (`correction_standing.moved`) -- a session or command pinned in their
    place, or a baseline moved, is MOVED, a conversation the answer no longer
    belongs to, and a reading proving neither is UNREAD. Then the issue
    (`reads`), its controls and requirements read last; and then the comment
    once more behind those requests (`record_admission.stands`), by its id as
    well as its record, so a session pinned, a cycle moved, or a record
    refused while the issue and its thread were being read withholds the
    tick's state and is UNREAD rather than read past -- no notice is posted,
    and no park written, over a conversation the record no longer names.
    """
    reading = _commits.CorrectionCommit(gh, issue, state).fresh()
    if isinstance(reading, _commits.CorrectionOutcome) or state.withheld:
        log.info("issue=#%d its pinned comment no longer reads as its manifest correction's tick read it", issue.number)
        return Live.UNREAD
    held = _standing.read(reading, issue.number)
    own = held.attempt is not None and held.attempt.source == source
    if not own or held.standing in _NOT_ITS_OWN:
        return Live.UNREAD
    moved = _standing.moved(reading, source)
    if moved is _standing.Standing.STALE:
        return Live.MOVED
    if moved is not None:
        return Live.UNREAD
    live = reads(gh, issue, state, source)
    if live is Live.STANDS and not _record_admission.stands(gh, issue, state):
        live = Live.UNREAD
    return live


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
    either. A comment written while these requests are out is past
    `reading`, so the launch is strict (`OwedLaunch.strict`): its charge and
    start land only over `reading` as it was read.
    """
    return judged(reading) and still()


def resolves(gh: GitHubClient, issue: Issue, state: PinnedState, source: _records.CorrectionSource) -> bool:
    """Whether the issue still stands for the correction's next write (`reads`).

    The circuit's question behind the launch's charge, and the question the
    strict edit recording a park over the attempt asks right before it leaves
    (`correction_notices.recorded`).
    """
    live = reads(gh, issue, state, source)
    if live is Live.STANDS:
        return True
    log.info("issue=#%d reads %s ahead of its manifest correction's next write; holding it", issue.number, live.value)
    return False
