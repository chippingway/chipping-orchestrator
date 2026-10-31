# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the fixing stage's resume of a reviewer's change request freezes before its launch, for the capture of that run.

A round a reviewer's change request handed its developer can park -- a
question, a timeout, a push or a tree it could not publish, a report it could
not deliver, a launch that may have run -- and the round is finished on
`workflow:fixing` by the resume a human's reply or an operator's
`/orchestrator continue` buys (`resume`). That resume is the validating route's
(`pending_fix_at` unset) and finishes the very request the round answered, so
its report is captured on the change request's road as the direct round's is
(`validating/fix_road`), and a live hold, a lost write, or a restart that
discards the return leaves it for the dispatcher's recovery to finish
(`captured_fixes`) rather than for a second developer to write again. The
in_review route's resume, which answers a pull request's human feedback, is
another road's and freezes nothing here.

What the road freezes is what its settlement applies once the report is handed
on, none of which the run's output can say afterwards: the requirements the
run was handed, fingerprinted off the scan's one read as the report is stamped;
the batch the prompt delivered, as the pairs its settlement advances the
readers to (`feedback._consumed_delivery`) -- the reply, or the command a
continue answered beside the replay -- and nothing later on the thread; the
round settlement the route owes, `review_round` bumped and the bookmarks
cleared, with the settled-round mark the hand-back is bound by; and the
handoff, over the records the resume was decided on as the comment spells
them at the launch -- the route discriminator, the reviewer's feedback anchor
a continue replays, the pull request the issue points at, the
code-publication receipt, and the settled report and verification evidence
the reviewer's request was reviewed over, which the park the round took
left as they were -- so a move of any of them since is another road's, and
the run no longer the answer to it: a report settled since, or evidence a
later revision superseded, leaves an answer to a review nobody is asking
about any more. The receipt also names the head the pull request stands on
where the checkout carries a commit an earlier run left unpushed
(`completion_frozen.published_over`), so a resume reporting over that work is
still admitted on the head the run did not start on.
The park the resume answers is not frozen: it is the one record the resume
itself moves, taken down when the run's report is handed on. It is held at
that write instead, the report recorded decided on its flags as the tick read
them (`reporting._PARK_FLAGS`), so a park recorded meanwhile -- a spent run
ledger's among them -- refuses the record and stands.
"""
from __future__ import annotations

from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_routes as _routes,
    report_records as _report_records,
    verification_records as _evidence_records,
)
from orchestrator.workflow.stages.fixing import (
    feedback as _feedback,
    models as _models,
    reporting as _reporting,
    state as _state,
)
from orchestrator.workflow.stages.implementing import late_gate_models as _late_gate_models
from orchestrator.workflow.stages.implementing.completion_roads import CompletionRoad, RoadCheckout
from orchestrator.workflow.state import WorkflowLabel

_PR_NUMBER = "pr_number"

_REVIEWER_ANCHOR = "pending_fix_reviewer_comment_id"

# The records the validating route's resume is decided on, frozen as the
# comment spells them at its launch: the route, the reviewer's anchor, the
# pull request; the code-publication receipt naming the head that pull
# request stands on, all three of its members; and the settled report and every verification evidence
# record the reviewer's request was reviewed over -- the revision floor a
# later revision raises among them -- which no park moves.
FROZEN = (
    _state._PENDING_FIX_AT,
    _REVIEWER_ANCHOR,
    _PR_NUMBER,
    _frozen.PUBLISHED_COMMIT,
    _frozen.PUBLISHED_LEASE,
    _frozen.PUBLISHED_PULL_REQUEST,
    _report_records.CURRENT_REPORT,
    _report_records.REPORT_HANDOFF,
    _evidence_records.CURRENT_EVIDENCE,
    _evidence_records.PENDING_EVIDENCE,
    _evidence_records.EVIDENCE_HISTORY,
    _evidence_records.EVIDENCE_HANDOFF,
    _evidence_records.REVISION_FLOOR,
)


def road(
    ctx: _models._FixingContext,
    delivered: _models._FixingFeedback,
    checkout: RoadCheckout,
    requirements: str,
    owed: _late_gate_models._Spends,
) -> CompletionRoad | None:
    """The change request's road the resume over `delivered` is launched on; None on the in_review route.

    `requirements` is the fingerprint the run is handed and its report
    stamped with, and `owed` the round settlement the route's report rides.
    """
    if ctx.state.get(_state._PENDING_FIX_AT) is not None:
        return None
    return CompletionRoad(_records.CompletionHandoff(
        route=_routes.CompletionRoute.REQUESTED_CHANGES,
        origin=WorkflowLabel.FIXING,
        requirements_revision=requirements,
        watermarks=_feedback._consumed_delivery(ctx.state, delivered).consumed_pairs(ctx.state),
        spends=owed.fields + _reporting._SETTLES_THE_ROUND,
        frozen=_frozen.frozen_over_the_comment(ctx.state, FROZEN),
    ), checkout)
