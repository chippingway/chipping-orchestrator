# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed rewrite's finish captured or settled, retired whole where its recovery resets or parks the attempt.

A finish that recorded the landed head's evidence transaction and stopped
short of its route leaves it pending beside the attempt
(`rewrite_landing_records.captured`), and one that settled it and then died
in the tail of its route -- before the announcement, the relabel, or the
retirement -- leaves it current beside the attempt
(`rewrite_landing_records.settled`). The recovery's helpers
(`rewrite_landing_moved`) retire both wherever a snapshot reads the landing
moved. These hold both to the same readings on the two roads that end a
recovery without that landing's route -- a reset that releases the attempt,
and a park that keeps it -- and every recovery context the workflow builds
carries them: each recovery road's (`rewrite_recovery.recovers`), the abort
over an unreadable checkout's, the eligibility gate's park of a label the
refresh does not drive (`base_rewrite`), and the dispatcher's held anchor
(`rewrite_recovery_parks.answers_a_held_anchor`).

- Over a reset that landed (`retires_over_the_reset`, the answer a recovery
  context's `settles_over_a_reset` carries): the transaction is abandoned
  on the state the park lands, as its own half stages it
  (`rewrite_landing_moved.abandons_over_the_reset`), and settled evidence is
  invalidated into history whole on that same state, its revision, binding,
  and provenance kept, so it goes with the attempt's release or neither goes.
  With no room for its history entry it is never dropped: it stays current and
  whole beside the attempt that keeps every reader off it, the base tip the
  attempt recorded its replay as made onto blanked in a write of its own, so
  every later proof of it reads movement
  (`rewrite_evidence_proof.standing_refusal`) and invalidates it whole once
  the comment has room, however the checkout is put back meanwhile -- and the
  answer is False, for the git owner to keep the attempt and hold the tick
  with nothing released or parked
  (`git/base_sync/persistence._releases_over_the_reset`).
- Before a park that keeps the attempt (`retires_unproved`): the transaction
  is proved again and abandoned where it moved
  (`rewrite_landing_moved.proves_captured`), and settled evidence is proved
  ready (`rewrite_finish_readiness.settled_word`) and invalidated whole where
  it moved (`rewrite_finish_readiness.invalidates`), over the checkout as it
  reads now and the branch the comment names, none of it needing the fetch an
  abort could not take. Movement the caller already read -- a record a park's
  own commit adopted while its notice was posted -- stands as that proof, so
  no reading taken now hides it by finding it put back. With no checkout on
  disk there is nothing to prove the landing over, so both are retired as
  over a reset, on the state the park lands; the movement is recorded against
  them first, in a write of its own, by the proof every recovery context
  carries (`rewrite_recovery_parks.proves_before_a_park`). The landed road's
  own holds ask it too (`rewrite_landed`), ahead of a hold's write.

Nothing here posts, parks, resets, or routes anything.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import (
    report_commits as _commits,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_writes as _writes,
    rewrite_landing_moved as _landing_moved,
    rewrite_landing_records as _landing_records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence

log = logging.getLogger("orchestrator.workflow")


def retires_over_the_reset(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext, why: str = _landing_moved._RELEASED,
) -> bool:
    """Stage the retirement of what a finish captured or settled for the landed head; whether the attempt may go.

    A recovery's answer to a reset that landed, asked by the git owner before
    the attempt is dropped from `context.state`: the reset took the checkout
    off the landed head, which is movement under both. The transaction is
    abandoned (`rewrite_landing_moved.abandons_over_the_reset`), and settled
    evidence is invalidated on the same state (`_invalidates_over_the_reset`),
    so both land with the attempt's release or neither does. False only where the
    settled evidence has no room for its history entry, and is kept whole
    beside the attempt. `why` names the write it rides, logged.
    """
    _landing_moved.abandons_over_the_reset(context, why)
    return _invalidates_over_the_reset(context, why)


def retires_unproved(context: _AutoRebaseRecoveryContext, moved: ReportEvidence | None = None) -> bool:
    """Prove what a finish captured or settled for the landed head before a park keeps it, retiring what moved.

    Whether the park may go on. The transaction is proved first
    (`rewrite_landing_moved.proves_captured`), and settled evidence then
    proved ready again and invalidated whole where it moved; nothing is read
    or written where neither stands, and what nothing moved under is kept.
    `moved` is movement the caller already read under that evidence, which is
    the proof the transaction is abandoned with and invalidates settled
    evidence outright. With no checkout on disk both are retired on the state
    the park lands (`retires_over_the_reset`). False only where evidence still
    stands once its retirement was asked -- settled evidence with no room for
    its history entry among it, its movement recorded instead -- for the git
    owner to hold the tick with nothing parked.
    """
    settled = _landing_records.settled(context.state)
    if _landing_records.captured(context.state) is None and settled is None:
        return True
    if not context.worktree.is_dir():
        return retires_over_the_reset(context, _landing_moved._CHECKOUT_GONE)
    branch = _naming._resolve_branch_name(context.state, context.spec, context.issue.number)
    unread = _AutoRebaseRecoverySnapshot(branch=branch, local_head="")
    if not _landing_moved.proves_captured(context, unread, moved):
        return False
    settled = _landing_records.settled(context.state)
    if settled is None:
        return True
    finish = _landing_moved._finish(context, settled.binding.target.target_head, unread, None)
    word = moved or _readiness.settled_word(finish, settled)[0]
    return word is None or _readiness.invalidates(finish, settled)


def _invalidates_over_the_reset(context: _AutoRebaseContext | _AutoRebaseRecoveryContext, why: str) -> bool:
    """Stage the invalidation of evidence a finish settled for the landed head on `context.state`; may the attempt go.

    Into history whole, its revision and binding kept, for the park to land
    with the attempt's release. With no room for its history entry it is not
    dropped: it stays current, whole, beside the attempt that keeps every
    reader off it, and the movement is recorded instead by blanking the base
    tip the attempt recorded its replay as made onto, so every later proof of
    the evidence reads movement (`rewrite_evidence_proof.standing_refusal`)
    and invalidates it whole once the comment has room -- putting the checkout
    back first revives nothing. A reset recorded ahead of it has that blank
    landed already (`rewrite_recovery_parks.records_the_reset`); a checkout
    gone from disk has it landed here. It only shrinks the comment, so it
    lands at once, guarded as the finish's own abandonment is
    (`rewrite_finish_writes.ABANDONMENT`), with whatever else this answer
    staged. False then, for the git owner to keep the attempt and hold the
    tick with nothing parked until room is made.
    """
    settled = _landing_records.settled(context.state)
    if settled is None:
        return True
    log.info(
        "issue=#%d invalidating verification evidence revision %d settled for %.8s, %s",
        context.issue.number, settled.revision, settled.binding.target.target_head, why,
    )
    if _settlement.retire_current_evidence(context.state):
        return True
    context.state.set(_base_sync_state._PENDING_REWRITE_BASE, None)
    recorded = _commits.ReportCommit(context.gh, context.issue, context.state).lands(
        context.state, _writes.ABANDONMENT,
    )
    log.error(
        "issue=#%d the pinned comment has no room to retire verification evidence revision %d settled for %.8s; "
        "keeping it current beside the attempt, its base tip blanked (%s), and holding until room is made",
        context.issue.number, settled.revision, settled.binding.target.target_head, recorded.status.value,
    )
    return False
