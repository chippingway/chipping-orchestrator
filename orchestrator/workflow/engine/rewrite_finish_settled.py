# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dormant settled-evidence policy's steps in a landed rewrite's evidence phase, beside the one every road selects.

A finish is held to one of two policies: the one every production road hands
over, which proves again only a transaction an earlier finish captured for the
landed head, and a dormant one a caller selects only by building the finish
with `rewrite_finish_models.LandedFinish.proves_settled`. The dormant policy
proves evidence already settled for the head ready again
(`rewrite_finish_readiness.stands_ready`), and invalidates it into history
whole wherever anything it is bound to moved since it settled.

Each step here is one the evidence phase (`rewrite_finish_settlement.resolves`)
takes whichever policy holds the finish, and it answers for both: a finish not
held to the dormant policy goes on exactly as the policy every road selects
has it, reading nothing more. That phase is callable on its own, announcing,
relabelling, parking, and retiring nothing; the coordinator
(`rewrite_finish.finalizes`) takes none of the policy's proofs around its
announcement, park, relabel, or retirement yet.

- `stands_ready_if_settled` proves evidence settled current for the head
  ready, where any is, and -- asked for the base -- holds a head with none to
  the base its replay was made onto, or the base the tick counted it against.
- `out_of_step` says why the records beside settled evidence hold the route.
- `retires_the_adopted` invalidates a settlement the settlement step's answer
  left current -- its own, or another road's it adopted -- over movement the
  answer read under its binding, the announcement a finish of this landing
  made of it aside, before anything is resolved afresh -- and, where another
  finish's route took the attempt off the comment meanwhile or another road
  replaced it, over the comment as it stands; and `stands_as_read` says
  whether the attempt that answer left is the one the finish captured:
  unmoved, or advanced by its own announcement.

Nothing here runs the configured commands, posts an artifact, launches a
developer, or announces anything.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import attempt_records as _attempt_records, attempts as _attempts
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_captured as _captured,
    rewrite_finish_readiness as _readiness,
    verification_durable as _durable,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_evidence_proof import standing_refusal
from orchestrator.workflow.engine.rewrite_finish_announced import advanced_by_the_announcement
from orchestrator.workflow.engine.rewrite_finish_marks import retires_as_it_stands
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish

log = logging.getLogger("orchestrator.workflow")


def stands_ready_if_settled(finish: LandedFinish, *, or_the_base: bool = False) -> FinishOutcome | None:
    """`stands_ready` over evidence settled current for `finish`'s landed head, where any is; None to go on.

    Asked only of a finish held to the dormant settled-evidence policy: any
    other finish goes on from here with nothing read. `or_the_base` asks for
    the proof a route's last write needs, behind requests that took time: a
    base advanced meanwhile holds the route with the attempt standing, a head
    with no evidence current held to the base tip its replay was made onto
    (`rewrite_finish_captured.stands_before_the_route`), so the recovery
    continues it to another rebase. An attempt that records no tip -- blanked
    to record movement, blanked because the base moved while git ran, or a
    legacy attempt -- proves no base, so its head is held to the base this
    tick counted it against (`rewrite_evidence_proof.standing_refusal`): one
    advanced, rewound or repointed under the local ref, or unreadable holds
    the route for the next tick's fetch to count the head again.
    """
    if not finish.proves_settled:
        return None
    current = _settlement.read_current_evidence(finish.state)
    stopped = None
    if current is not None and current.binding.target.target_head == finish.head:
        stopped = _readiness.stands_ready(finish, current)
    elif or_the_base:
        stopped = _captured.stands_before_the_route(finish, landing=False)
    unproven = not _attempt_records._recorded_onto(finish.state)
    if stopped is not None or not (or_the_base and unproven):
        return stopped
    counted = finish.landed.candidate.checkout
    moved = standing_refusal(finish, onto=counted.base.tip)
    if moved is None:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s: its attempt records no base tip, and the base this tick counted "
        "it against reads otherwise now (%s)",
        finish.issue.number, finish.head, moved.refusal,
    )
    return FinishOutcome.HELD


def out_of_step(finish: LandedFinish, current: _records.CurrentEvidence | None) -> str:
    """Why a record beside the head's resolved evidence holds the route over `current`, or "".

    Any pending record, and -- beside `current`, where there is one -- a
    handoff that does not name it or a revision floor nobody can read
    (`rewrite_finish_readiness.beside_current`), and, for a finish not held to
    the settled-evidence policy, a revision spent past it. That policy holds
    no route over a readable revision spent past `current`: it outranks the
    evidence for good, which its readiness proof invalidates rather than
    holding every later poll over it.
    """
    beside = _readiness.beside_current(finish.state, current)
    if beside or finish.proves_settled or current is None:
        return beside
    if _record_state._latest_revision(finish.state) == current.revision:
        return ""
    return "a revision past it was spent"


def retires_the_adopted(
    finish: LandedFinish,
    pending: _records.PendingEvidence,
    movements: list[ReportEvidence],
    attempt: _commit_models.PinnedCommit,
) -> bool:
    """Whether the records the answer to `pending` left resolve afresh, evidence it read moving retired first.

    Always, with nothing read, for a finish not held to the settled-evidence
    policy or with nothing current under `pending`'s receipt. Otherwise that
    evidence -- settled by this answer, or adopted from another road -- is
    invalidated whole over movement the answer read under its binding
    (`movements`), however soon it was put back. The evidence records' own
    moves are no such movement (`verification_durable.moves_only_the_evidence`),
    nor the attempt's: the announcement a finish of this landing put on
    `attempt`, the one captured before the answer (`stands_as_read`), or any
    member where another finish's route or another road took `attempt` off
    the comment -- over which, holding the route whatever this says, the
    evidence is invalidated as the comment stands
    (`rewrite_finish_marks.retires_as_it_stands`). False, logged, where
    that invalidation did not land.
    """
    current = _settlement.read_current_evidence(finish.state)
    if not finish.proves_settled or current is None or current.receipt != pending.receipt:
        return True
    captured = stands_as_read(finish, attempt, finish.state)
    excused = advanced_by_the_announcement(finish, attempt, finish.state.data) if captured else _attempts._ATTEMPT_KEYS
    if all(_durable.moves_only_the_evidence(moved, excused or ()) for moved in movements):
        return True
    if captured:
        invalidated = _readiness.invalidates(finish, current)
    else:
        invalidated = retires_as_it_stands(finish, pending.receipt, attempt)
    if invalidated:
        return True
    log.warning(
        "issue=#%d holding the route of %.8s: verification evidence revision %d was read moving while it "
        "settled, and could not be invalidated",
        finish.issue.number, finish.head, pending.revision,
    )
    return False


def stands_as_read(finish: LandedFinish, attempt: _commit_models.PinnedCommit, state: PinnedState) -> bool:
    """Whether `state` carries the attempt `attempt` captured, so movement read under it is this finish's to retire.

    Unmoved; or -- for a finish held to the settled-evidence policy -- advanced
    by its own announcement alone, the mark and the record of its event put
    down for the landed head by a finish of this very landing
    (`rewrite_finish_announced.advanced_by_the_announcement`), which leaves
    the settlement that finish made this finish's to invalidate over what its
    answer read rather than an attempt another road put in its place.
    """
    if not attempt.moved(state.data):
        return True
    return finish.proves_settled and advanced_by_the_announcement(finish, attempt, state.data) is not None
