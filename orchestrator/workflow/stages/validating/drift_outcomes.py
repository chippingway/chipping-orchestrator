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

A silent reply that ends on a report outcome is neither: the prompt asks for a
report whenever the report has to change to answer the edit, and a report needs
no commit to be delivered. So where the caller named what its resume was
handed, the report is recorded for the head the pull request carries and the
reply is routed as an acknowledgement -- and a commit this run made is held to
the same contract before the gate reads it. `drift_reports` owns the recording,
and the caller binds what was recorded once its own bookkeeping is written.

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
from orchestrator.workflow.engine import comments as _comments, guards as _guards, messages as _messages
from orchestrator.workflow.stages.implementing import parks as _dev_parks
from orchestrator.workflow.stages.validating import (
    dev_fix as _dev_fix,
    drift_reports as _drift_reports,
    models as _models,
    state as _state,
)


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
    if publishable is None or _drift_reports._withholds_the_stranded(state, publishable):
        return _dispose_silent_reply(gh, issue, state, run)
    return _publishes_the_fix(gh, spec, issue, state, publishable)


def _publishes_the_fix(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    """Push what the resume left through the gate, its report recorded first.

    The report goes onto the comment before the gate reads the candidate,
    since past that line the gate can hold it, the push can fail, and the
    process can die -- and the session that wrote it is already gone. Binding
    it to the publication the push left is the caller's, behind its own
    bookkeeping.
    """
    if run.handed is not None and _drift_reports._records_the_run(
        gh, issue, state, run,
    ):
        return _state._OUTCOME_PARKED
    if not _dev_fix._publish_dev_fix(gh, spec, issue, state, run):
        return _state._OUTCOME_PARKED
    return _state._OUTCOME_PUSHED


def _dispose_silent_reply(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    """Read a resume that left nothing to publish: a report, an ACK, or a question.

    A report comes first, because the drift prompt asks for one whenever the
    report has to change to answer the edit -- and it needs no commit to be
    delivered, so reading it as the question it is not would park an issue
    whose developer finished. A stranded commit still owed its report is
    nothing to publish either, so its reply is read here too.
    """
    if run.handed is not None and _drift_reports._reports(run.agent_result):
        return _drift_reports._records_a_report_alone(gh, issue, state, run)
    ack_reason = _messages._drift_ack_reason(
        run.agent_result.last_message or "",
    )
    if ack_reason:
        _post_drift_ack(gh, issue, state, ack_reason)
        return "ack"
    _dev_parks._on_question(
        gh, issue, state,
        _guards._ParkedRun(
            run.agent_result,
            _guards._ROUTE_DEV_DRIFT_RESUME,
        ),
    )
    return _state._OUTCOME_PARKED


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
    * ``"reported"`` -- only where the caller named what the resume was
      `handed`: the dev produced no commit and ended on a report outcome,
      which is recorded for the head the pull request already carries.
      Routed like an ack -- the same head, re-reviewed against the new
      requirements -- with the reviewer held until the report is confirmed.
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

    A caller naming `handed` also holds the run to the report contract: the
    report of a commit this run made is recorded before the gate -- a run
    that committed with none parks instead -- and a stranded commit the issue
    already owes a report for is not published without one. The caller binds
    what was recorded, on ``"pushed"`` and ``"reported"``, once its own
    bookkeeping is written.
    """
    state, run = _models._dev_fix_run(context_args, fields)
    return _dispose_user_content_change_result(gh, spec, issue, state, run)
