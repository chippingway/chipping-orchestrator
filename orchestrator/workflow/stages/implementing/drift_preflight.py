# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the state has to answer before an awaiting-human tick spawns anything.

Two situations reach here, and both are about work that already exists without a
session to explain it. A body edit that lands before any dev session was
recorded normally just falls through to a fresh spawn against the new body --
unless the worktree carries unpushed commits from an earlier tick, in which case
the tick refuses: those commits never saw the edited requirements, and pushing
them would publish work against a spec the human just changed. Whether to
discard them is the operator's call, so it parks as `stale_recovered_work`.

That refusal records nothing about the edit and everything about itself.
Nothing ran, so there is no prompt to settle and no baseline to move -- but the
park writes its own reason down (`_STALE_RECOVERED_WORK`), which is what lets
the next tick tell its own sentence from a fresh one. Said again it would be
the same words once a poll; unrecognized it would stand in front of the reply
it asked for, since the edit it refused is still an edit every tick. So the
refusal announces once, and after that the tick belongs to whoever answers it:
the road falls through to the park's own resume, which is where a human's reply
is delivered and recorded. A park standing for some OTHER reason hears it --
the refusal supersedes that park, because what the issue is waiting on now is
a decision about those commits.

Clearing a park records nothing either. Nobody has been handed anything at the
moment the flags come off, so the edit is passed on
(`_EDIT_OWED_BY_THE_SPAWN`) and settled by the spawn below against the
conversation that spawn quotes, which is the same rule the resume road keeps,
asked one step later. A spawn the retry budget refuses invokes no agent and
settles nothing, so the edit is still there for the continuation a human buys.

The other is an `agent_timeout` park nobody has replied to. That park is
retryable without a human, so a tick with no new comment tries the quiet
recovery first -- publishing a commit that landed after the timeout -- and only
then falls through. The no-comment condition is the whole gate: once a human HAS
replied, the reply is the signal and the resume path owns the tick instead. A
reply is what that resume would deliver -- the tick's frozen batch -- so a
comment the resume would hand nobody cannot hold the recovery off either.

That batch is the handler's, frozen once before the parked-continue classifier
and handed on through it and the drift check to the resume here, so the
classification, the recovery's gate, the prompt, and the settlement all read
one thread at one moment.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    paths as _worktree_paths,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
)
from orchestrator.workflow.stages.implementing import (
    disposition as _disposition,
    models as _models,
    resume as _resume,
    resume_batch as _resume_batch,
    state as _state,
    worktree as _worktree,
)


def _handle_pre_session_drift(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> str:
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if _worktree_creation._has_new_commits(spec, worktree):
        if state.get(_state._PARK_REASON) == _state._STALE_RECOVERED_WORK:
            return _state._EDIT_OWED_BY_THE_SPAWN
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} issue body changed but the "
            "worktree carries unpushed commits from a previous tick "
            "and no dev session is recorded. Refusing to push commits "
            "that never saw the edited requirements; decide whether "
            "to discard the recovered work (reset the branch) and "
            "let a fresh agent run, or accept it as-is.",
            reason=_state._STALE_RECOVERED_WORK,
            bounded=True,
        )
        state.set(_state._PARK_REASON, _state._STALE_RECOVERED_WORK)
        gh.write_pinned_state(issue, state)
        return _state._EDIT_OWNS_THE_TICK
    if state.get(_state._AWAITING_HUMAN):
        _comments._post_issue_comment(
            gh, issue, state,
            ":pencil2: issue content changed; clearing the park and "
            "spawning a fresh dev run against the updated requirements.",
        )
        state.set(_state._AWAITING_HUMAN, False)
        state.set(_state._PARK_REASON, None)
    return _state._EDIT_OWED_BY_THE_SPAWN


def _recover_quiet_implementer_timeout(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    batch: _resume_batch._ReplyBatch,
) -> bool:
    if state.get(_state._PARK_REASON) != _state._AGENT_TIMEOUT:
        return False
    # The replies the resume behind this would deliver: a comment only this
    # gate counted would hand the tick to a resume with nothing to deliver.
    if batch.comments or batch.reserved:
        return False
    recovery = _disposition._try_recover_implementing_timeout_park(
        gh, spec, issue, state,
    )
    if recovery == "pushed":
        gh.write_pinned_state(issue, state)
    return True


def _prepare_awaiting_dev_run(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    batch: _resume_batch._ReplyBatch,
) -> _models._PreparedDevRun | None:
    if _recover_quiet_implementer_timeout(gh, spec, issue, state, batch):
        return None
    worktree = _worktree._ensure_resume_worktree(spec, issue, state)
    before_sha = _verification_probes._head_sha(worktree)
    resumed = _resume._resume_developer_on_human_reply(
        gh, spec, issue, batch, pause_guard=True,
    )
    if resumed is None:
        return None
    worktree, agent_result, paused = resumed
    return _models._PreparedDevRun(agent_result, before_sha, paused, worktree)
