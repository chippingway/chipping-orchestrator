# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round that finished on a report, and the write that closes it.

Every developer prompt this stage sends teaches the report contract, so a fix
round can end on `REPORT: READY` or `REPORT: VERIFIED` exactly as an initial
implementation can. When it does, the round owes a publication this tick
cannot guarantee: the push can fail, the post can fail, the process can die
between them.

So what such a round consumed and what its route spent do not close here.
Both ride the RECORD of the report -- durable before the size gate and before
the push -- and the write that completes the transaction is the one that
applies them, whether that is this tick's binding or the reconciliation ahead
of a later handler. Settled here instead, a crash in that window leaves the
feedback answered and the reviewer round spent for a report nobody published,
with the `pending_fix_*` replay source cleared along with them.

Every other outcome a fix round reaches -- the `ACK:`, the question, the
timeout, the dirty tree -- writes no report at all, and those close their own
bookkeeping directly in `resume`. Telling the two apart is the whole of what
this owner is asked first.
"""
from __future__ import annotations

from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import (
    report_binding as _report_binding,
    report_delivery as _report_delivery,
    report_outcomes as _report_outcomes,
    report_records as _report_records,
)
from orchestrator.workflow.stages.fixing import feedback as _feedback, models as _models
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _late_publication_state,
)
from orchestrator.workflow.state import WorkflowLabel


def _reports(run: _models._FixingResumeRun) -> bool:
    """Whether this run finished on one of the two report outcomes."""
    return _report_outcomes._finished_on_a_report(run.dev_result)


def _recording_stops_the_tick(
    ctx: _models._FixingContext,
    run: _models._FixingResumeRun,
    feedback: _models._FixingFeedback,
    owed,
) -> bool:
    """Record this round's report, carrying what its run consumed and spent.

    True is a tick this call ended: a report this build cannot record, which
    parks with the commit still in the worktree and nothing published.

    The two groups are handed over rather than written beside the record for
    the reason the record itself is durable -- the publication they belong to
    is not this tick's to guarantee. Settled by the write that COMPLETES the
    transaction, they cannot come apart from the report they were earned by.
    """
    return _report_delivery.recording_stops_the_tick(
        ctx.gh, ctx.issue, ctx.state, run.dev_result,
        _report_records.RouteDebt(
            route=WorkflowLabel.FIXING,
            watermarks=_feedback._consumed_delivery(
                ctx.state, feedback,
            ).consumed_pairs(ctx.state),
            spends=owed.fields,
        ),
    )


def _holds_an_unpublished_report(
    ctx: _models._FixingContext, run: _models._FixingResumeRun,
) -> bool:
    """Put this round's report on the pull request; True where it is still owed.

    Bound to the publication first and posted second, in the engine's own two
    steps: the binding is one local write, so a post GitHub refuses leaves a
    transaction the reconciliation ahead of a later handler can finish rather
    than a delivery nothing would go back for.

    The commit the report is about is the one the size gate RECORDED pushing,
    not the head this run left: the gate publishes the candidate it measured,
    and a checkout something moved between the two readings would bind the
    report to a commit the pull request never received. The head is the
    fallback for a push whose receipt this build could not read back.

    True holds the caller's relabel, which is what keeps a reviewer from being
    sent to a head whose report nothing on the pull request carries.
    """
    _report_binding.binds_and_publishes(
        ctx.gh, ctx.issue, ctx.state, _report_binding.ReportPublication(
            pull_request=ctx.pr,
            repo_slug=ctx.spec.slug,
            branch=_naming._resolve_branch_name(
                ctx.state, ctx.spec, ctx.issue.number,
            ),
            commit=(
                _late_publication_state._published_commit(ctx.state)
                or run.after_sha or ""
            ),
        ),
    )
    return _report_delivery.owes_a_report(ctx.state)
