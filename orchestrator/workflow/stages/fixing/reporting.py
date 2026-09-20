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

from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import (
    report_binding as _report_binding,
    report_delivery as _report_delivery,
    report_outcomes as _report_outcomes,
    report_record_state as _record_state,
    report_records as _report_records,
)
from orchestrator.workflow.stages.fixing import feedback as _feedback, models as _models
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_publication_state as _late_publication_state,
)
from orchestrator.workflow.stages.validating import stranded as _stranded
from orchestrator.workflow.state import WorkflowLabel


def _reports(run: _models._FixingResumeRun) -> bool:
    """Whether this run finished on one of the two report outcomes."""
    return _report_outcomes._finished_on_a_report(run.dev_result)


def _misread_the_contract(run: _models._FixingResumeRun) -> bool:
    """Whether this run reached for the report contract and missed.

    Kept apart from every ordinary no-report reply because it may not take an
    ordinary no-report road. The commonest miss is an `ACK:` line beside a
    report, and the ACK fast path reading that would return the pull request
    to review as needing no change while throwing away the report the
    developer meant to deliver. There is nothing here to record and nothing
    here to act on, so it falls through to the park that asks a human.
    """
    return _report_outcomes._reached_for_the_contract(run.dev_result)


def _is_report_only(
    ctx: _models._FixingContext, run: _models._FixingResumeRun,
) -> bool:
    """Whether this run's whole answer is the report it wrote.

    The shape `_build_pr_comment_followup` asks for by name: an item that
    wants report content only is answered in the report, with no commit for
    it. Read as an ordinary no-commit reply it would park as a question, and
    the report the round was asked for would sit unpublished on the pinned
    comment behind a human's reply.

    Everything that could make it something else is refused first. A run that
    timed out wrote nothing anybody finished. A head that MOVED is a code
    change and belongs on the publication road. A commit an earlier run
    stranded is code this branch still owes the pull request, so the push
    tail has to carry it before any report describes the head. And a dirty
    tree is work nobody can see the shape of, which is the one thing a report
    may never be published over.
    """
    if run.dev_result.timed_out:
        return False
    if run.after_sha and run.after_sha != run.before_sha:
        return False
    if _stranded._stranded_fix_unpushed(
        ctx.spec, run.worktree, ctx.state, ctx.issue,
    ):
        return False
    return not _worktree_status._worktree_dirty_files(run.worktree)


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
    ctx: _models._FixingContext, candidate: str = "",
) -> bool:
    """Put this round's report on the pull request; True where it is still owed.

    Bound to the publication first and posted second, in the engine's own two
    steps: the binding is one local write, so a post GitHub refuses leaves a
    transaction the reconciliation ahead of a later handler can finish rather
    than a delivery nothing would go back for.

    The commit the report is about is the one the size gate RECORDED pushing,
    not the head the caller read: the gate publishes the candidate it
    measured, and a checkout something moved between the two readings would
    bind the report to a commit the pull request never received. `candidate`
    is the caller's own fallback for a road with no receipt to read back -- a
    report-only round names the head its pull request already stands on, since
    that is the code the report is about.

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
                or candidate
            ),
        ),
    )
    return _report_delivery.owes_a_report(ctx.state)


def _settles_unless_a_transaction_will(
    ctx: _models._FixingContext, feedback: _models._FixingFeedback,
) -> None:
    """Close the consumption here, unless a transaction is carrying it.

    A PENDING transaction is the one record that will: it is bound to a
    publication, the reconciliation ahead of a later handler completes it, and
    the write that does applies the very pairs this round recorded. Anything
    short of that -- a delivery nothing bound, a binding a refusal parked, a
    push that never landed -- is a record no road goes back to on its own, so
    leaving the consumption on it would hand the same feedback to a second
    developer on the very next tick.

    Applying it here as well is safe where the transaction does take it later:
    the watermarks ratchet forward and the bookkeeping is a frozen value, so
    a settlement replayed is a no-op rather than a second count.
    """
    if not _record_state.carries_pending_report(ctx.state):
        _feedback._settle_consumed_feedback(ctx.state, feedback)


def _finishes_a_reported_round(
    ctx: _models._FixingContext,
    feedback: _models._FixingFeedback,
    owed,
    candidate: str,
) -> None:
    """Put this round's report on the pull request and close the round on it.

    A report still owed afterwards holds the relabel: the code is out and the
    report it is about is not, and a reviewer sent to that head would be
    reading an implementation nothing on the pull request describes. The round
    is not closed either -- what closes it is the write that completes the
    transaction, here or in the reconciliation ahead of a later handler.
    """
    if _holds_an_unpublished_report(ctx, candidate):
        _settles_unless_a_transaction_will(ctx, feedback)
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    _late_gate_models._spend(ctx.state, owed)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
