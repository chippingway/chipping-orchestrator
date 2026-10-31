# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reviewer's change request freezes before its developer is launched, for the capture of that run.

The developer a handed change request owes is launched once (`review_handoffs`),
and its report is the round's one answer to the reviewer: a live hold, a lost
write, or a restart that discards the return would leave the request handed,
its developer launched, and nothing durable describing what that developer
did -- which the fixing stage then reads as a launch that may have run and
drops, or parks for `/orchestrator continue`, paying for the work again. So
the launch carries this road (`road`), and the shared coordinator captures a
return that finished on its report as it comes back
(`implementing/completion_roads`).

What the road freezes is what that answer is an answer to, none of which the
run's own output can say afterwards. The route is the change request's, the
report recorded under `workflow:fixing`. The requirements are the baseline the
issue records, the revision the round's report is stamped with where no
capture holds it: the fix prompt hands the developer the reviewer's findings
and no requirements of its own, and the resumed conversation was last handed
that baseline. The round settlement is the frozen pair the round spends --
`review_round` one past the reviewer's round and the feedback anchor cleared
-- with the settled-round mark the fixing stage's recovery binds a hand-back
by, the very pair the round's own report rides. The handoff is frozen over
what the request is: the request as handed -- its round, subject, evidence
claim, the agent-run count its owed launch was handed at, and the anchor of
its post -- the pull request the issue points at, and the feedback anchor a
failed run's continue replays. Each is frozen as the comment spells it, not as
the tick staged it, so a move the tick made and has yet to write is never read
as another road's. The rest of what the request's retirement is decided on
(`review_writes.ANSWERED`) -- the park's flags, and the start of the owed
launch, which the launch itself writes -- is held at the write instead: the
round's report is recorded, captured or not, decided on all of it and on
everything the request stands on (`review_writes.VERDICT_STANDS_ON`) -- the
settled report pair and every verification evidence record it was reviewed
over -- as the tick read them (`report_records.HandedRun.decided_on`), so the
recovery's re-read of that subject binds the transfer that records the
report, and a subject moved or damaged while it was read refuses it.

The prompt delivers nothing the issue-thread readers count, since the
reviewer's findings are a comment this orchestrator posted, so the road
settles no watermark and records no delivered stretch.
"""
from __future__ import annotations

from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_routes as _routes,
    prompt_delivery as _prompt_delivery,
)
from orchestrator.workflow.stages.implementing.completion_roads import CompletionRoad, RoadCheckout
from orchestrator.workflow.stages.validating import models as _models, review_verdicts as _verdicts
from orchestrator.workflow.state import WorkflowLabel

_PR_NUMBER = "pr_number"

# The records a change request's handoff is frozen over: the request as
# handed, the pull request the issue points at, and the feedback anchor.
FROZEN = (_verdicts.RETURNED_VERDICT, _PR_NUMBER, _verdicts._FEEDBACK_ANCHOR)


def road(context: _models._RequestedChanges, before_sha: str, spends: tuple) -> CompletionRoad:
    """The road the developer `context` hands the request to is launched on, from `before_sha`.

    `spends` is the round settlement the round's report rides, frozen as the
    caller froze it for that report.
    """
    state = context.state
    baseline = state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH)
    handoff = _records.CompletionHandoff(
        route=_routes.CompletionRoute.REQUESTED_CHANGES,
        origin=WorkflowLabel.FIXING,
        requirements_revision=baseline if isinstance(baseline, str) else "",
        spends=spends,
        frozen=_frozen.frozen_over_the_comment(state, FROZEN),
    )
    branch = _naming._resolve_branch_name(state, context.spec, context.issue.number)
    return CompletionRoad(handoff, RoadCheckout(context.wt, branch, before_sha))
