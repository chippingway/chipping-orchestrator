# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed rewrite's finish captured, abandoned wherever its recovery reads the landing moved.

A finish that recorded the landed head's evidence transaction and stopped
short of its route leaves it pending beside the attempt
(`rewrite_finish_captured`), and only the recovery of the push already landed
-- over a remote and a checkout both still on that head -- may take the route
it carries (`rewrite_landed`). Every other road the recovery is sent down
reads the landing somewhere else and clears, resets, or parks the attempt
without that route: an unmoved checkout back on the anchor, a remote that is
not on the checkout -- rolled back, or moved out of band -- and a remote and
checkout that agree on another head. These are the helpers that abandon the
transaction before any such road is taken, so that movement under a decision
leaves no decision a later route, or the dispatcher's reconciliation once the
attempt is cleared, may take. The recovery's coordinator (`rewrite_recovery`)
asks them of every snapshot before the road it chooses, and the landed road
(`rewrite_landed`) of a checkout or remote it reads leaving the head; every
road's context carries the reset answer, and so does the refresh's abort over
a checkout whose lag against base could not be counted.

`abandons_off_the_landing` answers whether a road may go on: True where the
snapshot reads no head off the head a finish captured evidence for, or where
nothing captured for that head stands once the abandonment was asked
(`abandons`), and False where a transaction still stands that no write could
retire, for the coordinator to hold the tick with nothing reset, cleared, or
parked. A head the snapshot could
not read -- a checkout whose head would not prove, or a remote not yet read --
establishes no movement, so the transaction is kept: the road such a snapshot
takes resets the checkout, and that reset, once it lands, is the movement the
abandonment answers (`abandons_over_the_reset`), while one that fails keeps the
attempt and the transaction both. `abandons` abandons it over the movement
already read, however the heads read by then, so the transaction is abandoned
unrun, or refused for good where the comment has no room for that, in a write
of its own landed as the attempt's checkpoint
(`git/base_sync/checkpoints._lands_the_checkpoint`): staged on a copy of the
tick's state and decided on the attempt and its evidence as the tick last
confirmed them. Only where that write does not land is the transaction still
standing -- refused, or over an attempt or evidence record that moved by no
write of this recovery's, which is kept exactly as it stands, or sent with its
answer lost, which the next tick's reading settles.

A recovery park that keeps the attempt keeps the transaction with it, for the
human reply that brings the recovery back: a reset that did not land, an issue
relabelled out of the stages the refresh drives, a landing made for another
publication or one its record does not account for. What such a park read is
put right by a human, and the reply then finishes the landing, so the git
owner asks before every such park (`abandons_unproved`) for the transaction to
be proved again (`proves_captured`) -- over the issue and comment read afresh,
held to the last word, none of it needing the fetch an abort could not take --
and abandoned now
where anything it rests on moved, a configuration or a pull request repointed
among the reasons, so putting that back before the reply revives nothing. One
that still proves, or that only a reading nobody could take holds, is kept
for that finish.

A reset is the one road that moves the checkout off the landed head itself,
and the git owner's park behind it drops the attempt in the one write that
records it, landed as the attempt's checkpoint
(`git/base_sync/persistence._reset_clear_and_park`).
`abandons_over_the_reset` is the answer that owner stages on that very state
once the reset landed (`_AutoRebaseRecoveryContext.settles_over_a_reset`), so
the transaction goes with the attempt's release or neither goes: a park write
that fails leaves both standing, and a reset that failed moved nothing and
keeps both.

Only a transaction a finish of the attempt recorded is read
(`rewrite_landing_records.captured`): the one under the receipt the finish put
on the attempt in the very write that recorded it
(`pending_auto_base_rebase_evidence_receipt`), or -- for an attempt from
before that receipt existed, whose finish recorded evidence only behind its
announcement mark -- one about the head that mark names. A finish resolves
the landed head's evidence before it announces it, so no mark need be down,
and the replay the attempt's record names -- written before the push, or not
yet written in the window git leaves -- says nothing either way. Any other
pending transaction was recorded by another road -- a newer head it
published, or a newer record about the same one -- and is kept as that road
wrote it, with its revision floor, whatever this recovery reads, on every road
it takes.

Evidence a finish already settled for the head and left current behind a tail
cut short is none of these helpers' to read: no recovery road retires it,
over a landed reset or before a park that keeps the attempt.

Every helper here runs under the issue's writer claim the recovery is reached
under, so what it reads afresh moves only by this recovery's own writes or
from outside the orchestrator -- a human's edit of the issue or its pinned
comment, the pull request, the configuration, or the branch. It proves the
transaction again and asks the last word over those readings, and abandons
it over what moved; it keeps no reading of the comment for a later step to
reconcile against another orchestrator writer, since none writes the issue
while the claim is held. An abandonment that lands is this recovery's own
checkpoint: what the tick staged ahead of it and had not written -- a gate's
records of its hold, a reply recorded read -- rides it once,
and the tick's state reads as the comment does for the park or hold behind it.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.git.base_sync import (
    checkpoints as _checkpoints,
    recovery_push as _recovery_push,
    replay_evidence as _replay_evidence,
    state as _base_sync_state,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.rewrite_handoffs import _LandedRewrite, _PushOutcome
from orchestrator.git.ref_transport import _RefRead
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import (
    report_commits as _commits,
    rewrite_finish_captured as _captured,
    rewrite_landing_records as _landing_records,
    verification_carries as _carries,
    verification_records as _records,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import LEFT_THE_LANDING, last_word
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad, LandedFinish

log = logging.getLogger("orchestrator.workflow")

_RELEASED = "in the write that releases its attempt behind the reset that took the checkout off it"

_CHECKOUT_GONE = "in the write that parks its attempt, the checkout it was captured on gone"


def abandons_over_the_reset(context: _AutoRebaseContext | _AutoRebaseRecoveryContext, why: str = _RELEASED) -> None:
    """Stage the abandonment of what a finish captured for the landed head on the state a landed reset's park writes.

    The recovery's answer to a reset (`_AutoRebaseRecoveryContext.settles_over_a_reset`),
    asked by the git owner once the reset landed and before the attempt is
    dropped from `context.state`: the reset took the checkout off the landed
    head, which is movement under the transaction. Staged on the state whose
    changes the park's record then lands, the abandonment goes with the
    attempt's release or not at all, so no cleared attempt leaves the
    transaction behind it for the reconciliation to settle once the checkout
    is put back. With no room
    for its history entry, the transaction is dropped instead and refused for
    good, as the finish's own abandonment refuses one (`rewrite_finish_captured`):
    the base tip the attempt recorded its replay as made onto is blanked with
    it, so where the attempt outlives that write -- the park over a checkout
    gone from disk keeps it -- every later reading of the base proves nothing
    (`rewrite_evidence_proof.standing_refusal`), and no finish of this landing
    runs or carries the evidence again, with neither the transaction nor its
    history entry left to say a run was captured. A reset's release drops the
    tip with the attempt either way. `why` names the write it rides, logged.
    """
    pending = _landing_records.captured(context.state)
    if pending is None:
        return
    head = pending.binding.target.target_head
    log.info(
        "issue=#%d abandoning verification evidence revision %d recorded for %.8s, %s",
        context.issue.number, pending.revision, head, why,
    )
    if not _carries.abandons(context.state, pending):
        context.state.set(_records.PENDING_EVIDENCE, None)
        context.state.set(_base_sync_state._PENDING_REWRITE_BASE, None)


def abandons_off_the_landing(context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot) -> bool:
    """Abandon the transaction a finish captured for the landed head where `snapshot` reads a head off it; may it go on.

    Asked by the recovery's coordinator of every snapshot it reads, before
    the road the snapshot chooses is taken; a remote and a checkout both on
    the transaction's head are the landed road's to finish, which reads them
    again itself. A head the snapshot holds as "" is one nobody read, which
    establishes no movement, so the transaction is kept for a reset that
    lands to abandon (`abandons_over_the_reset`). False only where a
    transaction still stands that the abandonment could not retire, logged:
    the coordinator holds the tick then rather than take a road that would
    leave it behind.
    """
    pending = _landing_records.captured(context.state)
    head = "" if pending is None else pending.binding.target.target_head
    if not head or not {snapshot.local_head, snapshot.remote_head} - {"", head}:
        return True
    if abandons(context):
        return True
    log.warning(
        "issue=#%d holding the recovery of %.8s: the verification evidence captured for it could not be "
        "abandoned yet, so nothing is reset, cleared, or parked until a later tick abandons it",
        context.issue.number, head,
    )
    return False


def abandons(context: _AutoRebaseRecoveryContext, why: str = LEFT_THE_LANDING.refusal) -> bool:
    """Abandon what a finish of the attempt captured, over movement already read, as a checkpoint; whether none stands.

    `why` is that movement, logged. The abandonment is staged on a copy of the
    tick's state -- retired into the evidence history, or with no room for
    that entry dropped with the recorded base tip blanked
    (`abandons_over_the_reset`) -- and landed as the attempt's checkpoint
    (`git/base_sync/checkpoints._lands_the_checkpoint`): over the reading the
    tick last confirmed, carrying what the tick staged since, and decided on
    the attempt and its evidence. Nothing is read again for the movement and
    nothing is routed, and nothing is written where no transaction is
    recorded for that head. False where one is still recorded once that
    write was asked: refused -- an attempt or evidence record moved by no
    write of this recovery's among the reasons, kept as it stands -- or sent
    and never confirmed.
    """
    if _landing_records.captured(context.state) is None:
        return True
    staged = _commits.ReportCommit(context.gh, context.issue, context.state).staging()
    abandons_over_the_reset(replace(context, state=staged), why)
    return _checkpoints._lands_the_checkpoint(
        context.gh, context.issue, context.state, "abandoning the evidence captured for the landing", staged,
    )


def abandons_unproved(context: _AutoRebaseRecoveryContext) -> bool:
    """Prove the transaction a finish captured for the landed head before a park keeps it, abandoning it where it moved.

    Whether the park may go on -- asked by the git owner ahead of every
    recovery park that keeps the attempt (`git/base_sync/persistence._proves_before_the_park`),
    over the checkout as it reads now and the branch the comment names
    (`proves_captured`). Nothing is read or written where no transaction is
    recorded for that head, and one nothing moved under is kept. With no
    checkout on disk there is nothing to prove the landing over, the checkout
    it was captured on being gone, so the abandonment is staged on the state
    the park's record then lands (`abandons_over_the_reset`). False only where
    movement was read and the transaction still stands once the abandonment
    was asked, for the git owner to hold the tick with nothing parked -- and
    where the comment names no branch live work may use
    (`naming._admitted_branch`), since no landing can be proved over a branch
    nothing may be pushed to, and nothing derived stands in for it.
    """
    if _landing_records.captured(context.state) is None:
        return True
    if not context.worktree.is_dir():
        abandons_over_the_reset(context, _CHECKOUT_GONE)
        return True
    branch = _naming._admitted_branch(context.state, context.spec, context.issue.number)
    if branch is None:
        log.warning(
            "issue=#%d records no branch live work may use; holding its "
            "captured landing unproved with nothing parked", context.issue.number,
        )
        return False
    return proves_captured(context, _AutoRebaseRecoverySnapshot(branch=branch, local_head=""))


def proves_captured(context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot) -> bool:
    """Prove the transaction a finish captured for the landed head, abandoning it where it moved; whether none stands.

    Over the landing as `snapshot` read it, a checkout with no head read
    among it. The transaction's binding is proved again over the issue and
    comment read afresh (`rewrite_finish_captured.proved_again`) and held to
    the last word beside it (`rewrite_evidence_proof.last_word`), neither of
    which needs the fetch a failed abort could not take; where either reads
    movement, the transaction is abandoned unrun -- or, with no room, refused
    for good -- as the attempt's checkpoint, with that movement as its reason
    (`abandons`).
    """
    pending = _landing_records.captured(context.state)
    if pending is None:
        return True
    finish = _finish(context, pending.binding.target.target_head, snapshot)
    proof = _captured.proved_again(finish, pending)
    moved = last_word(finish, pending.binding, earlier=proof)[0]
    return moved is None or abandons(context, moved.refusal)


def _finish(context: _AutoRebaseRecoveryContext, head: str, snapshot: _AutoRebaseRecoverySnapshot) -> LandedFinish:
    """The finish of `head`'s landing as `snapshot` read it, over the checkout read now."""
    read = _recovery_push._recovered_candidate(context, snapshot)
    return LandedFinish(
        gh=context.gh,
        spec=context.spec,
        issue=context.issue,
        state=context.state,
        landed=_LandedRewrite(
            candidate=replace(read, checkout=replace(read.checkout, head=head)),
            outcome=_PushOutcome.OBSERVED,
            remote=_RefRead(sha=snapshot.remote_head),
        ),
        label=_replay_evidence._recovered_stage(context.label),
        road=FinishRoad.RECOVERY,
    )
