# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a mid-implementation edit to the requirements is answered with.

Re-decomposing is off the table once code exists -- too disruptive -- so the
locked dev session decides what the new body means instead. The session is what
routes it: with one recorded, the human is told and the session is resumed with
the updated requirements and the conversation so far quoted; without one, the
pre-session path answers instead.

What records the new baseline is the settlement of a prompt somebody read, and
nothing else on this road. A resume that reached an agent records the revision
its own prompt fingerprints; a spawn the pre-session road hands the edit to
records the revision ITS prompt carried; and a tick that delivered nothing --
a refusal park, a launch the run circuit turned away, a shutdown kill, a live
pause -- records nothing at all, so the edit is still there for whoever
answers it next. Written ahead of the run instead, the baseline would mark an
edit answered by a prompt no agent ever read: the continuation a human buys
would spawn against requirements nothing on the issue still calls new, and the
words on the thread would reach that spawn recorded as already delivered.

The resumed run's answer is the disposition's (`drift_disposition`), which is
wider than a normal run's because an edit has a fourth possible answer.

What the edit is recorded as answered by is the RUN, on either road. The
resume freezes its prompt and its delivery record together and settles that
record once the run is back, for every outcome that reached an agent -- a
push, an ACK, a timeout, a question -- and for none that did not. The
pre-session road settles nothing itself: clearing a park delivers nothing, so
the edit is settled by the fresh spawn below it, against the conversation that
spawn actually quoted.

The resume is launched on the drift road, frozen over that same reading
(`drift_road`), so a return a live hold, a lost write, or a restart keeps from
the disposition is captured with the report it wrote, and the dispatcher's
recovery answers it through that same disposition with no developer run
(`captured_drift`).
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    comments as _comments,
    drift_delivery as _drift_delivery,
    retry_ledger as _retry_ledger,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    captured_report as _captured_report,
    completion_roads as _completion_roads,
    drift_disposition as _drift_disposition,
    drift_preflight as _drift_preflight,
    drift_road as _drift_road,
    models as _models,
    resume as _resume,
    worktree as _worktree,
)
from orchestrator.workflow.stages.implementing.drift_models import _ImplementingDriftRun
from orchestrator.workflow.stages.implementing.resume_request import _DevResumeRequest
from orchestrator.workflow.stages.implementing.state import _BRANCH, _DEV_AGENT, _EDIT_OWNS_THE_TICK
from orchestrator.workflow.state import WorkflowLabel


def _handle_user_content_drift(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> str:
    """React to a human editing the issue title/body after the dev spawned.

    Which road answers it decides what happens, and none of them records a
    baseline the run behind it has not earned:
      * With a recorded dev session -> notify the human, resume the locked
        session with the updated requirements quoted from one frozen read, and
        dispose the result (publish a fresh commit, park a
        commit-less timeout, ACK an explicit "existing work satisfies" reply,
        or park the question), settling that read where the run reached an
        agent. Always owns the tick -- the caller must return.
      * Without a dev session but with recovered unpushed commits from a prior
        tick -> refuse the tick outright (those commits never saw the edited
        body), owning it for as long as the operator leaves them there.
      * Without a dev session and without recovered commits -> clear any park
        and hand the edit to the fresh-spawn path: that spawn builds the
        implement prompt from the current `issue.body` and settles both the
        conversation it quoted and the revision it answers, so a spawn the
        budget refuses leaves the edit exactly as it found it.
      * With a dev session but an UNSPENT continuation on the issue -> the
        pre-session road as well, whatever the transcript could have said. An
        issue parked on a spent budget sits there for as long as it takes a
        human to answer, so the requirements move under it -- and what that
        human bought is one FRESH spawn, the only run this stage charges.
        Resumed here the agent would run against the edit with the grant
        still sitting on the issue, ready to buy a second run the budget
        never saw.

    The issue spec ("don't re-decompose mid-implementation -- too disruptive")
    rules out routing back to `decomposing`; the locked session decides what to
    do with the new body instead.
    """
    if state.get(_DEV_AGENT) and not _retry_ledger._grant_is_unspent(state):
        _resume_dev_on_implementing_drift(gh, spec, issue, state)
        return _EDIT_OWNS_THE_TICK
    return _drift_preflight._handle_pre_session_drift(gh, spec, issue, state)


def _run_implementing_drift_resume(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    checkout: _completion_roads.RoadCheckout,
) -> _ImplementingDriftRun:
    answered = _drift_delivery._drift_resume_prompt(gh, issue, state)
    resumed = _resume._resume_dev_with_text(_DevResumeRequest(
        gh, spec, issue, state, answered.text, pause_guard=True,
        # The re-grounding conversation a rotated, retired or poisoned
        # session's respawn is given, handed over rather than read again:
        # taken there it would be a second reading, minutes newer than the
        # record this tick settles, and the comment written in between would
        # reach the agent and be handed to it again on the next poll.
        thread_text=answered.delivery.rendered_text,
        # Frozen over that same reading, so a return a live hold, a lost
        # write, or a restart discards is captured with the report it wrote.
        completion=_drift_road.road(
            WorkflowLabel.IMPLEMENTING, state, _drift_road.DriftReading.settled_by(answered.delivery, state), checkout,
        ),
    ))
    captured = _captured_report.pending_source(state, resumed[1])
    return _ImplementingDriftRun.finished(checkout.before_sha, resumed, answered.delivery, captured)






def _resume_dev_on_implementing_drift(
    gh: _client.GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: _pinned_state.PinnedState,
) -> None:
    # Resolved and prepared ahead of the notice, so a record naming no branch
    # live work may use, or a checkout that is not the issue's own, is refused
    # before anything is said or run.
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    worktree = _worktree._ensure_resume_worktree(spec, issue, state)
    _comments._post_issue_comment(
        gh, issue, state,
        ":pencil2: issue body changed; resuming dev session with "
        "the updated requirements.",
    )
    drift = _run_implementing_drift_resume(
        gh, spec, issue, state, _drift_road.launched_in(spec, issue.number, state, worktree),
    )
    state.set("last_agent_action_at", _usage._now_iso())
    state.set(_BRANCH, branch)
    _drift_disposition._dispose_implementing_drift(gh, spec, issue, state, drift)


def _settle_edit_on_the_spawn(
    state: _pinned_state.PinnedState, prepared: _models._PreparedDevRun,
) -> None:
    """Settle a pre-session edit against the spawn that answered it.

    The park clearing that let this tick spawn delivered nothing to anybody,
    so what the edit is recorded as answered by is the fresh prompt below it:
    the conversation that prompt quoted, and only for a run that read it. The
    caller has already returned on a shutdown kill and on a live pause, which
    leaves the launch nothing invoked -- and the recovered publication no
    agent ran for, which carries no record at all.
    """
    if prepared.delivery is not None and prepared.agent_result.invoked:
        prepared.delivery.settle(state)
