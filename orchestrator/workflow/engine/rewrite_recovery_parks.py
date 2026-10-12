# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park a base rewrite's recovery takes, landed over the comment read afresh rather than written whole.

Every recovery park posts its notice on the issue thread and then records
the park (`git/base_sync/persistence._parks_the_recovery`), and that record
is decided on the comment as the tick read it a notice earlier: long enough
for another road to settle and review a later report, or move an evidence
record. Written whole from the tick's state, the record would put each of
those back, and nothing on the comment would say so. The park over a landed
reset is where that costs the most, since the attempt it drops takes out with
it the evidence a finish captured or settled for the landed head
(`rewrite_landing_moved.abandons_over_the_reset`): written whole, it would
retire that evidence and put back the report it was superseded by beside it.

So the workflow hands this park in on every recovery context it builds
(`_AutoRebaseRecoveryContext.lands_a_park`), and the record lands through the
guarded commit (`report_commits.ReportCommit`) as `PARK`: owning every field
the tick staged since its reading -- the park's flags, and the watermark and
ledger its notice moved, and over a landed reset the attempt with every
record it abandoned and the evidence retired beside it -- decided on the
attempt, the park's flags, and the evidence records as the tick read them,
and keeping every other field, a report or review record among them, as the
fresh comment carries it. A record refused or never confirmed is no park:
the tick's state is withheld from every whole-state write behind it
(`ReportCommit.withholds`), its own park flag still holding this tick's
handlers back, and the next tick's recovery reads the comment as it then
stands, with the attempt it carries, and answers it again. A state nothing
was read into has no reading to guard it by and is written whole, as every
park always was.

A reset park moves the checkout before any of that is written, and with it
the landing evidence a finish settled for the head was proved over. Retired
only in the park's write, or behind it, that evidence would outlive a process
lost between the reset and the write, or a write that did not land, and a
checkout put back on the head before the next poll would prove it ready again.
So the reset is recorded against it first (`records_the_reset`): the base tip
the attempt recorded its replay as made onto is blanked in a write of its own,
which only shrinks the comment, and with no tip nothing proves which base the
head was replayed onto, so every later proof of that evidence defers
(`rewrite_evidence_proof.standing_refusal`) and invalidates it whole once the
comment has room. A blank that does not land holds the tick with nothing
reset. A transaction a finish captured and never settled is left to the
park's own write, as it always was: a reset git refuses moved nothing, and the
run stands for the next proof.

The dispatcher's answer to an anchor it holds a handler back for is the git
owner's (`answers_a_held_anchor`), and its stranded park keeps the attempt, so
it is handed this park beside the proof every such park asks first
(`rewrite_landing_moved.abandons_unproved`).
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    recovery_holds as _recovery_holds,
    state as _base_sync_state,
)
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.workflow.engine import (
    guards as _guards,
    pinned_commit_models as _commit_models,
    prompt_delivery as _prompt_delivery,
    report_commits as _commits,
    rewrite_finish_writes as _writes,
    rewrite_landing_moved as _landing_moved,
    rewrite_landing_records as _landing_records,
    verification_records as _evidence_records,
)

log = logging.getLogger("orchestrator.workflow")

_PARK_FLAGS = frozenset((_base_sync_state._AWAITING_HUMAN, _base_sync_state._PARK_REASON))

# A park's record, decided on the attempt it keeps or drops, the park's own
# flags, and the evidence records a landed reset retires beside the attempt.
PARK = _commits.ReportWrite(
    owned=_PARK_FLAGS | {_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID},
    decided_on=frozenset(_attempts._ATTEMPT_KEYS) | _PARK_FLAGS | {
        _evidence_records.PENDING_EVIDENCE,
        _evidence_records.CURRENT_EVIDENCE,
        _evidence_records.EVIDENCE_HISTORY,
    },
)


def lands_a_park(context: _AutoRebaseRecoveryContext, message: str, reason: str) -> None:
    """Park `context`'s issue for a human with `message` and `reason`, recorded through the guarded commit as `PARK`.

    The notice is posted and the park staged on the tick's state as every
    auto-rebase park stages it (`git/base_sync/persistence._park_auto_rebase_failure`);
    what lands is laid over that state, so whatever the recovery does behind
    it starts from the comment as it now stands.
    """
    state = context.state
    _guards._park_awaiting_human(context.gh, context.issue, state, message, reason=reason)
    state.set(_base_sync_state._PARK_REASON, reason)
    if state.synced is None:
        context.gh.write_pinned_state(context.issue, state)
        return
    landed = _commits.ReportCommit(context.gh, context.issue, state).lands(state, PARK)
    if landed.status is not _commit_models.CommitStatus.COMMITTED:
        log.warning(
            "issue=#%d the park of its auto-rebase recovery did not land (%s); nothing is recorded, "
            "and the next tick's recovery answers the comment as it then stands",
            context.issue.number, (landed.refusal or landed.status).value,
        )


def answers_a_held_anchor(held: _AutoRebaseRecoveryContext) -> None:
    """Answer an anchor the dispatcher holds a handler back for, handed the workflow's proof and park.

    The git owner's answer (`git/base_sync/recovery_holds._answers_a_held_anchor`)
    restores a checkout, clears the attempt, or parks it stranded; that park
    keeps the attempt, so it asks the proof first
    (`rewrite_landing_moved.abandons_unproved`) and is recorded as every
    recovery park is (`lands_a_park`).
    """
    _recovery_holds._answers_a_held_anchor(held, _landing_moved.abandons_unproved, lands_a_park)


def records_the_reset(context: _AutoRebaseRecoveryContext) -> bool:
    """Record a reset about to move the checkout against evidence settled for the landed head; may the reset go on.

    The recovery's answer ahead of every reset (`_AutoRebaseRecoveryContext.records_before_a_reset`):
    where a finish of the attempt settled evidence for the head and the
    attempt still records the base tip its replay was made onto, that tip is
    blanked through the guarded commit as the finish's own abandonment is
    (`rewrite_finish_writes.ABANDONMENT`), and laid over the tick's state.
    True where nothing needed recording or the blank landed; False, logged,
    where it was refused or went unconfirmed, for the git owner to hold with
    nothing reset.
    """
    settled = _landing_records.settled(context.state)
    if settled is None or not _attempt_records._recorded_onto(context.state):
        return True
    commit = _commits.ReportCommit(context.gh, context.issue, context.state)
    staged = commit.staging()
    staged.set(_base_sync_state._PENDING_REWRITE_BASE, None)
    landed = commit.lands(staged, _writes.ABANDONMENT)
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        log.info(
            "issue=#%d recorded the reset ahead of it against verification evidence revision %d settled for %.8s",
            context.issue.number, settled.revision, settled.binding.target.target_head,
        )
        return True
    log.warning(
        "issue=#%d the reset could not be recorded against verification evidence revision %d settled for %.8s "
        "(%s); nothing is reset until a later tick records it",
        context.issue.number, settled.revision, settled.binding.target.target_head,
        (landed.refusal or landed.status).value,
    )
    return False
