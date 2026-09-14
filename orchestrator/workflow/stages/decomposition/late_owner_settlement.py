# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist owner-check settlement, cancellation, unreadable parks, and recovery notices.

Cancellation drops the pending claim and records its phase before telemetry.
Recovery announcements are deduplicated within the existing park episode.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.workflow.engine import comments as _comments, usage as _usage
from orchestrator.workflow.late_split.models import LateFailure
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

log = logging.getLogger("orchestrator.workflow")


_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# Stamped on every follow-up so a later tick recognizes one it posted even
# when the pinned write that was supposed to record it never landed. This
# mode's own, not the validating route's: a follow-up from another episode
# must not be able to silence this one. An HTML comment, so it is invisible in
# the rendered thread.
_RECOVERY_FOLLOWUP_MARKER = "<!--orchestrator-late-owner-recovery-->"

_RECOVERED_FOLLOWUP = (
    ":arrows_counterclockwise: Recovered automatically: this issue's own "
    "state could not be read when the adjudication finished, and now can; "
    "processing resumed. No action needed.\n\n"
    f"{_RECOVERY_FOLLOWUP_MARKER}"
)

_UNREADABLE_PARK = (
    "this issue's oversized committed candidate has been adjudicated, but "
    "whether the issue itself is still open could not be read from GitHub -- "
    "so nothing was published, superseded, or created. The result is "
    "recorded: the next tick takes the same read again without re-running any "
    "agent, and says so here when it succeeds."
)


def _cleared(context: _LateContext) -> None:
    """Drop the claim this read answered, saying so if a park is being retired.

    The follow-up goes out BEFORE the write that clears the park, so a crash
    between them costs the write rather than the sentence -- the next tick
    finds the claim still standing, finds its own follow-up already on the
    thread, and clears without repeating it.

    Only a park THIS guard filed is retired or announced. An issue stopped on
    a question or a stalled revision was never told anything by this guard, so
    there is nothing to take back and nothing of somebody else's to clear.

    Retired whether or not it was ever announced, and announced only if it
    was: a park whose own notice GitHub refused told nobody anything, so there
    is no alarming last word to take back and a follow-up would be the first
    this episode said -- a recovery message for a failure the thread never
    heard about.

    "Was it announced" is asked of the obligation, which is safe HERE and only
    here: the tick reconciles that obligation against the issue before any of
    this runs, so a notice the thread carries has already been discharged from
    what GitHub holds. Without that step the question would answer itself from
    a record, and a post that landed beside a write that did not would read as
    a silence -- costing the human the one sentence this park promises them.
    """
    if _late_park_state._stands_for(context, _late_park_state.PARK_OWNER_UNREADABLE):
        if _late_notice._owed_notice(context) is None:
            _announce_recovery(context)
        _late_parks._answer_park(context)
    context.generation = replace(
        context.generation, owner_check_pending=False,
    )
    _late_park_state._persist(context)


def _cancelled(context: _LateContext) -> None:
    """Mark this cycle cancelled for the cleanup that has to settle it.

    Irreversible within the cycle: the stamp is kept from the first marking,
    so a later tick that finds the issue reopened re-marks the same
    cancellation rather than moving the moment the obligation was taken on.

    The pending marker goes with it. What it exists for is bringing a tick
    back to this read, and this read has now been taken.

    A park notice still owed goes with it too. Every sentence this mode owes
    a human explains a candidate under adjudication, and a cancelled cycle
    has none: saying one now would ask somebody to settle a question about an
    issue they have already closed.

    Durable before it is reported, like every other record in this mode. What
    the remote still owes is already on the generation and is not touched
    here -- reclaiming it is the cleanup path's job, and this is the mark that
    path reads.

    Recorded and reported ONCE per cycle. Several barriers can reach a closed
    reading in one run -- the read taken between two children, the one taken
    before the activation -- and a record that already carries the mark is
    left exactly where the FIRST one put it: the stamp, the boundary, and the
    `late_cancellation` a sink is handed all belong to that marking, and
    repeating them would put one record per barrier on a cycle that ended at
    the first. The claim the repeat's own read was taken under is still
    dropped, because that read has now been taken.
    """
    if context.generation.cancelled:
        _claim_dropped(context)
        return
    log.warning(
        "issue=#%d was closed while its oversized candidate %s was being "
        "adjudicated; cancelling cycle %d",
        context.issue.number,
        context.generation.candidate_sha,
        context.generation.cycle_id,
    )
    context.generation = replace(
        context.generation.cancel(_usage._now_iso()),
        phase=LatePhase.CANCELLING,
        owner_check_pending=False,
    )
    _late_notice._notice_settled(context)
    _late_park_state._persist(context)
    _late_outcome._emit_cancellation(context)


def _claim_dropped(context: _LateContext) -> None:
    """Take the owner-read obligation off a cycle already marked over.

    What the claim exists for is bringing a tick back to a read of this
    issue, and the read that reached this has been taken. Written only where
    one is actually standing: a repeat that owes nothing writes nothing, so
    a cancelled cycle costs a pinned write on the barrier that marked it and
    on none of the barriers after it.
    """
    if not context.generation.owner_check_pending:
        return
    context.generation = replace(
        context.generation, owner_check_pending=False,
    )
    _late_park_state._persist(context)


def _unreadable(context: _LateContext) -> None:
    """Leave the claim standing, and park unless something else already does.

    Nothing durable is written here: the claim the read was taken under IS the
    retry obligation, and it went out before the read. What is left to decide
    is only whether a human is told, which is the park.

    The park is skipped for an issue already handed back to one -- that issue
    is stopped either way, and overwriting the reason it was stopped for would
    cost the human the question they were actually asked.

    What happens to the notice that park staged depends on whether anything
    will ever say it instead. A park a later attempt supersedes is re-taken
    and re-announced by that attempt, so holding its sentence back costs a
    tick; a park no attempt supersedes -- a stalled revision waiting to be
    told what a dirty checkout now means -- has no such tick coming, and
    dropping its sentence would leave a human looking at an `awaiting_human`
    with nothing saying what to do about it for as long as the read kept
    failing. That one is said, on a thread this tick could not prove is open,
    because silence there is unbounded and a stray comment is not.
    """
    _late_outcome._emit_failure(context, LateFailure.OWNER_READ_FAILED)
    if _late_park_state._stands_parked(context):
        log.info(
            "issue=#%d is already parked; leaving the owner read owed rather "
            "than replacing what it is parked on",
            context.issue.number,
        )
        _late_parks._release_unsuperseded_park(context)
        return
    _late_parks._park(
        context,
        _UNREADABLE_PARK,
        reason=_late_park_state.PARK_OWNER_UNREADABLE,
    )


def _announce_recovery(context: _LateContext) -> None:
    """Retire the alarming last word the park this tick answered left behind.

    The thread is read rather than a receipt remembered, because the comment
    and the write that clears the park cannot be one operation. Scoped to this
    episode by the park's own mention id, so an older follow-up sitting below
    the watermark cannot silence a later park's, and a park with no mention
    behind it says nothing at all -- nobody was pinged, so there is nothing to
    take back.
    """
    if context.state.get(_LAST_ACTION_COMMENT_ID) is None:
        return
    if _episode_already_announced(context):
        return
    _comments._post_issue_comment(
        context.gh, context.issue, context.state, _RECOVERED_FOLLOWUP,
    )


def _episode_already_announced(context: _LateContext) -> bool:
    """Whether this park episode's follow-up is already on the thread."""
    watermark = context.state.get(_LAST_ACTION_COMMENT_ID)
    return any(
        _RECOVERY_FOLLOWUP_MARKER in (issue_comment.body or "")
        for issue_comment in context.gh.comments_after(
            context.issue, watermark,
        )
    )
