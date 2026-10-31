# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the fixing stage's resume of a pull request's human feedback freezes before its launch, for its capture.

A human commenting on a pull request the reviewer approved is routed here by
`in_review` (`pending_fix_at` set beside the batch's bookmarks), and the fixing
tick behind it resumes the developer over that batch -- the fresh rescan, or an
operator's `/orchestrator continue` replaying the recorded id lists beside it
(`resume`). Its report is the round's one answer to that feedback, so the
launch carries this road and the shared coordinator captures a return that
finished on its report as it comes back (`implementing/completion_roads`): a
live hold, a lost write, or a restart that discards the return leaves it for
the dispatcher's recovery to finish (`captured_fixes`) rather than for a second
developer to write again over the same batch. An `ACK:`, a question, a timeout,
or a failure finishes on no report, so it earns no capture: its run is
accounted as it returns and the batch it was handed stays the live tick's to
settle or not, with nothing replayed from it later.

What the road freezes is what its settlement applies once the report is handed
on, none of which the run's output can say afterwards. The requirements the
run was handed are fingerprinted off the scan's one read, as its report is
stamped. The batch its prompt delivered is frozen as the pairs its settlement
advances the readers to (`feedback._consumed_delivery`): the issue thread, the
pull request's conversation, its inline review comments, and its review
summaries, each to the newest id quoted on its own surface, the shared
IssueComment cursor no further than the scan's two reads prove complete
(`known_through`), and the delivered stretch only where it already reaches
the reply boundary the read began at -- so nothing posted after the scan is
ever recorded as delivered, and a stretch an earlier bounded prompt left short
of that boundary is never carried over the omission beneath it.
The round settlement the route owes is the reset `review_round` and the
cleared bookmarks, with the settled-round mark the hand-back is bound by.

The handoff is frozen over what that batch was cut from, as the comment
spells it at the launch: the route's stamp (`pending_fix_at`) and the id lists
a `/orchestrator continue` rebuilds the batch from, the pull request the issue
points at, the code-publication receipt -- whose head a resume over a commit an
earlier run left unpushed is still admitted on
(`completion_frozen.published_over`) -- and the pull request's three readers
the batch was read above. Nothing moves any of them while the capture holds
the stage, so a move since is another road's or a human's: a route another
in_review flip stamped, a batch bookmarked afresh, a reader somebody advanced
past what the run was handed, and the run no longer the answer to the input
the issue now carries. The issue thread's reply boundary and delivered stretch
are left out on purpose, since a park's walk and a run-grant's control move
them over nothing delivered while the capture waits, and the requirements
fingerprint already answers for that surface. The park the resume answers is
not frozen either, as on the change request's road: the report's write takes
it down decided on its flags as the tick read them (`reporting._PARK_FLAGS`).
"""
from __future__ import annotations

from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_routes as _routes,
    prompt_delivery as _prompt_delivery,
)
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    feedback as _feedback,
    models as _models,
    reporting as _reporting,
    state as _state,
)
from orchestrator.workflow.stages.implementing import late_gate_models as _late_gate_models
from orchestrator.workflow.stages.implementing.completion_roads import CompletionRoad, RoadCheckout
from orchestrator.workflow.state import WorkflowLabel

_PR_NUMBER = "pr_number"

# The records the in_review route's resume is decided on, frozen as the
# comment spells them at its launch: the route's stamp and the id lists of
# the batch it bookmarked, the pull request, the code-publication receipt
# whole, and the readers of the pull request's three surfaces.
FROZEN = (
    _state._PENDING_FIX_AT,
    *_bookmarks.BATCH_IDS,
    _PR_NUMBER,
    _frozen.PUBLISHED_COMMIT,
    _frozen.PUBLISHED_LEASE,
    _frozen.PUBLISHED_PULL_REQUEST,
    _prompt_delivery.PINNED_PR_LAST_COMMENT_ID,
    _prompt_delivery.PINNED_PR_LAST_REVIEW_COMMENT_ID,
    _prompt_delivery.PINNED_PR_LAST_REVIEW_SUMMARY_ID,
)


def road(
    ctx: _models._FixingContext,
    delivered: _models._FixingFeedback,
    checkout: RoadCheckout,
    requirements: str,
    owed: _late_gate_models._Spends,
) -> CompletionRoad:
    """The pull request feedback road the resume over `delivered` is launched on.

    `requirements` is the fingerprint the run is handed and its report
    stamped with, and `owed` the round settlement the route's report rides.
    """
    return CompletionRoad(_records.CompletionHandoff(
        route=_routes.CompletionRoute.PR_FEEDBACK,
        origin=WorkflowLabel.FIXING,
        requirements_revision=requirements,
        watermarks=_feedback._consumed_delivery(ctx.state, delivered).consumed_pairs(ctx.state),
        spends=owed.fields + _reporting._SETTLES_THE_ROUND,
        frozen=_frozen.frozen_over_the_comment(ctx.state, FROZEN),
    ), checkout)
