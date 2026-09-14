# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a tick's pollable issues become handler calls.

Everything between "the repo has open issues" and "one `_handle_<stage>` is
running" lives here, because the decisions are one chain and each link is only
safe given the one before it.

The chain starts with the hard-skip filter. `backlog` / `paused` park an issue
outside the state machine entirely, and the filter runs twice on purpose: once
in `_classify_pollable_issue` so a parked issue never reaches the partition,
and once in `_process_issue` so a directly dispatched one is still refused.
Dropping it early is not an optimization -- a parked issue carries no workflow
label, so leaving it in would fold it into the family bucket and flip that
bucket cap-counted, reserving the only per-repo slot under the default
`parallel_limit=1` and starving every fan-out issue behind a hold nobody is
working on.

The partition is the concurrency contract. Family-aware labels (`decomposing`
/ `blocked` / `umbrella`) and the unlabeled-pickup `None` are cross-issue
writers -- a parent's recovery seeds `parent_number` on a child whose own
handler would clobber the same pinned-state comment -- so they collect into one
bucket that drains sequentially, and everything else fans out. A label read
that raises is answered `(False, None)`, which routes that issue into the
family bucket rather than dropping it: the conservative side of an unreadable
label is the serialized one, where `_process_issue`'s per-issue exception
isolation picks up a sustained failure.

Cap exemption is what keeps the serialization from deadlocking. A bucket whose
every label is a no-agent, no-worktree handler (`_CAP_EXEMPT_FAMILY_LABELS`)
skips the per-repo and global caps, because a `blocked` parent polling its own
children would otherwise wait on the only slot those children need to finish.
Closed fan-out issues are exempt for the same reason at the other end: their
handler is a terminal finalize with no spawn, so it must not queue behind
active agent work.

A closed issue on the two cleanup-swept decomposition labels is the one case
where the label does NOT name the handler. `decomposing` and `umbrella` reach
the sweep yielding them only so their generation ledger can be settled, and
handing one to the stage handler its label names would spawn the decomposer on
an issue a human closed, or walk a dependency graph and activate children under
it. So the cleanup route is taken FIRST, ahead of the table and ahead of the
pinned-state guards, and the issue never reaches either.

Past that route, one read of the issue's own pinned comment answers six
questions that can stop the tick outright: a live late adjudication the label
was moved out from under, a child of a split whose snapshot the remote no
longer has, an owner whose cancelled cycle is still holding something on the
remote, the restart an operator authorizes by taking that cycle's `rejected`
back off, an issue that has spent every agent run it is allowed, and an
unlabeled issue that already carries a pinned comment. Most of them are asked
here rather than in a stage precisely because the issues they are about are
ones nothing below would touch safely -- a consumer that
ended wears `done` or `rejected`, reopening leaves the label where it was, and
both are terminal no-ops; a reopened cancelled owner wears a label whose
handler would spawn the decomposer or activate children over a cycle a close
already ended; a restart's own issue wears either no label at all, where the
handler would greet it as new and mint a second pinned comment, or the target
label it applied a moment before a crash, where the cancelled-cycle guard
would hand it `rejected` again; and an issue whose workflow label a human took
off reaches the pickup handler, which GREETS one -- minting a second pinned
comment that the first shadows from the moment it is written, while the
finished workflow in that first one goes on deciding.

That is also why such an issue is partitioned as FAN-OUT rather than into the
family bucket, despite wearing a family-aware label. The bucket's exemption is
all-or-nothing, so a closed owner sharing it with an open `decomposing` issue
would be cap-counted and skipped under saturated caps -- cleanup starved by
work it has nothing to do with. As fan-out it is submitted cap-exempt on its
own, and it does not need the family mutex: what serializes a parent against
its children is a mutex over handlers that ACTIVATE, and this one reads its
consumers and writes only issues it has proved terminal. The fan-out lane
already runs those consumers' own closed-sweep finalizers concurrently, so the
bucket would not have protected against them either.

The spent lifetime agent-run ledger is on that list for the opposite reason:
the issue it is about is one EVERY stage below would touch, and each in a way
that is right about some other park. An `awaiting_human` flag routes one stage
to a resume on the next reply and another to a hold waiting on words, and
neither is an answer to an issue that has run out of the agent runs it may
ever spend. So the park is held once, ahead of the table, rather than taught
to thirteen handlers -- and it is the one question here that steps aside for
work that has ENDED, since what an ending reaches below is a terminal that
ends the issue rather than a road that spends anything on it. A closed ISSUE
is the half the object in hand shows; a recorded PULL REQUEST that has merged
or been closed is the half it cannot, and is read here for that reason. What
that second reading means depends on the LABEL the tick was routed on: on
`workflow:implementing` a settled `discussion` plan is the agreement that
licensed the build rather than the build ending, so it is carved out there and
nowhere else -- `discussion` itself drains the same pull request through its
own terminal.

Only issue NUMBERS cross the thread boundary. PyGithub's `Issue` and the
`GitHubClient` / `Repository` / `Requester` chain behind it hold mutable
per-request state that is not documented thread-safe, so `_refetch_and_process`
mints a per-worker client and refetches against it -- every in-flight call is
then the sole consumer of its own requester.

That refetch is also what makes the cleanup classification safe to act on,
which is why the sequential path takes one of its own. A closed owner is
routed to the sweep on a reading taken during enumeration, and the sweep's
re-read of the close is only a question if the issue was read again since -- so
`_process_polled_issue` classifies and refetches on the caller's thread rather
than dispatching the object the poll yielded.

The handler for a label is reached by importing the module
`_STAGE_HANDLER_TARGETS` pairs it with, at call time: twelve of them are
conflicts, decomposition, discussion, documenting, fixing, implementing,
question, validating, and in_review owners under `workflow/stages/`, and the
thirteenth is the `pickup` sibling an unlabeled issue starts on -- and the stage
tree imports this subpackage, so binding any of them
at module scope would point that edge back at itself. Every entry names the
owner its handler lives on, so the patch that intercepts a dispatch is the one
against whichever module the table names.
"""
from __future__ import annotations

import contextlib
import functools
import importlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.base_sync import refresh_selection as _refresh_selection
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import (
    _ISSUE_STATE_CLOSED,
    CLEANUP_ROUTE_LABELS,
    CLEANUP_SWEEP_LABELS,
    issue_is_closed,
)
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.analytics import recording
from orchestrator.scheduler import IssueScheduler
from orchestrator.workflow.engine import (
    observations,
    run_grant as _run_grant,
    run_limit as _run_limit,
    terminals as _terminals,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

# Every isolated per-issue failure reports through one line so an operator
# grepping a tick's log sees the same shape whether the issue was dispatched
# sequentially, refetched on a worker, or drained from the family bucket.
_PROCESSING_FAILED_LOG = "repo=%s issue=#%s processing failed"

# The three ways a cleanup observation goes unspent, said in the one line that
# holds it, so an operator watching a closed owner sit still for a tick can
# tell a worker holding the issue from a pass that reached it and broke, and
# either from a pass that ran the whole ending, left it owed, and could not
# get the issue back under a label a later tick would find it by.
_HELD_BY_A_WORKER = "a worker is already running it"
_PASS_FAILED = "the pass that took it failed before marking anything"
_ENDING_UNFINISHED = "the ending it ran is owed under no label the sweep asks for"

# What a pull request reads as once it is over, whichever way it ended. The
# run-limit hold asks for both together, because what it is deciding is
# whether the work is finished rather than which ending finished it.
_ENDED_PR_STATES = frozenset((_terminals._MERGED, _ISSUE_STATE_CLOSED))

_FAMILY_AWARE_LABELS = frozenset((
    WorkflowLabel.DECOMPOSING, WorkflowLabel.BLOCKED, WorkflowLabel.UMBRELLA,
))

_CAP_EXEMPT_FAMILY_LABELS = frozenset((
    WorkflowLabel.BLOCKED, WorkflowLabel.UMBRELLA,
))

# Every label whose CLOSED issues the sweep yields for cleanup only. Kept as a
# set of the members the sweep publishes so the two cannot drift: a label
# queried there and missing here is a closed issue dispatched to the stage
# handler its label names, which is the one thing the cleanup route exists to
# prevent.
_CLEANUP_ROUTE_LABELS = frozenset(CLEANUP_ROUTE_LABELS)

# The narrower pair, and the one question that is about an OPEN issue: the two
# an adjudication actually RUNS under are the two where a close landing after
# the poll changes which handler this tick calls, so the sequential path pays a
# refetch for them. The recovery labels beside them are only ever asked about
# while closed -- an open `ready` issue is not an ending in progress -- so
# nothing there earns that request.
_CLEANUP_SWEEP_LABELS = frozenset(CLEANUP_SWEEP_LABELS)

_FAMILY_BUCKET_ISSUE: int = 0

_CONFLICTS_PACKAGE = "orchestrator.workflow.stages.conflicts"
_DECOMPOSITION_PACKAGE = "orchestrator.workflow.stages.decomposition"
_LATE_CANCELLATION_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_cancellation"
_LATE_RELABEL_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_relabel"
_LATE_RESTART_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_restart"
_LATE_REUSE_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_reuse"
_DISCUSSION_PACKAGE = "orchestrator.workflow.stages.discussion"
_DOCUMENTING_PACKAGE = "orchestrator.workflow.stages.documenting"
_FIXING_PACKAGE = "orchestrator.workflow.stages.fixing"
_IMPLEMENTING_PACKAGE = "orchestrator.workflow.stages.implementing"
_LATE_RECONCILE_OWNER = f"{_IMPLEMENTING_PACKAGE}.late_reconcile"

# The owner that tells the `discussion` stage's plan from a delivery, read
# through rather than re-derived so what counts as a plan is decided once.
_IMPLEMENTING_HANDLER_OWNER = f"{_IMPLEMENTING_PACKAGE}.handler"
_IN_REVIEW_PACKAGE = "orchestrator.workflow.stages.in_review"
_QUESTION_PACKAGE = "orchestrator.workflow.stages.question"
_VALIDATING_PACKAGE = "orchestrator.workflow.stages.validating"

_TERMINAL_LABELS = (WorkflowLabel.DONE, WorkflowLabel.REJECTED)

# The one handler a label does not choose. It is reached by being closed on a
# cleanup-swept label instead, and it is deliberately not in the table below:
# an entry there would make it the handler for those labels open or closed.
_CLEANUP_SWEEP_TARGET = (
    f"{_DECOMPOSITION_PACKAGE}.late_sweep", "_handle_closed_owner_cleanup",
)

# Keyed by the member rather than the label string so the table cannot drift
# from the vocabulary it routes: a relabeled state is a lookup miss here, and a
# lookup miss is an issue nobody handles.
_STAGE_HANDLER_TARGETS: Mapping[str | None, tuple[str, str]] = MappingProxyType({
    None: ("orchestrator.workflow.engine.pickup", "_handle_pickup"),
    WorkflowLabel.DECOMPOSING: (f"{_DECOMPOSITION_PACKAGE}.run", "_handle_decomposing"),
    WorkflowLabel.READY: (f"{_DECOMPOSITION_PACKAGE}.blocked", "_handle_ready"),
    WorkflowLabel.BLOCKED: (f"{_DECOMPOSITION_PACKAGE}.blocked", "_handle_blocked"),
    WorkflowLabel.UMBRELLA: (f"{_DECOMPOSITION_PACKAGE}.umbrella", "_handle_umbrella"),
    WorkflowLabel.IMPLEMENTING: (f"{_IMPLEMENTING_PACKAGE}.handler", "_handle_implementing"),
    WorkflowLabel.DOCUMENTING: (f"{_DOCUMENTING_PACKAGE}.handler", "_handle_documenting"),
    WorkflowLabel.VALIDATING: (f"{_VALIDATING_PACKAGE}.handler", "_handle_validating"),
    WorkflowLabel.IN_REVIEW: (f"{_IN_REVIEW_PACKAGE}.handler", "_handle_in_review"),
    WorkflowLabel.FIXING: (f"{_FIXING_PACKAGE}.handler", "_handle_fixing"),
    WorkflowLabel.RESOLVING_CONFLICT: (
        f"{_CONFLICTS_PACKAGE}.handler", "_handle_resolving_conflict",
    ),
    WorkflowLabel.QUESTION: (f"{_QUESTION_PACKAGE}.handler", "_handle_question"),
    WorkflowLabel.DISCUSSION: (f"{_DISCUSSION_PACKAGE}.handler", "_handle_discussion"),
})


@dataclass(frozen=True)
class _PollReading:
    """What the poll established about one issue, carried to its worker.

    Both halves are readings the ENUMERATION took, and neither is one the
    worker can take again: it mints its own client and refetches the issue, so
    a human who reopens one in that window would have the fresh object answer
    differently. `cleanup_only` is the route a closed late owner was
    classified into and may not be re-derived out of; `closed` is the same
    reading for an issue whose label names an ordinary terminal instead, where
    the guard that ends a live cycle is what reads it.
    """

    cleanup_only: bool = False
    closed: bool = False


# What an ordinary open issue carries, which is nothing at all.
_POLLED_OPEN = _PollReading()


def _pinned_state_refuses(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    label: str | None,
    *,
    observed_closed: bool = False,
) -> bool:
    """True when what this issue's own pinned comment records stops the tick.

    ONE read, seven questions, because the read is what costs -- a comment
    walk per labelled issue per tick, on top of the one that issue's own
    handler makes.

    The first is a restart an operator has authorized. A settled cancellation
    whose `rejected` has been taken off is a fresh cycle waiting to be
    projected, and so is one this orchestrator already began and left
    half-applied -- a restart writes its target label before it retires the
    marker, so a tick that crashed in between finds a live-looking label over
    a record that still says cancelled.

    The second is a live late adjudication. An oversized committed candidate is
    adjudicated under ``workflow:decomposing``, and while that question is open
    the label is not a state anything else may set. A hand relabel cannot be
    refused where it is written -- the orchestrator never sees that write -- so
    it is caught here, the one place a label becomes a handler call: the issue
    is put back and left for the next tick rather than dispatched to whichever
    stage the new label named, which for ``ready`` or ``implementing`` would
    publish a candidate nobody adjudicated.

    The third is a child of a split whose snapshot has since been reclaimed.
    That one has to be asked HERE rather than inside a stage, because the issue
    it is about is one the dispatcher would otherwise have nothing to do with:
    a consumer that ended wears ``done`` or ``rejected``, reopening leaves the
    label where it was, and both are terminal no-ops below. Asking before the
    table also means a relabel straight to another stage cannot route around
    it. It costs nothing extra on the wire in the steady state -- the guard
    asks this host before it asks the remote.

    The fourth is an owner whose cycle a close already ended and whose cleanup
    has not finished. Cancellation is irreversible within a cycle, so a human
    who reopens the issue gets a fresh one -- but not while the old one still
    holds a branch, a ref, or a held pull request, because both labels an
    adjudication can be wearing name a handler that would act on the issue
    rather than settle it.

    The fifth is an unlabeled issue this orchestrator has already met. What an
    unlabeled issue reaches is the pickup handler, which GREETS one, and a
    pinned comment is the record of having been greeted -- so it is asked LAST
    and answered off the read alone. The one unlabeled issue it must not stop
    is the restart, which is answered four questions above it and returns
    before this one is reached.

    The restart and the unfinished cleanup are asked FIRST, because they are
    the ones that have to RUN rather than merely answer, and the three below
    them can refuse indefinitely. The reuse guard HOLDS a dispatch -- writing
    nothing, on purpose -- for as long as an ancestor's ref cannot be asked
    about, and an owner of its own cancelled cycle nested under such an
    ancestor would spend that entire outage never reconciling its own held PR,
    branch, or ref. Nothing is lost by the order: neither a cancelled cycle
    nor a restart mid-transaction starts any work, so neither question below
    is about anything either is going to do, and both are asked again on the
    tick after the ending or the fresh cycle is written.

    The restart comes ahead of the cancellation refusal within that pair, and
    only one of the two can be about a given issue: an issue with a marker
    standing, or with the authorizing gesture on its surface, is one the
    refusal would answer by handing it `rejected` again -- undoing the
    authorization the restart is halfway through honoring.

    The adjudication and the reclaimed snapshot step aside for the label the
    adjudication actually sits on, which is where every one of its own ticks
    is spent, and where an ancestor's snapshot is not what the issue is
    working from -- but only once the record PROVES the adjudication is this
    issue's own, and never past the reading that asks whether that record can
    be acted on at all. The label alone proves nothing: a child of a split
    closed while it was being decomposed comes back with ``decomposing`` exactly
    where it was and no generation at all, and its ancestor's ref may well
    have been reclaimed while it was closed. Waving that through on the label
    would spawn the decomposer against the reuse instructions in its body,
    naming a ref that is gone. So the read is taken first and the label is
    answered out of it. Imported at call time like the handlers below, since
    the stage tree imports this module.

    The last of them is the size gate's own unfinished business, and it is
    asked here for the reason the others are: it belongs to no one stage. A
    pair frozen for a pull request the remote already carries is durable and
    the count that follows it is not, so a tick that died in between leaves a
    record naming both commits with no number on it -- and the handler about
    to run would spawn a reviewer, resume a developer, or read a pull request
    still standing where the gate froze it, while the record goes on freezing
    the branch out of the base refresh. Taking the reading first is what makes
    the freeze a resumable step rather than a window; scoped by the record's
    own source stage, so it is answered on the stage it was entered on and
    nowhere else.

    The spent agent-run ledger is asked between those two groups, and the
    place is the whole point of it. Behind the pair that RUN, because a
    cancelled cycle still holding a branch and a restart an operator
    authorized are endings rather than work, and a park that outranked them
    would leave both owed for as long as the issue is stopped -- which here is
    for good. Ahead of everything else, because every road below is a stage's,
    and a stage reading `awaiting_human` answers it with the park it was
    written against: a resume on the next reply, a hold waiting on guidance, a
    classifier that refuses a command carrying none. None of those is an
    answer to an issue that has spent every run it may ever have.
    """
    late_relabel = importlib.import_module(_LATE_RELABEL_OWNER)
    state = late_relabel._dispatch_state(gh, issue)
    if state is None:
        return True
    late_cancellation = importlib.import_module(_LATE_CANCELLATION_OWNER)
    if observed_closed:
        # The poll read this issue closed and the worker has refetched it
        # since. A reopen in that window would leave the fresh object saying
        # open with a live cycle under it, so the reading is applied here
        # rather than re-derived from the object the guard is about to read.
        late_cancellation._mark_observed_close(gh, issue, state)
    if _cycle_stops_the_tick(gh, spec, issue, label, state):
        return True
    if _run_limit_holds_the_tick(
        gh, spec, issue, state,
        _spent_work_has_ended(gh, issue, state, label, observed_closed),
    ):
        return True
    if label == WorkflowLabel.DECOMPOSING and late_relabel._adjudicating(state):
        # The adjudication steps past the guards below because they are the
        # other stages' -- but not past the one that asks whether its own
        # record can be read. The publication group is the whole of what this
        # mode settles by and the one thing it cannot re-derive, so a partial
        # one is refused here rather than read as a candidate nothing had
        # published and routed back to `implementing` with the evidence
        # retired behind it.
        return importlib.import_module(
            _LATE_RECONCILE_OWNER,
        )._reconciles_published_work(gh, spec, issue, label, state)
    return _record_stops_the_tick(gh, spec, issue, label, state)


def _run_limit_holds_the_tick(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    ended: bool,
) -> bool:
    """Whether this issue has spent every agent run it is allowed to.

    True is the whole tick: no handler is called, so nothing is spawned,
    nothing is relabelled, and everything the issue was carrying when it ran
    out -- a locked session, a pull request, a branch, a manifest, a
    generation's record -- is left exactly where the park found it. A lifetime
    total is spent once and no clock returns it, so unlike every other park in
    this repository there is nothing to wait for here and no road below that
    could be right about the wait.

    Held once, here, rather than taught to each stage. The park is a claim
    about the ISSUE and not about any stage's road, while `awaiting_human`
    means something different on every one of those roads: `implementing`
    resumes a locked developer on the next trusted reply, the conversation
    stages read one as the answer their agent asked for, and the spent-budget
    holds wait on a command that buys another attempt. Each is right about the
    park it was written against; none of them buys back a run.

    Work that has ENDED is let past, and that exemption is the reason this is
    a question rather than a filter above the partition. What an ending
    reaches below is a terminal -- the merged, rejected, and human-closed
    finalizers, and the cleanup sweep that settles a generation ledger -- and
    every one of those ENDS the issue rather than spending anything on it.
    Refusing them would leave a spent issue permanently mid-ending: a pull
    request nothing finalizes, a receipt nobody posts, a ledger no sweep
    settles. And "permanently" is meant: a lifetime total buys no clock, so
    an issue held here is held until a human arrives, and an ending it never
    reaches is one nothing else will.

    `ended` is that question already answered, handed in rather than asked
    here: `_spent_work_has_ended` beside this owns the two facts it is read
    off and the order they cost anything in. What the answer buys is the tick
    reaching the stage its label names, whose own terminal does the ending --
    and nothing it lets through can spend a run, since the circuit every
    launch goes through reads the same ledger and refuses on it.

    The one thing that lifts it is asked here too, and asked nowhere else:
    a trusted `/orchestrator add-agent-runs N` widening what this issue may
    spend (`run_grant.py`). It belongs to the hold rather than to a stage for
    the same reason the park does -- the ledger is spent by every role at
    every stage, so no one handler is the place a human would say it -- and a
    command that lifts the park lets the tick go on to the stage its label
    names, which is the run the human just paid for.

    It is asked BEHIND the ending, and the order is the point: reading that
    command MUTATES -- it widens the allowance, clears this park, consumes
    the batch it read, posts an acknowledgement and records a phase. None of
    that is anything work a human has already merged or closed should earn.
    Asked first, a terminal issue would buy runs it will never spend, and a
    malformed request over one would collect a refusal receipt on a thread
    about to be finalized.

    The sentence the park owes the thread is replayed before the hold
    returns, because this is the road that strands it: nothing below runs, so
    a notice a refused post or an unreadable thread left owed would be owed
    for as long as the issue is parked. The refusal is recorded either way --
    a park nobody can see going on refusing is one an operator reads as a
    workflow that stopped for no reason.
    """
    if not _run_limit._park_stands(state) or ended:
        return False
    if _run_grant._lifts_the_park(gh, issue, state):
        return False
    log.info(
        "repo=%s issue=#%s has spent every agent run it is allowed; holding "
        "it for a human rather than dispatching it",
        spec.slug, issue.number,
    )
    _run_limit._replay_owed_notice(gh, issue, state)
    _run_limit._emit_phase(gh, issue, _run_limit.RunLimitPhase.STANDING)
    return True


def _spent_work_has_ended(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    label: str | None,
    observed_closed: bool,
) -> bool:
    """Whether the work a spent ledger would hold is already over.

    Asked BEHIND the park, and that is what keeps it cheap: the pull-request
    half below is a request, and an issue with runs left to spend has no hold
    for an ending to lift. So a tick that is not parked costs nothing here.

    The free fact comes first. A closed ISSUE is the object already in hand,
    and the poll's own reading counts beside it, since an issue closed when it
    was enumerated is one this tick was routed on the strength of. The PULL
    REQUEST behind it is the half the object cannot show.
    """
    if not _run_limit._park_stands(state):
        return False
    if observed_closed or issue_is_closed(issue):
        return True
    return _recorded_pr_has_ended(gh, issue, state, label)


def _recorded_pr_has_ended(
    gh: GitHubClient, issue: Issue, state: PinnedState, label: str | None,
) -> bool:
    """Whether the pull request this issue records has merged or been closed.

    The half of "is this work over" the issue's own flag cannot answer, and
    the reason the hold above asks a request at all: a merge leaves the issue
    open until a stage terminal reads it, and a close nobody merged leaves it
    open for good, so a spent issue behind either would sit on the park
    forever with the ending it is owed unreachable.

    Read fail-OPEN through the terminals' own guarded reading, which is where
    the shape of that read lives: a fetched pull request is lazy, so the
    lookup asks GitHub nothing and the request that can fail is the attribute
    access behind it. A reading that did not come back says nothing about
    whether the work is over, and answering True on one would lift a park on
    a request that failed -- so it leaves the hold exactly where it was and
    the next poll asks again.

    The `discussion` stage's PLAN is not an ending ON ONE STAGE, and that is
    why the LABEL decides it rather than the record alone. An issue relabelled
    out of `discussion` arrives on `workflow:implementing` still recording the
    plan's number, and merging that plan is an agreement -- the humans read a
    design and said build it -- so the stage that would receive this tick
    carries on rather than finalizing. Answered as an ending there, the hold
    would step aside every poll for an issue no terminal is going to finalize,
    and say in the log that it was letting one through.

    Everywhere else the same pull request is exactly the ending it looks like.
    `discussion` itself drains a settled plan through its own terminal, so a
    carve-out applied to that label stops the one stage the plan belongs to
    from ever ending -- and behind a permanent park there is no later tick to
    do it instead.

    Told apart off the SAME reading the state came from, through the owner
    that decides what a plan is, so the classification and the ending are
    about one snapshot rather than two.

    What a True buys is the tick reaching the stage the label names, whose
    own terminal does the ending. Nothing here finalizes anything itself.
    """
    linked = _terminals._linked_pull_request(
        gh, issue, state, "checking whether its work has already ended",
    )
    if not linked.was_read or linked.state not in _ENDED_PR_STATES:
        return False
    if label == WorkflowLabel.IMPLEMENTING:
        implementing = importlib.import_module(_IMPLEMENTING_HANDLER_OWNER)
        if implementing._recorded_pr_is_the_plan(state, linked.head):
            return False
    log.info(
        "issue=#%s has spent every agent run it is allowed and records a pull "
        "request that has merged or been closed; letting the tick reach the "
        "terminal that ends it",
        issue.number,
    )
    return True


def _record_stops_the_tick(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    label: str | None,
    state,
) -> bool:
    """What the read answers once a live cycle has been established.

    Split from the questions above it because those decide whether there is a
    cycle to ask about at all: a cancelled or reclaimed record stops the tick
    whatever the label says, and only past them does the label mean what it
    reads. Each stage owner below is imported at call time for the reason the
    ones above are -- the stage tree imports this module back.

    An auto-rebase anchor the base refresh has not answered is asked second,
    ahead of the reconciliation, and it is the one question here that is not
    a late record's. The refresh settles an interrupted rebase before any
    handler runs, but a pull request that would not read returns before its
    recovery does -- and the handler this dispatcher is about to reach would
    spawn an agent over a replay no push has published. Whether that holds
    the tick, and the freezes and parks under which holding it would be a
    deadlock instead, are the refresh selection's to say; it sits below this
    layer, so it is bound at module scope.
    """
    late_relabel = importlib.import_module(_LATE_RELABEL_OWNER)
    if late_relabel._holds_the_label(gh, issue, state):
        log.warning(
            "repo=%s issue=#%s was relabelled %r while its committed candidate "
            "was under adjudication; not dispatching it",
            spec.slug, issue.number, label,
        )
        return True
    if _refresh_selection._recovery_holds_dispatch(
        issue, label, state,
        _worktree_paths._worktree_path(spec, issue.number),
    ):
        log.info(
            "repo=%s issue=#%s carries an auto-rebase anchor the base refresh "
            "has not answered yet; holding the %r handler so no agent runs "
            "over an unpublished replay",
            spec.slug, issue.number, label,
        )
        return True
    late_reconcile = importlib.import_module(_LATE_RECONCILE_OWNER)
    if late_reconcile._reconciles_published_work(
        gh, spec, issue, label, state,
    ):
        return True
    late_reuse = importlib.import_module(_LATE_REUSE_OWNER)
    return (
        late_reuse._refuses_reuse(gh, spec, issue, state)
        or _greeted_already(spec, issue, label, state)
    )


def _greeted_already(
    spec: config.RepoSpec,
    issue: Issue,
    label: str | None,
    state: PinnedState,
) -> bool:
    """True when an unlabeled issue is one this orchestrator has already met.

    What an unlabeled issue reaches is the pickup handler, and what pickup
    does is GREET one: it posts the "picking this up" comment, baselines the
    drift hash over a thread it assumes nobody has worked, and mints the
    issue's pinned comment. Every one of those is a first-contact act.

    An issue that already carries a pinned comment has been through it, so
    greeting it again writes a SECOND one -- and `read_pinned_state` answers
    with the first authenticated comment it finds, so the new record is
    invisible from the moment it is written while the old one goes on
    deciding. What the old one carries is a finished workflow: a `pr_number`
    and a branch nothing will reconcile, a watermark over comments the fresh
    greeting has not read, a terminal somebody reached. Two records, one
    unreachable, is worse than either.

    So an issue whose workflow label a human took off is left exactly where
    they left it, and said so once a tick. The way back into the workflow is
    applying a workflow label, which is the same way an outsider's issue is
    driven by hand. The one unlabeled issue this does NOT stop is the restart,
    which is answered two guards above and never reaches here.
    """
    if label is not None or state.comment_id is None:
        return False
    log.info(
        "repo=%s issue=#%s carries a pinned comment and no workflow label; "
        "leaving it where it was rather than greeting it a second time",
        spec.slug, issue.number,
    )
    return True


def _cycle_stops_the_tick(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    label: str | None,
    state: PinnedState,
) -> bool:
    """Whether a late cycle's own business is the whole of this dispatch.

    The two guards that RUN rather than merely answer, kept together because
    only one of them can be about a given issue and the order between them is
    the whole reason: a restart applies its target label before it retires its
    marker, so a tick that crashed in between finds a live-looking label over
    a record that still says cancelled -- and the refusal below would answer
    that by handing the issue `rejected` again, undoing the authorization the
    restart is halfway through honoring.

    Imported at call time like every other stage owner this module reaches,
    since the stage tree imports this module.
    """
    late_restart = importlib.import_module(_LATE_RESTART_OWNER)
    if late_restart._restarts(gh, spec, issue, label, state):
        return True
    late_cancellation = importlib.import_module(_LATE_CANCELLATION_OWNER)
    return late_cancellation._refuses_cancelled(
        gh, spec, issue, label, state,
    )


def _parked_past_the_mark(spec: config.RepoSpec, issue: Issue) -> bool:
    """Whether a control label the closed reading was let past applies again.

    `backlog` / `paused` park an issue outside the state machine, and the one
    thing that may still happen under one is recording a close: an observed
    close ends a late cycle irreversibly, the pass that would record it is the
    one the park would have dropped, and a mark deferred is a mark lost. That
    is the whole of the waiver -- the mark is behind this, and the ending it
    earns is deferred by the same label wherever it is entered.

    So everything past the mark is parked again, and it has to be by asking
    rather than by inference: a record with no late cycle marks nothing at
    all, and the guard above answers `False` for one, which would otherwise
    put a parked issue in front of the very handler the label exists to stop.

    Costs no request: the labels are already on the object this was handed.
    """
    skip_label = hard_skip_control_label(issue)
    if skip_label is None:
        return False
    log.info(
        "repo=%s issue=#%s has %r and owns no cycle a close would end; "
        "skipping everything the park defers",
        spec.slug, issue.number, skip_label,
    )
    return True


def _cleanup_sweep_only(issue: Issue, label: str | None) -> bool:
    """True when this issue is here for its ledger and nothing else.

    A closed issue on one of the four cleanup-routed labels reaches a tick
    only because the cleanup sweep asked for it, and what it is owed is a pass
    over its generation ledger. Its label still names a stage handler -- one
    spawns the decomposer, one walks a dependency graph and activates
    children, one hands the issue to a developer -- so the closed reading has
    to be taken before the label is, or the sweep would be resuming the
    workflow a human closed.
    """
    return label in _CLEANUP_ROUTE_LABELS and issue_is_closed(issue)


def _call_handler(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    target: tuple[str, str],
) -> None:
    """Import the module a target names and run the handler off it."""
    module_name, handler_name = target
    issue_handler = getattr(importlib.import_module(module_name), handler_name)
    issue_handler(gh, spec, issue)


def _route_issue_to_handler(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    label: str | None,
    *,
    reading: _PollReading = _POLLED_OPEN,
) -> None:
    """Dispatch one issue to its stage handler by workflow label.

    The module the table names is imported at call time and the handler read
    off it as an attribute, so the patch that intercepts a dispatch is the one
    against that module -- the stage's own handler owner.
    ``done`` / ``rejected`` are terminal no-ops; an unrecognized label is
    logged and left alone for a human. Timing and the ``stage_evaluation``
    analytics record stay in ``_process_issue``, which wraps this call in its
    try / except / finally.

    Two routes are taken ahead of the table. A closed issue on a cleanup-swept
    label goes to the sweep owner, because its label names a handler that would
    resume the workflow its close ended. And what the issue's own pinned
    comment records can stop the tick outright -- a restart an operator has
    authorized over a settled cancellation, a live adjudication the label was
    moved out from under, a snapshot this child was cut from and the remote no
    longer has, a cancelled cycle this owner has still to settle, or an
    unlabeled issue this orchestrator has already greeted once. The
    cleanup route comes first: that guard spends a pinned read to decide, and a
    closed owner is not dispatched on any of those answers.

    ``cleanup_only`` is that first route arriving as a decision rather than as
    a reading. It is set by the submit that a closed cleanup owner was
    classified into, and it BINDS: the worker refetches the issue after the
    classification, so a human who reopens one in that window would otherwise
    have the freshly-read label send it to the handler its cap-exempt submit
    was granted on the understanding it would never reach. What the sweep does
    with an issue that is open again is mark the cancellation the observed
    close already earned and stop there, leaving every external part of the
    ending to the guard that owns a reopened cancelled owner from the next
    tick.

    A control label the closed reading was let past is re-applied BEHIND the
    guard, because what that reading buys is the mark and nothing else: the
    park was waived so an observed close could be recorded before it was lost,
    and a record with no late cycle to mark has nothing to record -- so the
    stage handler below it would be the one reaction an operator's `paused`
    exists to prevent.
    """
    if reading.cleanup_only or _cleanup_sweep_only(issue, label):
        _call_handler(gh, spec, issue, _CLEANUP_SWEEP_TARGET)
        return
    if _pinned_state_refuses(
        gh, spec, issue, label, observed_closed=reading.closed,
    ):
        return
    if _parked_past_the_mark(spec, issue):
        return
    target = _STAGE_HANDLER_TARGETS.get(label)
    if target is not None:
        _call_handler(gh, spec, issue, target)
    elif label not in _TERMINAL_LABELS:
        log.warning(
            "repo=%s issue=#%s label=%r not implemented yet; leaving alone",
            spec.slug, issue.number, label,
        )


def _process_polled_issue(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue,
) -> None:
    """Dispatch one issue this thread polled and still holds.

    The sequential path's own entry, and what it adds over `_process_issue` is
    the classification the other two paths get on their way to a worker: an
    issue on a cleanup-swept label is refetched before anything routes it, and
    a CLOSED reading at poll time additionally BINDS it to the sweep.

    The refetch is the load-bearing half, and it is taken on both readings of
    the close rather than on one. The object in hand is the enumeration's,
    and the two labels this applies to are the two where the close decides
    which handler runs: an owner closed after the poll would otherwise reach
    the stage its label names on a stale open reading -- spawning the
    decomposer, or walking a dependency graph and activating children, on an
    issue a human just ended -- and an owner reopened after the poll would
    have a cleanup pass settle a ledger the live cycle is writing again, since
    the sweep's own close re-read would be re-reading the same stale object.

    The binding is the other half, and it is one-way for the reason the
    workers' is: a closed classification may not become an agent-spawning
    stage handler on the strength of a reopen this tick raced, while an issue
    that was open when it was polled has been classified as ordinary work all
    along and the freshly-read close is what sends it to the sweep.

    Refetched on the caller's own client rather than through
    `_refetch_and_process`: nothing here crosses a thread, so what that mints
    a per-worker client for does not apply, while the read it takes does.

    Hard-skipped issues are dropped here as the partition drops them, rather
    than inside `_process_issue`, so the classification this path takes is the
    same one the other two take.

    Which labels that applies to is `_cleanup_routed`'s question, and it is
    not the same one the partition asks: a closed issue is routed by any of
    the four cleanup labels, while only the two an adjudication runs under
    earn the refetch an OPEN issue costs.

    A latched close overrides the label as it does in the partition, and for
    the same reason: the reading it carries is one the reopen it survived took
    off the remote, so nothing this path could read would find it. It
    overrides the hard-skip filter with it -- an operator's park defers the
    external half of the ending, which is what the sweep does with a parked
    issue anyway, and never the mark. And the cleanup it routes to is wrapped
    in the same observation hold the worker paths use, because a pass that
    raises here marked nothing either.
    """
    issue_number = int(issue.number)
    latched = observations.close_observed(spec.slug, issue_number)
    skip, label = _classify_pollable_issue(gh, spec, issue)
    if skip and not latched:
        return
    closed = issue_is_closed(issue)
    if not latched and not _cleanup_routed(label, closed=closed):
        _polled_ordinary(gh, spec, issue, closed=closed)
        return
    if not latched and not closed:
        _polled_open_owner(gh, spec, issue_number)
        return
    # The refetch is INSIDE the hold, because it is the first thing a cleanup
    # spends and the likeliest thing to fail: a read that raised marked
    # nothing, and the reading this pass was taking would otherwise be gone.
    with _cleanup_observation(gh, spec, issue_number):
        _process_issue(
            gh, spec, gh.get_issue(issue_number),
            reading=_PollReading(cleanup_only=True, closed=True),
        )


def _cleanup_routed(label: str | None, *, closed: bool) -> bool:
    """Whether this tick's own path has to treat the issue as a cleanup.

    The two an adjudication RUNS under answer yes whatever the issue reads
    as, because the close is exactly what this path has no hand-off to take
    for it: an owner closed after the poll would otherwise reach the stage
    its label names on a stale open reading. The two an interrupted ending
    can be LEFT on answer yes only while closed -- an open `ready` issue is a
    developer's to pick up rather than an ending in progress, and refetching
    every one of them per tick would spend a request on a question nobody is
    asking.
    """
    if label in _CLEANUP_SWEEP_LABELS:
        return True
    return closed and label in _CLEANUP_ROUTE_LABELS


def _polled_open_owner(
    gh: GitHubClient, spec: config.RepoSpec, issue_number: int,
) -> None:
    """Refetch an owner the poll read OPEN, and dispatch what comes back.

    The refetch is the load-bearing half of this route: a cleanup-swept label
    decides which handler runs off the close, and this path has no hand-off
    to take that reading for it. So it is also where a close can first exist
    at all, which is why the dispatch is wrapped in the hold one earns.
    """
    refetched = gh.get_issue(issue_number)
    with _refetched_close(gh, spec, refetched, _POLLED_OPEN):
        _process_issue(gh, spec, refetched)


def _polled_ordinary(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    *,
    closed: bool,
) -> None:
    """Dispatch one polled issue whose label names its own handler.

    A CLOSED one carries the poll's reading and keeps it unless the pass
    spent it, for the reason the worker paths do: nothing latched it, this
    pass is what would have acted on it, and neither a raise nor a pinned
    read the guard could not take leaves anything behind. An open one carries
    nothing and has nothing to keep.
    """
    if not closed:
        _process_issue(gh, spec, issue)
        return
    with _closed_reading(gh, spec, int(issue.number)):
        _process_issue(gh, spec, issue, reading=_PollReading(closed=True))


def _process_issue(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    *,
    reading: _PollReading = _POLLED_OPEN,
) -> None:
    # Postponed-task hold: applying `backlog` (or `paused`) parks the issue
    # outside the state machine entirely until the label is removed, so the
    # orchestrator never decomposes, spawns an agent, or otherwise reacts
    # while the operator is using the label as a "not yet" signal. Hard-skips
    # are NOT counted as a stage evaluation: no handler runs and there is
    # nothing to time.
    label = gh.workflow_label(issue)
    if _hard_skipped(spec, issue, label, reading):
        return
    log.info("repo=%s issue=#%s label=%r", spec.slug, issue.number, label)
    # Time the handler dispatch and append a single `stage_evaluation`
    # analytics record on exit. `evaluation_result` flips to "error" inside the
    # except clause so an unhandled exception still produces a timing
    # record before propagating -- the tick loop's per-issue try/except
    # already logs and isolates the failure, so re-raising here keeps
    # the existing dispatch / exception contract intact. The append
    # itself is internally hardened against OSError; an analytics
    # misconfiguration cannot stop the per-issue tick from advancing.
    start = time.monotonic()
    evaluation_result = "ok"
    try:
        # Advertised for the whole dispatch, so a close another thread
        # observes while this one is acting is not dropped again out from
        # under the barriers that read it. Those barriers stand immediately
        # before a push and the publications they guard carry no late cycle,
        # which is the one thing a poll drops a reading on. The drop is
        # postponed rather than refused: `observations` takes it again as the
        # window closes.
        with observations.publishing(spec.slug, issue.number):
            _route_issue_to_handler(gh, spec, issue, label, reading=reading)
    except Exception:
        evaluation_result = "error"
        raise
    finally:
        duration_s = round(time.monotonic() - start, 3)
        recording.record_stage_evaluation(
            repo=getattr(gh, "_repo_slug", None) or "",
            issue=issue.number,
            stage=stage_name(label),
            duration_s=duration_s,
            result=evaluation_result,
        )


@dataclass(frozen=True)
class _PollablePartition:
    """Family / fanout split of one repo's pollable issues for a single tick.

    ``family_numbers`` and ``family_labels`` are index-aligned so the
    cap-exempt decision (`_family_bucket_cap_exempt`) can read each
    family-aware issue's workflow label. ``fanout_closed`` is the subset of
    ``fanout_numbers`` whose issue is already closed -- a cheap terminal
    finalize, or a cleanup pass over a closed owner's ledger, and neither
    spawns, so both are submitted cap-exempt.
    """
    family_numbers: list[int]
    family_labels: list[str | None]
    fanout_numbers: list[int]
    fanout_closed: set[int]
    cleanup_numbers: set[int] = field(default_factory=set)


@dataclass
class _PollablePartitionBuilder:
    """Sorts one tick's issues, with the held observations overriding it.

    ``deferred`` is the set an earlier tick observed closed and could hand to
    no worker, and it decides this issue's route on its own -- ahead of the
    label, ahead of the close, and ahead of every filter that runs before this
    builder, because the reading those all come from is exactly what a reopen,
    a park, or a relabel in the meantime has taken away. An issue in it goes
    where a closed owner goes: fan-out, cap-exempt, and cleanup-only. What
    the sweep does with one that reads open again is mark the cancellation
    the observed close already earned and stop there, which is safe on any
    label and a no-op for an issue carrying no late cycle at all.
    """

    family_numbers: list[int] = field(default_factory=list)
    family_labels: list[str | None] = field(default_factory=list)
    fanout_numbers: list[int] = field(default_factory=list)
    fanout_closed: set[int] = field(default_factory=set)
    cleanup_numbers: set[int] = field(default_factory=set)
    deferred: frozenset[int] = frozenset()

    yielded: set[int] = field(default_factory=set)

    def owed(self, issue_number: int) -> bool:
        """Whether an earlier poll's held observation decides this route."""
        return issue_number in self.deferred

    def add(self, issue_number: int, label: str | None, closed: bool) -> None:
        owed = self.owed(issue_number)
        self.yielded.add(issue_number)
        if not owed and _drains_in_family_bucket(label, closed):
            self.family_numbers.append(issue_number)
            self.family_labels.append(label)
            return
        self.fanout_numbers.append(issue_number)
        if closed or owed:
            self.fanout_closed.add(issue_number)
        if owed or (closed and label in _CLEANUP_ROUTE_LABELS):
            self.cleanup_numbers.add(issue_number)

    def add_unyielded(self) -> None:
        """Add every held observation this enumeration never reached.

        What the enumeration yields is decided by the labels the closed sweep
        queries, so a human who moves the label off one of them -- or closes
        the issue on a label the sweep does not query at all -- makes the
        owner unreachable. The observation is older than any of that and is
        not lost with it: the issue is added by NUMBER, on the strength of the
        reading alone, and routed exactly where a closed owner goes.
        """
        for owed in sorted(self.deferred - self.yielded):
            self.add(owed, None, True)

    def build(self) -> _PollablePartition:
        return _PollablePartition(
            self.family_numbers,
            self.family_labels,
            self.fanout_numbers,
            self.fanout_closed,
            self.cleanup_numbers,
        )


def _drains_in_family_bucket(label: str | None, closed: bool) -> bool:
    """Whether this issue belongs in the serialized, all-or-nothing bucket.

    Every family-aware label does, with one exception: a CLOSED issue on a
    cleanup-swept label runs the sweep rather than the stage its label names,
    and the sweep neither spawns nor activates. Leaving it in the bucket would
    tie its exemption to whatever else landed there -- one open `decomposing`
    issue and the whole bucket is cap-counted, so a repository at its cap
    stops reclaiming refs until the decomposer is idle.
    """
    if closed and label in _CLEANUP_ROUTE_LABELS:
        return False
    return label is None or label in _FAMILY_AWARE_LABELS


def _read_issue_routing(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue,
) -> tuple[bool, str | None]:
    """Return ``(skip, label)`` from the issue's control / workflow labels.

    The label is reported whether or not the issue is skipped, because a
    caller that keeps a skipped one still has to bucket it -- and a parked
    issue answered `None` would read as the unlabeled pickup, which is a
    family-aware route and would flip the whole bucket cap-counted.
    """
    label = gh.workflow_label(issue)
    return _hard_skipped(spec, issue, label, _POLLED_OPEN), label


def _hard_skipped(
    spec: config.RepoSpec,
    issue: Issue,
    label: str | None,
    reading: _PollReading,
) -> bool:
    """Whether a control label parks this issue outside the state machine.

    ``backlog`` / ``paused`` park everything, with one exception: an issue
    somebody observed CLOSED. Dropping one of those loses the close itself --
    an observed close ends a late cycle irreversibly, and the only pass that
    would ever record that is the one this filter is about to discard, so an
    owner paused while closed would come back from a reopen and an unpause
    with a live generation and spawn against it. So it is routed, and what
    the control label defers is everything past the mark: both the sweep and
    the dispatcher's own cancelled-cycle guard read the same label and stop
    there.

    Any of the three readings counts, because each is a close somebody saw:
    the bound cleanup route, the bound closed reading behind a label that
    names an ordinary terminal, and this tick's own look at a closed issue on
    a cleanup-swept label.
    """
    skip_label = hard_skip_control_label(issue)
    if skip_label is None:
        return False
    if reading.cleanup_only or reading.closed or _cleanup_sweep_only(
        issue, label,
    ):
        log.info(
            "repo=%s issue=#%s has %r and was observed closed; ending its "
            "late cycle and deferring everything else",
            spec.slug, issue.number, skip_label,
        )
        return False
    log.info(
        "repo=%s issue=#%s has %r; skipping",
        spec.slug, issue.number, skip_label,
    )
    return True


def _classify_pollable_issue(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue,
) -> tuple[bool, str | None]:
    """Read one pollable issue's workflow label for the family / fanout split.

    Returns ``(skip, label)``. ``skip=True`` marks a hard-skip control label
    (``backlog`` / ``paused``): the operator parked the issue outside the
    state machine, so the caller drops it BEFORE the partition -- a parked,
    workflow-label-less issue folded into the family bucket would flip the
    whole bucket cap-counted and starve fanout under ``parallel_limit=1``
    (``_process_issue`` skips it anyway).

    A label-read failure (including one raised by ``hard_skip_control_label``
    itself) is reported as ``(False, None)`` so the issue is conservatively
    routed into the family bucket, where ``_process_issue``'s own per-issue
    exception isolation picks up any sustained failure. The label read runs
    on the caller thread so bucketing needs no extra worker-side round-trip.
    """
    try:
        return _read_issue_routing(gh, spec, issue)
    except Exception:
        log.exception(
            "repo=%s issue=#%s label read failed; routing to family bucket "
            "so per-issue exception isolation can pick up any sustained "
            "failure", spec.slug, issue.number,
        )
        return False, None


def _partition_pollable_issues(
    gh: GitHubClient,
    spec: config.RepoSpec,
    deferred: frozenset[int] | None = None,
) -> _PollablePartition:
    """Split this tick's pollable issues into the family and fanout buckets.

    Family-aware labels (``decomposing`` / ``blocked`` / ``umbrella``) and
    the unlabeled-pickup ``None`` are cross-issue writers -- a parent's
    ``_handle_decomposing`` recovery seeds ``parent_number`` on a child
    while the child's ``_handle_blocked`` would otherwise clobber the same
    pinned-state comment -- so they must never run two at a time and are
    collected into ``family_numbers`` (with index-aligned ``family_labels``).
    Every other label touches only its own per-issue state and fans out, as
    does a CLOSED issue on a cleanup-swept label, whose handler is the sweep
    rather than the stage its label names. A closed fan-out issue is
    additionally recorded in ``fanout_closed``, because what it runs is a
    cheap terminal finalize or a cleanup pass over a closed owner's ledger --
    neither spawns, so both are submitted cap-exempt. Hard-skip (``backlog``
    / ``paused``) issues are dropped entirely.

    A held close observation outranks both of those filters, because it is
    not a reading of this tick's at all: it is one an earlier poll took and
    could hand to nobody. An operator who parks the issue does not undo it --
    the sweep it routes to marks the cancellation and defers every external
    step, which is exactly what the park asks for -- and an issue the
    enumeration does not even yield is added on the strength of the
    observation alone, since a human who moved the label off the two the
    closed sweep queries would otherwise take the reading away for good.
    """
    builder = _PollablePartitionBuilder(deferred=deferred or frozenset())
    for issue in gh.list_pollable_issues():
        _sorted_pollable(builder, gh, spec, issue)
    builder.add_unyielded()
    return builder.build()


def _sorted_pollable(
    builder: _PollablePartitionBuilder,
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
) -> None:
    """Classify one yielded issue into the bucket its route names.

    A CLOSED reading is latched the moment this establishes it, which is the
    earliest anything in this process knows. What stands between here and the
    submit that would carry it is the rest of the enumeration -- a label read
    per issue in the repository -- and a worker holding this issue is asking
    the latch before every irreversible step it takes for the whole of that
    window. A reading latched only once the scheduler had refused would leave
    that worker free to spawn, create a child, or activate one against an
    issue this poll already saw ended.

    It is the same reading either way, and every path that carries it settles
    it: an admitted cleanup drops it once its pass has run, an admitted
    ordinary pass drops it where the record positively says there is nothing
    to end, and a refused submit keeps it deliberately.

    And it is written DOWN here too, not only latched. A latch is memory, so
    an accepted submit whose task never starts -- a scheduler shutdown, a
    process that dies before the worker takes it -- would otherwise leave the
    observation with no durable half at all, and a human who reopens the issue
    before the next process polls it takes the reading off the remote for
    good. The receipt is the only thing that survives that, so it goes on the
    thread while the record can still name the cycle it belongs to.

    It costs one pinned read per closed fan-out issue, and no more: the
    receipt is written from the object this enumeration already listed, and
    the same read answers whether the reading is owed at all -- an issue whose
    record says there is nothing to end has its latch dropped again here, so
    the machinery is carried only by the owners that actually need it.

    Only where the reading actually travels with the route: the closed
    fan-out set is exactly what carries one, and a closed issue drained in the
    family bucket is a hard human stop with nothing to finalize.
    """
    issue_number = int(issue.number)
    closed = issue_is_closed(issue)
    skip, label = _classify_pollable_issue(gh, spec, issue)
    if skip and not (closed or builder.owed(issue_number)):
        return
    builder.add(issue_number, label, closed)
    if issue_number in builder.fanout_closed:
        _recorded_at_poll(gh, spec, issue)


def _recorded_at_poll(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue,
) -> bool:
    """Latch this closed reading and get its durable half written.

    Latched FIRST, because the reading is the one thing this exists to keep
    and everything after it is a request that can fail. Dropped again only
    where the record positively says there is nothing to end -- a closed issue
    with no late cycle is owed a turn, not an observation, and carrying one
    would send it through a cleanup pass it never earned.

    Answers whether the reading was kept, so a caller that has to hold one
    across the pass it is handing it to knows whether it is holding anything.
    """
    issue_number = int(issue.number)
    observations.observe_close(spec.slug, issue_number)
    late_cancellation = importlib.import_module(_LATE_CANCELLATION_OWNER)
    if late_cancellation._record_observed_close(
        gh, spec, issue_number, polled=issue,
    ):
        return True
    observations.settle_close(spec.slug, issue_number)
    return False


@contextlib.contextmanager
def _refetched_close(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    reading: _PollReading,
):
    """Hold a close the REFETCH established and the enumeration could not.

    An issue open when it was listed and closed by the time its pass refetches
    it carries a reading nothing else in this process holds: no latch was
    taken, because there was nothing to latch, and nothing was written down.
    Every step behind the refetch can fail -- the pinned read the guard is
    built on, the write that marks the cancellation -- and a human who reopens
    the issue before the next poll takes the reading off the remote for good,
    leaving the stage handler its label names to resume a cycle a close ended.

    So it is taken here, where it first exists and before anything acts on it,
    exactly as the enumeration takes its own: latched, written down from the
    same object, and dropped again where the record says there is nothing to
    end. What the pass then does with it is the ordinary thing -- the guard
    reads the same close off the same object -- and what a pass that could not
    finish leaves behind is the reading, held for the next tick.

    A pass already carrying a closed reading holds nothing here: the poll's
    own is the older of the two and is already latched and already written.
    """
    if reading.closed or not issue_is_closed(issue):
        yield
        return
    if not _recorded_at_poll(gh, spec, issue):
        yield
        return
    with _closed_reading(gh, spec, int(issue.number)):
        yield


def _family_bucket_cap_exempt(family_labels: list[str | None]) -> bool:
    """True when a family bucket may skip the per-repo / global caps.

    A bucket is cap-exempt only when EVERY issue in it this tick runs a
    no-agent / no-worktree handler -- all labels in ``_CAP_EXEMPT_FAMILY_LABELS``
    (``blocked`` / ``umbrella``, pure dep-graph walks). Such a bucket must
    always get its turn even when the parallel caps are saturated by real
    implementation work: a ``blocked`` parent polling its children, or an
    ``umbrella`` aggregating them, would otherwise be starved of the only
    per-repo slot under the default ``parallel_limit=1`` -- and a ``blocked``
    parent waiting on its own children would deadlock them. A bucket
    containing ``decomposing`` (spawns the decomposer agent) or an
    unlabeled-pickup ``None`` (routes through ``_handle_pickup``, may spawn an
    agent) stays cap-counted.

    A closed issue on a cleanup-swept label is not here to be exempted: it is
    partitioned as fan-out instead (see ``_drains_in_family_bucket``), so it
    is submitted cap-exempt on its own rather than tying its turn to whatever
    else this bucket happens to hold.
    """
    return all(lbl in _CAP_EXEMPT_FAMILY_LABELS for lbl in family_labels)


def _refetch_and_process(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue_number: int,
    *,
    semaphore_cm: contextlib.AbstractContextManager | None = None,
    reading: _PollReading = _POLLED_OPEN,
) -> None:
    """Mint a per-worker client, refetch the Issue, and run its handler.

    Only issue NUMBERS cross the thread boundary. PyGithub's ``Issue`` and
    the parent ``GitHubClient`` / ``Repository`` / ``Requester`` chain hold
    mutable per-request state that is not documented thread-safe, so each
    worker calls ``gh._for_worker_thread()`` to mint a fresh client and
    refetches its Issue against THAT client -- every in-flight HTTP call is
    then the sole consumer of its requester's state.

    ``semaphore_cm`` wraps the ``_process_issue`` call so the in-tick parallel
    path can thread the cross-repo ``global_semaphore`` through here; the
    scheduler path leaves it ``None`` (a no-op) because the scheduler owns
    the cross-repo cap itself.

    ``cleanup_only`` rides along because the refetch is exactly where a
    classification can go stale. A closed cleanup owner is submitted on its
    own cap-exempt terms, and a reopen between the poll and this call must not
    turn that submit into an agent-spawning stage handler running outside the
    caps -- so the route is carried rather than re-derived.

    Staleness runs the other way too, and that one is an OBSERVATION rather
    than a route: an issue open when it was listed can be closed by the time
    this reads it, and nothing in this process holds that reading. It is
    taken here, against the object the refetch just returned.
    """
    worker_gh = gh._for_worker_thread()
    worker_issue = worker_gh.get_issue(issue_number)
    cm = contextlib.nullcontext() if semaphore_cm is None else semaphore_cm
    with cm, _refetched_close(worker_gh, spec, worker_issue, reading):
        _process_issue(worker_gh, spec, worker_issue, reading=reading)


def _drain_scheduler_family_bucket(
    gh: GitHubClient,
    spec: config.RepoSpec,
    scheduler: IssueScheduler,
    family_numbers: list[int],
) -> None:
    """Drain this tick's family-aware issues sequentially under one bucket.

    Runs as the single ``family=True`` scheduler submit per repo, so the
    family slot is held for the whole drain: a concurrent tick mid-drain
    cannot squeeze a second family worker past the gate and no two
    family-aware handlers ever run at once. ``scheduler.track_active`` wraps
    each iteration so ``is_active(repo, n)`` reports True for the issue
    currently being processed inside the bucket -- the pre-tick base refresh
    relies on that signal to avoid rebasing a worktree under a running agent;
    without the per-iteration claim only the bucket's sentinel key would
    appear in the in-flight set and a concurrent refresh would race the agent.

    ``track_active`` yields a ``claimed`` bool: when False the issue is
    already in flight on another worker (e.g. a fanout submit accepted on a
    previous tick before this issue was relabeled into the family bucket), so
    the drain skips ``_process_issue`` for that iteration and the next polling
    pass picks it up once the other worker exits -- two workers running the
    same handler concurrently would race the worktree and pinned state.
    Per-issue exception isolation lives inside the loop so one raising family
    handler does not abort the rest of the bucket.

    Each per-issue call mirrors the fanout path: ``_refetch_and_process``
    mints a fresh ``GitHubClient`` via ``gh._for_worker_thread()`` and
    refetches the Issue against it (PyGithub is not documented thread-safe).
    """
    for issue_number in family_numbers:
        try:
            with scheduler.track_active(spec.slug, issue_number) as claimed:
                if not claimed:
                    log.info(
                        "repo=%s issue=#%s already in flight; "
                        "family bucket skipping this iteration",
                        spec.slug, issue_number,
                    )
                    continue
                _refetch_and_process(gh, spec, issue_number)
        except Exception:
            log.exception(
                _PROCESSING_FAILED_LOG,
                spec.slug, issue_number,
            )


def _scheduler_per_repo_cap(spec: config.RepoSpec) -> int:
    return max(1, int(getattr(spec, "parallel_limit", 1) or 1))


def _submit_scheduler_family_bucket(
    gh: GitHubClient,
    spec: config.RepoSpec,
    scheduler: IssueScheduler,
    partition: _PollablePartition,
    per_repo_cap: int,
) -> None:
    family_numbers = partition.family_numbers
    if not family_numbers:
        return

    submitted = scheduler.submit(
        spec.slug,
        _FAMILY_BUCKET_ISSUE,
        functools.partial(
            _drain_scheduler_family_bucket, gh, spec, scheduler, family_numbers,
        ),
        family=True,
        cap_exempt=_family_bucket_cap_exempt(partition.family_labels),
        per_repo_cap=per_repo_cap,
    )
    if submitted:
        return

    # The scheduler logs the precise skip reason (closed, family_slot_held,
    # cap, ...) inside `submit`; this line gives the dispatch-layer context
    # -- which issues were waiting on this bucket -- so an operator can
    # correlate "umbrella not advancing" with a previous tick's bucket
    # still in flight.
    log.info(
        "repo=%s family bucket (%d issues) not submitted this "
        "tick; next polling pass retries",
        spec.slug, len(family_numbers),
    )


def _submit_scheduler_fanout_issues(
    gh: GitHubClient,
    spec: config.RepoSpec,
    scheduler: IssueScheduler,
    partition: _PollablePartition,
    per_repo_cap: int,
) -> None:
    for issue_number in partition.fanout_numbers:
        cleanup_only = issue_number in partition.cleanup_numbers
        # Held from here rather than from wherever the worker first reads
        # something: the claim exists the moment this submit is admitted, and
        # a poll meeting the issue between that and the handler is refused
        # because a worker has it -- which is exactly when its own reading
        # must not be dropped. Given back by the task, or below if the submit
        # was refused and no task will run.
        observations.claim_publication(spec.slug, issue_number)
        submitted = scheduler.submit(
            spec.slug,
            issue_number,
            _released_after(spec, issue_number, _fanout_task(
                gh, spec, issue_number, reading=_PollReading(
                    cleanup_only=cleanup_only,
                    closed=issue_number in partition.fanout_closed,
                ),
            )),
            family=False,
            # A closed issue's handler is a cheap terminal finalization with
            # no agent spawn -- exempt it from the per-repo / global caps so
            # a merged-PR or closed-question issue flips to `done` promptly
            # instead of being starved behind active agent work under
            # `parallel_limit=1` (mirrors the `_CAP_EXEMPT_FAMILY_LABELS`
            # exemption for `blocked` / `umbrella`).
            cap_exempt=(issue_number in partition.fanout_closed),
            per_repo_cap=per_repo_cap,
        )
        if submitted:
            continue
        observations.release_publication(spec.slug, issue_number)
        _refused_submit(
            gh, spec, issue_number,
            cleanup_only=cleanup_only,
            closed=issue_number in partition.fanout_closed,
        )


def _released_after(
    spec: config.RepoSpec, issue_number: int, task: Callable[[], None],
) -> Callable[[], None]:
    """The submitted task with the claim's own hold given back behind it.

    The hold starts at the submit and has to outlive the queue, so the worker
    is what ends it -- and it ends whichever way the task goes, since a pass
    that raised is one that stopped holding the issue just as surely as one
    that returned.
    """
    return functools.partial(_releases_the_claim, spec.slug, issue_number, task)


def _releases_the_claim(
    repo_slug: str, issue_number: int, task: Callable[[], None],
) -> None:
    """Run one submitted task, and give the claim's hold back after it.

    Registered before the task runs rather than called after it, so a pass
    that raises gives the hold back too: one that stopped holding the issue
    did so whichever way it ended.
    """
    with contextlib.ExitStack() as given_back:
        given_back.callback(
            observations.release_publication, repo_slug, issue_number,
        )
        task()


def _refused_submit(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue_number: int,
    *,
    cleanup_only: bool,
    closed: bool,
) -> None:
    """Hold whatever observation a refused fan-out submit was carrying.

    A cleanup route already says a late owner was observed closed, so the
    reading is latched on the strength of the route alone. A closed issue on
    any OTHER label may be carrying the same reading and no label says so: an
    authorized settlement hands its issue to `implementing` a moment before it
    retires the cycle, and a close landing in that window wears a label whose
    handler is an ordinary terminal.

    That one was latched by the enumeration that read it closed, and is
    dropped here only where the record positively says there is nothing to
    end. The order is the whole of it: the probe is a request, and a request
    can fail or can land after the very retirement it was asking about -- so
    a reading conditioned on it would be lost to either, and the reading is
    the one thing this path exists to keep. A latch held over an issue with
    no cycle costs the next tick one cleanup pass that settles it; a reading
    dropped costs the close itself.
    """
    if cleanup_only:
        _deferred_cleanup(gh, spec, issue_number, _HELD_BY_A_WORKER)
        return
    if closed:
        _kept_closed_reading(gh, spec, issue_number)


@contextlib.contextmanager
def _closed_reading(
    gh: GitHubClient, spec: config.RepoSpec, issue_number: int,
):
    """Hold one closed issue's reading across the pass that would spend it.

    Asked on the way out however the pass ends, because a pass can fail to
    spend the reading without failing at all: the pinned read the guard is
    built on answers a refusal of its own, so a tick that could not read the
    record refuses the issue and marks nothing. What a pass that DID mark it
    leaves behind is a record positively saying there is nothing to end,
    which is exactly what drops the reading again.
    """
    try:
        yield
    finally:
        _kept_closed_reading(gh, spec, issue_number)


def _kept_closed_reading(
    gh: GitHubClient, spec: config.RepoSpec, issue_number: int,
) -> None:
    """Hold a closed reading no pass acted on, unless the record says not to.

    Latched FIRST and dropped again only where the record positively says
    there is nothing to end. The order is the whole of it: the probe is a
    request, and a request can fail -- so a reading conditioned on it would be
    lost to that, and the reading is the one thing this path exists to keep. A
    latch held over an issue with no cycle costs the next tick one cleanup
    pass that settles it; a reading dropped costs the close itself.

    The probe and the durable receipt are ONE read for the same reason. They
    ask the same record about the same reading, and two reads of a record the
    worker is writing can disagree: one saw a cycle and kept the observation
    while the other saw the retirement behind it and left the thread saying
    nothing, which leaves the reading in memory alone for a restart to take.
    So the owner writes the receipt from the read that decides this, and
    answers with what that read established.
    """
    observations.observe_close(spec.slug, issue_number)
    late_cancellation = importlib.import_module(_LATE_CANCELLATION_OWNER)
    if not late_cancellation._record_observed_close(gh, spec, issue_number):
        observations.settle_close(spec.slug, issue_number)
        return
    _said_deferred(spec, issue_number, _HELD_BY_A_WORKER)


def _fanout_task(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue_number: int,
    *,
    reading: _PollReading,
    semaphore_cm: contextlib.AbstractContextManager | None = None,
) -> Callable[[], None]:
    """The callable one fan-out submit hands the scheduler.

    An ordinary issue is refetched and dispatched, and what it carries with it
    is the poll's own CLOSED reading: the worker refetches, so a human who
    reopens the issue in that window would otherwise have the fresh reading
    say open and a live late cycle resume against it. The reading is the
    poll's, so it is bound rather than re-derived.

    A cleanup carries an OBSERVATION as well as a turn, so it is wrapped in
    the settlement that observation is owed -- which is a thing only the
    worker can decide, since only the worker knows whether the pass ran.
    """
    if reading.cleanup_only:
        return functools.partial(
            _swept_for_cleanup, gh, spec, issue_number,
            semaphore_cm=semaphore_cm,
        )
    if reading.closed:
        return functools.partial(
            _closed_ordinary_pass, gh, spec, issue_number,
            semaphore_cm=semaphore_cm,
        )
    return functools.partial(
        _refetch_and_process, gh, spec, issue_number,
        semaphore_cm=semaphore_cm,
    )


def _closed_ordinary_pass(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue_number: int,
    *,
    semaphore_cm: contextlib.AbstractContextManager | None = None,
) -> None:
    """Run a closed issue's ordinary pass, keeping the reading if it fails.

    The pass carries the poll's closed reading and is the only thing that
    will ever act on it: the enumeration latched it, and this task is what
    settles it. So a failure anywhere -- the refetch, the pinned read, the
    write that marks the cancellation -- has to leave the latch standing, or
    a human who reopens before the next poll takes the reading off the remote
    for good.

    Asked on the way OUT rather than only on a raise, because a pass can
    fail to spend the reading without failing at all: the pinned read the
    guard is built on answers a refusal of its own, so a tick that could not
    read the record refuses the issue and marks nothing. Settled the same way
    a refused submit settles one -- only where the record positively says
    there is nothing to end, which is exactly what a pass that DID mark it
    leaves behind.

    Held only where the enumeration kept a reading at all. It asked the same
    record already, and an issue it settled there is a closed one with no late
    cycle: asking again would spend a pinned read to reach the same answer,
    and re-latching in between would route an ordinary terminal through a
    cleanup pass on the tick after this one.
    """
    if not observations.close_observed(spec.slug, issue_number):
        _refetch_and_process(
            gh, spec, issue_number,
            semaphore_cm=semaphore_cm, reading=_PollReading(closed=True),
        )
        return
    with _closed_reading(gh, spec, issue_number):
        _refetch_and_process(
            gh, spec, issue_number,
            semaphore_cm=semaphore_cm, reading=_PollReading(closed=True),
        )


def _swept_for_cleanup(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue_number: int,
    *,
    semaphore_cm: contextlib.AbstractContextManager | None = None,
) -> None:
    """Take one latched close, and settle it only if the pass lands.

    Settled AFTER the pass rather than when the submit was accepted, because
    an accepted submit is not a cancellation persisted: the worker's own
    refetch is a GitHub read, and a read that fails leaves the cycle unmarked
    with nothing left saying a close was ever seen. A human reopening the
    issue before the next poll would then get ordinary workflow dispatch over
    a cycle a close already ended.

    So a pass that raises anywhere -- the refetch, the route, the sweep --
    hands the observation back, whether this worker was carrying one from an
    earlier tick or was the first to see the close. The next tick submits the
    cleanup again on the strength of it, and the sweep it reaches repeats
    whatever the failed pass did manage: every step of the ending is
    idempotent, and the mark itself is kept from its first stamp.
    """
    with _cleanup_observation(gh, spec, issue_number):
        _refetch_and_process(
            gh, spec, issue_number, semaphore_cm=semaphore_cm,
            reading=_PollReading(cleanup_only=True, closed=True),
        )


@contextlib.contextmanager
def _cleanup_observation(
    gh: GitHubClient, spec: config.RepoSpec, issue_number: int,
):
    """Hold one cleanup's observation until the pass has actually run it.

    Every path that runs a cleanup wraps it in this, and they all have to:
    the scheduler's fan-out submit, the in-tick parallel one, and the
    sequential loop that dispatches on its own thread. A pass that raises
    anywhere -- the refetch, the route, the sweep -- marked nothing, so the
    reading it was carrying is still the only one there is, and dropping it
    there would let a reopen before the next tick resume the very cycle the
    close ended.

    A pass that RETURNS is asked what it left, because returning is not
    finishing: a live consumer holds the ref, a remote that refuses a delete
    holds the branch, and the terminal is one more request that can be
    declined. What the answer decides is only whether this reading is the
    LAST route back -- an owner still wearing a swept label is one the sweep
    reaches on its own cadence, and one whose label the cancelled cycle's own
    agent moved is reachable by nothing else at all.
    """
    try:
        yield
    except Exception:
        _deferred_cleanup(gh, spec, issue_number, _PASS_FAILED)
        raise
    _kept_cleanup_reading(gh, spec, issue_number)


def _kept_cleanup_reading(
    gh: GitHubClient, spec: config.RepoSpec, issue_number: int,
) -> None:
    """Hold a cleanup's reading where nothing else would come back for it.

    The one question this asks the remote after a pass, and it is asked of the
    ending rather than of the pass: every step of a cleanup is idempotent and
    each is skipped where the record already says what a visit would say, so a
    reading kept over an owner that settled a moment later costs one more pass
    and a reading dropped over one that did not costs the close itself.

    The observation is re-latched before the question rather than after the
    answer, because the answer is a request and a request can fail. What that
    ordering leaves at worst is a latch over an owner with nothing left to
    end, which the next tick's own cleanup pass settles.
    """
    observations.observe_close(spec.slug, issue_number)
    late_cancellation = importlib.import_module(_LATE_CANCELLATION_OWNER)
    if late_cancellation._cleanup_settled(gh, spec, issue_number):
        observations.settle_close(spec.slug, issue_number)
        return
    _said_deferred(spec, issue_number, _ENDING_UNFINISHED)


def _deferred_cleanup(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue_number: int,
    reason: str,
) -> None:
    """Latch a close no pass took, say why, and write it down once.

    A cleanup submission is the only kind whose loss costs an OBSERVATION
    rather than a turn: this poll saw the issue closed, and a human who
    reopens it before the next pass takes that reading away. Two things can
    cost one. The scheduler admits no second worker for an issue one is
    already running, so a submit can be refused outright; and a pass that was
    admitted can fail before it has marked anything.

    Either way the reading is latched rather than discarded, and it is read
    by both of the parties that could not otherwise have it. The next tick
    routes the issue to the sweep on the strength of it -- whatever the issue
    reads as by then -- and the run already holding the issue asks the same
    latch before every step the remote keeps, so a close it could never see
    for itself still ends its cycle where it stands.

    The durable half is attempted by every pass that latches one and settled
    by the first that lands it. A comment rather than a pinned write for the
    reason the latch exists at all -- the pinned comment is written whole, so
    writing it from here would drop whatever the worker holding the issue
    recorded in between -- and retried rather than tried once, because a post
    GitHub refuses leaves an observation with no durable half at all, which a
    restart before the run reaches a barrier takes away for good. The owner
    itself is what bounds the repeats: it writes nothing where the thread
    already says this, and remembers the attempt that landed.
    """
    observations.observe_close(spec.slug, issue_number)
    _said_deferred(spec, issue_number, reason)
    late_cancellation = importlib.import_module(_LATE_CANCELLATION_OWNER)
    late_cancellation._record_observed_close(gh, spec, issue_number)


def _said_deferred(
    spec: config.RepoSpec, issue_number: int, reason: str,
) -> None:
    """Say what was held, so an operator can tell one hold from the other."""
    log.info(
        "repo=%s issue=#%d observed closed with a late cycle to settle, but "
        "%s; holding the observation and sweeping it on the next polling "
        "pass",
        spec.slug, issue_number, reason,
    )


def _dispatch_via_scheduler(
    gh: GitHubClient, spec: config.RepoSpec, scheduler: IssueScheduler,
) -> None:
    """Enumerate pollable issues this tick and hand work to the scheduler.

    Family-aware work (unlabeled pickup + decomposing / blocked /
    umbrella -- the cross-issue writers) is folded into ONE bucket
    submit per repo that drains its issues sequentially on a single
    worker thread; non-family issues are submitted individually. The
    in-tick parallel path in ``tick()`` partitions the same way (one
    drain task for the family bucket, per-issue futures for fanout).

    One bucket per repo is what keeps the family mutex from starving
    itself. The scheduler grants the family slot to the first accepted
    ``family=True`` submit and silently skips every later one this tick,
    so a per-issue family submit would let a stale ``blocked`` child
    take the slot while the parent ``umbrella`` that should relabel it
    never runs -- and the pair would trade the slot back and forth
    forever. Draining every family issue inside the one accepted submit
    means the umbrella always gets its turn within the same tick.

    The bucket task uses ``scheduler.track_active`` around each
    per-issue iteration so ``scheduler.is_active(repo, n)`` reports True
    for the issue currently being processed inside the bucket -- the
    pre-tick base refresh relies on that signal to avoid rebasing a
    worktree under a running agent. Without per-iteration tracking,
    only the bucket's sentinel key would appear in the in-flight set
    and a concurrent refresh would race the agent.

    Each per-issue callable mirrors the in-tick parallel path: mint a
    fresh ``GitHubClient`` via ``gh._for_worker_thread()`` and refetch
    the Issue against that client so the worker drives its own
    Requester chain (PyGithub is not documented thread-safe).

    Completion reaping is the polling loop's job, not this function's.
    ``runtime.ticks.run_tick`` calls ``scheduler.reap()`` exactly once
    after every configured repo's tick returns, which is the cadence surfaced
    to operators and documented in ``docs/observability.md`` ("one reap
    per polling pass"). Reaping here as well would multiply that to N+1
    reaps per pass under ``REPOS``.

    ``spec.parallel_limit`` is forwarded as the scheduler's per-call cap
    override so a per-repo configuration tighter than the scheduler
    default still binds. Label-read failures route the offending issue
    into the family bucket so ``_process_issue``'s own exception
    isolation picks up any sustained failure -- the same recovery the
    in-tick parallel path uses.

    When every family-aware issue this tick runs a no-agent handler
    (label in ``_CAP_EXEMPT_FAMILY_LABELS`` -- ``blocked`` or
    ``umbrella``, both pure label/dep-graph walks), the bucket submit is
    marked ``cap_exempt=True`` so it does not consume a
    ``MAX_PARALLEL_ISSUES_PER_REPO`` or ``MAX_PARALLEL_ISSUES_GLOBAL``
    slot. Such a bucket must always get its turn even when the caps are
    saturated by ordinary implementation work -- otherwise a ``blocked``
    parent polling its own children would be starved of the only
    per-repo slot (under the default ``parallel_limit=1``) and deadlock
    the very children it waits on. A bucket containing ``decomposing``
    (spawns the decomposer agent) or an unlabeled-pickup ``None`` stays
    cap-counted. ``backlog`` / ``paused`` issues are filtered out before
    this split -- a parked issue carries no workflow label, so leaving it in
    would fold it into the bucket and force ``cap_exempt=False``, starving
    fanout behind a hard-skip hold under ``parallel_limit=1``. The family mutex
    still applies, so a follow-up tick that finds another family issue
    still serializes against this bucket.

    Closed fan-out issues are likewise submitted ``cap_exempt=True``: a
    closed issue carrying a sweep label (``in_review`` / ``fixing`` /
    ``resolving_conflict`` / ``question`` / ...) only runs a terminal
    finalization (flip to ``done`` / ``rejected`` + branch cleanup) with no
    agent spawn, so it must not be starved behind active agent work -- a
    merged-PR issue could otherwise sit closed-but-labeled for many ticks
    while a sibling ``validating`` / ``documenting`` agent holds the only
    per-repo slot. A closed ``decomposing`` / ``umbrella`` owner is a fan-out
    submit for exactly this reason: its handler is the cleanup sweep, which
    settles a ledger and spawns nothing, and folding it into the bucket would
    make its turn depend on whatever else landed there.
    """
    per_repo_cap = _scheduler_per_repo_cap(spec)
    # `_partition_pollable_issues` owns the skip-label filtering, per-issue
    # label-read isolation, and the family/fanout split (including the closed
    # fan-out set). `backlog` / `paused` issues are dropped there so a parked,
    # workflow-label-less issue never folds into the bucket and flips it
    # cap-counted, which would reserve the only per-repo slot and starve
    # fanout under `parallel_limit=1`.
    partition = _partition_pollable_issues(
        gh, spec, observations.observed_closes(spec.slug),
    )

    # One `family=True` submit per repo drains every family-aware issue
    # sequentially (see `_drain_scheduler_family_bucket`). The bucket is
    # cap-exempt only when every family issue runs a no-agent handler
    # (`_family_bucket_cap_exempt`); the helper keeps the exempt probe and
    # the submit off the no-family path entirely.
    _submit_scheduler_family_bucket(gh, spec, scheduler, partition, per_repo_cap)
    _submit_scheduler_fanout_issues(gh, spec, scheduler, partition, per_repo_cap)
