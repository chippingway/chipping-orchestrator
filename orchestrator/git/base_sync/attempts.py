# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record one auto-rebase attempt leaves of itself on the pinned comment.

The refresh pins its recovery anchor before git runs, rebases, pushes, and
announces what it published -- durable moments with windows between them, and
a process can die in any of them. The anchor alone says where the branch
started and nothing else: which publication the attempt was made for, which
commit its replay produced, and whether a finish already said so are three
facts it cannot supply, and each of them is something the tick that comes back
has no other way to learn.

So they are recorded beside it, and this owner is where that group is read and
ended -- and where the members with no road of their own are written. The
anchor and the terms ride a write that exists for something else: the statement
in `startup` that pins the attempt before git runs. The replay and the
announcement mark have no such statement. Each has to be durable in a moment
nothing else writes in, and each is owed by BOTH finishes -- the publisher's
own and the recovery's -- so a writer belonging to either would leave the other
free to skip it.

What every step that ends an attempt shares is this owner's clear: the reset
that puts the branch back, the abort of a rebase that failed, the no-op that
moved nothing, the relabel that takes the issue out of the refresh's reach, and
the finalize that publishes all drop the whole record rather than the member
they happen to name.

That is also why the writes, the reads, and the clear sit in ONE owner and not
in three: the shape a member is written in and the shape it is refused in are
the same decision, and split across modules a writer would be free to put down
what the reader beside it cannot vouch for. The count of members that costs is
what the subject costs -- three moments a member can first be known, four
questions a caller can ask of the group -- rather than a module that outgrew
itself.

Reading is deliberately three-valued. ABSENT is a comment carrying no member
at all, which is an attempt from before this record existed or one whose
anchor is all that was ever pinned. DECLARED is the terms with no head: the
window between `git rebase` returning and the write that records what it
produced, where the branch may be standing on a replay nothing here can name.
DAMAGED is a comment that claims the record and cannot show it -- a member
taken out, a head that is not a whole git object id, a pull request that is
not an identity, a stage no publication is entered from. Collapsing those
three into one answer is what would let the state nobody can vouch for take a
road reserved for one that can, so every reader here keeps them apart and
every caller is made to say which it is acting on.
"""
from __future__ import annotations

from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
    _PendingRewrite,
)
from orchestrator.git.base_sync.state import (
    _PENDING_ANNOUNCED_SHA,
    _PENDING_PUSH_SHA,
    _PENDING_REWRITE_PR,
    _PENDING_REWRITE_SHA,
    _PENDING_REWRITE_STAGE,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import (
    WorkflowLabel,
    publishes_onto_a_pull_request,
)

# Every key one attempt's record of its own replay goes down as, so a reader
# can tell a comment carrying none of them from one a hand edit or a
# half-finished write took a member out of. The announcement mark is not one
# of them: it is a checkpoint about a finish rather than a term of the
# attempt, and it has its own reader for that reason.
_PENDING_REWRITE_KEYS = (
    _PENDING_REWRITE_SHA, _PENDING_REWRITE_PR, _PENDING_REWRITE_STAGE,
)

# Everything one auto-rebase attempt puts on the pinned comment, so the step
# that ends it drops the whole record rather than the field it happens to
# name.
_ATTEMPT_KEYS = (_PENDING_PUSH_SHA, *_PENDING_REWRITE_KEYS, _PENDING_ANNOUNCED_SHA)


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


def _pending_rewrite(state: PinnedState) -> _PendingRewrite:
    """The record one interrupted attempt left of the replay it made.

    Read whole or not at all, like every other record this domain acts on: a
    pull request that is not an identity, a stage no publication is entered
    from, and a head that is not a whole git object id each answer as a record
    nobody may act on, which every caller reads as "cannot say" rather than as
    a fact about the world. The head is held to the same shape every other
    recorded commit here is, and for the same reason -- it is compared against
    one this tick read off a checkout, and a value that cannot be a commit
    would either never match or match something nothing ever wrote.

    Whole means something different for the TERMS and for the head, because
    they are written a `git rebase` apart. The terms go down with the anchor
    before the branch can move, so a comment carrying them and no head is not
    a group short of a member: it is an attempt this reader can date to the
    window between git returning and the write that records what it produced.
    A comment carrying a head with the terms missing is the other way round --
    nothing writes that order -- so it is damage.

    Which of the three absences a caller has is what travels back on the
    answer: one nobody ever wrote, one still in flight, or one something took
    apart.
    """
    # Lazy for the reason every upward reach in this package is: the shape a
    # recorded commit is held to is the late domain's own, and spelling it
    # twice is how a comment comes to accept what every other reader refuses.
    from orchestrator.workflow.late_split import formats as _formats
    recorded = state.get(_PENDING_REWRITE_SHA)
    number = state.get(_PENDING_REWRITE_PR)
    stage = _recorded_stage(state.get(_PENDING_REWRITE_STAGE))
    if not _formats.whole_number(number) or number <= 0 or stage is None:
        return _PendingRewrite(damaged=_claims_a_record(state))
    if recorded is None:
        return _PendingRewrite(pr_number=number, stage=stage)
    if not _formats.is_hex_of(recorded, _formats.COMMIT_LENGTHS):
        return _PendingRewrite(damaged=True)
    return _PendingRewrite(sha=recorded, pr_number=number, stage=stage)


def _claims_a_record(state: PinnedState) -> bool:
    """Whether a comment with unreadable terms claims an attempt anyway.

    Read by VALUE rather than by the key being there, because the write that
    ends an attempt blanks these fields rather than removing them: a group of
    nulls is the record nobody wrote, and a member carrying something beside
    one that does not is the record something took apart.
    """
    return any(
        state.get(key) is not None for key in _PENDING_REWRITE_KEYS
    )


def _recorded_stage(recorded: object) -> WorkflowLabel | None:
    """The stage a record names, or None where it names no publication.

    Held to the same predicate a permit holds its own evidence to -- the
    states that push onto a pull request the remote already carries -- so a
    record naming any other describes an attempt this workflow never made.
    """
    try:
        stage = WorkflowLabel(recorded)
    except ValueError:
        return None
    return stage if publishes_onto_a_pull_request(stage) else None


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
