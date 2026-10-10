# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist and end the lifecycle of one auto-rebase attempt.

Replay and announcement checkpoints each land in the crash window they close.
The workflow's publication of a clean rebase records its replay here, and the
workflow's finish -- of a publication, of the recovery's retry, or of a push
the recovery found already landed -- puts the announcement mark down through
its own guarded checkpoint (`workflow/engine/rewrite_finish.py`) and reads it
back here. Every completion clears the whole attempt, and so does the
handoff of an unpublished replay to the late generation adjudicating it
(`workflow/engine/rewrite_takeover.py`), in the write that has the generation
take the replay over -- the one ending that also retires the park the
attempt's own road left, since nothing is left to answer it, with the replies
that park was answered with recorded read
(`workflow/engine/rewrite_takeover_parks.py`). attempt_records
validates interrupted replay evidence and defines the field group that the
clear includes.
"""
from __future__ import annotations

from orchestrator.git.base_sync import attempt_records as _attempt_records
from orchestrator.git.base_sync.models import _AutoRebaseContext
from orchestrator.git.base_sync.state import (
    _AUTO_REBASE_PARK_REASONS,
    _AWAITING_HUMAN,
    _PARK_REASON,
    _PENDING_ANNOUNCED_SHA,
    _PENDING_PUSH_SHA,
    _PENDING_REWRITE_SHA,
)
from orchestrator.github.pinned_state import PinnedState

# Everything one auto-rebase attempt puts on the pinned comment, so the step
# that ends it drops the whole record rather than the field it happens to
# name.
_ATTEMPT_KEYS = (_PENDING_PUSH_SHA, *_attempt_records._PENDING_REWRITE_KEYS, _PENDING_ANNOUNCED_SHA)


def _clears_the_attempt(state: PinnedState) -> None:
    """Drop the whole record of one auto-rebase attempt.

    The anchor, the terms it was made under, the head the replay produced, and
    the mark a finish left are one record and are dropped as one: the anchor
    alone would bring a later tick back to an attempt it cannot prove the
    checkout belongs to, and the rest names a commit and a pull request
    nothing is leased to publish onto. Every step that ends an attempt goes
    through here rather than spelling one field, so a road that forgets a
    member cannot exist.

    Blanked rather than removed, like every other field this domain retires.
    A group of nulls is the record nobody wrote, which is what lets the reader
    below tell it from the one something took apart.

    Staged rather than persisted: what makes the drop durable is the caller's
    own write, which is what lets it land with the route, the park, or the
    receipt it belongs to, or not at all.
    """
    for key in _ATTEMPT_KEYS:
        state.set(key, None)


def _retires_its_park(state: PinnedState) -> bool:
    """Drop a park the attempt's own road left standing; whether one stood.

    Every auto-rebase park asks a human to reply so the refresh comes back to
    this attempt, which an ending that hands the attempt over leaves nobody to
    come back for. Left standing, the park would hold the very stage the
    replay is handed back to, whose handler stands down on these reasons.
    Every other park -- a stage's, an adjudication's -- is somebody else's
    question and is left as it is. The flags alone: what the retired park was
    answered with is its caller's to record read
    (`workflow/engine/rewrite_takeover_parks.py`).

    Staged like the clear, so it lands with the write that ends the attempt.
    """
    if not state.get(_AWAITING_HUMAN) or state.get(_PARK_REASON) not in _AUTO_REBASE_PARK_REASONS:
        return False
    state.set(_AWAITING_HUMAN, False)
    state.set(_PARK_REASON, None)
    return True


def _records_the_replay(context: _AutoRebaseContext, replayed: str) -> None:
    """Say which commit this attempt produced, durably, before it is spent.

    The anchor pinned before git ran is what brings an interrupted attempt
    back; it is not what says the checkout it comes back to is this attempt's
    own work. A rebase REPLAYS the branch, so the commit the pull request
    still carries is on no local history afterwards and the two look diverged
    -- which is exactly what a checkout somebody else left, a worktree rebuilt
    from elsewhere, and an operator's reset look like too. Told those apart by
    the divergence alone, a later tick would force-push whatever it found over
    the candidate on the remote, under a lease the anchor happily satisfies.

    So the head goes down as a record of its own, and it goes down on the
    reading the publication itself is decided from rather than one taken
    again here: the worktree is writable between any two reads, and a record
    naming a commit other than the one about to be pushed would vouch for
    neither.

    Durable HERE, which is before the first step that can leave the replay
    standing. The two answers ahead of this -- a head this host cannot read,
    and a rebase that moved nothing -- each end the whole attempt themselves,
    so a crash before them strands nothing. Everything after can: the dirty
    park, the size gate that may hand the issue to an adjudication, the push,
    and the finalize all leave a rewritten branch behind if the process dies,
    and none of them may be reached with the replay unrecorded.

    The one window it cannot cover is its own -- between `git rebase`
    returning and this write -- and that is what the terms pinned with the
    anchor answer: an attempt carrying them and no head reads back as one
    still IN FLIGHT rather than as one that never ran.
    """
    context.state.set(_PENDING_REWRITE_SHA, replayed)
    context.gh.write_pinned_state(context.issue, context.state)


def _already_announced(state: PinnedState, local_head: str) -> bool:
    """Whether a finish already said what it published, for this commit.

    The mark a finish leaves between its announcement and its relabel, and the
    only thing that tells the last window of a finish from every earlier one.
    Everything else a finish does before its own write is invisible to a later
    tick: the notice is a comment, the audit event is on the sinks, and the
    label alone cannot say whose move it was.

    Held to the commit, like every other recorded id here -- which is why
    `_foreign_mark` beside this is what a road that would announce something
    asks: a mark naming any other head, or naming no commit at all, is not an
    answer this reader may give as "nothing was announced".
    """
    recorded = state.get(_PENDING_ANNOUNCED_SHA)
    return bool(local_head) and recorded == local_head


def _carries_an_announcement(state: PinnedState) -> bool:
    """Whether a finish on this attempt got as far as announcing something.

    The bare presence of the mark, and it is a fact about the ROUTE rather
    than about any commit: the key is written between a finish's notice and
    its relabel and dropped by the write that clears the attempt, so a comment
    carrying it says the notice went out and the audit event was filed for a
    publication that had already landed. Which head it names is a separate
    question, and the two readers below are what ask it.

    That makes this the question a caller asks when what it needs to know is
    whether the route got that far AT ALL. A road that would push has to,
    because the remote no longer standing on an announced publication is
    somebody's rollback -- and one deciding whether an attempt ever started
    has to, because no finish announces the anchor, so a mark equal to it is a
    checkpoint something took apart rather than an absence.

    Blanked rather than removed by that clear, like every other field this
    domain retires, so the key being there with a null under it is the record
    nobody wrote.
    """
    return state.get(_PENDING_ANNOUNCED_SHA) is not None


def _foreign_mark(state: PinnedState, local_head: str) -> bool:
    """Whether a mark stands here that does not belong to the head in hand.

    Presence rather than truth, for the reason every other checkpoint on this
    comment is read that way. The mark is written by a finish naming what it
    had just published and dropped by the write that clears the attempt, so
    the key being there says a finish announced THIS attempt's replay -- and a
    value that is not that commit, or not a commit at all, is a checkpoint
    something took apart.

    Read as "not announced", such a mark costs the pull request a second
    notice and the stream a second `base_rebased` for one publication that
    happened once, with no way for a reader to tell which of the two describes
    the head the branch ended on.
    """
    if not _carries_an_announcement(state):
        return False
    return not _already_announced(state, local_head)
