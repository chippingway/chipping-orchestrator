# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a taken-over auto-rebase replay leaves its pull request owing once the settlement publishes it.

An authorized `single` over a generation that took an unpublished replay over
from its auto rebase (`workflow/engine/rewrite_takeover.py`) publishes a head
this orchestrator made: the clean rebase of the head the pull request stood
on, which no developer report is about. Handed back to its stage as it is,
the reviewer road refuses the report the issue last settled and parks for a
human whose reply only restarts a report of a commit this orchestrator made
-- the gap the rewrite finish closes for every rebase it publishes itself. So
the settlement records the same claim (`workflow/engine/report_rewrite_debt.py`)
before its label hands the head on: the pull request, the branch the push
went to, the head the replay replaced, and the replay itself, retargeting a
claim an earlier rewrite left exactly as that owner does.

What proves the rewrite is the generation's own ownership of the replay,
beside the code-publication receipt the push wrote -- or the retry after a
landed push re-recorded -- naming the replay over the frozen head on the frozen
pull request. Either short of that records nothing, and the reviewer road
holds the report it finds to the head, as it does for every head nobody
proved this orchestrator's.

The ownership stays on the generation until the retirement that drops it, so
a retry after a landed push re-derives the same claim without pushing again,
and a claim already recorded is a replay that writes nothing. A proved claim
the pinned comment has no room for holds the handoff with the push kept: the
issue stays under adjudication and the next tick records the claim and
finishes the settlement once room is made. The park that asks for that room
is measured before it is taken, since it grows the same full comment: where
it does not fit either, nothing is posted or written, and the generation's
ownership and the receipt already on the comment are what the next tick
re-derives the claim from.
"""
from __future__ import annotations

import copy
import logging

from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_state as _report_record_state,
    report_record_values as _record_values,
    report_rewrite_debt as _rewrite_debt,
    report_rewrite_room as _rewrite_room,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateFailure
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import late_publication_state as _late_publication_state

log = logging.getLogger("orchestrator.workflow")

_UNRECORDED_PARK = (
    "this issue's adjudicated candidate `{replay}` -- the orchestrator's auto "
    "rebase of `{replaced}` -- is published on pull request #{pr}, and the "
    "report debt that head is owed does not fit on this issue's pinned state "
    "comment. Handed back without it, the reviewer would be handed the report "
    "of the head it replaced, so the issue is still under adjudication with "
    "the push kept. Remove records this issue no longer needs from the pinned "
    "state comment and the next tick records the debt and finishes the "
    "settlement, without pushing again or re-running any agent."
)


def _records_the_replay_debt(context: _LateContext) -> bool:
    """Make durable the report debt a published taken-over replay leaves; False where it parked for room.

    True, with nothing written, for every candidate the generation did not
    take over from an auto rebase, for a receipt that does not prove its
    publication, for a standing claim the replay cannot be carried onto, and
    for a claim already recorded.
    """
    if not context.generation.publication.replayed_as(context.generation.candidate_sha):
        return True
    rewrite = _published_replay(context)
    if rewrite is None:
        log.warning(
            "issue=#%d the code-publication receipt does not prove the taken-over replay %s "
            "published; recording no report debt for it",
            context.issue.number, context.generation.candidate_sha,
        )
        return True
    standing = context.state.get(_rewrite_debt.REWRITE_DEBT)
    if _rewrite_debt.records_rewrite(context.state, rewrite):
        if context.state.get(_rewrite_debt.REWRITE_DEBT) != standing:
            _late_park_state._persist(context)
        log.info(
            "issue=#%d PR #%d stands on the taken-over replay %.8s of %.8s; it is owed a report of that head",
            context.issue.number, rewrite.pr_number, rewrite.rewritten_head, rewrite.previous_head,
        )
        return True
    if _rewrite_room.outgrows_the_comment(context.state, rewrite):
        return _parked_for_room(context, rewrite)
    log.warning(
        "issue=#%d the report debt standing on PR #%d cannot be carried onto the taken-over replay %s; "
        "leaving it as it is",
        context.issue.number, rewrite.pr_number, rewrite.rewritten_head,
    )
    return True


def _published_replay(context: _LateContext) -> _rewrite_debt.RewriteDebt | None:
    """The rewrite the receipt proves the settlement published as the replay, or None.

    The receipt has to name the replay pushed from the head the generation
    froze onto the pull request it froze, which is what both the settlement's
    own push and the retry after a landed one record. The branch is the one
    the settlement pushed, resolved as every push of this issue resolves it.
    """
    generation = context.generation
    publication = generation.publication
    published = _late_publication_state._publication_from(
        context.state, publication.published_sha, publication.published_pr_number,
    )
    if published != generation.candidate_sha:
        return None
    return _rewrite_debt.RewriteDebt(
        pr_number=publication.published_pr_number,
        branch=_naming._resolve_branch_name(context.state, context.spec, context.issue.number),
        previous_head=publication.published_sha,
        rewritten_head=generation.candidate_sha,
    )


def _parked_for_room(context: _LateContext, rewrite: _rewrite_debt.RewriteDebt) -> bool:
    """Hold the handoff for a proved debt the pinned comment has no room for; always False.

    Parked for the room where the park fits the comment, and held with nothing
    posted or written where it does not: a write past what GitHub holds would
    fail after the notice it follows, while the comment as it stands already
    carries everything the next tick asks again from.
    """
    log.error(
        "issue=#%d published the taken-over replay %s on PR #%d and the report debt it is owed does not "
        "fit on the pinned state comment; holding the settlement",
        context.issue.number, rewrite.rewritten_head, rewrite.pr_number,
    )
    _late_outcome._emit_failure(context, LateFailure.PR_RECONCILE_FAILED)
    if not _the_park_fits(context):
        log.error(
            "issue=#%d has no room on the pinned state comment for the park that would ask for room either; "
            "posting and writing nothing, so the next tick asks again",
            context.issue.number,
        )
        return False
    _late_parks._park(
        context,
        _UNRECORDED_PARK.format(
            replay=rewrite.rewritten_head, replaced=rewrite.previous_head, pr=rewrite.pr_number,
        ),
        reason=_late_park_state.PARK_PR_UNRECONCILED,
    )
    return False


def _the_park_fits(context: _LateContext) -> bool:
    """Whether the room park, and the notice it posts, keep the pinned comment within what GitHub holds.

    Measured on the comment its writes produce at their widest: the
    generation as it is written, the park's flags, and the entry its notice
    adds to the ledger of this orchestrator's comments beside the watermark it
    moves, both at the widest id a comment is recorded at. The sentence the
    park owes is left out, as the write behind its delivery leaves it out: the
    notice owner keeps that obligation only where it fits beside the flags
    (`late_notice._owe_notice`) and drops it once the sentence is posted.
    """
    measured = PinnedState(state_data=copy.deepcopy(context.state.data))
    _late_state.write_late_generation(measured, context.generation)
    measured.data.pop(_late_notice.PARK_NOTICE, None)
    measured.set(_late_park_state._AWAITING_HUMAN, True)
    measured.set(_late_park_state._PARK_REASON, _late_park_state.PARK_PR_UNRECONCILED)
    _comments._reserve_comment_slot(measured, _record_values.MAX_RECORDED_NUMBER)
    measured.set(_late_park_state._LAST_ACTION_COMMENT_ID, _record_values.MAX_RECORDED_NUMBER)
    return _report_record_state.fits_the_comment(measured.data)
