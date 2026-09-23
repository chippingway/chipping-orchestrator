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

The disposition is wider than a normal run's because an edit has a fourth
possible answer. A fresh commit publishes, a commit-less timeout parks, a
question parks -- and a dev that replies "the existing work already satisfies
this" is ACKed rather than parked, which is what keeps a no-op edit from sitting
awaiting a human who has nothing left to say. That ACK also clears the
silent-park streak: the session answered, so it is not the poisoned one the
streak is counting.

A commit-less reply has one more reading, and it is the same one the ordinary
disposition makes: an issue still owing a report it could not deliver was never
waiting for code, so a run that comes back with a report publishes the commits
the branch already carries rather than parking as a question. A human's reply
to a park reaches the park's own resume rather than this road -- the drift
check measures a parked issue by what the park had already read -- so this
road meets that debt only where an edit came with the reply.

What the edit is recorded as answered by is the RUN, on either road. The
resume freezes its prompt and its delivery record together and settles that
record once the run is back, for every outcome that reached an agent -- a
push, an ACK, a timeout, a question -- and for none that did not. The
pre-session road settles nothing itself: clearing a park delivers nothing, so
the edit is settled by the fresh spawn below it, against the conversation that
spawn actually quoted.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.agents import models as _agent_models
from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    comments as _comments,
    drift_delivery as _drift_delivery,
    guards as _guards,
    messages as _messages,
    prompt_delivery as _delivery,
    report_redelivery as _report_redelivery,
    retry_ledger as _retry_ledger,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    candidate_recovery as _candidate_recovery,
    disposition as _disposition,
    drift_preflight as _drift_preflight,
    models as _models,
    parks as _parks,
    resume as _resume,
    session_read as _session_read,
    worktree as _worktree,
)
from orchestrator.workflow.stages.implementing.state import (
    _BRANCH,
    _CODEX_SESSION_ID,
    _DEV_AGENT,
    _EDIT_OWNS_THE_TICK,
    _SILENT_PARK_COUNT,
)


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
    session = state.get(_DEV_AGENT) or state.get(_CODEX_SESSION_ID)
    if session and not _retry_ledger._grant_is_unspent(state):
        _resume_dev_on_implementing_drift(gh, spec, issue, state)
        return _EDIT_OWNS_THE_TICK
    return _drift_preflight._handle_pre_session_drift(gh, spec, issue, state)


@dataclass(frozen=True)
class _ImplementingDriftRun:
    worktree: Path
    agent_result: _agent_models.AgentResult
    before_sha: str | None
    paused: bool
    committed: bool
    # The record of what this resume's prompt actually quoted, which is what
    # the disposition settles. It travels with the run rather than being
    # re-read after it: the thread moves while an agent is out, and a mark
    # taken off what it ends on crosses replies nobody delivered.
    delivery: _delivery.PromptDeliverySnapshot

    @classmethod
    def finished(
        cls,
        before_sha: str | None,
        resumed: tuple[Path, _agent_models.AgentResult, bool],
        delivery: _delivery.PromptDeliverySnapshot,
    ) -> _ImplementingDriftRun:
        """One finished resume, told from the head it started on."""
        worktree, agent_result, paused = resumed
        after_sha = _verification_probes._head_sha(worktree)
        return cls(
            worktree=worktree,
            agent_result=agent_result,
            before_sha=before_sha,
            paused=paused,
            committed=bool(after_sha) and after_sha != before_sha,
            delivery=delivery,
        )


def _run_implementing_drift_resume(
    gh: _client.GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: _pinned_state.PinnedState,
) -> _ImplementingDriftRun:
    worktree = _worktree._ensure_resume_worktree(spec, issue, state)
    before_sha = _verification_probes._head_sha(worktree)
    answered = _drift_delivery._drift_resume_prompt(gh, issue, state)
    resumed = _resume._resume_dev_with_text(
        gh, spec, issue, state, answered.text, pause_guard=True,
        # The re-grounding conversation a rotated, retired or poisoned
        # session's respawn is given, handed over rather than read again:
        # taken there it would be a second reading, minutes newer than the
        # record this tick settles, and the comment written in between would
        # reach the agent and be handed to it again on the next poll.
        thread_text=answered.delivery.rendered_text,
    )
    return _ImplementingDriftRun.finished(before_sha, resumed, answered.delivery)


def _post_implementing_drift_ack(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState, reason: str,
) -> None:
    quoted = _session_read._as_blockquote(reason)
    _comments._post_issue_comment(
        gh, issue, state,
        ":speech_balloon: dev session reports the existing "
        f"work satisfies the edit:\n\n{quoted}",
    )
    state.set(_SILENT_PARK_COUNT, 0)


def _dispose_implementing_drift(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    drift: _ImplementingDriftRun,
) -> None:
    if (
        _guards._ignore_if_never_invoked(issue, drift.agent_result)
        or _guards._ignore_if_interrupted(issue, drift.agent_result)
        or drift.paused
    ):
        return
    # Every run that consumes nothing has returned by now, so what is left
    # read the prompt -- a timeout and a question included, since what the
    # park that follows says is wrong is the answer rather than the input.
    drift.delivery.settle(state)
    if drift.committed or _report_redelivery.redelivers_an_owed_report(
        spec, state, drift.agent_result, drift.worktree,
    ):
        _candidate_recovery._publish_committed_work(
            gh, spec, issue, state,
            _models._AgentWork(drift.agent_result, drift.worktree),
        )
    elif drift.agent_result.timed_out:
        _disposition._park_agent_timeout(gh, issue, state, drift.before_sha)
    else:
        ack_reason = _messages._drift_ack_reason(
            drift.agent_result.last_message or "",
        )
        if ack_reason:
            _post_implementing_drift_ack(gh, issue, state, ack_reason)
        else:
            _parks._on_question(
                gh, issue, state,
                _guards._ParkedRun(
                    drift.agent_result,
                    _guards._ROUTE_DEV_DRIFT_RESUME,
                ),
            )
    gh.write_pinned_state(issue, state)


def _resume_dev_on_implementing_drift(
    gh: _client.GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: _pinned_state.PinnedState,
) -> None:
    _comments._post_issue_comment(
        gh, issue, state,
        ":pencil2: issue body changed; resuming dev session with "
        "the updated requirements.",
    )
    drift = _run_implementing_drift_resume(gh, spec, issue, state)
    state.set("last_agent_action_at", _usage._now_iso())
    state.set(
        _BRANCH,
        _naming._resolve_branch_name(state, spec, issue.number),
    )
    _dispose_implementing_drift(gh, spec, issue, state, drift)


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
