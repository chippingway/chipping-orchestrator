# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist and end the lifecycle of one auto-rebase attempt.

Replay and announcement checkpoints each land in the crash window they close.
Both publication and recovery use these writers, and every completion clears
the whole attempt. attempt_records validates interrupted replay evidence and
defines the field group that the clear includes.
"""
from __future__ import annotations

from orchestrator.git.base_sync import attempt_records as _attempt_records
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
)
from orchestrator.git.base_sync.state import (
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


def _announces(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    published: str,
) -> None:
    """Record that a finish has said what it did, before it routes.

    The one write in a finish whose whole purpose is the window behind it.
    Everything a finish announces -- the notice on the pull request, the audit
    event on both sinks -- goes out before the relabel, and the write that
    clears the record of the attempt goes out after it. A process lost in
    between comes back to an attempt that looks unfinished, and announcing it
    again puts a second `base_rebased` on the stream and a second notice on
    the pull request for one publication that happened once.

    Made by BOTH finishes, because both leave that window: the publisher's own
    tail announces a rebase it just pushed and the recovery's announces one an
    earlier tick left, and neither is distinguishable afterwards from an
    attempt that never got that far.

    Written while the anchor is still pinned, and that is deliberate: the
    anchor is what brings the tick that reads this back at all, so this write
    may say only that the announcement was made and must leave every other
    field of the attempt exactly where it is. The clear rides the finish's own
    last write, which is what keeps the anchor standing until every road is
    behind it.
    """
    context.state.set(_PENDING_ANNOUNCED_SHA, published)
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
