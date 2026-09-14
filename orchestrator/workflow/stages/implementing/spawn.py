# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Deciding what one implementing tick actually runs, if anything.

The first question is not which prompt to build -- it is whether the issue is
parked. An awaiting-human tick belongs to the human's reply (or to the quiet
timeout recovery); only an unparked one is allowed to spawn.

An unparked tick still has a shortcut before the agent: a worktree that already
carries commits is a previous run whose publication was interrupted, so the
recovered result is synthesized and the commits are pushed rather than
implemented again. Neither road is taken on an issue that still owes a push
for a commit the size gate approved: that commit is what the tick is about,
so it publishes from a checkout standing on it and parks for the worktree
otherwise -- because the ahead-of-base question the shortcut asks re-decides a
settled one, and the spawn would buy a second developer run for an
implementation that is already written. The one issue the shortcut is not
true of is one a read-only relabel just let through
-- a discussion may be held on the branch its PR is open against, so the
commits there predate this stage entirely, and the guard records the tip it
certified for exactly this read. Then the retry budget
gates the spawn -- retiring the pinned session where a continuation is what
paid for it, since what a human bought is a fresh conversation and the run
records an id of its own only when the backend hands one back -- and the
agent spec is
persisted BEFORE the run -- so a spawn that commits but returns no session id
still leaves the durable role identity behind and a later `DEV_AGENT` flip
cannot retarget the next resume at a backend that never ran on this issue.

`before_sha` is captured on every path, including the shortcut, because the
disposition downstream distinguishes a commit produced by THIS run from
carried-over work by comparing against it. The branch is persisted on every
prepared run for the same reason: whatever the next tick resolves has to be the
branch this one worked on.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models, settings as config
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    naming as _naming,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    issue_usage as _issue_usage,
    prompt_context as _prompt_context,
    prompts as _prompts,
    retry_budget as _retry_budget,
    retry_ledger as _retry_ledger,
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    disposition as _disposition,
    drift_preflight as _drift_preflight,
    models as _models,
    session as _session,
    session_read as _session_read,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _recovered_dev_result(state: PinnedState) -> AgentResult:
    return AgentResult(
        session_id=_session_read._read_dev_session(state)[3],
        last_message="(orchestrator restart: pushing previously committed work)",
        exit_code=0,
        timed_out=False,
        stdout="",
        stderr="",
    )


def _spawn_implementer(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> tuple[AgentResult, bool] | None:
    if not _charge_fresh_spawn(gh, issue, state):
        gh.write_pinned_state(issue, state)
        return None
    session = _models._DevSession(*_session_read._read_dev_session(state))
    state.set(_state._DEV_AGENT, session.spec)
    agent_result = _usage._run_agent_tracked(
        gh,
        _run_charge_state.AgentRunBudget(issue=issue, state=state),
        agent_role="developer",
        stage=_state._IMPLEMENTING_STAGE,
        backend=session.backend,
        prompt=_prompts._build_implement_prompt(
            spec,
            issue,
            _prompt_context._recent_comments_text(issue),
            config.default_repo_specs(),
        ),
        cwd=worktree,
        agent_spec=session.spec,
        extra_args=session.extra_args,
        review_round=state.get("review_round", 0),
        retry_count=state.get(_state._RETRY_COUNT),
    )
    _issue_usage._accumulate_issue_usage(state, agent_result.usage)
    if agent_result.session_id:
        state.set(_state._DEV_SESSION_ID, agent_result.session_id)
        state.set(_state._DEV_RESUME_COUNT, 0)
    return agent_result, _guards._paused_during_agent_run(gh, issue)


def _charge_fresh_spawn(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Gate one fresh spawn, and make it a fresh SESSION where a grant pays.

    The budget refuses or charges as it always has. What is here is the other
    half of what a continuation buys: an attempt a human paid for is a fresh
    spawn, so the transcript that ran the budget out may not still be pinned
    when it finishes.

    Asked on this road rather than only where the command is read, because
    the grant is DURABLE and the tick that spends it need not be the tick
    that granted it. A process that dies in between comes back to an unparked
    issue with the attempt still owed, and the budget is shared with
    decomposing, so an issue can reach this spawn carrying a grant taken out
    on a park this stage never saw -- with a `dev_session_id` from an earlier
    cycle still on it. Left there, it survives a run that hands back no id of
    its own (`_spawn_implementer` records one only when the backend returns
    it), and the next ordinary reply resumes the conversation the cap
    stopped.

    The grant is read BEFORE the charge and the retirement taken after it,
    because the gate is what spends the grant: read the other way round there
    would be nothing left to recognize. A refused tick retires nothing, since
    nothing ran.
    """
    granted = _retry_ledger._grant_is_unspent(state)
    if not _retry_budget._charge_or_park(
        gh, issue, state, stage=_state._IMPLEMENTING_STAGE,
    ):
        return False
    if granted:
        _session._drop_poisoned_dev_session(state)
    return True


def _recovered_work_present(
    spec: _config_models.RepoSpec, state: PinnedState, worktree: Path, before_sha: str,
) -> bool:
    """True when the commits on the branch are a previous dev run's.

    "Ahead of base" is the whole test for an issue that reached this stage the
    ordinary way: nothing but a dev run puts commits there, so finding some
    means a run committed and died before its publication. It is not the test
    for an issue a read-only relabel let through, because those are allowed to
    arrive on a branch that already carries a PR's commits -- the relabel
    guard certified them, recording the tip it vouched for, and reading them
    as a finished run would skip the implementer and republish the design's
    predecessor as the work the discussion just agreed to.

    The baseline is spent as soon as it stops describing the branch: once the
    dev commits, HEAD moves off it and every later tick is judged the ordinary
    way again.

    Which makes that a COMPARISON, and a comparison whose head could not be
    read establishes nothing. `_head_sha` reports its own failure as "", so an
    unread checkout arrives here differing from the certified tip exactly as a
    checkout the dev has committed on does -- and read that way the baseline
    is spent, the implementer is skipped, and the design's predecessor is
    republished as the work the discussion just agreed to. So a baseline
    stands until something shows the branch has moved off it. The road with no
    baseline is untouched, and deliberately: there the commits ARE a previous
    run's whatever the probe says, and refusing them would buy a second
    developer over an implementation the first one already finished.
    """
    if not _worktree_creation._has_new_commits(spec, worktree):
        return False
    baseline = state.get(_state._READ_ONLY_BASELINE_SHA)
    if not baseline:
        return True
    if not before_sha or str(baseline) == before_sha:
        return False
    state.set(_state._READ_ONLY_BASELINE_SHA, None)
    return True


def _ensure_dev_worktree(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> Path:
    """Prepare the dev checkout, restoring a pruned one from the right ref.

    A fresh implementing run belongs at base, and `_ensure_worktree` puts a
    missing branch there. An issue that already has a PR does not: it reaches
    this stage carrying commits the PR is open against -- a discussion relabel
    is the way in -- and rebuilding its local ref from `<remote>/<base>` would
    hand the dev an empty tree, then let publication force-push that over the
    PR. `_ensure_pr_worktree` restores from the PR head instead, which is only
    a ref to ask for once a PR exists, so `pr_number` decides.
    """
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    if state.get("pr_number") is None:
        return _worktree_creation._ensure_worktree(
            spec, issue.number, branch=branch,
        )
    return _worktree_creation._ensure_pr_worktree(
        spec, issue.number, branch=branch,
    )


def _prepare_active_dev_run(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> _models._PreparedDevRun | None:
    """Run or recover one unparked dev tick, once the checkout can be trusted.

    The size gate's own recovery comes first, and it is here rather than in
    the preflight because it is a question about the RESTORED checkout. An
    approval this issue has not published yet names a commit, and that commit
    is the whole of what the tick is about: it publishes from the checkout
    standing on it, and parks for the worktree where nothing here can show it.

    Neither of the two roads below may be taken on one. The shortcut asks
    whether the branch is ahead of base, which answers "nothing to publish"
    for a base that has since absorbed the commit and "fresh candidate" for
    one that has not -- re-deciding a settled question either way -- and the
    spawn would pay for a second developer over an implementation the first
    one already finished.
    """
    worktree = _ensure_dev_worktree(spec, issue, state)
    if _disposition._holds_approved_commit(gh, spec, issue, state, worktree):
        gh.write_pinned_state(issue, state)
        return None
    before_sha = _verification_probes._head_sha(worktree)
    if _recovered_work_present(spec, state, worktree, before_sha):
        log.info(
            "issue=#%d skipping agent; worktree already has commits",
            issue.number,
        )
        return _models._PreparedDevRun(
            _recovered_dev_result(state), before_sha, False, worktree,
            recovered=True,
        )
    spawned = _spawn_implementer(gh, spec, issue, state, worktree)
    if spawned is None:
        return None
    agent_result, paused = spawned
    return _models._PreparedDevRun(agent_result, before_sha, paused, worktree)


def _prepare_dev_run(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
) -> _models._PreparedDevRun | None:
    """Set up and run (or recover) the dev agent for one implementing tick.

    Returns a prepared run for the caller to dispose, or None
    when the tick is already complete and the caller must return:
      * awaiting-human with an `agent_timeout` park and no human reply -> a
        silent `_try_recover_implementing_timeout_park` attempt (state written
        here on "pushed", left parked on "stuck");
      * awaiting-human resume with no new comments -> nothing to do;
      * a fresh spawn blocked by the 24h retry cap (parked, state written).

    `before_sha` is the pre-agent HEAD watermark the timeout disposition uses
    to tell a commit produced by THIS run from carried-over commits already on
    the branch.
    """
    if state.get(_state._AWAITING_HUMAN):
        prepared = _drift_preflight._prepare_awaiting_dev_run(gh, spec, issue, state)
    else:
        prepared = _prepare_active_dev_run(gh, spec, issue, state)
    if prepared is not None:
        state.set(
            _state._BRANCH,
            _naming._resolve_branch_name(state, spec, issue.number),
        )
    return prepared
