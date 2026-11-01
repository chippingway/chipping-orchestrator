# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late developer revision freezes before its launch, for the capture of the report it finishes on.

The developer a human's guidance buys under a late adjudication
(`late_revision`) finishes on a report outcome when it committed a change or
its report had to change, and that return is the one thing that answers the
guidance: a live hold, a lost write, or a restart that discards it would leave
the guidance unread and the paid run lost. So the launch carries this road
(`road`), and the shared coordinator captures a return that finished on a
READY or VERIFIED report as it comes back
(`implementing/completion_roads.CompletionRoad.captures`), for the
dispatcher's recovery to finish with no developer run (`captured_revision`).
An `ACK:`, a question, and a run that failed or did not finish earn none: they
keep their accounting alone, as before.

The road is `late_revision`, recorded under `workflow:decomposing`, and it
settles its own input (`completion_routes.RouteContract.settles_input`): the
guidance the run was handed is consumed by the reconciliation that answers it,
in the late baselines, the shared reply boundary, and the issue-wide
requirements baseline alike, never by the report's later settlement. What it
freezes is the reading the revision's prompt was cut from -- the conversation
a fresh or replacement spawn is re-grounded with included, rendered off that
same reading (`late_revision._resumed`) -- its requirements
revision, and its consumption as the two pairs a recovery holds a reading of
the thread to again (`_consumed`) -- the newest trusted comment the reading
counted, which a cut of the thread at that comment fingerprints exactly as the
launch did, and the requirements it hashed to. Its handoff is frozen over the
records that say which candidate the run answered, what its prompt quoted, and
where that candidate stands (`FROZEN`): the cycle and generation, the frozen
candidate and base, the phase, the late baseline's comment watermark and the
replies owed a whole quote -- which, with the thread cut where the reading
counted, select every guidance comment the prompt quoted -- the route
bookkeeping a hold on the pair still owes (`late_spends`), the publication
group a post-publication generation was entered on, the pull request, and the
code-publication receipt, through which a pull request still standing on the
commit last published there -- the head a post-publication candidate was built
on -- is admitted (`completion_frozen.published_over`). None of those moves
while a capture holds the stage, so one moved since is another road's or a
human's -- an obligation an operator added among them, which the run was never
quoted, or a handoff the pair now owes -- and the run no longer the answer the
cycle is owed. The measurement
taken over the pair is not among them: the reconciliation measures the
candidate again from scratch, whatever the record says it measured before.

What becomes of the capture once the reconciliation answers the run -- handed
to the delivery in the very commit that re-measures the candidate, kept
pending where the comment has no room for that commit, withdrawn behind a park
-- is `late_revision_landing`'s.
"""
from __future__ import annotations

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_routes as _routes,
    prompt_delivery as _prompt_delivery,
)
from orchestrator.workflow.late_split import formats as _formats, keys as _late_keys
from orchestrator.workflow.stages.decomposition.late_content_models import _LateContentSignal
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import completion_roads as _completion_roads, drift_road as _drift_road
from orchestrator.workflow.state import WorkflowLabel

# The records a revision's handoff is frozen over: which candidate the run
# answered -- the cycle, the generation, the frozen pair, the phase -- what its
# prompt quoted -- the late baseline's comment watermark and the replies owed a
# whole quote -- the route bookkeeping a hold on the pair still owes, and where
# that candidate stands: the publication group a post-publication generation
# was entered on, the pull request, and the code-publication receipt whole --
# and the obligations a split may already have taken on outside, which a
# revision may not replace its candidate over: the children it created and the
# resources and consumers its ledgers record. Nineteen in all. The issue the
# cycle is on and the measurement taken over the pair are not among them: the
# capture's own invocation binds it to this issue's comment and cycle, and the
# reconciliation measures again from scratch.
FROZEN = (
    _late_keys.CYCLE_ID,
    _late_keys.GENERATION,
    _late_keys.CANDIDATE_SHA,
    _late_keys.BASE_SHA,
    _late_keys.PHASE,
    _late_keys.COMMENT_WATERMARK_ID,
    _late_keys.OWED_REPLIES,
    _late_keys.SPENDS,
    _late_keys.POST_PUBLICATION,
    _late_keys.SOURCE_STAGE,
    _late_keys.PUBLISHED_PR_NUMBER,
    _late_keys.PUBLISHED_SHA,
    "pr_number",
    _frozen.PUBLISHED_COMMIT,
    _frozen.PUBLISHED_LEASE,
    _frozen.PUBLISHED_PULL_REQUEST,
    _late_keys.SPLIT_CHILDREN,
    _late_keys.RESOURCES,
    _late_keys.CONSUMERS,
)


def road(context: _LateContext, signal: _LateContentSignal) -> _completion_roads.CompletionRoad:
    """The road the revision `signal` buys is launched on, in the issue's own checkout, frozen over the comment.

    Frozen over the comment as the tick last read it, so nothing the tick
    staged ahead of the launch -- the park it answers, the notice it posted --
    is read afterwards as another road's move.
    """
    state, number = context.state, context.issue.number
    return _completion_roads.CompletionRoad(_records.CompletionHandoff(
        route=_routes.CompletionRoute.LATE_REVISION,
        origin=WorkflowLabel.DECOMPOSING,
        requirements_revision=signal.requirements_hash,
        watermarks=_consumed(signal),
        frozen=_frozen.frozen_over_the_comment(state, FROZEN),
    ), _drift_road.launched_in(context.spec, number, state, _worktree_paths._worktree_path(context.spec, number)))


def read_through(capture: _records.CompletionCapture) -> int | None:
    """The newest trusted comment the reading `capture`'s revision was handed counted; None where it froze none."""
    through = dict(capture.handoff.watermarks).get(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID)
    return through if _formats.whole_number(through) else None


def _consumed(signal: _LateContentSignal) -> tuple:
    """The reading's consumption, as pairs: the newest trusted comment it counted, and the requirements it hashed to."""
    hashed = ((_prompt_delivery.PINNED_USER_CONTENT_HASH, signal.requirements_hash),)
    through = signal.fingerprint.comment_watermark_id
    if not _formats.whole_number(through):
        return hashed
    return ((_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID, through), *hashed)
