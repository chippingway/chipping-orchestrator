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

from orchestrator import config as _config
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
)
from orchestrator.workflow.state import WorkflowLabel

# What a reply that reached for the report contract and missed is held under.
# The run is over, so nothing here clears on its own: what it asks for is a
# session resumed to say the same thing in the shape the contract names.
_MISREAD_PARK = (
    "{mentions} this issue's developer run answered the pull request feedback "
    "with a message that reaches for the completion-report contract and does "
    "not keep it -- most often an `ACK:` line written beside a report, which "
    "the two readings contradict each other on. Nothing was published: any "
    "commit the run made is still in the worktree, the branch is untouched, "
    "and no report went onto the pull request. Read either half alone this "
    "would be wrong in a way nothing later could undo -- the `ACK:` returns "
    "the pull request to review as needing no change, and the report claims "
    "work nobody published. Reply and the orchestrator resumes the session; "
    "the answer it gives then is the one that counts."
)


def _stops_on_a_misread_contract(
    ctx: _models._FixingContext, run: _models._FixingResumeRun,
) -> bool:
    """Hold a reply that reached for the report contract and missed.

    True is a tick this call ended. The commonest miss is an `ACK:` line
    written beside a report, and the two halves of such a message say
    opposite things: read on the `ACK:` the pull request goes back to review
    as needing no change, and read on the report it claims work this
    orchestrator would then publish undescribed. A run that ALSO committed is
    the sharpest version -- left to the publication tail it pushes the commit
    and relabels with no report on the pull request at all.

    So neither half is acted on. There is no report here to record, no reply
    here to route, and the run that wrote it has ended, which leaves the one
    road every message this workflow cannot read by itself takes: announce it
    once, hold the work where it is, and let the reply resume the session.
    """
    if not _report_outcomes._reached_for_the_contract(run.dev_result):
        return False
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state,
        _MISREAD_PARK.format(mentions=_config.HITL_MENTIONS),
    )
    return True


def _is_report_only(
    ctx: _models._FixingContext, run: _models._FixingResumeRun,
) -> bool:
    """Whether this run's whole answer is the report it wrote.

    The shape `_build_pr_comment_followup` asks for by name: an item that
    wants report content only is answered in the report, with no commit for
    it. Read as an ordinary no-commit reply it would park as a question, and
    the report the round was asked for would sit unpublished on the pinned
    comment behind a human's reply.

    Every reading here is POSITIVE, which is the whole of what makes this road
    safe. What it has to establish is that the code this report describes is
    the code the pull request already carries, and no absence proves that: a
    HEAD nobody could read comes back empty, and the stranded probe answers
    False both for a branch in sync and for a fetch that failed, a remote that
    moved, or a divergence nothing could count. Read as "nothing to publish",
    either would bind a report against the head the preflight happened to see
    and hand a reviewer a description of work that is not there.

    So: the run completed, its checkout named a head, that head is the one the
    run started on, that head is what the pull request is standing on, and the
    tree PROVED clean. A head that MOVED is a code change and belongs on the
    publication road; a head ahead of the pull request is a commit the push
    tail still owes it; and a tree is asked through `is_clean` rather than
    through the file list beside it, since that list answers empty for a
    status nobody could read -- an unread checkout is work nobody can see the
    shape of, which is the one thing a report may never be published over.
    """
    if run.dev_result.timed_out or not run.after_sha:
        return False
    if run.after_sha != run.before_sha:
        return False
    if run.after_sha != getattr(ctx.pr.head, "sha", ""):
        return False
    return _worktree_status._worktree_status(run.worktree).is_clean


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

    `candidate` is the commit the CALLER proved, and it is the only subject
    this binding will take. The receipt this stage writes on a landed push is
    deliberately not read here: it is persistent, so on any tick that did not
    push it names an older round's commit -- and a report bound to that one
    describes work the developer never did, on a pull request that may well be
    standing on it for reasons of its own. Each caller scopes the proof to its
    own attempt instead: the push tail names the commit its run left, the
    bounce reads the receipt its own push has just written, a report-only
    round names the head its pull request already stands on, and the recovery
    names a clean checkout it re-proved against that head.

    An empty candidate binds nothing. There is no commit to be about, so the
    report stays owed for a road that can name one.

    True holds the caller's relabel, which is what keeps a reviewer from being
    sent to a head whose report nothing on the pull request carries.
    """
    if not candidate:
        return _report_delivery.owes_a_report(ctx.state)
    _report_binding.binds_and_publishes(
        ctx.gh, ctx.issue, ctx.state, _report_binding.ReportPublication(
            pull_request=ctx.pr,
            repo_slug=ctx.spec.slug,
            branch=_naming._resolve_branch_name(
                ctx.state, ctx.spec, ctx.issue.number,
            ),
            commit=candidate,
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
