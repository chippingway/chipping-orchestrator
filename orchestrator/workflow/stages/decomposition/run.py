# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One `decomposing` tick: what runs before the agent, and what the agent earns.

Two different questions wear this label, and the first thing a tick does is
ask which one it is. An issue whose record carries a live late generation is
not waiting to be decomposed: its implementation is committed, measured past
the ceiling, and waiting on a verdict, so the whole tick belongs to the late
coordinator and nothing below runs. Everything else is the initial
decomposition this owner has always driven.

An initial decomposition standing on a spent spawn budget is asked next, and
it is asked before the tick has a road to walk down at all: the drift reset,
the kill switch, and the human-reply resume each clear or answer a park that
is not this one, and this one is lifted only by the human its notice asked
for. What holding it costs is nothing, and what it keeps is everything the
issue arrived with.

The order in `_prepare_decomposer_run` is the contract. A parked tick -- and
one spending an attempt a retry-cap continuation bought, which left the replies
its park held past the boundary, or one owing a manifest correction's launch,
whose rejected run settled the boundary through what it read -- reads its
thread once before anything else is decided (`replies.py`), and the drift
check, the prompt, and the settlement
behind its run are all cut from that one read: measured off it, a reply past
the park's boundary is the park's answer rather than an edit, so it resumes the
locked session instead of retiring it, while a changed title, body, or already-read comment still takes the fresh
decomposition, a reply beside it or not -- quoting that same read. A thread that
cannot be read holds the tick with nothing reset or launched, and a park over a
split no reading shows a child of is released to the reply answering it ahead
of the recovery's hold. Drift goes first after that, so a
body edited during a crash window clears the manifest markers before recovery
can read them and finalize a split the human no longer wants. Recovery goes
next, and deliberately ahead of the `DECOMPOSE` kill switch: children already
open on GitHub have to be resolved whether or not new decompositions are still
enabled -- a kill switch that stranded existing work would be the wrong kind of
off. Only past both does the tick pick its run
(`correction_reconcile.run_for_the_tick`): the manifest correction an earlier
tick left pending first -- launched, retired, or given up before any decomposer
is charged behind it -- then resuming a parked session or spawning a fresh one.
Ahead of all of it but the reroute's marker, a correction owed a park that does
not stand takes it (`correction_reconcile.recovers_park`), so the frozen read
and the drift check meet a parked issue whose later replies are the park's, and
a correction record nobody can read holds the tick.

Everything after the run is about what that run is allowed to publish. A
`paused` label applied mid-run wins over the whole disposition, an agent that
left commits or edits in a read-only worktree parks with the worktree kept for
inspection (forwarding typed correlation fields to the shared park funnel), and
an interrupted run is dropped entirely -- checked in that order so a killed
run's changes stay inspectable rather than being discarded as untrustworthy.
A manifest the parser refuses earns one correction of the same session, which
is disposed of on the same plan exactly as the run it corrects -- every hold,
park, and check again -- and earns none of its own.
A run handed a frozen read -- the resume, or the fresh decomposition an edit
or a continuation buys -- settles what it was handed only where it read it,
and every park its disposition takes is bounded, the split's own among them, so
a comment written while it was out stays past the boundary for the next resume.

The worktree is torn down by an `ExitStack` callback rather than at each exit,
because `keep_worktree` is decided in the middle of that sequence and every
path after it -- including one that raises -- has to honor the decision. One
raise decides it too: a run that meets a pinned record admission refuses
(`pinned_refusal.RecordRefused`) keeps the worktree for the human who disposes
of that record.
"""
from __future__ import annotations

import logging
from contextlib import ExitStack

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import creation as _worktree_creation, decomposition as _worktree_decomposition
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    guards as _guards,
    park_watermarks as _park_watermarks,
    record_admission as _record_admission,
)
from orchestrator.workflow.stages.decomposition import (
    correction_reconcile as _correction_reconcile,
    drift as _drift,
    handoff as _handoff,
    late_coordinator as _late_coordinator,
    outcomes as _outcomes,
    recovery as _recovery,
    replies as _replies,
    retry_cap as _retry_cap,
)
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from orchestrator.workflow.stages.decomposition.models import _DecomposerCleanup, _DecomposerRunPlan

log = logging.getLogger("orchestrator.workflow")


def _prepare_decomposer_run(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> _DecomposerRunPlan:
    # A reroute `ready` landed is answered by this label, so its marker goes
    # before anything below can run a decomposer or hand the issue back there.
    if not _drift._retires_ready_reroute(gh, issue, state):
        return _DecomposerRunPlan(agent_result=None)

    # A manifest correction owed a park that does not stand -- its own park's
    # write lost, or an answer nothing acted on -- parks before the thread is
    # read, so a reply written while it was out is that park's to deliver
    # rather than an edit retiring the session it saved; a correction record
    # nobody can read holds the tick. A recovery that read the requirements
    # moved hands back the issue it read them off, which the rest of the run
    # is decided on.
    current = _correction_reconcile.recovers_park(gh, issue, state)
    if current is None:
        return _DecomposerRunPlan(agent_result=None, keep_worktree=True)

    # A parked tick, or one spending what a continuation bought, reads its
    # thread ONCE, before drift is decided: the drift check, the prompt, and
    # its settlement are all cut from this read, so a reply landing between
    # two of them is in none of them. One nobody could read holds the tick
    # with the park, and any worktree it is keeping for inspection, as they
    # stand.
    frozen = _replies.reads_the_thread(current, state)
    replies = _replies.freeze(gh, current, state) if frozen else None
    if frozen and replies is None:
        return _DecomposerRunPlan(agent_result=None, keep_worktree=True)
    return _run_on_the_reading(gh, spec, current, state, replies)


def _run_on_the_reading(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    replies: _replies.DecomposerReplies | None,
) -> _DecomposerRunPlan:
    """The run this tick earns, decided on the one reading the tick froze (None for one that froze none)."""
    # User-content drift FIRST, so it runs BEFORE the half-finished recovery:
    # otherwise recovery could finalize against a stale manifest when the issue
    # was edited during a crash window.
    _drift._reset_decomposing_on_drift(gh, issue, state, replies)
    # A park standing over a split no reading shows a child of holds nothing a
    # decomposer run could be seen to duplicate, so a reply answering it is let
    # past the recovery's hold below; any sign of a child keeps the hold.
    if replies is not None and replies.followup is not None and _replies.parked(state):
        _recovery._release_an_empty_split(gh, issue, state)

    if (
        _recovery._recover_stale_manifest(gh, spec, issue, state)
        or _handoff._route_disabled_to_implementing(gh, spec, issue, state)
    ):
        return _DecomposerRunPlan(agent_result=None)

    return _correction_reconcile.run_for_the_tick(gh, spec, issue, state, replies)


def _process_decomposer_run(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    run_plan: _DecomposerRunPlan,
) -> None:
    """Process a finished decomposer run and dispatch its manifest or park.

    A run handed a frozen reading of a parked thread is disposed of inside a
    bounded-park scope (`park_watermarks.bounded_parks`), so every park it
    earns -- its own, and the split's however deep -- walks the reply boundary
    from what the run's settlement recorded through our own comments and stops
    at a comment written while it was out.
    """
    if run_plan.agent_result is None:
        return
    with _park_watermarks.bounded_parks(run_plan.bounded):
        _dispose_decomposer_run(gh, spec, issue, state, run_plan)


def _dispose_decomposer_run(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    run_plan: _DecomposerRunPlan,
) -> None:
    """Settle one finished run, then hold it, park it, or dispatch its manifest."""
    decomposer_result = run_plan.agent_result
    # A launch the agent-run circuit refused reached no process, so nothing
    # below is about this run: the worktree it would be judged on carries
    # whatever an earlier one left, and a `decomposer_dirty` park in its name
    # would overwrite the durable park the refusal itself took.
    if _guards._ignore_if_never_invoked(issue, decomposer_result):
        return

    if _outcomes._settle_decomposer_run(gh, issue, state, run_plan):
        return

    # The decomposer is read-only. Preserve a changed worktree for operator
    # inspection, setting the cleanup policy before parking or persistence can
    # raise and trigger the handler's finally block.
    wt = _worktree_decomposition._decompose_worktree_path(spec, issue.number)
    if (
        _worktree_creation._has_new_commits(spec, wt)
        or _worktree_status._worktree_dirty_files(wt)
    ):
        run_plan.keep_worktree = True
        _outcomes._park_dirty_worktree(gh, issue, state, run_plan)
        return

    # An interrupted run has no trustworthy manifest. The read-only check
    # stays first so changes left by a killed run remain available to inspect.
    if _guards._ignore_if_interrupted(issue, decomposer_result):
        return

    # A rejected manifest's one correction, launched in its place, is disposed
    # of exactly as this run was, on the same plan; it earns none of its own.
    # Its parks are bounded where its launch's were (`correction_road.bounds`),
    # so a reply written while it was out stays past the boundary.
    if _outcomes._dispatch_decomposer_manifest(gh, spec, issue, state, run_plan):
        with _park_watermarks.bounded_parks(run_plan.bounded):
            _dispose_decomposer_run(gh, spec, issue, state, run_plan)


def _late_adjudication_owns_the_tick(
    gh: _client.GitHubClient, spec: config.RepoSpec, issue: Issue, state: _pinned_state.PinnedState,
) -> bool:
    """Whether this `decomposing` tick belongs to the late size gate.

    Asked before anything else this handler does, and asked of every tick
    rather than only of the ones that look late. The coordinator's own first
    steps are the reconciliations an earlier tick left owed -- a park notice a
    refused comment stranded, an owner read that could not be taken -- and
    those are owed by exactly the records the gates below would route past. On
    an issue that never entered the size gate they cost nothing: there is no
    generation to read them off, and the call comes straight back saying so.

    What it answers with is what the tick did. Only "this is not a late
    adjudication" falls through, so an oversized committed candidate is never
    handed to the agent that would re-decompose the issue from scratch -- and
    the read-only scratch checkout that agent needs is never created for a run
    that reads the developer's own worktree instead.

    Nor is "not an adjudication" the same as "never entered the gate", which
    is why one more question stands between that answer and the decomposer: a
    revision that came back at or below the ceiling is a record whose size
    question is ANSWERED, and what it is owed is publication rather than a
    second plan for work that is already written.
    """
    adjudicated = _late_coordinator._adjudicate_late_generation(
        gh, spec, issue, state,
    )
    if adjudicated.disposition != _LateDisposition.NOT_LATE:
        return True
    return _handoff._settled_candidate_owns_the_tick(gh, spec, issue, state)


def _handle_decomposing(gh: _client.GitHubClient, spec: config.RepoSpec, issue: Issue) -> None:
    state = _record_admission.admitted_state(gh, issue)
    # Ahead of the late route as well as the gates below it: a retry-cap park
    # is this budget's, not the size gate's, and the sentence it owes is owed
    # whichever of the two questions wearing this label the tick is about.
    _retry_cap._replay_owed_notice(gh, issue, state)
    if _late_adjudication_owns_the_tick(gh, spec, issue, state):
        return
    # The spent-budget park, ahead of every road below that would walk past
    # one: the drift reset and the kill switch both clear park flags, and the
    # resume reads a reply as the answer -- and this park is answered by a
    # human buying another attempt, not by an edit, a setting, or a comment.
    if _retry_cap._park_owns_the_tick(gh, issue, state):
        return
    cleanup = _DecomposerCleanup(
        gh=gh,
        spec=spec,
        issue=issue,
        run_plan=_DecomposerRunPlan(agent_result=None),
    )
    with ExitStack() as cleanup_stack:
        cleanup_stack.callback(cleanup.close)
        cleanup_stack.push(cleanup.keeps_on_refusal)
        cleanup.run_plan = _prepare_decomposer_run(
            gh,
            spec,
            issue,
            state,
        )
        _process_decomposer_run(
            gh,
            spec,
            issue,
            state,
            cleanup.run_plan,
        )
