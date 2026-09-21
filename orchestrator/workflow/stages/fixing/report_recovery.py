# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A report this issue recorded and never bound, answered before any spawn.

The record is written ahead of the size gate and the push precisely so a tick
that dies past it comes back to an issue that can still say what its developer
reported. What nothing else goes back for is the OTHER half of that write: the
input the run consumed rides the same record, and until something applies it the
scan behind this owner reads that feedback as unread -- pays a second developer
to answer it, and replaces the first report with the second.

So what a dead tick consumed is read off its record rather than re-derived --
and applied only where this road ENDS. A publication still ahead is one the
settlement that completes it moves the readers for; a park is the other answer,
and there the batch that reached an agent is written down as read in the park's
own write. The round is never spent with it either way, because what closes a
round is a publication.

Whether the code DID go out is re-proved rather than remembered. The receipt
this stage writes on a landed push is persistent, so on a tick that pushed
nothing it names an older round's commit -- and a pull request standing on that
commit for reasons of its own would let a report about work nobody published go
out on the strength of it. What is asked instead is the checkout: a tree
provably clean and a head it could name. Whether the pull request is STANDING
on that head is the binding's to ask, over a pull request it reads afresh,
because the only one this owner holds was fetched before the tick began.

The two DEFINITE refusals are the exception, and they release the record as they
park: this owner runs ahead of the parked dispatch, so a record left on the
comment is one the next tick binds the moment the checkout comes back -- and a
human who merely restores or cleans it, without the reply the notice asks for,
publishes the report nothing could place. The debt outlives the record there,
which is what keeps the review held and the reply answerable.

A tick that binds stops there, and where the publication SETTLES it finishes the
recovered round as the live road would have: the route bookkeeping the record
froze is on the comment, so the issue is handed back to `workflow:validating`
rather than left on `fixing` under a route it no longer carries -- a scan
running on past that reads an in_review batch as a validating one and parks an
ordinary `ACK:` instead of answering it. A binding whose post did not land
relabels nothing: the transaction is the reconciliation's to finish ahead of the
next handler, and the bookmarks an outstanding publication replays from have to
outlive this tick.

Every round handed back here is handed back on the strength of the mark that
settlement raised, and on nothing weaker -- the one a settlement finished
ELSEWHERE (the reconciliation ahead of this handler, or a tick that died between
that write and its own relabel) and equally the one settled by the binding just
above. A settled report and a publication receipt both outlive the transaction
that made them, so a pull request standing on the commit one names is no
evidence that this round just closed; taken for it, a manual relabel would be
bounced back to the reviewer with its feedback unread. Nor is the settling
itself evidence: a delivery is claimed by one key whoever wrote it, and an
implementing candidate and the validating drift route each write one too, so a
record this stage never wrote can be the one that settles here -- closing ITS
route's bookkeeping, raising no mark of this stage's, and bouncing a reviewer's
own change request back unread if the relabel were taken from it.

That mark is CONSUMED here rather than merely read, and it is PLACED before it
is acted on -- by `round_marks`, which the relabel itself goes through, so the
live road and this one answer the identical comment the same way. The
reconciliation that raises it runs ahead of every handler on every non-terminal
label, and a fixing round can leave `fixing` with its transaction outstanding,
so the settlement may land while the issue is elsewhere, where nothing reads
this. A mark this owner cannot place is retired rather than spent, and retiring
it is still this road's to do: it is the mark of a round that is over either
way, and only the relabel is withheld.
"""
from __future__ import annotations

import logging

from orchestrator import config as _config
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    report_consumed_values as _consumed,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
)
from orchestrator.workflow.stages.fixing import (
    models as _models,
    reporting as _reporting,
    round_marks as _round_marks,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# What a delivered record nobody can read is held under. Durable, because the
# condition does not clear on its own: what it asks for is the pinned comment
# repaired, or the field cleared to abandon the report.
_UNREADABLE_PARK = (
    "{mentions} this issue records a developer report it still owes its pull "
    "request, and the record cannot be read: a field is missing, or is not the "
    "shape this orchestrator writes. Nothing was published and nothing was "
    "discarded -- the branch, the pull request, and every other record are "
    "exactly as they were. The workflow is held here rather than carried on, "
    "because the input that run consumed rides the same record: read past it, "
    "this issue pays a second developer to answer feedback the first one "
    "already answered and replaces the first report with the second. Repair "
    "the pinned comment -- or clear the `developer_report_delivery` field to "
    "abandon the report -- and the next tick resumes on its own."
)

# What a report no road on this host can publish is held under.
_UNPUBLISHABLE_PARK = (
    "{mentions} this issue recorded a developer report its pull request never "
    "received, and the worktree it was written in cannot say whether the code "
    "it describes got there: the checkout is either no longer on this host or "
    "carrying uncommitted changes, and neither the recovery nor the "
    "republishing bounce will publish a report over a checkout in that state. "
    "Nothing was published, because doing it on a guess would hand a reviewer "
    "a description of work that may not be there -- and that recorded report "
    "is RELEASED here rather than left waiting, since restoring or cleaning "
    "the checkout would otherwise be enough on its own to publish it and send "
    "the issue back to review, which is the one thing this notice is asking a "
    "human to decide. The branch, the pull request, and the debt are "
    "untouched: this issue still owes its pull request a report, and the "
    "review stays held until one is there. Clean up or restore the checkout "
    "if you want that commit published, then reply: the orchestrator resumes "
    "the developer, and the report that session writes is the one that gets "
    "published. It needs no new commit to deliver it."
)


def _answers_a_report_first(ctx: _models._FixingContext) -> bool:
    """Everything this issue's report obligation owes, before anything scans.

    Two questions in the order they can be asked. A round whose report has
    SETTLED is finished and handed back, because the write that settled it
    closed this route's bookkeeping and a scan running past that reads whatever
    landed since under a route that no longer exists. A report still owed and
    never BOUND is answered next, off the record the dead tick left.

    True is a tick this call ended.
    """
    return (
        _finishes_a_settled_round(ctx)
        or _recovers_an_unbound_delivery(ctx)
    )


def _finishes_a_settled_round(ctx: _models._FixingContext) -> bool:
    """Hand back the round a raised mark says just settled, if it is one.

    Asked twice a tick and by two callers, because the answer is the same
    question either way: ahead of everything, for the settlement some other
    write landed, and again behind the binding above, for the one it landed
    itself. A settlement is not licence to relabel -- the mark it raised is,
    and only where this owner can still place it.

    False is every round this stage may not end here, and the mark is RETIRED
    on the way out wherever one is standing that can no longer be about the
    round in hand.

    The reconciliation ahead of every handler completes a transaction and lets
    the tick carry on, which is right for the stages behind it and wrong for
    this one: the write that settled it applied the route bookkeeping the
    record froze -- `pending_fix_at` and the fix bookmarks among them -- so the
    round is over and the issue is still sitting on `workflow:fixing`. Carrying
    on, the rescan below reads whatever landed since under a route the
    settlement has just closed, and answers an in_review batch as a validating
    one: an ordinary `ACK:` is refused or parked instead of returning the pull
    request to review.

    So the round is FINISHED first and the tick ends. Whatever arrived since is
    read on the next poll, by the stage the label now names, on the route that
    batch really belongs to.

    What says the round is over is the mark that settlement raised, and nothing
    else. Every other reading on the comment OUTLIVES a transaction: the
    settled report is replaced rather than retired, and the publication receipt
    beside it is persistent, so a pull request standing on the commit a report
    names says only that some round once published it. Read that way, a manual
    relabel onto `workflow:fixing` -- or any route that reaches this stage
    without leaving its own anchor -- would be taken for a round that just
    settled and bounced straight back to the reviewer with the fresh feedback
    it was moved here to answer never scanned.

    The mark is CONSUMED rather than merely read, because the settlement that
    raises it does not have to happen under this label. A reconciliation runs
    ahead of every handler on every non-terminal label, and a fixing round can
    leave `fixing` with its transaction still outstanding -- a silent
    validating-route recovery does exactly that -- so the write that settles it
    may land while the issue is somewhere else entirely, and no handler there
    reads this mark. Left standing, it would be waiting for whichever fixing
    round came next, which is a round it says nothing about.
    """
    if not ctx.state.get(_state._SETTLED_ROUND):
        return False
    if not _round_marks._places_the_round_in_hand(ctx.state):
        ctx.state.set(_state._SETTLED_ROUND, None)
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return False
    _reporting._hands_the_round_back(ctx)
    return True


def _recovers_an_unbound_delivery(ctx: _models._FixingContext) -> bool:
    """Apply what an unbound report recorded, and bind it where it may.

    True is a tick this call ended, and it ends one only where the binding TOOK
    the delivery. Settled, the round the record froze is closed and the issue
    goes back to `workflow:validating`, which is what the live road would have
    done and what keeps the scan behind this from reading the issue under a
    route the settlement has just cleared. Bound but unposted, nothing is
    relabelled: the transaction is the reconciliation's to finish, and the
    bookmarks it replays from have to outlive this tick.

    The hand-back a settlement earns is asked for through the same correlation
    a settlement found already raised is, and never taken from the settling
    itself. Two readings make that difference real. A delivery is claimed by
    one key whoever wrote it, and this stage is not the only writer: an
    implementing candidate and the validating drift route each record one, and
    either can still be owed when a reviewer's change request moves the issue
    here. Settling such a record closes ITS route's bookkeeping and raises no
    fixing mark at all, so a hand-back taken on the settling would bounce the
    reviewer's own request back to `workflow:validating` with the feedback
    that earned it never scanned and this route's bookmarks still standing.
    And the settling write stamps the label it read AFRESH, so a human who
    relabelled while the developer ran -- or a label read that failed -- leaves
    a settlement this stage cannot place. Routed through the correlation, both
    end the tick with the report published and the label untouched, and the
    next poll reads the issue under the label it really carries.

    False is every other issue and also the delivery a binding refused without
    consuming -- a comment too full, a subject its reader will not take.
    Nothing is discarded there, the tick carries on, and a later one asks
    again; stopping instead would hold the roads that answer a human in front
    of a condition only a human clears.

    A checkout this tick could not READ is the exception that ends the tick
    saying nothing at all. It is no evidence about the branch, so it may buy
    neither a publication nor a notice -- and the road behind this one would
    make it buy the notice: the record's own pairs cover the batch, so the
    scan finds nothing to act on and the bounce announces a report no road can
    move, over a checkout nobody has read.

    Presence is asked before meaning, and that order is what keeps a damaged
    record from being read as an issue with nothing outstanding. The debt every
    road behind this reads is CLAIMED by the key alone, so a record a hand edit
    truncated is a debt nothing here could describe -- and read as an absence
    it would fall straight through to the scan, whose watermarks that same
    record was holding back, and pay a second developer to answer the feedback
    the first one already answered. Parked once instead, with the record
    untouched for whoever repairs or abandons it.
    """
    if not _delivery_state.carries_delivered_report(ctx.state):
        return False
    delivered = _delivery_state.read_delivered_report(ctx.state)
    if delivered is None:
        _report_delivery.parks_an_undeliverable_report(
            ctx.gh, ctx.issue, ctx.state,
            _UNREADABLE_PARK.format(mentions=_config.HITL_MENTIONS),
        )
        return True
    published = _published_checkout(ctx)
    if not published:
        if not _releases_an_unpublishable_report(ctx):
            ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        # A reading nobody could take ends the tick where it stands, and
        # that is the whole of what it is allowed to do: nothing published,
        # nothing released, nothing said. Let past, the scan behind this
        # finds no feedback it may act on -- the record's own pairs cover the
        # batch -- and the bounce announces a report no road can move, which
        # is a claim about the branch this tick could not read a thing about.
        # The decisive "" falls through instead: the bounce is the road that
        # republishes a commit the pull request has not got, and the report
        # goes out bound to the push it makes.
        return published is None
    still_owed = _reporting._holds_an_unpublished_report(ctx, published)
    if _delivery_state.carries_delivered_report(ctx.state):
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return False
    if still_owed:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    else:
        _finishes_a_settled_round(ctx)
    return True


def _releases_an_unpublishable_report(ctx: _models._FixingContext) -> bool:
    """Announce a report no road on this host is going to get out, once.

    True is a tick this call ended. Shared by the two roads that reach the
    question from opposite sides -- this owner's own recovery, over a record a
    dead tick left, and a live report-only round whose checkout refuses the
    reading it needed -- because the refusal and everything it owes are one
    rule: a second copy would be a second notice, and the release below is the
    half a copy comes to forget.

    Two refusals here are DEFINITE, and a definite refusal is one no later poll
    answers differently -- so leaving either to the next tick is leaving the
    issue to find no feedback, no publishable checkout and an owed report every
    poll, and quietly do nothing at all with any of them.

    A worktree that is GONE is the first: nothing to republish and nothing to
    prove, since the commit the report describes is either already on the pull
    request or went with the checkout and no reading left here can say which. A
    tree this host PROVED dirty is the second, and it is the one the stranded
    bounce cannot help with either: that road refuses a dirty checkout exactly
    as this one does, so the two decline together and nothing moves until
    somebody cleans it.

    Every other decline is left alone. A status nobody could read is not a
    dirty tree -- a later poll may read it -- and a head ahead of the pull
    request is a checkout the bounce still republishes from, with the report
    going out on the push it makes.

    The park is not this call's to own past the notice: a reply clears it
    through the ordinary parked dispatch, which resumes the developer, and the
    report that session writes supersedes the one nothing could deliver.

    So the recorded report is RELEASED in this same write, and the debt is
    not. This owner runs ahead of the parked dispatch, which is what makes the
    difference matter: left on the comment, the record is one the very next
    tick can bind the moment the checkout comes back -- so a human who merely
    restores or cleans it, without the reply this notice asks for, publishes
    the report nothing could place and sends the issue to review on it. That
    is the decision the notice exists to put in front of them, and a condition
    clearing itself is no answer to it. What the debt keeps is everything that
    holds: the review stays held, the roads that read an owed report still
    read one, and the reply brings the report that discharges it.

    What the dead run CONSUMED is recorded with it, off the record's own pairs,
    and only here -- taken BEFORE the release, since afterwards there is no
    record to read them from. Everywhere else the publication is still ahead
    and the settlement that completes it is what moves a reader; a park is
    where this road ends instead, so the batch that reached an agent is
    written down as read rather than handed to whatever answers the reply.

    A record this build cannot READ is left alone here, because there is
    nothing to read those pairs from and the road that parks a damaged record
    owns it instead.
    """
    delivered = _delivery_state.read_delivered_report(ctx.state)
    if delivered is None or not _refuses_for_good(ctx):
        return False
    _consumed.advance_consumed(ctx.state, delivered.watermarks)
    _delivery_state.clear_delivered_report(ctx.state)
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state,
        _UNPUBLISHABLE_PARK.format(mentions=_config.HITL_MENTIONS),
    )
    return True


def _refuses_for_good(ctx: _models._FixingContext) -> bool:
    """Whether this checkout's refusal is one no later poll takes back."""
    worktree = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    if not worktree.exists():
        return True
    tree = _worktree_status._worktree_status(worktree)
    return tree.readable and not tree.is_clean


def _published_checkout(ctx: _models._FixingContext) -> str | None:
    """The commit a clean checkout PROVED it is standing on, "", or None.

    Every reading is positive, because what an absence would license here is a
    report about code the remote does not have. What the absences are FOR is
    the difference between the two empty answers.

    "" is a checkout that answered and said no: one this host does not hold,
    and a tree carrying something. Both are decisive for good, and both leave
    the report owed for the terminal park that announces them.

    None is a reading nobody could TAKE: a status that established nothing,
    and a head that would not resolve. Neither says anything about the branch,
    so neither may be spent on -- not on a publication, and not on a notice
    telling a human this issue is stuck. The caller holds everything where it
    stands and the next poll asks again.

    Whether the PULL REQUEST is standing on that commit is not asked here, and
    deliberately: the only pull request this owner holds is the one the
    preflight fetched, and a push that landed since is invisible in it. The
    binding re-reads the pull request for its own reasons and holds the
    candidate to THAT reading, so the comparison happens once, against the
    world it is acted on in -- and a head the pull request has moved off falls
    through to the bounce, which re-proves the remote and republishes the
    commit rather than parking over a copy nobody refreshed.
    """
    worktree = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    if not worktree.exists():
        return ""
    tree = _worktree_status._worktree_status(worktree)
    if not tree.readable:
        log.info(
            "issue=#%d could not read the checkout holding the report it "
            "owes; holding it for a tick that can", ctx.issue.number,
        )
        return None
    if not tree.is_clean:
        return ""
    head = _verification_probes._head_sha(worktree)
    if head:
        return head
    log.info(
        "issue=#%d could not read the head of the checkout holding the report "
        "it owes; holding it for a tick that can", ctx.issue.number,
    )
    return None
