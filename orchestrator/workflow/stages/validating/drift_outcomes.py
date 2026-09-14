# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading a drift resume, where a silent reply means something else.

Everywhere else in this stage a dev run that produced no commit is a question,
and the question park is the safe answer. A body-edit resume is the one place
that would be wrong: the prompt explicitly invites the dev to say the existing
work already satisfies the edit, so parking on that reply would stall an issue
whose only remaining problem is that nobody read the answer.

The `ACK:` marker is what separates the two, and it is required rather than
inferred. A generic non-empty no-commit reply is far more often a clarifying
question, and swallowing one as an acknowledgement would post a misleading
"existing work satisfies" note AND continue with `awaiting_human=False`,
stranding the real question with no one waiting on it.

Everything else defers to the shared fix disposition -- the timeout park, the
stranded-commit gate, the push -- so the two routes cannot disagree about what
a publishable run is. This owner only decides which of them a silent reply is
handed to.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, messages as _messages
from orchestrator.workflow.stages.implementing import parks as _dev_parks
from orchestrator.workflow.stages.validating import dev_fix as _dev_fix, models as _models, state as _state


def _post_drift_ack(
    gh: GitHubClient, issue: Issue, state: PinnedState, reason: str,
) -> None:
    quoted = _messages._as_blockquote(reason)
    _comments._post_issue_comment(
        gh, issue, state,
        ":speech_balloon: dev session reports the existing work "
        f"satisfies the edit:\n\n{quoted}",
    )
    state.set("silent_park_count", 0)


def _dispose_user_content_change_result(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    if run.agent_result.interrupted:
        return _state._OUTCOME_PARKED
    if run.agent_result.timed_out:
        _dev_fix._park_dev_fix_timeout(gh, issue, state, run.before_sha)
        return _state._OUTCOME_PARKED
    publishable = _dev_fix._publishable_dev_fix(spec, issue, state, run)
    if publishable is None:
        ack_reason = _messages._drift_ack_reason(
            run.agent_result.last_message or "",
        )
        if ack_reason:
            _post_drift_ack(gh, issue, state, ack_reason)
            return "ack"
        _dev_parks._on_question(gh, issue, state, run.agent_result)
        return _state._OUTCOME_PARKED
    return (
        _state._OUTCOME_PUSHED
        if _dev_fix._publish_dev_fix(gh, spec, issue, state, publishable)
        else _state._OUTCOME_PARKED
    )


def _post_user_content_change_result(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    *context_args,
    **fields,
) -> str:
    """Post-resume handling for a user-content-change dev resume.

    Returns one of:

    * ``"ack"`` -- the dev produced no commit but explicitly signaled
      acknowledgement via the `ACK: ...` marker emitted by
      `_build_user_content_change_prompt`. The reply is posted on the
      issue as an FYI and the handler does NOT park `awaiting_human`.
      Caller decides what to do with the label: validating stays put
      (the reviewer reruns on the current head); in_review bounces
      back to `validating` (the prior reviewer approval was for the
      old requirements, so the in_review HITL ready-ping must wait
      for a re-approval) WITHOUT spawning `documenting` -- no commit
      landed for the docs pass to react to.
    * ``"pushed"`` -- new commit landed and the push succeeded, OR this
      no-commit run found a committed-but-unpublished fix stranded on the
      branch by a prior parked / interrupted resume and published it (the
      stranded-fix gate, mirroring `_handle_dev_fix_result`).
      Validating stays on `validating` (and bumps `review_round`) so
      the reviewer re-evaluates the new head; in_review also hands
      straight back to `validating`. Docs are not run on this exit --
      the single docs pass is deferred to the final-docs handoff after
      reviewer approval. Any stale approval state must be reset by
      the caller before relabeling.
    * ``"parked"`` -- timeout, dirty tree, push fail, silent crash
      (empty `last_message`), OR a no-commit response WITHOUT the
      `ACK:` marker (treated as a clarification question via
      `_on_question`). State already carries the park flags. A
      shutdown-killed (interrupted) run also returns ``"parked"`` but
      WITHOUT setting any park flags or posting -- the run is ignored
      and the next tick retries the resume.

    The explicit `ACK:` marker is required because a generic non-empty
    no-commit response is often a clarification question, not an
    acknowledgement; swallowing it as an ack would post a misleading
    "existing work satisfies" comment AND continue the workflow with
    `awaiting_human=False`, stranding the real question.
    """
    state, run = _models._dev_fix_run(context_args, fields)
    return _dispose_user_content_change_result(gh, spec, issue, state, run)
