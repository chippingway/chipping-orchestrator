# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report this issue recorded and never bound, answered before any spawn.

The record is written ahead of the size gate and the push precisely so a tick
that dies past it comes back to an issue that can still say what its developer
reported. What nothing else goes back for is the OTHER half of that write: the
input the run consumed rides the same record, and until something applies it
the scan behind this owner reads that feedback as unread -- pays a second
developer to answer it, and replaces the first report with the second.

So the watermarks are applied here, first, off the record itself rather than
re-derived: what a dead tick consumed is what its record says it consumed. The
round is NOT spent with them, because what closes a round is a publication and
a delivery is a report whose code may never have gone out.

Whether the code DID go out is re-proved rather than remembered. The receipt
this stage writes on a landed push is persistent, so on a tick that pushed
nothing it names an older round's commit -- and a pull request standing on
that commit for reasons of its own would let a report about work nobody
published go out on the strength of it. What is asked instead is the checkout:
a tree provably clean, a head it could name, and that head being what the pull
request carries. Then the branch IS published and the report describes it,
whichever run wrote the record.

A tick that binds stops there, and where the publication SETTLES it finishes
the recovered round as the live road would have: the route bookkeeping the
record froze is on the comment, so the issue is handed back to
`workflow:validating` rather than left on `fixing` under a route it no longer
carries -- a scan running on past that reads an in_review batch as a
validating one and parks an ordinary `ACK:` instead of answering it. A binding
whose post did not land relabels nothing: the transaction is the
reconciliation's to finish ahead of the next handler, and the bookmarks an
outstanding publication replays from have to outlive this tick.
"""
from __future__ import annotations

from orchestrator import config as _config
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    report_consumed_values as _consumed,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
)
from orchestrator.workflow.stages.fixing import models as _models, reporting as _reporting
from orchestrator.workflow.state import WorkflowLabel

# What a report no road on this host can publish is held under.
_UNPUBLISHABLE_PARK = (
    "{mentions} this issue records a developer report its pull request never "
    "received, and the worktree it was written in cannot say whether the code "
    "it describes got there: the checkout is either no longer on this host or "
    "carrying uncommitted changes, and neither the recovery nor the "
    "republishing bounce will publish a report over a checkout in that state. "
    "Nothing was discarded -- the report is still on the pinned comment -- and "
    "nothing was published, because doing it on a guess would hand a reviewer "
    "a description of work that may not be there. Clean up or restore the "
    "checkout if you want that commit published, then reply: the orchestrator "
    "resumes the developer, and the report that session writes is the one that "
    "gets published. It needs no new commit to deliver it."
)


def _recovers_an_unbound_delivery(ctx: _models._FixingContext) -> bool:
    """Apply what an unbound report recorded, and bind it where it may.

    True is a tick this call ended, and it ends one only where the binding
    TOOK the delivery. Settled, the round the record froze is closed and the
    issue goes back to `workflow:validating`, which is what the live road
    would have done and what keeps the scan behind this from reading the
    issue under a route the settlement has just cleared. Bound but unposted,
    nothing is relabelled: the transaction is the reconciliation's to finish,
    and the bookmarks it replays from have to outlive this tick.

    False is every other issue and also the delivery a binding refused
    without consuming -- a comment too full, a subject its reader will not
    take. Nothing is discarded there, the tick carries on, and a later one
    asks again; stopping instead would hold the roads that answer a human in
    front of a condition only a human clears.
    """
    delivered = _delivery_state.read_delivered_report(ctx.state)
    if delivered is None:
        return False
    _consumed.advance_consumed(ctx.state, delivered.watermarks)
    published = _published_checkout(ctx)
    if not published:
        _holds_a_report_nothing_can_publish(ctx)
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return False
    still_owed = _reporting._holds_an_unpublished_report(ctx, published)
    if _delivery_state.carries_delivered_report(ctx.state):
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return False
    if not still_owed:
        ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    return True


def _holds_a_report_nothing_can_publish(ctx: _models._FixingContext) -> None:
    """Announce a report no road on this host is going to get out, once.

    Two refusals here are DEFINITE, and a definite refusal is one no later
    poll answers differently -- so leaving either to the next tick is leaving
    the issue to find no feedback, no publishable checkout and an owed report
    every poll, and quietly do nothing at all with any of them.

    A worktree that is GONE is the first: nothing to republish and nothing to
    prove, since the commit the report describes is either already on the
    pull request or went with the checkout and no reading left here can say
    which. A tree this host PROVED dirty is the second, and it is the one the
    stranded bounce cannot help with either: that road refuses a dirty
    checkout exactly as this one does, so the two decline together and
    nothing moves until somebody cleans it.

    Every other decline is left alone. A status nobody could read is not a
    dirty tree -- a later poll may read it -- and a head ahead of the pull
    request is a checkout the bounce still republishes from, with the report
    going out on the push it makes.

    The park is not this call's to own past the notice: a reply clears it
    through the ordinary parked dispatch, which resumes the developer, and
    the report that session writes supersedes the one nothing could deliver.
    """
    if not _refuses_for_good(ctx):
        return
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state,
        _UNPUBLISHABLE_PARK.format(mentions=_config.HITL_MENTIONS),
    )


def _refuses_for_good(ctx: _models._FixingContext) -> bool:
    """Whether this checkout's refusal is one no later poll takes back."""
    worktree = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    if not worktree.exists():
        return True
    tree = _worktree_status._worktree_status(worktree)
    return tree.readable and not tree.is_clean


def _published_checkout(ctx: _models._FixingContext) -> str:
    """The commit a clean checkout and the pull request agree on, or "".

    Every reading is positive, because what an absence would license here is
    a report about code the remote does not have. A checkout this host does
    not hold, a status nobody could read -- `is_clean` is False for that, as
    the file list beside it is not -- a head that would not resolve, and a
    head the pull request is not standing on each answer "", which leaves the
    report owed for the bounce that republishes such a commit.
    """
    worktree = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    if not worktree.exists():
        return ""
    if not _worktree_status._worktree_status(worktree).is_clean:
        return ""
    head = _verification_probes._head_sha(worktree)
    if not head or head != getattr(ctx.pr.head, "sha", ""):
        return ""
    return head
