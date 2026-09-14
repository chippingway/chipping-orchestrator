# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late cycle owes once the issue it belongs to is gone.

A human can close a late-split owner at any point of its reconciliation: while
its candidate is being measured, while an agent is deciding, between the
snapshot and the first child, in the middle of the split loop, or long after
the supersession. Every one of those leaves a different amount of this
orchestrator's work standing on somebody's repository, and none of them leaves
a workflow anybody wants resumed. So the close ends the CYCLE, and this owner
is what the ending consists of.

**The mark goes down before anything external happens**, and it is the whole
reason the rest is safe to retry. It says the cycle is over, so no gate below
will spawn an agent, adjudicate, relabel, or create another child; it carries
the moment the cleanup obligation was taken on; and it is irreversible within
the cycle -- a human who reopens the issue gets a fresh cycle rather than this
one resumed, so a later visit re-marks the same cancellation and moves neither
the stamp nor the boundary it was taken at. Being durable first is what lets
every step after it be attempted again: a tick that dies mid-cleanup comes back
to a record that already says what it is doing.

It keeps the boundary as well as the moment, because `cancelling` is itself a
phase and it overwrites the one it interrupted. That phase is what says whether
the consumer ledger accounts for every child cut from the snapshot, so a record
that forgot it could never prove a ref reclaimable again.

**Then the pull request this cycle holds, which is the one external thing a
cancellation owns that the umbrella's terminal never sees.** A cycle that
reached the size gate may be holding one under a "do not merge" notice with
the original description preserved on the issue -- the plan pull request a
design discussion left behind, or the implementation one the work is already
on where the gate was entered past publication. Nobody is going to adjudicate
it now, so the hold comes off, one notice says why, and the pull request is
closed -- in that order, so a change that ends up closed is not also
left wearing a hold nothing will ever take back. Said at most once, proved from
the pull request's own thread rather than from a record, because the comment
and the entry that records it cannot be made one operation.

Asked again on every visit, though, because a pull request is not a thing that
stays where it was put. The entry records what an earlier visit did, and an
owner still being visited for something else -- a branch the remote will not
delete -- would otherwise take its terminal, leave the sweep for good, and
leave a change a human reopened standing under a cancelled cycle. What is
bounded is the RECORD of it rather than the asking: the write and both sinks
are behind a state that actually moved.

**Everything else is the reclamation owner's, unchanged.** The superseded
branch and the immutable ref are settled by exactly the rules and in exactly
the order the umbrella's terminal settles them in: a branch only where the
target is one this issue is published under, a ref only once every recorded
direct consumer is proved ended on a reading taken this visit, both refused
outright while the obligation ledger holds an entry this binary cannot type.
A cancellation buys no shortcut through any of it -- a child that is live again
keeps the ref whether or not its owner is closed.

One branch is this ending's own to take ON, though, and it is the one the
transaction could not write down in time: the held PR is superseded and the
branch it carried recorded in two writes, so a close between them leaves a
branch nothing names. Settling around that is retiring over it -- see
`_superseded_branch`.

**Every child that already exists is left entirely alone.** The split records a
child before it seeds one and activates none until the transaction completes,
so a cancellation mid-loop finds real GitHub issues carrying real slices of
somebody's work. What happens to them next is a human's decision, not this
ending's: they are not closed, not relabelled, not written to, and not
commented on -- the receipt a reclamation leaves is what a LIVE split owes the
children it is still responsible for, and a cancelled cycle is responsible for
none of them. A consumer is still READ, because proving each of them ended is
what permits the ref to go at all, and that reading is the whole of what any
of them costs.

Their LEDGER entries are discharged, which is a different thing from touching
them. The ledger is not an inventory of what exists; it is the list of what
this orchestrator still owes somebody's repository, and a cancelled cycle owes
a child nothing -- the entry's obligation was the receipt, and there is no
receipt. Marking them reconciled is a local write to this issue's own pinned
comment, and it is what lets a settled cycle read as settled: leaving them
pending would say the ending is unfinished forever, on an obligation no pass
is ever going to discharge.

Nothing about the ref goes unsaid by that. The transport drops this host's
copy of it before it touches the remote and refuses the whole reclamation if
that copy cannot be proved gone, so a child reopened afterwards finds no
mirror, asks the remote once, and is stopped and told by its own guard on its
own dispatch -- which is where a receipt would only ever have been read.

**A reopen resumes nothing, and skips no part of the ending.** The mark is
irreversible within the cycle, so a human who reopens the issue does not get
that cycle back, and EVERY label names a handler that would act on the issue
rather than settle it. So a cancelled cycle wearing one is refused whatever it
says -- the two an adjudication runs under, the `implementing` a `single`
verdict hands the issue to a moment before a close is observed, and any a
human moved it to since. The same reconciliation is entered from the
dispatcher's own pinned-state guard too, and the same terminal follows it.
Running the cleanup there rather than merely refusing is what makes the
refusal end: the closed-owner sweep visits closed issues only,
so a refusal with nothing behind it would freeze the issue until somebody
closed it again. What the reopen does not earn is a way past the ending -- an
issue worked again without reaching it would be the cancelled cycle resumed by
accident, and the authorization for a fresh attempt is a human taking
`rejected` off, not a human reopening the issue.

**The terminal comes last, and only once nothing is owed** -- branch, ref, and
every unreconciled `plan_pr` entry the LEDGER holds, which is a wider reading
than what this pass acts on. Acting takes the hold's own record, since
releasing one means knowing which pull request this cycle marked; being owed
takes the ledger, because an entry left under a number a later write cleared
is still an obligation, a retired owner is one nothing revisits, and a restart
counts every unreconciled resource as owed. An owner that has settled all of
them is handed `rejected`, which is both the honest end of the cycle and what
takes the issue out of the closed-owner sweep for good --
every label the sweep queries is one the owner keeps until this write lands,
and this write is the only thing that takes one off. Where it may be written
from is the transition graph's own answer for every label a workflow wrote:
each state a late cycle can be interrupted on declares that edge, and a state
that does not is refused and said out loud instead of relabelled out from
under whoever put the issue there. `ready` and `blocked` are the exception,
and not a human's placement at all: a decomposition run spawned before the
close writes one of them as its ordinary outcome and lands after it, so the
terminal is written from both rather than left refused on every visit the
sweep will make forever. The UNLABELED state is the one exception in the
other direction -- an operator who has taken `rejected` off wears nothing at
all, and re-applying it there would undo the one authorization a restart has.

A control label defers everything past the mark. `backlog` and `paused` park
an issue outside the state machine, and the ending is external work; the fact
that the cycle is over is written all the same, because the pass that would
record it is the only one there is. So a cancellation that finishes costs a bounded number of passes,
and one that cannot -- a remote that refuses a delete, a consumer that is live
again, a ledger a human has to settle -- keeps the label, keeps being visited,
and says on every visit what it is still holding. That is the same bargain the
umbrella's terminal makes, for the same reason: an unreclaimed remote has to
stay visible to somebody.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github import (
    client as _client,
    comments as _github_comments,
    issues as _issues,
    labels as _labels,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import observations as _observations, usage as _usage
from orchestrator.workflow.late_split import (
    endings as _endings,
    events as _events,
    lineage as _lineage,
    models as _late_models,
    restart as _restart,
    state as _late_state,
    telemetry as _telemetry,
)
from orchestrator.workflow.stages.decomposition import (
    late_cleanup as _late_cleanup,
    late_hold as _late_hold,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan
from orchestrator.workflow.state import (
    WorkflowLabel,
    is_allowed_transition,
    stage_name,
)

log = logging.getLogger("orchestrator.workflow")

_PLAN_PR = _late_models.LateResourceKind.PLAN_PR

_BRANCH = _late_models.LateResourceKind.BRANCH

# Stamped on the notice a cancelled cycle leaves on the pull request it
# was holding, so a pass that repeats after a crash recognizes its own. Scoped
# to the cycle, which is the scope of a cancellation: a pull request outlives
# a cycle, and a restart mints a fresh one, so an unscoped marker would read a
# previous attempt's notice as this one's. An HTML comment, so it is invisible
# in the rendered thread.
_CANCELLED_MARKER = (
    "<!--orchestrator-late-cancellation:issue={issue}:cycle={cycle}-->"
)

_CANCELLED_NOTICE = (
    ":no_entry: **Cancelled.** Issue #{owner} was closed while its committed "
    "implementation was being adjudicated for size, so this pull request is "
    "closed without merging. Nothing further is published or created for that "
    "adjudication.\n\nReopening the issue does not resume it. The cancelled "
    "cycle settles what it already put on this repository and the issue ends "
    "on `rejected`, which an operator removes to authorize a fresh attempt."
    "\n\n{marker}"
)

# The receipt a poll leaves on the thread for the close it could hand to no
# worker. Scoped to the cycle, because that is the scope of a cancellation: an
# operator who authorizes a restart gets a fresh cycle, and an unscoped receipt
# would end that one too, for a close that happened before it existed.
_OBSERVED_CLOSE_MARKER = (
    "<!--orchestrator-late-close-observed:issue={issue}:cycle={cycle}-->"
)

_OBSERVED_CLOSE_NOTICE = (
    ":no_entry: **Cancelled.** This issue was observed closed while its "
    "oversized committed candidate was still being worked, so late-split "
    "cycle {cycle} is cancelled: nothing further is adjudicated, created, or "
    "activated for it.\n\nReopening the issue does not resume that cycle. "
    "What it already put on this repository is settled by a later pass and "
    "the issue ends on `rejected`, which an operator removes to authorize a "
    "fresh attempt.\n\n{marker}"
)

# How a still-owed held pull request is named in the line that says what a
# closed owner is waiting on. The ledger's own targets are bare identifiers,
# and a bare number beside a branch and a ref would not say what it was.
_OWED_PLAN_PR = "held PR #{0}"

# The same, for the one shape no pass can settle: a number with no
# preserved description beside it, which is a hold nothing can prove and
# a human has to repair.
_UNPROVABLE_HOLD = "held PR #{0} (no preserved description)"

# The two labels a cancelled cycle's own decomposer can leave its owner on: a
# run spawned before the close writes one of them as its ordinary outcome, and
# a close observed inside that run lands ahead of it. Neither declares an edge
# to `rejected`, so the terminal an owner left there earns is one the graph
# alone would refuse and nothing else would ever write.
_RELABELLED_MID_ENDING = (WorkflowLabel.READY, WorkflowLabel.BLOCKED)

# The labels that bring a tick back to a CLOSED issue -- the two an
# adjudication runs under and the two an interrupted ending can be left on.
# Nothing else does, so an ending still owed is reachable by wearing one of
# them or by the in-memory observation, and by nothing at all once it wears
# neither.
_SWEPT_LABELS = frozenset(_issues.CLEANUP_ROUTE_LABELS)


def _reconcile_closed_owner(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """End one late cycle whose owner is gone, as far as this visit can.

    The closed half of the ending: the reconciliation below, and then the
    terminal, which is asked last and of what the whole pass left.
    """
    settled = _reconciled(gh, spec, issue, state, generation)
    _retired(gh, issue, state, settled)


def _cleanup_settled(
    gh: _client.GitHubClient, spec: config.RepoSpec, issue_number: int,
) -> bool:
    """Whether the ending a cleanup pass was routed for is actually over.

    What the dispatcher asks before it drops the close a cleanup was carrying,
    and the reason it has to ask at all: a pass can return having finished
    nothing. A consumer that is live again holds the ref, a remote that
    refuses a delete holds the branch, a held pull request a human reopened
    holds itself, and the terminal write is one more request that can be
    declined -- each of them leaves the pass returning normally with the
    ending still owed.

    Held only where nothing ELSE would come back, though, because the reading
    is not the only route: the closed sweep queries the two labels an
    adjudication runs under AND the two an interrupted ending can be left on,
    so an owner still wearing any of the four is one a later tick reaches on
    the sweep's own cadence -- which is the budget an operator set. Holding a
    reading over it would buy nothing and cost a cleanup pass per tick for as
    long as the ending is owed, and an ending can be owed for a very long
    time: a consumer that is live again keeps the ref until somebody ends it.

    What it covers is the label OUTSIDE all four, which is where a hand
    relabel or a terminal correction can leave an owner mid-ending. The sweep
    repairs that label where it can, so what the reading is really holding is
    the pass whose repair GitHub refused -- and there it is the only route
    left, until the process carrying it exits.

    An owner that is OPEN again is settled rather than held, and that is not
    the same as finished. The sweep may act externally on nobody's reopened
    issue -- it marks the cancellation and stops -- so holding the reading
    would route the owner back to a pass that is forbidden to advance it,
    every tick, forever. What the mark buys instead is the dispatcher's own
    guard, which is durable, owns a reopened cancelled owner, and reconciles
    it from the next tick.

    Fail-closed on a read that did not answer. The reading is the one thing
    this path exists to keep, and a request that failed establishes nothing
    about the ending -- so it keeps the observation and the next tick asks
    again, which costs one cleanup pass over an owner that may owe nothing.
    """
    try:
        reading = _owner_reading(gh, issue_number)
    except Exception:
        log.exception(
            "repo=%s issue=#%d could not be read back after its cleanup "
            "pass; holding the observation, since nothing establishes the "
            "ending finished", spec.slug, issue_number,
        )
        return False
    issue, state = reading
    if not _issues.issue_is_closed(issue):
        return True
    if gh.workflow_label(issue) in _SWEPT_LABELS:
        return True
    return _ending_is_over(gh, issue, state)


def _owner_reading(
    gh: _client.GitHubClient, issue_number: int,
) -> tuple[Issue, _pinned_state.PinnedState]:
    """The issue and the record a question about its ending is asked of.

    One reading rather than two, because the two answers have to agree: an
    owner refetched before the record and judged against a record written
    after it would be told about a close, a settlement, or a terminal that
    belongs to the other half.
    """
    issue = gh.get_issue(issue_number)
    return issue, gh.read_pinned_state(issue)


def _ending_is_over(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState,
) -> bool:
    """Whether one closed owner's record shows nothing of its cycle left.

    Three things in the order they become true, because a pass that stopped
    at any of them left the next one work to do: the cancellation is marked,
    every obligation the ledger holds is settled, and the terminal that says
    so is on the issue. The last is asked of GitHub rather than of the record
    -- the label is the write that takes an owner out of the sweep, and it is
    the one step of the ending that leaves no trace in the pinned comment.

    Asked only of an owner outside every swept label, so `rejected` is not
    the only label it can answer True for -- an ending whose terminal write
    GitHub refused stays on the label it had, which is what brings the next
    pass.

    A record with no cycle at all is over by definition: an umbrella the
    initial decomposer made never had one, and a retirement that dropped one
    is an ending that already ran.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        return True
    if not generation.cancelled or _outstanding(generation):
        return False
    return gh.workflow_label(issue) == WorkflowLabel.REJECTED


def _still_owed(generation: _late_models.LateGeneration) -> bool:
    """Whether this cycle still holds something on the remote.

    The half of `_ending_is_over` that costs no request, asked on its own by
    the pass that decides whether an owner may be allowed to leave the sweep:
    what a terminal is withheld for is exactly what a label the sweep queries
    has to keep the issue reachable for.
    """
    return generation.is_present and bool(_outstanding(generation))


def _record_observed_close(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue_number: int,
    *,
    polled: Issue | None = None,
) -> bool:
    """Write down, on the thread, a close no pass could be handed.

    The durable half of an observation the polling thread is holding, and a
    COMMENT rather than a pinned write for the reason the observation had to
    be held in the first place: the pinned comment is written whole, and a
    second writer racing the worker that owns the issue would drop whatever
    that worker recorded in between. A comment is added, so it races nothing.

    What reads it back is the process AFTER this one. The latch covers every
    observation this process makes -- the run holding the issue asks it before
    every step the remote keeps -- and what no latch survives is a restart, so
    the receipt is here for the tick that comes up against a cycle a dead
    process was already ending.

    Skipped where there is nothing to end: an owner with no cycle, and one
    whose record already carries the mark. Skipped too where the thread
    already says it, since a receipt is one sentence rather than one per poll
    that observes the same close.

    Retried, though, for as long as the thread does not have one. Raising
    here would cost the tick that was posting it, so a refusal is logged and
    the latch carries the observation meanwhile -- but a latch is memory, and
    an observation whose receipt never landed is one a restart takes away
    entirely. So the memo that suppresses the second attempt is written by
    the attempt that SUCCEEDED, and every later poll tries again until one
    does.

    Under a claim, because asking and posting cannot be made one operation.
    The claim is what stops two polls in that gap -- a worker's failed pass
    and the next tick's enumeration meet there -- from walking the same
    receipt-less thread and posting one apiece, and it carries the GENERATION
    of the reading it was taken for: a cleanup settling the observation
    mid-post has already dropped the memo on purpose, and re-creating it
    would suppress the next close's receipt for a reading nobody holds. Handed
    back either way, since a claim over an attempt that ended would suppress
    every later poll's receipt for good.

    Answers whether the reading is one a later pass still has to be handed,
    off the SAME record read the receipt was written from. The two questions
    were once asked of two reads, and two reads of a record a worker is
    writing can disagree: one saw a cycle and kept the observation while the
    other saw the retirement behind it and left the thread saying nothing, so
    the reading survived in memory alone and a restart took it. One read
    answers both, and a read that established nothing keeps the reading --
    which is the answer a request that failed is entitled to give.

    `polled` is the object the caller already has, where it has one. The
    enumeration writes the receipt from the issue it just listed rather than
    fetching the same one again, which is the whole of what asking at poll
    time costs over asking at the end of a pass: one pinned read.
    """
    claim = _observations.claim_receipt_post(spec.slug, issue_number)
    if claim is None:
        return _owns_a_live_cycle(gh, spec, issue_number) is not False
    try:
        cycle = _observed_close_posted(gh, spec, issue_number, polled=polled)
    except Exception:
        log.exception(
            "repo=%s issue=#%d observed closed, but the receipt saying so "
            "could not be posted; the observation is held in memory only "
            "until a later poll gets one onto the thread, and a restart "
            "before then would lose it",
            spec.slug, issue_number,
        )
        _observations.release_receipt_post(claim)
        return True
    _observations.receipt_written(claim)
    return cycle is not None


def _observed_close_posted(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue_number: int,
    *,
    polled: Issue | None = None,
) -> int | None:
    """Post this cycle's close receipt, unless something already says it.

    Answers which cycle this observation belongs to, having discharged the
    receipt in three ways rather than one: the post landed, the thread
    already carries it, or there is nothing for it to say -- an owner with no
    cycle a close would end, which is a state no later reader needs a receipt
    for and the caller drops the reading on.
    """
    issue = gh.get_issue(issue_number) if polled is None else polled
    state = gh.read_pinned_state(issue)
    cycle = _ending_cycle(
        spec, issue_number, _late_state.read_late_generation(state),
    )
    if cycle is None:
        return None
    marker = _observed_close_marker(issue_number, cycle)
    if _carries_observed_close(gh, issue, marker):
        return cycle
    gh.comment(issue, _OBSERVED_CLOSE_NOTICE.format(
        cycle=cycle, marker=marker,
    ))
    log.warning(
        "repo=%s issue=#%d observed closed while a worker held it; its late "
        "cycle %d is cancelled and the thread now says so",
        spec.slug, issue_number, cycle,
    )
    return cycle


def _ending_cycle(
    spec: config.RepoSpec,
    issue_number: int,
    generation: _late_models.LateGeneration,
) -> int | None:
    """Which cycle a close observed now would end on this issue, if any.

    The record's own answer, and -- for the one window where the record has
    none -- the cycle a worker on this very issue is retiring RIGHT NOW. That
    window is an authorized settlement's last write: the identity comes off the
    record and the barrier that would answer a latched close stands behind
    it, so a reading taken in between would be called spent against a record
    whose worker is still holding the question open.

    It is what makes the durable half survive that write at all. A receipt is
    scoped to a cycle and a retired record has none to scope it to, so an
    observation made in the window would be latched in memory and written
    down nowhere -- exactly the shape a restart takes away entirely.

    None for a cycle already marked over as well as for no cycle at all:
    the ending is already on the record and the sweep its label names is
    what runs it, so the reading buys nothing a later pass has not got.
    """
    if generation.cancelled:
        return None
    if generation.is_present:
        return generation.cycle_id
    return _observations.cycle_being_retired(spec.slug, issue_number)


def _observed_close_marker(issue_number: int, cycle_id: int) -> str:
    """The receipt one cycle's observed close is stamped with."""
    return _OBSERVED_CLOSE_MARKER.format(issue=issue_number, cycle=cycle_id)


def _carries_observed_close(
    gh: _client.GitHubClient, issue: Issue, marker: str,
) -> bool:
    """Whether this cycle's own close receipt is already on the thread.

    Walked whole rather than from a watermark: the receipt is posted by a
    poll rather than by a stage, so no watermark this mode keeps was moved
    past it and one bounded by any of them could start above it.
    """
    return _github_comments.carries_own_marker(
        gh.comments_after(issue, None),
        marker,
        bot_login=getattr(gh, "_bot_login", None),
    )


def _mark_observed_close(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState,
) -> None:
    """Mark a live cycle on an issue the POLL read closed.

    The dispatcher's own reading, applied where it can still change
    something. It is BOUND to the task rather than re-derived because the
    worker refetches the issue after the poll classified it: a human who
    reopens in that window would have the fresh object say open, and the
    close the poll saw would be gone with nothing left to end the cycle.

    Nothing to do where the record carries no cycle or already carries the
    mark, which is every closed issue but the narrow window this exists for.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present or generation.cancelled:
        return
    log.warning(
        "issue=#%s was read closed by the poll that classified it and wears "
        "a LIVE late cycle; ending cycle %d rather than dispatching it on a "
        "reading a reopen has since taken away",
        issue.number, generation.cycle_id,
    )
    _marked(gh, issue, state, generation)


def _closed_under_a_label(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Mark a live cycle whose owner this dispatch can see is already closed.

    The cleanup route takes a closed owner on either label an adjudication
    runs under, so what reaches HERE closed is one whose label names an
    ordinary terminal instead: the `implementing` an authorized settlement
    hands the issue to a moment before it retires the cycle. A close landing in
    that window is one nothing else would ever end -- the terminal arc that
    label names drains a merged pull request or a human close and writes the
    late record off nowhere, and the relabel guard beside it merely puts
    `decomposing` back, which a reopen before the next tick takes away again.

    An observed close ends the cycle, so it is marked here and the ending
    below runs from the mark like any other. Costs no request: the reading is
    the issue this guard was handed, and the record is the one it already
    read.

    This is the FRESH reading, taken of the issue the worker refetched. The
    poll's own is bound to the task and applied by `_mark_observed_close`
    ahead of this guard, because a human who reopens between the two would
    otherwise take it away -- so the two together cover a close whichever
    side of the refetch it landed on.
    """
    if generation.cancelled or not _issues.issue_is_closed(issue):
        return generation
    log.warning(
        "issue=#%s is closed and wears %r over a LIVE late cycle; ending "
        "cycle %d rather than leaving it for a label that would not",
        issue.number, gh.workflow_label(issue), generation.cycle_id,
    )
    return _marked(gh, issue, state, generation)


def _owns_a_live_cycle(
    gh: _client.GitHubClient, spec: config.RepoSpec, issue_number: int,
) -> bool | None:
    """Whether this issue's record carries a cycle a close would end, or None.

    Asked for a CLOSED issue whose submit was refused, and only then: the
    cleanup route establishes the same thing from the label, and this
    establishes it from the record for the one window where no label says it.
    A read on a path that runs when a worker is already holding the issue is
    a read this orchestrator can afford.

    Taken only where the receipt above is not being written from a read of
    its own, which is the repeat case -- a poll whose thread already carries
    the receipt, or one another poll is posting right now. The first pass
    answers this from the read it wrote the receipt with, so the two never
    disagree about the same record.

    Three answers rather than two, and the third is what keeps the reading
    safe. False is the record positively saying there is nothing to end -- no
    cycle, or one already marked -- and a record whose cycle a worker is
    retiring right now is not saying that at all, so the retirement window is
    part of the question. None is a read that established NOTHING, which is
    not the same claim, and the caller keeps the observation it latched
    rather than dropping it on a request that failed.
    """
    try:
        state = gh.read_pinned_state(gh.get_issue(issue_number))
    except Exception:
        log.exception(
            "repo=%s issue=#%d could not be read for a late cycle a close "
            "would end; keeping the observation the poll took",
            spec.slug, issue_number,
        )
        return None
    return _ending_cycle(
        spec, issue_number, _late_state.read_late_generation(state),
    ) is not None


def _inherited_close(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Adopt a close a process that is gone observed and never settled.

    An in-memory latch dies with the process holding it, and a close observed
    against a worker is exactly the reading no tick after that process has any
    other way to take: the issue may well be open again, and its record still
    says the cycle is live. So the thread is asked, and a receipt there is as
    good as the reading that produced it -- the cycle is marked cancelled
    here, and the ending below runs from the mark like any other.

    Asked ONCE per owner per process, which is what keeps it off the wire in
    the steady state. What it recovers is an observation a DEAD process was
    holding; every observation this one makes is in the latch already, and the
    latch costs no request at all. So a thread that carries no receipt is
    walked on the first tick that sees this owner and never again.

    Once it has actually ANSWERED, that is. A claim standing over a walk that
    raised would send every later tick straight past the receipt and on to
    the live stage handler, which is the one thing this exists to prevent --
    so the claim is held for the length of the walk and handed back by an
    exception leaving it, and the tick fails where it stands, exactly as the
    pinned read above it does.
    """
    if generation.cancelled:
        return generation
    with _observations.scanning_receipt(spec.slug, issue.number) as claimed:
        if not claimed:
            return generation
        marker = _observed_close_marker(issue.number, generation.cycle_id)
        if not _carries_observed_close(gh, issue, marker):
            return generation
    log.warning(
        "repo=%s issue=#%s carries a receipt for a close its own record "
        "never recorded; adopting that observation and ending cycle %d",
        spec.slug, issue.number, generation.cycle_id,
    )
    return _marked(gh, issue, state, generation)


def _latched_close_ends(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> bool:
    """Mark a latched close on this owner, and say whether the walk stops.

    The barrier a handler already inside its own walk takes. The dispatcher's
    guard asked the same question before the label became this call, but a
    dependency-graph scan is a request per child and the poll runs beside it:
    a close latched in the middle of one reaches no other pass, and what the
    walk would otherwise do next is reclaim a remote, hand the issue its
    terminal, or start an agent on a child.

    Marking is the whole of what happens here, which is the same bargain the
    post-agent guard makes: the mark says the cycle is over, every gate below
    reads it, and what the remote is still owed is settled by the ending --
    from the closed-owner sweep if the issue is closed by then, and from the
    dispatcher's own guard if a human has reopened it. Doing that work HERE
    would be doing it on a reading this walk cannot trust.

    True only where there is a cycle to end. An umbrella the initial
    decomposer made carries no generation, and a latched close against one is
    a closed issue the ordinary terminals own.
    """
    if not _observations.close_observed(spec.slug, issue.number):
        return False
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        return False
    log.warning(
        "repo=%s issue=#%s was observed closed while its children were being "
        "walked; ending cycle %d rather than acting on that walk",
        spec.slug, issue.number, generation.cycle_id,
    )
    _marked(gh, issue, state, generation)
    return True


def _refuses_cancelled(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    label: str | None,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether this issue is a cancelled cycle's ending and nothing else.

    The open half, and the reason it exists: a cancellation is irreversible
    within its cycle, so a human who reopens the issue does not get that cycle
    back. Between the reopen and the ending the issue would otherwise be
    dispatched to the handler its label names, and EVERY label names a handler
    that acts: one spawns the decomposer, one walks the dependency graph and
    activates children, the rest drive a delivery stage against a branch and a
    pull request this cycle no longer owns. Any of them would be the cancelled
    cycle resumed, so none of them is reached -- what the label is decides
    nothing about whether this refuses.

    What it does decide is where the ending can be written. `rejected` is what
    the CYCLE earns rather than what a closed issue earns: it is what the
    operator removes to authorize a restart, and reaching it is the only way
    back into ordinary work that does not silently resume a cycle a close
    already ended. It is written from the states the transition graph declares
    the edge from and nowhere else -- under a label it does not, the
    reconciliation still runs, the refusal still stands, and the cycle stays
    cancelled where it is rather than being relabelled out from under whoever
    put the issue there. A reopened owner that settles is retired exactly as a
    closed one is, and left open, since closing an issue a human just reopened
    is not this owner's to do.

    Running the reconciliation rather than merely refusing is what makes the
    refusal end: the closed-owner sweep visits closed issues only, so this is
    the one pass that would ever come back to a reopened owner, and a refusal
    with nothing behind it would freeze the issue until somebody closed it
    again.

    The unlabeled state is refused with every other one, and by this owner.
    The restart is asked one guard ahead, so an issue reaching here with no
    label is one that guard has already declined -- because the cycle still
    owes something, or because nothing on the record proves the terminal was
    applied and then removed. Either way the issue is not a fresh attempt and
    is not ordinary work: letting it fall through would hand a cancelled cycle
    to the pickup path, which greets it as new and mints a SECOND pinned
    comment that shadows the one this reading came from.

    What the unlabeled state does still decide is whether the terminal may be
    written from it, which `_ends_here` answers off the record rather than off
    the label. An operator who has taken `rejected` off is not handed it back;
    an issue that never got it -- a workflow label a human stripped
    mid-cleanup, so the ending had no state to write from -- is, once the
    cleanup it interrupted finishes.

    A record with no cycle on it is asked one more question before it is
    waved through, and only where the record itself says there is one to ask:
    a retirement that dropped a cycle records which cycle it dropped, so a
    close observed inside that very write is one a later process can still
    adopt off the thread.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        generation = _retired_close_adopted(gh, spec, issue, state)
        if generation is None:
            return False
    generation = _closed_under_a_label(gh, issue, state, generation)
    generation = _inherited_close(gh, spec, issue, state, generation)
    if not generation.cancelled:
        return False
    log.warning(
        "repo=%s issue=#%s wears %r over a cancelled late cycle; settling "
        "that cycle rather than dispatching the issue",
        spec.slug, issue.number, label,
    )
    if _parked_ending(spec, issue):
        return True
    settled = _reconciled(gh, spec, issue, state, generation)
    _terminal_proved(gh, issue, state, settled)
    _terminal_recovered(gh, issue, label, state, settled)
    if _ends_here(state, settled, label):
        _retired(gh, issue, state, settled)
    return True


def _retired_close_adopted(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> _late_models.LateGeneration | None:
    """Put back a cycle a retirement dropped, if a close was seen inside it.

    The one window the reinstatement behind the retirement write cannot cover
    for itself: that barrier is this process's memory, and a process that dies
    between the write and it leaves a record with no cycle identity and a
    receipt on the thread naming one. Nothing else would ever look at that
    receipt -- the guard above returns on a record with no cycle, and the
    closed-owner sweep reads the same field to decide anything is owed.

    So the retirement records which cycle it dropped, and this is what reads
    it back. The thread is asked exactly once per owner per process, under the
    same claim the inherited-close scan takes and for the same reason: what it
    recovers is an observation a DEAD process was holding, and one this
    process makes is in the latch already.

    The cycle goes back with the ledgers the retirement carried across and an
    identity rebuilt beside them -- see `_reconstructed`, which is what makes
    the ending REPORTABLE as well as runnable.

    Marked here rather than left for the inherited-close scan behind it,
    because the two share one claim: this walk is the one that answered, so
    it is the one that records what it found. What comes back is a record
    that already says the cycle is over, and the ending below runs from it
    like any other.

    None wherever there is nothing to adopt: a record no retirement wrote, a
    thread that carries no receipt for the cycle it names, and a walk that
    could not answer -- which hands its claim back and leaves the tick to the
    dispatcher's own per-issue isolation.
    """
    retired = _endings.read_retired_cycle(state)
    if retired is None:
        return None
    with _observations.scanning_receipt(spec.slug, issue.number) as claimed:
        if not claimed:
            return None
        marker = _observed_close_marker(issue.number, retired)
        if not _carries_observed_close(gh, issue, marker):
            return None
    log.warning(
        "repo=%s issue=#%s carries a receipt for a close observed inside the "
        "write that retired cycle %d; putting that cycle back so the ending "
        "has something to run from",
        spec.slug, issue.number, retired,
    )
    return _marked(gh, issue, state, _reconstructed(issue, state, retired))


def _reconstructed(
    issue: Issue, state: _pinned_state.PinnedState, retired: int,
) -> _late_models.LateGeneration:
    """Rebuild enough of a dropped cycle for the ending to be recorded by.

    The ledgers are already there -- a retirement carries them across, since
    an obligation does not stop being owed because the identity beside it was
    cleared -- and the cycle comes from the correlation. What has to be put
    back beside them is the IDENTITY every record of this cycle is correlated
    by: a cancellation is reported on two sinks, and a record that cannot name
    the root of its own lineage is one the domain refuses outright, so a
    reconstruction short of it would end the cycle and say nothing about it.

    The root is read off the ancestry, which survives the clear because it is
    a fact about the split this issue was CUT from rather than about the cycle
    this issue ran -- and an owner with no ancestry is the root of its own
    lineage, which is what the split writes for one. The depth comes with it,
    for the same reason and from the same place.

    The boundary is the one a finished cycle stands at. A retirement is the
    last write of a publication that created no child and preserved no ref,
    and of a terminal whose every obligation was already reclaimed, so there
    is no consumer ledger for the reclamation rule to find short.
    """
    ancestry = _lineage.read_late_ancestry(state)
    return replace(
        _late_state.read_late_generation(state),
        cycle_id=retired,
        current_issue=issue.number,
        root_issue=ancestry.root_issue or issue.number,
        lineage_depth=ancestry.lineage_depth,
        phase=_late_models.LatePhase.CLEANING_UP,
    )


def _parked_ending(spec: config.RepoSpec, issue: Issue) -> bool:
    """Whether a control label defers everything past the mark.

    `backlog` and `paused` park an issue outside the state machine, and the
    ending is external work: a held pull request closed, a branch deleted, a
    ref reclaimed. Doing any of it would be reacting exactly where an operator
    said not to.

    The MARK is not deferred with it, and is already down by the time this is
    asked. A close ends the cycle irreversibly, and the pass this filter is
    about is the only one that would ever record it -- an owner parked while
    closed would otherwise come back from a reopen and an unpause with a live
    generation and spawn against it. So the fact is written and the reaction
    waits for the tick the label comes off.
    """
    skip_label = _labels.hard_skip_control_label(issue)
    if skip_label is None:
        return False
    log.info(
        "repo=%s issue=#%s has %r over a cancelled late cycle; the mark "
        "stands and everything it owes waits for the label to come off",
        spec.slug, issue.number, skip_label,
    )
    return True


def _ends_here(
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
    label: str | None,
) -> bool:
    """Whether the cycle's terminal may be written from where the issue is.

    The transition graph answers for every label a WORKFLOW wrote: each state
    a late cycle can be interrupted on declares the edge to `rejected`, and a
    state that does not -- `question`, applied by an operator who wants the
    issue discussed rather than ended -- is refused and said out loud on every
    visit rather than relabelled out from under whoever put it there. What
    ends that refusal is the same handshake as always: an operator taking the
    label off.

    The graph cannot answer for the two labels this cycle's OWN agent leaves
    behind. A decomposer spawned before the close writes `ready` or `blocked`
    as its ordinary outcome, and a close observed inside that run lands ahead
    of it -- so the ending, already irreversible, finds the owner wearing a
    decomposition outcome its own cancellation voided. Neither label declares
    that edge, so an ending refused there would be refused on every visit the
    cleanup sweep makes, forever: the sweep is what brings a tick back to such
    an owner, and the terminal is the only thing that lets it stop.

    From the UNLABELED state the RECORD answers instead of the label, because
    the label cannot tell apart the issues that reach it wearing none. One is
    the restart handshake: an operator took `rejected` off, and re-applying it
    would undo the one authorization a restart has. Another never got the
    terminal at all -- a human stripped the workflow label while the cleanup
    was still running, so every visit since has found the ending owed under a
    state it could not be written from. A third had it attempted and refused.
    What separates the first from the other two is the PROOF half of the
    terminal record: a cycle whose `rejected` was seen on the issue has been
    through the handshake, and one carrying only the decision, or nothing at
    all, is owed the write rather than holding the removal of one.
    """
    if label is None:
        return not _endings.terminal_confirmed(state, generation.cycle_id)
    if label in _RELABELLED_MID_ENDING:
        return True
    return is_allowed_transition(label, WorkflowLabel.REJECTED)


def _reconciled(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Settle everything one cancelled cycle owes that can be settled now.

    The order is the contract. The cancellation is durable before any external
    call, so nothing below can happen against a record that does not already
    say the cycle is over; the held pull request is settled before the branch
    and the ref, because it is the only obligation here a human is still
    looking at.

    Every step is idempotent, and each is skipped where the record already
    says what this visit would say -- so the pass a refusal keeps bringing
    back costs only the obligations that are actually still owed.

    And the held pull request is asked once more at the end, because the
    steps between the two asks are a branch delete, a ref delete, and a
    consumer read apiece -- long enough for a human to reopen it inside them.
    """
    marked = _marked(gh, issue, state, generation)
    reconciled = _plan_pr_settled(gh, issue, state, marked)
    owed = _superseded_branch(gh, spec, issue, state, reconciled)
    scan = _proof_scan(gh, issue, owed)
    settled = _late_cleanup._settle(gh, spec, issue, state, scan)
    return _reverified(
        gh, issue, state, _children_discharged(gh, issue, state, settled),
    )


def _reverified(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Ask the held PR again, on the far side of everything else owed.

    The terminal is the write that cannot be taken back: it takes the issue
    off every label the closed-owner sweep queries, so an owner that reaches
    it is one nothing revisits. The pull request was settled at the top of
    this pass and the record has said `reconciled` ever since -- but between
    the two stand a branch delete, a ref delete, and a fresh read of every
    recorded consumer, and a human who reopens the change inside them leaves
    the record saying one thing and the remote another. Retiring on the
    record would leave that change open under a cancelled cycle with nothing
    coming back for it.

    So the reading the terminal is taken on is one taken HERE, immediately
    before it. A pull request still where the earlier ask left it costs a
    fetch and a comment listing and moves nothing -- the notice is gated on
    this cycle's marker already on the thread, and one that is not open is
    left exactly as it is -- while one that is open again is closed again and
    an entry that could not be settled holds the terminal for the next visit.

    Only where nothing else is owed, which is the only visit whose terminal
    is actually due. An owner still holding a branch the remote will not
    delete is one the sweep is bringing back anyway, and the ask at the top
    of that next pass is the same ask.
    """
    if _outstanding(generation) or _held_pull_request(generation) is None:
        return generation
    return _plan_pr_settled(gh, issue, state, generation)


def _children_discharged(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Say on the ledger that the children this cycle made owe it nothing.

    A child entry is the split's own receipt -- this generation created issue
    #N -- and it is written `pending` because the create comes before
    anything that could confirm it. Nothing has ever moved one since: the
    reclamation does not look at child entries, and rightly, because a child
    is a live issue somebody is working rather than an object to reclaim.

    A cancellation has to move them, and for a reason outside itself.
    `rejected` is what authorizes a restart, and a restart projects its fresh
    cycle only over a ledger with nothing unreconciled left on it -- child
    entries included, correctly, since the projection drops the ledger and
    may not discharge an obligation by forgetting it. Retiring over them
    would hand an operator a terminal whose restart then refuses for good.

    So the ending records what is already true rather than inventing it: the
    children exist, this cycle is over, and nothing further about them is
    owed. Not one of them is touched on GitHub -- what moves is the parent's
    own account of what it made.
    """
    pending = _pending_children(generation)
    if not pending:
        return generation
    discharged = generation
    for target in pending:
        discharged = _late_cleanup._recorded(
            discharged, _late_models.LateResourceKind.CHILD, target,
            _late_models.LateResourceState.RECONCILED,
        )
    _persisted(gh, issue, state, discharged)
    return discharged


def _pending_children(
    generation: _late_models.LateGeneration,
) -> tuple[str, ...]:
    """The child receipts this record has not yet said it owes nothing on."""
    if _late_cleanup._unwritable(generation):
        return ()
    return tuple(
        entry.target
        for entry in generation.resources
        if entry.kind == _late_models.LateResourceKind.CHILD
        and entry.resource_state != _late_models.LateResourceState.RECONCILED
    )


def _superseded_branch(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Take on the branch a supersession left behind but never wrote down.

    The transaction settles the held pull request and records the branch
    that pull request carried in two separate writes, and it must: the second
    is the retirement that hands the parent to `umbrella`, and retiring ahead
    of a supersession that might not land would leave the children loose
    beside a change still carrying their work. A close landing in that window
    leaves a cycle whose candidate is preserved on the ref, whose held PR is
    closed, and whose branch nothing on the record names -- so the
    reclamation, which walks the record, would settle around it and retire
    the owner over a branch the remote keeps for good.

    Asked of the announcement's own receipt rather than of the phase. Both go
    down in one write, so they say the same thing the first time -- the
    children are made, the links are said, and the supersession is what comes
    next -- but only one of them survives a retry: a park at the supersession
    is resumed from the top of the transaction, which rewrites `snapshotting`
    and `splitting` over the boundary while the announcement, already made,
    is stepped over. So a second failed attempt stands at `splitting` with the
    receipt still set, and the phase no longer says what was reached.

    Not before that receipt, though, and that is the whole of the timing: the
    snapshot is created AND proved ahead of the first child, so the candidate
    stops being only on that branch by the time the announcement is made.
    Earlier, deleting it would take the one copy of somebody's work.

    Only where nothing is recorded yet, in any state. A record that already
    names a branch is the ordinary case the reclamation owns, and re-recording
    a `reconciled` one as owed would ask the remote to delete it again.

    And only once the pull request this pass was just asked to settle IS
    settled, which is the same order the transaction takes: it records the
    branch in the retirement that follows a supersession, never beside one
    that failed. `superseding` is the boundary written BEFORE that attempt,
    so a record standing there says the attempt was reached and nothing about
    whether it landed -- and inferring the branch from it while the pull
    request is still open would delete, out from under a change a human can
    still see, the branch that change is built on. The obligation is not lost
    by waiting: the held PR is re-asked on every visit, and the visit that
    closes it is the one that takes the branch on.
    """
    if not generation.links_announced:
        return generation
    if _late_cleanup._unwritable(generation) or _names_a_branch(generation):
        return generation
    if _owed_plan_pr(generation):
        log.warning(
            "issue=#%d was cancelled at its supersession and its held PR is "
            "not settled; leaving the branch that PR carries alone until it "
            "is", issue.number,
        )
        return generation
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    log.warning(
        "issue=#%d was cancelled between the supersession of its held PR and "
        "the write that records the branch it superseded; taking %r on as "
        "owed rather than retiring over it", issue.number, branch,
    )
    owed = _late_cleanup._recorded(
        generation, _BRANCH, branch, _late_models.LateResourceState.PENDING,
    )
    _persisted(gh, issue, state, owed)
    return owed


def _names_a_branch(generation: _late_models.LateGeneration) -> bool:
    """Whether this record already holds the superseded branch, any state."""
    return any(entry.kind == _BRANCH for entry in generation.resources)


def _marked(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Record that this cycle is over, once, before anything acts on it.

    A record that already carries the mark is handed straight back: the flag,
    the stamp, and the boundary the cancellation interrupted are all decided
    by the FIRST observation, and a human who reopened the issue and closed it
    again has not started a new cleanup obligation. Skipping the write is also
    what bounds the record of it -- one `late_cancellation` per cycle, emitted
    by the visit that made the mark true rather than by every visit that reads
    it back.

    The pending owner read goes with it, for the reason the post-agent guard
    drops it: what that marker exists for is bringing a tick back to a fresh
    read of this issue, and this pass is one.
    """
    if generation.cancelled:
        return generation
    log.warning(
        "issue=#%d was closed while its late cycle %d stood at %s; "
        "cancelling it and reconciling what it owes the remote",
        issue.number, generation.cycle_id, generation.phase,
    )
    cancelled = replace(
        generation.cancel(_usage._now_iso()),
        phase=_late_models.LatePhase.CANCELLING,
        owner_check_pending=False,
    )
    _persisted(gh, issue, state, cancelled)
    _telemetry.emit_late_event(
        gh,
        _events.LateEvent(family=_events.LateEventFamily.CANCELLATION),
        cancelled,
        stage=stage_name(gh.workflow_label(issue)),
    )
    return cancelled


def _plan_pr_settled(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Take the hold off the pull request it marked, say why, and close it.

    Only the pull request this generation actually held -- the plan one where
    the cycle was entered before publication, and the implementation one the
    work is already on where it was entered past it. `pr_number` on the
    stage's own keys is whichever one the issue currently records and may name
    a change somebody else opened; the hold's record names the one this cycle
    marked, and closing anything else would end a change no adjudication ever
    touched.

    The hold comes off first, so a pull request that ends up closed is not
    also left carrying a "do not merge" notice forever. A release that failed
    on a still-open pull request stops the close: what that failure means is
    that the preserved description is not back where it belongs, and closing
    over it would settle the entry with a human's words still replaced.

    Run on EVERY visit, including one whose entry already reads `reconciled`.
    That entry records what an earlier visit did, and a pull request is not a
    thing that stays where it was put: a human can reopen one, and an owner
    the sweep is still visiting for a branch it cannot delete would otherwise
    reach `rejected` -- and leave the sweep for good -- beside a plan pull
    request that is open again under a cancelled cycle. Re-asking costs one
    fetch and one comment listing, and neither step repeats anything: the
    notice is gated on this cycle's own marker already on the thread, a pull
    request that is not open is left exactly as it is, and a description that
    is no longer this cycle's hold is not rewritten.

    What IS bounded is the record of it. The write and both sinks are behind a
    state that actually moved, because an entry saying what it already said is
    not news -- reporting it every visit would put one `late_cleanup` per
    cadence on an owner that is simply waiting for something else.
    """
    number = _held_pull_request(generation)
    if number is None:
        return generation
    released, reached = _reached(gh, issue, generation, number)
    settled = _plan_pr_entry(released, str(number))
    if settled is not None and settled.resource_state == reached:
        return released
    recorded = _late_cleanup._recorded(
        released, _PLAN_PR, str(number), reached,
    )
    _persisted(gh, issue, state, recorded)
    _reported(gh, issue, recorded, str(number))
    return recorded


def _reached(
    gh: _client.GitHubClient,
    issue: Issue,
    generation: _late_models.LateGeneration,
    number: int,
) -> tuple[_late_models.LateGeneration, _late_models.LateResourceState]:
    """Release the hold, close the pull request, and say where that left it.

    The record travels back with the answer because the release is entitled to
    change it: what is written afterwards has to be written onto whatever the
    release left, not onto the copy this attempt started from.

    A release that failed stops the close rather than shortening it. The
    preserved description is the only copy of what the hold replaced, so a
    pull request closed while the hold is still on it is a human's words
    replaced for good.
    """
    release = _late_hold._release_hold(gh, issue, generation)
    if release.failed:
        return release.generation, _late_models.LateResourceState.FAILED
    if not _closed_over_notice(gh, issue, release.generation, number):
        return release.generation, _late_models.LateResourceState.FAILED
    return release.generation, _late_models.LateResourceState.RECONCILED


def _closed_over_notice(
    gh: _client.GitHubClient,
    issue: Issue,
    generation: _late_models.LateGeneration,
    number: int,
) -> bool:
    """Fetch the held pull request and hand it its cancellation.

    The fetch is guarded here rather than left to the helper, because a
    PyGithub pull request is lazy and the request that can fail is as likely
    to be this one as the write behind it -- and an exception escaping a
    cleanup pass would take the branch and the ref down with it, neither of
    which owes this pull request anything.

    Said at most once, proved from the thread the notice is on: the comment
    and the entry recording it cannot be made one operation, so a crash
    between them repeats this call, and the marker is what makes the repeat
    silent.
    """
    try:
        held = gh.get_pr(number)
    except Exception:
        log.exception(
            "issue=#%d could not read held PR #%d to close it",
            issue.number, number,
        )
        return False
    receipt = _cancelled_marker(issue, generation)
    return gh.supersede_pr(
        held,
        notice=_CANCELLED_NOTICE.format(owner=issue.number, marker=receipt),
        marker=receipt,
    )


def _cancelled_marker(
    issue: Issue, generation: _late_models.LateGeneration,
) -> str:
    """The receipt this cycle's cancellation notice carries."""
    return _CANCELLED_MARKER.format(
        issue=issue.number, cycle=generation.cycle_id,
    )


def _held_pull_request(generation: _late_models.LateGeneration) -> int | None:
    """The held pull request this pass may act on, if there is one.

    Both halves of the hold or neither. The number alone is not a hold this
    generation can prove it took: the identity and the description it
    displaced are written as ONE thing, so a record carrying the first and
    not the second is damaged rather than partial -- and acting on it would
    comment on and close a pull request nothing here ever marked, which for a
    number a human typed is somebody else's change. The release in front of
    this refuses such a record silently, having no copy to put back, so
    without this the close would run behind a no-op that proved nothing.
    `_unprovable_hold` is what holds the terminal for the repair instead.

    None while the RESOURCE ledger is opaque too, for the reason nothing else
    is reclaimed there: the typed view is a projection of the entries this
    binary could read and the write puts the verbatim copy back, so an
    outcome recorded against it would be dropped at the next write and the
    pull request acted on again forever. What holds the terminal in that case
    is the opaque ledger itself, which the reclamation owner already reports.
    """
    if _late_cleanup._unwritable(generation) or _unprovable_hold(generation):
        return None
    return generation.plan_pr_number


def _unprovable_hold(generation: _late_models.LateGeneration) -> bool:
    """Whether this record names a PR it cannot show it ever held."""
    return (
        generation.plan_pr_number is not None
        and generation.plan_pr_body is None
    )


def _owed_plan_pr(generation: _late_models.LateGeneration) -> tuple[str, ...]:
    """Every held pull request this cancellation has still to settle.

    What the terminal is held by, and a different question from what the pass
    ACTS on. Acting takes the hold's own record, since releasing one means
    knowing which pull request this cycle marked; being owed takes the LEDGER,
    because that is where an obligation lives once it is written. The two can
    disagree -- a supersession that failed leaves an entry behind, and the
    number beside it is a field a later write can clear or a hand edit can
    damage -- and only the ledger's answer may decide a terminal. An entry
    left behind by a `rejected` owner is a pull request nothing revisits, and
    it is also what makes a restart refuse the fresh cycle that terminal is
    supposed to authorize: restart counts every unreconciled resource as owed,
    and it is right to.

    A record naming a pull request it cannot show it held is owed too, and it
    is the one entry here nothing can settle: the description that hold
    displaced is the only copy there was, so no later pass may put it back or
    close over it. It holds the terminal until a human repairs the record,
    which is the answer that neither closes somebody else's change nor
    quietly forgets a pull request this cycle may really have marked.

    Empty while the RESOURCE ledger is opaque only because the reclamation
    owner already blocks on that outright, and its answer names it.
    """
    if _late_cleanup._unwritable(generation):
        return ()
    owed = tuple(
        _OWED_PLAN_PR.format(entry.target)
        for entry in generation.resources
        if entry.kind == _PLAN_PR
        and entry.resource_state != _late_models.LateResourceState.RECONCILED
    )
    if not _unprovable_hold(generation):
        return owed
    return owed + (_UNPROVABLE_HOLD.format(generation.plan_pr_number),)


def _proof_scan(
    gh: _client.GitHubClient,
    issue: Issue,
    generation: _late_models.LateGeneration,
) -> _ChildScan:
    """Read the consumers a held ref has to be proved against, if any.

    The reclamation rule needs a fresh reading of every recorded consumer, and
    that reading costs one request each. It buys nothing where no ref is held:
    a branch owes no consumer anything, and an owner whose refs are all
    reconciled has nothing a fresh disposition could unlock. So the scan is
    taken only where its answer can change one, which is what keeps a sweep
    over a repository's closed owners affordable.
    """
    if not _late_cleanup._held_snapshots(generation):
        return _ChildScan([], {}, {})
    return _late_cleanup._consumer_scan(gh, issue, generation)


def _retired(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Hand a settled cycle its terminal, or say what is still holding it.

    `rejected` is the honest end of a cycle whose owner a human closed, and it
    is also what stops this pass repeating: every label the closed-owner sweep
    queries is one the owner keeps until this write lands, so writing it is
    the only thing that takes the issue out of the sweep.

    Which is exactly why it may not be written early. An issue that has left
    the sweep is one nothing revisits, so a terminal taken over an unreclaimed
    branch or a retained ref would leave that object on the remote with
    nothing left to come back for it. The label staying put IS the retry, and
    the reason it stays is logged on every visit that holds -- a cleanup that
    never finishes and never says why is the one shape an operator cannot act
    on.

    An issue already wearing the terminal is left alone rather than written
    again. The sweep does not yield one, so that is the pass driven straight
    at an owner somebody already settled -- and re-setting a label costs a
    write and a second `stage_enter` on a state the issue never re-entered.
    It is asked after the hold rather than before it, so an owner that
    somehow wears the terminal over something still owed says so out loud.

    Written UNGUARDED, because it is not a transition. The graph describes the
    moves this workflow makes, and the move this corrects is one it did not:
    an agent's ordinary decomposition outcome landing on the owner after the
    close that cancelled the cycle it was running for. Under `enforce` a
    guarded write would raise there, every visit, and the owner would sit
    closed on a label no query reaches -- refusing the repair of a move the
    guard never described, which is the opposite of what the guard is for.

    It is recorded in two phases, exactly as an external obligation is. The
    DECISION goes down first -- which cycle this terminal is for -- because a
    tick that dies between the write and the record of it needs something
    durable to come back to. The PROOF goes down after, and only for a write
    that landed, because an operator authorizes a fresh cycle by REMOVING this
    label and the removal leaves an issue indistinguishable from one whose
    workflow label a human stripped mid-cleanup. An attempt is not a terminal:
    treating the decision as proof would let a write GitHub refused authorize
    a restart nobody asked for, on an owner that is unlabeled for the reason
    it always was.

    The proof this pass takes is the write RETURNING, and it may not be
    re-derived by reading the issue back: a client's cached labels survive the
    write that changes them, so a re-read here would answer with the label the
    issue wore a moment ago and record nothing. That matters most exactly
    where nothing would notice -- a closed owner leaves the sweep on this
    write and gets no second visit to see the label for itself.

    A write GitHub refuses is left for the next visit rather than raised: the
    obligations are settled and recorded by then, and the only thing missing
    is the label that says so -- which is exactly what the unproved decision
    brings this pass back for.
    """
    held = _outstanding(generation)
    if held:
        log.info(
            "issue=#%d is closed and cancelled, and still owes the remote: "
            "%s; it stays swept until it does not",
            issue.number, ", ".join(held),
        )
        return
    if gh.workflow_label(issue) == WorkflowLabel.REJECTED:
        _terminal_recorded(gh, issue, state, generation)
        return
    _endings.record_terminal(state, generation.cycle_id, confirmed=False)
    _persisted(gh, issue, state, generation)
    try:
        gh.set_workflow_label(issue, WorkflowLabel.REJECTED, guarded=False)
    except Exception:
        log.exception(
            "issue=#%d settled everything its cancelled cycle owed but could "
            "not be moved to rejected; the next sweep writes the label",
            issue.number,
        )
        return
    _terminal_recorded(gh, issue, state, generation)


def _terminal_proved(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Record a `rejected` this pass can SEE on the issue, once.

    The reading half of the receipt, and what makes the record available to
    passes that made no write at all: a cancellation that reached its terminal
    before this record existed carries no proof of it, and a tick that died
    between the label landing and the receipt carries none either. Both are an
    issue visibly wearing `rejected` over a cancelled cycle, which is a thing
    any visit can see and write down -- so the operator's FIRST removal is the
    one that authorizes the fresh cycle.

    Asked of the label as this pass FOUND it, which is why it is not what the
    pass that writes the terminal uses: a client's cached labels are not
    refreshed by the write that changes them, so re-reading one here after
    writing would answer with the label the issue wore before and record
    nothing at all.
    """
    if gh.workflow_label(issue) != WorkflowLabel.REJECTED:
        return
    _terminal_recorded(gh, issue, state, generation)


def _terminal_recovered(
    gh: _client.GitHubClient,
    issue: Issue,
    label: str | None,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Prove a terminal a dead process left unrecorded, off the remote itself.

    The one window neither half of the receipt covers. The decision goes down,
    the label write lands, and the process dies before the proof -- and what
    is left is an issue on `rejected` that nothing revisits, since a terminal
    is on no sweep's list. The operator reopens it and takes the label off,
    and now the record shows a decision with no proof, which is the same thing
    a label write GitHub REFUSED leaves behind. One of those is a gesture and
    the other is an ending still owed, and no local reading tells them apart.

    So the remote is asked, and only from BEHIND the reconciliation: what
    decides whether anything is still owed is the record this pass has just
    settled, not the one it found. An obligation the ending discovers rather
    than reads -- the branch a supersession left behind and never wrote down
    -- is on no ledger until `_reconciled` puts it there, so adopting a proof
    in front of that would let the restart project away a branch nobody had
    looked for yet. Everywhere else this returns before it costs anything: the
    proof is already recorded, something is still owed, or the issue is
    wearing a label and the question does not arise.

    What is asked is which workflow label THIS orchestrator applied last, not
    whether `rejected` was ever applied at all. Both halves narrow it. The
    actor, because a collaborator may apply and remove that same name by hand
    and a terminal is a write this orchestrator makes -- reading somebody
    else's back would let a label nobody here wrote stand in for one it did.
    And the newest, because an issue reaches this terminal once per cycle, so
    an older one's is still in the history and adopting that would authorize a
    fresh cycle off a removal an operator made two cycles ago. The cycles are
    separated by construction: a cycle exists only because a restart retired
    its marker, and a restart retires only once its own target label has
    landed as one of THIS orchestrator's applications -- a target it finds
    somebody else applied is taken off and put back for exactly this reason --
    so a stale `rejected` always has a later application of its own after it.

    Fail-closed on every other answer. A history whose newest application is
    some other state is an ending still owed, one that names nothing this
    vocabulary recognizes says as much, and one that could not be read vouches
    for nothing; each writes the terminal again rather than starting a fresh
    cycle on a removal nobody made.
    """
    if not _terminal_unproved(label, state, generation):
        return
    if gh.last_workflow_label_applied(issue) != WorkflowLabel.REJECTED:
        return
    log.warning(
        "issue=#%d carried %s for cancelled cycle %d and no pass recorded "
        "it; adopting the remote's own history so the removal an operator "
        "has already made is the one that authorizes a fresh cycle",
        issue.number, WorkflowLabel.REJECTED, generation.cycle_id,
    )
    _terminal_recorded(gh, issue, state, generation)


def _terminal_unproved(
    label: str | None,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> bool:
    """Whether this issue is the one window the remote has to answer for.

    Four local answers, and the remote is asked only past all of them. The
    issue wears no label, over a cycle a close ended, with nothing left owed
    and no proof its terminal ever landed -- which is what an operator's
    removal leaves, and equally what a crash between the label and the receipt
    does, and what a cancellation that ended before this record existed
    carries. The DECISION is deliberately not required: a record written by a
    binary that had no such field is exactly the case the reading exists to
    recover, and demanding one would leave every cancellation that predates it
    needing a second removal.

    "Nothing owed" is what bounds the cost. An unlabeled owner whose cleanup
    is unfinished is visited every tick, and asking the remote on each of
    those would put a paginated walk on the steady state; asking only once
    settled costs one walk per removal, because the tick that gets no proof
    writes the terminal back and the issue stops being unlabeled.
    """
    if label is not None or not generation.is_present:
        return False
    if not generation.cancelled or _unsettled(generation):
        return False
    return not _endings.terminal_confirmed(state, generation.cycle_id)


def _terminal_recorded(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Write down that this cycle's terminal is on the issue, once.

    Reached two ways, and they are the same claim from either side of the
    write: a pass that just set the label and was not refused knows it landed,
    and a pass that finds the label already there can see that it did. What
    neither is, and what may not reach here, is an attempt that raised.

    Bounded by what it records: a cycle already proved is left alone, so the
    guard that brings a tick back to a cancelled owner every tick costs a
    pinned write once rather than one per visit.
    """
    if _endings.terminal_confirmed(state, generation.cycle_id):
        return
    log.info(
        "issue=#%d carries %s over cancelled cycle %d; recording the terminal "
        "an operator removes to authorize a fresh one",
        issue.number, WorkflowLabel.REJECTED, generation.cycle_id,
    )
    _endings.record_terminal(state, generation.cycle_id, confirmed=True)
    _persisted(gh, issue, state, generation)


def _outstanding(generation: _late_models.LateGeneration) -> tuple[str, ...]:
    """Everything this cancellation may not leave the remote holding.

    The reclamation owner's own reading of the branch and the ref, plus the
    held pull request that owner never sees: a cycle cancelled before its
    split landed is the one case where one is still open, since
    every path that reaches an umbrella superseded it on the way.

    What it names is what this ending ACTS on and reports, which is why it is
    a list of names. Whether anything at all is still owed is the wider
    question `_unsettled` asks.
    """
    return _late_cleanup._blocking(generation) + _owed_plan_pr(generation)


def _unsettled(generation: _late_models.LateGeneration) -> bool:
    """Whether anything this cancellation took on is owed by any reading.

    Two readings, because neither contains the other and an obligation either
    one counts is one nobody is coming back for once the issue has left this
    owner. What the ending lists is the branch, the ref, and the plan pull
    request -- including the one it can name and cannot prove it ever held.
    What the domain's own settled-ledger answer adds is a child receipt, which
    is none of those three, and a consumer ledger this binary could not type.

    It is the question a DISPATCH is decided by rather than the one a terminal
    is: an unlabeled owner is let past this guard into ordinary work only over
    a cycle that owes nothing at all, and the restart beside it authorizes a
    fresh cycle on exactly the same reading -- so no state falls between the
    two, and neither can hand an issue to a stage handler over an obligation
    the other was holding.
    """
    if _outstanding(generation):
        return True
    return not _restart.obligations_settled(generation)


def _persisted(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Make one step of this pass durable before the next one acts."""
    _late_state.write_late_generation(state, generation)
    gh.write_pinned_state(issue, state)


def _reported(
    gh: _client.GitHubClient,
    issue: Issue,
    generation: _late_models.LateGeneration,
    target: str,
) -> None:
    """Say on both sinks what this pass did to the held PR.

    Read back off the record rather than inferred from what GitHub said, for
    the reason every other obligation is: the entry is the only thing that
    carries both halves of an attempt that half-landed.
    """
    entry = _plan_pr_entry(generation, target)
    if entry is None:
        return
    _late_cleanup._emit_cleanup(
        gh, generation, entry, stage_name(gh.workflow_label(issue)),
    )
    if entry.resource_state != _late_models.LateResourceState.RECONCILED:
        log.warning(
            "issue=#%d could not close the PR its cancelled cycle held "
            "(%s); it is retried on every visit until it is",
            issue.number, target,
        )


def _plan_pr_entry(
    generation: _late_models.LateGeneration, target: str,
) -> _late_models.LateResource | None:
    """The ledger entry this pass just wrote for the held PR.

    None where the update could not be applied at all, which the recording
    helper already logged: there is nothing to report about an obligation the
    record does not carry.
    """
    for entry in generation.resources:
        if entry.kind == _PLAN_PR and entry.target == target:
            return entry
    return None
