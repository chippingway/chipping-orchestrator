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

The dispatcher's answer to an anchor it holds a handler back for is the git
owner's (`answers_a_held_anchor`), and its stranded park keeps the attempt, so
it is handed this park beside the proof every such park asks first
(`rewrite_landing_moved.abandons_unproved`).
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import (
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
    rewrite_landing_moved as _landing_moved,
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
