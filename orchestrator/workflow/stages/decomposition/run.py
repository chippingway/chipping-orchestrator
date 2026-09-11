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

The order in `_prepare_decomposer_run` is the contract. Drift goes first, so a
body edited during a crash window clears the manifest markers before recovery
can read them and finalize a split the human no longer wants. Recovery goes
next, and deliberately ahead of the `DECOMPOSE` kill switch: children already
open on GitHub have to be resolved whether or not new decompositions are still
enabled -- a kill switch that stranded existing work would be the wrong kind of
off. Only past both does the tick pick between resuming a parked session and
spawning a fresh one.

Everything after the run is about what that run is allowed to publish. A
`paused` label applied mid-run wins over the whole disposition, an agent that
left commits or edits in a read-only worktree parks with the worktree kept for
inspection, and an interrupted run is dropped entirely -- checked in that order
so a killed run's changes stay inspectable rather than being discarded as
untrustworthy.

The worktree is torn down by an `ExitStack` callback rather than at each exit,
because `keep_worktree` is decided in the middle of that sequence and every
path after it -- including one that raises -- has to honor the decision.
"""
from __future__ import annotations

import logging
from contextlib import ExitStack

from github.Issue import Issue

from orchestrator import agents, config
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation, decomposition as _worktree_decomposition
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    guards as _guards,
    retry_budget as _retry_budget,
    usage as _usage,
)
from orchestrator.workflow.stages.decomposition import (
    drift as _drift,
    handoff as _handoff,
    late_coordinator as _late_coordinator,
    outcomes as _outcomes,
    recovery as _recovery,
    retry_cap as _retry_cap,
    session as _session,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateDisposition
from orchestrator.workflow.stages.decomposition.models import _DecomposerCleanup, _DecomposerRunPlan

log = logging.getLogger("orchestrator.workflow")



def _settle_decomposer_run(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    decomposer_result: agents.AgentResult,
) -> bool:
    """Fold this run's usage and park on a live pause or timeout.

    Returns True when the caller must return (paused or timed out), False
    to continue to the dirty-worktree check and manifest dispatch. None of
    these paths preserve the decompose worktree: the caller's `finally`
    tears it down on return. The read-only dirty/commits park (which DOES
    preserve the worktree) stays inline in `_handle_decomposing` so
    `keep_worktree` is set BEFORE the park's side effects run.
    """
    # Live pause: an operator applied `paused` / `backlog` while the
    # decomposer ran (fresh spawn or awaiting-human resume). Dispatch only
    # saw the pre-run labels, so re-check a freshly fetched issue and return
    # WITHOUT folding usage, parking on timeout, creating child issues,
    # relabeling, or writing pinned state -- durable GitHub state stays
    # exactly as the prior tick left it and the next tick re-runs the
    # decomposer once the label is removed. The read-only decompose worktree
    # is torn down by the caller's `finally` as on any normal exit and
    # recreated on the re-run.
    if _guards._paused_during_agent_run(gh, issue):
        return True

    state.set("last_agent_action_at", _usage._now_iso())
    # Fold this run's usage into the per-issue counters at the convergence
    # of the fresh-spawn and awaiting-human resume branches, so a real
    # resume exit is counted exactly once and the no-new-comment resume
    # (which returned above without running the agent) never touches the
    # counters. Interrupted runs are excluded entirely: the read-only
    # dirty/commits park below still writes pinned state (to preserve the
    # inspection worktree), so folding a killed run's usage first would
    # persist a counter the interrupted contract says must not accrue. The
    # clean-interrupted case is additionally short-circuited by the
    # `_ignore_if_interrupted` guard in `_handle_decomposing`.
    if not decomposer_result.interrupted:
        _usage._accumulate_issue_usage(state, decomposer_result.usage)

    if decomposer_result.timed_out:
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} decomposer timed out after "
            f"{config.AGENT_TIMEOUT}s, manual intervention needed.",
            reason="decomposer_timeout",
        )
        gh.write_pinned_state(issue, state)
        return True
    return False


def _prepare_decomposer_run(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> _DecomposerRunPlan:
    # User-content drift FIRST, so it runs BEFORE the half-finished recovery:
    # otherwise recovery could finalize against a stale manifest when the issue
    # was edited during a crash window.
    _drift._reset_decomposing_on_drift(gh, issue, state)

    if _recovery._recover_stale_manifest(gh, issue, state):
        return _DecomposerRunPlan(agent_result=None)

    if _handoff._route_disabled_to_implementing(gh, spec, issue, state):
        return _DecomposerRunPlan(agent_result=None)

    if state.get(_state._AWAITING_HUMAN):
        decomposer_result = _session._resume_decomposer_on_human_reply(
            gh, spec, issue, state,
        )
        return _DecomposerRunPlan(
            agent_result=decomposer_result,
            # A no-reply dirty park keeps its inspection worktree intact.
            keep_worktree=decomposer_result is None,
        )
    return _DecomposerRunPlan(
        agent_result=_session._spawn_fresh_decomposer(gh, spec, issue, state),
    )


def _process_decomposer_run(
    gh: _client.GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    run_plan: _DecomposerRunPlan,
) -> None:
    decomposer_result = run_plan.agent_result
    if decomposer_result is None:
        return

    # A launch the agent-run circuit refused reached no process, so nothing
    # below is about this run: the worktree it would be judged on carries
    # whatever an earlier one left, and a `decomposer_dirty` park in its name
    # would overwrite the durable park the refusal itself took.
    if _guards._ignore_if_never_invoked(issue, decomposer_result):
        return

    if _settle_decomposer_run(gh, issue, state, decomposer_result):
        return

    # The decomposer is read-only. Preserve a changed worktree for operator
    # inspection, setting the cleanup policy before parking or persistence can
    # raise and trigger the handler's finally block.
    wt = _worktree_decomposition._decompose_worktree_path(spec, issue.number)
    if (
        _worktree_creation._has_new_commits(spec, wt)
        or _verification_probes._worktree_dirty_files(wt)
    ):
        run_plan.keep_worktree = True
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} decomposer left commits or "
            "uncommitted changes in the worktree, but it must be "
            "read-only. Reset the worktree before resuming.",
            reason="decomposer_dirty",
        )
        gh.write_pinned_state(issue, state)
        return

    # An interrupted run has no trustworthy manifest. The read-only check
    # stays first so changes left by a killed run remain available to inspect.
    if _guards._ignore_if_interrupted(issue, decomposer_result):
        return

    _outcomes._dispatch_decomposer_manifest(gh, issue, state, decomposer_result)


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
    state = gh.read_pinned_state(issue)
    # Ahead of the late route as well as the gates below it: a retry-cap park
    # is this budget's, not the size gate's, and the sentence it owes is owed
    # whichever of the two questions wearing this label the tick is about.
    _retry_budget._replay_owed_notice(gh, issue, state)
    if _late_adjudication_owns_the_tick(gh, spec, issue, state):
        return
    # The spent-budget park, ahead of every road below that would walk past
    # one: the drift reset and the kill switch both clear park flags, and the
    # resume reads a reply as the answer -- and this park is answered by a
    # human buying another attempt, not by an edit, a setting, or a comment.
    if _retry_cap._park_owns_the_tick(gh, issue, state):
        return
    cleanup = _DecomposerCleanup(
        spec=spec,
        issue_number=issue.number,
        run_plan=_DecomposerRunPlan(agent_result=None),
    )
    with ExitStack() as cleanup_stack:
        cleanup_stack.callback(cleanup.close)
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
