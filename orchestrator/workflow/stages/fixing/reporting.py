# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round that finished on a report, and the write that closes it.

Every developer prompt this stage sends teaches the report contract, so a fix
round can end on `REPORT: READY` or `REPORT: VERIFIED` exactly as an initial
implementation can. When it does, the round owes a publication this tick cannot
guarantee: the push can fail, the post can fail, the process can die between
them.

So what such a round consumed and what its route spent do not close here. Both
ride the RECORD of the report -- durable before the size gate and before the
push -- and the write that completes the transaction is the one that applies
them, whether that is this tick's binding or the reconciliation ahead of a later
handler. Settled here instead, a crash in that window leaves the feedback
answered and the reviewer round spent for a report nobody published, with the
`pending_fix_*` replay source cleared along with them.

A mark rides beside that bookkeeping for the one thing the settlement cannot do:
move a label. It says THIS transaction settled, so the tick that finds the round
finished acts on evidence rather than on an inference from the settled report
and the head a pull request happens to carry -- both of which outlive every
transaction. It is cleared by the relabel that closes the round.

Every other outcome a fix round reaches -- the `ACK:`, the question, the
timeout, the dirty tree -- writes no report at all, and those close their own
bookkeeping directly in `resume`. Telling the two apart is the whole of what
this owner is asked first.
"""
from __future__ import annotations

import logging

from orchestrator import config as _config
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import (
    report_binding as _report_binding,
    report_delivery as _report_delivery,
    report_outcomes as _report_outcomes,
    report_records as _report_records,
)
from orchestrator.workflow.stages.fixing import models as _models, state as _state
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The mark this route's settlement raises, recorded beside the bookkeeping it
# closes so the one write that completes a publication carries both. It is the
# only thing that says a fixing round's report SETTLED while the label never
# moved -- the settled report and the publication receipt are persistent, so a
# head a pull request is standing on proves nothing about this transaction.
_SETTLES_THE_ROUND = ((_state._SETTLED_ROUND, True),)

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

# What a report nothing left on this issue can move is held under. The wait
# is real either way; what the park adds is that somebody is told about it and
# that a reply is enough to end it.
_STALLED_PARK = (
    "{mentions} this issue still owes its pull request a developer report, and "
    "no road left on this workflow can get it there: there is no unread "
    "feedback to answer, nothing on the branch left to publish, and the "
    "publication itself declines -- most often because the issue was edited "
    "after the report was written, so the report answers requirements that "
    "have moved. Nothing was discarded: the report is still on the pinned "
    "comment and the pull request stands exactly where it did. Reply and the "
    "orchestrator resumes the session; the report it writes then answers the "
    "issue as it stands, supersedes the one that could not, and is the one "
    "that gets published. It needs no new commit to deliver it."
)

# What a round that committed over a report the issue still owes is held
# under. The run is over, so what this asks for is a fresh report written over
# the branch as it now stands -- which the reply's resume writes and which
# supersedes the record nothing could bind.
_UNDESCRIBED_PARK = (
    "{mentions} this issue's developer run committed work while a report an "
    "earlier run wrote is still owed to the pull request, and answered the "
    "feedback with no report of its own. Nothing was published: the commit is "
    "still in the worktree, the branch is untouched, and the earlier report is "
    "still on the pinned comment exactly as it was. That report describes the "
    "branch as it stood before this commit, so publishing it against the new "
    "head would hand a reviewer a description of work it does not cover -- and "
    "a report is the one thing this orchestrator cannot write for itself. "
    "Reply and the orchestrator resumes the session; the report it writes then "
    "describes the branch as it stands, supersedes the one that could not, and "
    "is the one that gets published."
)


def _holds_for_a_human(
    ctx: _models._FixingContext,
    run: _models._FixingResumeRun,
    *,
    reported: bool,
) -> bool:
    """The two replies this round may act on no half of, held for a human.

    True is a tick this call ended. Both roads announce once and hold the work
    exactly where it is: nothing published, any commit still in the worktree,
    the branch untouched, and a reply that resumes the session.

    A reply that reached for the report CONTRACT and missed is the first. The
    commonest miss is an `ACK:` line written beside a report, and the two
    halves of such a message say opposite things: read on the `ACK:` the pull
    request goes back to review as needing no change, and read on the report it
    claims work this orchestrator would then publish undescribed. A run that
    ALSO committed is the sharpest version -- left to the publication tail it
    pushes the commit and relabels with no report on the pull request at all.

    A round that COMMITTED over a report the issue already owed is the second.
    A delivered record carries no commit: what it is ABOUT is the branch as its
    own run left it, and the only thing on the comment that says so is that
    nothing has been committed over it since -- so a round that moves the head
    while an earlier tick's report is still owed makes that report
    undescriptive of the branch, and every road that publishes afterwards would
    bind it to a commit it never saw. Three readings, all of which have to
    hold: the debt is an EARLIER tick's (a round that wrote its own report
    replaces the record at a fresh revision, so report and commit are one run's
    and bind together), the head MOVED (a round that committed nothing
    republishes exactly the branch the standing report was written over, which
    is what this stage's whole recovery road exists for), and the head READ,
    since a probe that answered nothing is no evidence of a commit and the
    disposition behind this refuses to push blind anyway.

    The work is then recorded as UNDESCRIBED, which is what stops every later
    road binding over it, and the reply the park earns resumes the developer:
    the report that session writes describes the branch as it stands and
    supersedes the one that could not.
    """
    if _report_outcomes._reached_for_the_contract(run.dev_result):
        _report_delivery.parks_an_undeliverable_report(
            ctx.gh, ctx.issue, ctx.state,
            _MISREAD_PARK.format(mentions=_config.HITL_MENTIONS),
        )
        return True
    if reported or not run.after_sha or run.after_sha == run.before_sha:
        return False
    if not _report_delivery.owes_a_report(ctx.state):
        return False
    ctx.state.set(_report_delivery.UNREPORTED_WORK, True)
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state,
        _UNDESCRIBED_PARK.format(mentions=_config.HITL_MENTIONS),
    )
    return True


def _is_report_only(
    ctx: _models._FixingContext, run: _models._FixingResumeRun,
) -> bool:
    """Whether this run's whole answer is the report it wrote.

    The shape `_build_pr_comment_followup` asks for by name: an item that wants
    report content only is answered in the report, with no commit for it. Read
    as an ordinary no-commit reply it would park as a question, and the report
    the round was asked for would sit unpublished on the pinned comment behind
    a human's reply.

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
    through the file list beside it, since that list answers empty for a status
    nobody could read -- an unread checkout is work nobody can see the shape
    of, which is the one thing a report may never be published over.

    The pull request is READ AGAIN for that comparison, and this road is the
    only one that has to. Every other publication here names a commit some
    push of this tick's just landed, which the size gate leases against the
    head it was proved on -- so a remote that moved under it refuses the push
    rather than the report. A report-only round pushes nothing at all: its
    evidence is that the head never moved, and the copy the preflight fetched
    says that of a pull request anybody may have pushed to in the minutes the
    developer was out. Compared against that copy, an untouched local checkout
    still matches, and a report describing the commit the round began on goes
    onto a pull request that has since moved past it -- with the issue handed
    back to the reviewer over a head nothing describes.

    A read nobody could take answers False, like every other absence here: the
    round then takes the ordinary no-commit road, which parks for a human
    rather than publishing over a pull request this tick could not place.
    """
    if run.dev_result.timed_out or not run.after_sha:
        return False
    if run.after_sha != run.before_sha:
        return False
    try:
        published = ctx.gh.get_pr(ctx.pr.number)
    except Exception:
        log.exception(
            "issue=#%d could not re-read PR #%s to say whether it is still "
            "standing where this round found it; publishing no report over it",
            ctx.issue.number, getattr(ctx.pr, "number", None),
        )
        return False
    if run.after_sha != getattr(getattr(published, "head", None), "sha", ""):
        return False
    return _worktree_status._worktree_status(run.worktree).is_clean


def _recording_stops_the_tick(
    ctx: _models._FixingContext,
    run: _models._FixingResumeRun,
    consumed: tuple,
    owed,
) -> bool:
    """Record this round's report, carrying what its run consumed and spent.

    True is a tick this call ended: a report this build cannot record, which
    parks with the commit still in the worktree and nothing published.

    Both groups are handed over rather than derived here. `consumed` is the
    pairs the caller FROZE before it settled them, so the record names exactly
    what was applied rather than what is left to apply -- derived after the
    settlement it would be empty, and the recovery that reads this record back
    would have nothing to put the feedback beyond. `owed` is the route
    bookkeeping, which is not applied anywhere yet: the publication it belongs
    to is not this tick's to guarantee, so the write that COMPLETES the
    transaction is what closes it.

    The mark rides with it because one write applies them. A settlement can
    close `pending_fix_at`, the bookmarks and `review_round`, and it cannot
    move a label -- so without the mark the tick that finds the round finished
    would have to INFER it from the settled report and the head the pull
    request happens to carry, and neither of those says anything about this
    transaction: both outlive it, so a manual relabel onto `workflow:fixing`
    would be read as a round that just settled and bounce straight back to the
    reviewer without reading the feedback it was moved here to answer.
    """
    return _report_delivery.recording_stops_the_tick(
        ctx.gh, ctx.issue, ctx.state, run.dev_result,
        _report_records.HandedRun(
            route=WorkflowLabel.FIXING,
            watermarks=consumed,
            spends=owed.fields + _SETTLES_THE_ROUND,
        ),
    )


def _hands_the_round_back(ctx: _models._FixingContext) -> None:
    """Retire the mark that round settled on, then send the reviewer the head.

    One owner for both halves because they are one act, and the ORDER is the
    whole of what makes the pair safe. The mark is durable and the relabel is
    not atomic with it, so one of the two windows has to be chosen: retired
    first, a tick that dies before the label moves leaves a round whose mark is
    down and whose issue is still on `workflow:fixing` -- and the no-feedback
    bounce behind it hands the reviewer the head on the very next poll.
    Relabelled first, that same death leaves a raised mark under a label that
    has moved on, and NOTHING later can tell it from a round that has just
    settled: a manual return to `workflow:fixing` carries no route anchor, owes
    no report, and reads back a handoff this stage itself settled under, so the
    mark would be spent on it and the feedback it was moved here to answer
    never scanned.

    So the write is this owner's and it lands first. Callers stage whatever
    else they owe into the state before calling; nothing they add afterwards
    would be durable in the window this ordering protects.

    Every road that can reach a relabel with the mark RAISED comes through
    here, and those are exactly the roads a settlement lands on: this round's
    own publication, the recovery's binding, the no-feedback bounce that
    republishes a stranded commit, and the tick that finds a round settled
    elsewhere. No other fixing road can carry one, because the read that finds
    a raised mark runs first in the handler and ends the tick there. The bounce
    comes through anyway on the roads that never saw a report: a mark that is
    not up is nothing to clear, and a road that has to remember whether to
    clear one is a road that comes to forget.
    """
    ctx.state.set(_state._SETTLED_ROUND, None)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)


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
    bounce reads the receipt its own push has just written, a report-only round
    names the head its pull request already stands on, and the recovery names a
    clean checkout it re-proved against that head.

    An empty candidate binds nothing. There is no commit to be about, so the
    report stays owed for a road that can name one.

    Work this issue records as UNDESCRIBED binds nothing either, whatever the
    caller proved. A delivered record carries no commit of its own: what it is
    ABOUT is the branch as its run left it, and the only thing that says so is
    that nothing has been committed over it since. Once something has, every
    road that publishes -- a push tail, the no-feedback bounce, the recovery
    ahead of a later handler -- would otherwise bind that report to a commit it
    never saw. Held instead, the code may still go out and the review waits for
    a report written over the branch as it stands.

    True holds the caller's relabel, which is what keeps a reviewer from being
    sent to a head whose report nothing on the pull request carries.
    """
    if not candidate or ctx.state.get(_report_delivery.UNREPORTED_WORK):
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


def _holds_a_stalled_report(ctx: _models._FixingContext) -> None:
    """Announce a report no road left on this issue can move, once.

    Reached by the no-feedback bounce, which is the last road of the tick:
    nothing unread, nothing stranded to publish, and a report still owed. Every
    road that could have moved it has already declined, so the alternative is
    an issue finding those same three answers on every poll and doing nothing
    with any of them -- silently, for as long as the pull request stays open.

    The way in that no other road covers is a transaction the engine will not
    settle because the REQUIREMENTS it was written against have moved: a human
    commented after the report was recorded, the publication stands down for a
    drift resume, and this stage has none. What supersedes such a report is
    another report, and what brings one is the reply this park asks for.

    A park anybody else has taken is left exactly as it is. The issue is
    already waiting on a human, which is what this would have asked for, and
    replacing the reason would answer their question on their behalf.
    """
    if ctx.state.get(_state._AWAITING_HUMAN):
        return
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state,
        _STALLED_PARK.format(mentions=_config.HITL_MENTIONS),
    )


def _finishes_a_reported_round(
    ctx: _models._FixingContext, owed, candidate: str,
) -> None:
    """Put this round's report on the pull request and close the round on it.

    A report still owed afterwards holds the relabel: the code is out and the
    report it is about is not, and a reviewer sent to that head would be
    reading an implementation nothing on the pull request describes. The round
    is not closed either -- what closes it is the write that completes the
    transaction, here or in the reconciliation ahead of a later handler.
    """
    if _holds_an_unpublished_report(ctx, candidate):
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    _late_gate_models._spend(ctx.state, owed)
    _hands_the_round_back(ctx)
