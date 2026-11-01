# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a rewritten head's report refresh freezes before its developer is launched, and which return it captures.

The report hold asks the developer for a fresh report of a head this
orchestrator rewrote (`report_refresh`), and that report is the one thing
that pays the debt the rewrite left. A live hold, a lost write, or a restart
that discards the return would leave the debt owed and the paid run lost, so
the launch carries this road (`road`), and the shared coordinator captures a
return that finished on the refresh's report as it comes back
(`implementing/completion_roads`), for the dispatcher's recovery to finish
with no developer run (`captured_refresh`).

The road is `report_refresh`, recorded under `workflow:validating` and paid
only by a fresh READY report (`completion_routes`): its requirements are the
baseline the drift check had just proved, and the head it launches from is the
rewritten head the checkout was proved to stand on. Its handoff is frozen over
what the refresh was entered under, as the comment spells it at the launch
(`FROZEN`): the pull request, the debt it answers, the code-publication receipt
whole, and the settled report pair the debt is owed a refresh over -- and, for
a refresh entered over a proved approval squash or final docs pass, the records
that lineage was proved from beside them (`LINEAGE`): every evidence record the
squash's carry is kept in, and the final docs pass's completion. A record moved
since is another road's or a human's, and the run's report no longer the one
the debt was owed.

The road's contract asks more of a return than a report outcome
(`RefreshRoad.source`). The run was asked for a report of the rewritten head
and nothing else, so only one that left the checkout clean on that head, with
no account quota stopping it, completed it: a quota stop is what its own
disposition parks it as whatever its message closed on, and a commit or loose
work makes the report one of something the pull request does not carry. That
is read as the run returns, so a hold behind it -- and a human cleaning or
resetting the checkout meanwhile -- cannot make a return that did not complete
the refresh into one its recovery publishes. Such a return keeps its
accounting alone, and the refresh's own disposition answers on that very
reading (`RefreshRoad.returned_over`), so no cleanup between the return and
the disposition publishes it on the live tick either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_routes as _routes,
    final_docs_records as _final_docs,
    report_records as _report_records,
    report_rewrite_debt as _rewrite_debt,
    verification_records as _evidence_records,
)
from orchestrator.workflow.stages.implementing import session_read as _session_read
from orchestrator.workflow.stages.implementing.completion_roads import CompletionRoad, RoadCheckout
from orchestrator.workflow.stages.validating import (
    report_refresh_models as _models,
    report_refresh_outcomes as _outcomes,
)
from orchestrator.workflow.state import WorkflowLabel

# The records every refresh's handoff is frozen over: the pull request, the
# debt it answers, the code-publication receipt whole, and the settled report
# pair the debt is owed a refresh over.
FROZEN = (
    "pr_number",
    _rewrite_debt.REWRITE_DEBT,
    _frozen.PUBLISHED_COMMIT,
    _frozen.PUBLISHED_LEASE,
    _frozen.PUBLISHED_PULL_REQUEST,
    _report_records.CURRENT_REPORT,
    _report_records.REPORT_HANDOFF,
)

# What a refresh entered over a proved lineage freezes beside them: every
# record an approval squash's carry is kept in -- owed, current, or in the
# history -- and the final docs pass's completion.
LINEAGE = (
    *FROZEN,
    _evidence_records.PENDING_EVIDENCE,
    _evidence_records.CURRENT_EVIDENCE,
    _evidence_records.EVIDENCE_HISTORY,
    _final_docs.FINAL_DOCS,
)


@dataclass(frozen=True)
class RefreshRoad(CompletionRoad):
    """The refresh's road: a return is captured only where the run completed what the refresh asked of it.

    `returned` is the checkout each attempt was read as when it returned, by
    the invocation it came from -- "" clean on the rewritten head, why not
    otherwise, None where nobody could read it -- which the refresh's own
    disposition answers on (`returned_over`).
    """

    returned: dict = field(default_factory=dict, compare=False)

    def source(self, agent_result: AgentResult) -> str | None:
        """The rewritten head, where no quota stopped the run and it left the checkout clean on that head; else None.

        The checkout is read as the refresh's own disposition reads it
        (`report_refresh_outcomes._checkout_refusal`), and kept as the
        attempt's reading: a HEAD or a tree nobody could read proves no clean
        checkout either, so it earns no capture.
        """
        if _session_read._is_session_limit(agent_result):
            return None
        head = self.checkout.before_sha
        refusal = _outcomes._checkout_refusal(self.checkout.worktree, head)
        self.returned[agent_result.invocation] = refusal
        return head if refusal == "" else None

    def returned_over(self, agent_result: AgentResult) -> str | None:
        """Why the checkout `agent_result` returned over refuses the refresh, as read then; "" where nothing did.

        "" too where no reading was taken of that attempt -- a return no
        report outcome qualified -- which leaves its disposition to read the
        checkout itself. A refusal read as the run returned is never undone
        by a later reading: a cleanup or a reset behind it makes no return
        over a commit or loose work a refresh.
        """
        return self.returned.get(agent_result.invocation, "")


def road(refresh: _models._ReportRefresh, worktree: Path) -> RefreshRoad:
    """The road `refresh`'s run is launched on in `worktree`, frozen over the comment as the refresh was entered on it.

    The branch is the debt's, which the refresh holds to the one the issue
    pins, and the head the run begins on is the rewritten head the checkout
    was proved to stand on.
    """
    handoff = _records.CompletionHandoff(
        route=_routes.CompletionRoute.REPORT_REFRESH,
        origin=WorkflowLabel.VALIDATING,
        requirements_revision=refresh.requirements,
        frozen=_frozen.frozen_over_the_comment(refresh.state, LINEAGE if refresh.approved else FROZEN),
    )
    return RefreshRoad(handoff, RoadCheckout(worktree, refresh.debt.branch, refresh.head))


def entered_over_a_lineage(capture: _records.CompletionCapture) -> bool:
    """Whether `capture`'s refresh was entered over a proved approval squash or final docs pass: it froze `LINEAGE`."""
    return set(LINEAGE) <= dict(capture.handoff.frozen).keys()
