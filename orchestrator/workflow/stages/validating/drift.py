# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A body edit that arrives while the reviewer is running.

Re-decomposing at this point would throw away work the dev has already pushed,
so the edit resumes the locked dev session on the new body instead. A landed
fix bumps `review_round` and stays on `validating`: the reviewer has to read
the updated body against the new diff, and the round it already spent was
against a head that no longer exists.

Three parks deliberately opt out, and the reason is who owns the human's next
comment. A reviewer timeout or silent crash produced no review output for the
dev to act on, so a "retry" reply has to re-spawn the REVIEWER -- and the
reviewer re-reads the edited body itself when it runs. `review_cap` is
sharper still: the cap has consumed every round, so resuming the dev would
just re-park on it, and the operator's `/orchestrator add-review-rounds`
comment is itself content that moves the drift hash -- without the bypass the
drift block would fire first and the command would never be parsed. A deferral
delivers the edit to nobody, so it records nothing about it: the reply it
stands down for has its own words recorded by the road that acts on them and
the requirements beside them by the round that runs, and an edit no prompt has
carried is still an edit on the tick after this one.
What it does record is the round it stood down FOR, because a silent recovery
clears the park and ends its tick while the round it released runs on the
next: without that note the edit would take the following tick down this road
ahead of the retry the park was taken for.

What the dev is quoted and what the issue may mark answered come off ONE read,
frozen with the prompt and settled once the run is back. The dev sees that
conversation inside the resume prompt, so leaving the watermark behind would
let the in_review handoff replay those same comments as fresh feedback --
while a mark taken to the thread's tip would cross the context the excerpt
bound left out, a reply written while the agent was out, and a run no
developer ever read the prompt through.

The requirements revision the resume is handed is the one its own prompt
fingerprints, and it travels with the run rather than being read back off the
comment: the report the session writes is stamped with it, however long its
publication takes. It is the delivery's rather than the drift check's, because
those two readings are taken a moment apart -- a reply written in between is in
the prompt and in the baseline the settlement records, and a report stamped
with the earlier revision would be held against requirements the issue has
already moved past and never published. A commit's report is recorded before
the push and bound once it lands; a report alone goes onto the unchanged head
and spends no round, exactly as an `ACK:` does. Either way the reviewer waits
for the report to be confirmed on the pull request, which is `report_hold`'s;
the binding is `report_settlement`'s.

What the resume freezes for the helper that finishes it is a record only this
route builds and only this route reads, so it answers on `drift_models.py`
beside this owner rather than on the stage's shared `models.py`.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _engine_drift,
    drift_delivery as _drift_delivery,
    guards as _guards,
    report_delivery as _report_delivery,
    report_records as _records,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    resume as _dev_resume,
    resume_batch as _resume_batch,
)
from orchestrator.workflow.stages.validating import (
    drift_models as _drift_models,
    drift_outcomes as _outcomes,
    models as _models,
    report_settlement as _report_settlement,
    rounds as _rounds,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel


def _run_validating_drift(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> _drift_models._ValidatingDriftRun:
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if not worktree.exists():
        worktree = _worktree_creation._ensure_worktree(
            spec,
            issue.number,
            branch=_naming._resolve_branch_name(state, spec, issue.number),
        )
    before_sha = _verification_probes._head_sha(worktree)
    answered = _drift_delivery._drift_resume_prompt(gh, issue, state)
    worktree, agent_result, paused = _dev_resume._resume_dev_with_text(
        gh, spec, issue, state, answered.text, pause_guard=True,
        # The frozen conversation the fresh-respawn preamble is re-grounded
        # with, so a rotated or retired session is handed this tick's one
        # read rather than a newer one the settlement never saw.
        thread_text=answered.delivery.rendered_text,
    )
    return _drift_models._ValidatingDriftRun(
        worktree, agent_result, before_sha, paused, answered.delivery,
    )


def _defer_validating_drift(state: PinnedState) -> bool:
    """Whether the reviewer owns this tick rather than the developer.

    A round this stage already stood down for outranks the park that asked
    for it, because the park is gone by the time that round runs: the silent
    recovery clears the flags and ends its tick, a report still owed holds
    the reviewer behind a clear already written, and the round runs a tick or
    more later. Read off the park alone, the edit would take that tick down
    the developer's road ahead of the retry -- so the deferral's own record
    answers first.

    Never while the pull request is still owed a report, whoever the round
    belongs to. No reviewer runs behind that debt, and the record it is owed
    was written against requirements a reply has already moved -- which the
    reconciliation stands down on until a resume answers the edit. Standing
    down for a round that hold is stopping would leave the two waiting on
    each other for the life of the issue with nobody told, so the edit takes
    the developer's road and the note stands for the round behind it.
    """
    if _report_delivery.owes_a_report(state):
        return False
    if state.get(_state._REVIEWER_OWES_A_ROUND):
        return True
    return bool(
        state.get("awaiting_human")
        and state.get(_state._PARK_REASON)
        in (
            _state._REASON_REVIEWER_TIMEOUT,
            _state._REASON_REVIEWER_FAILED,
            _state._REASON_REVIEW_CAP,
        )
    )


def _finish_validating_drift(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _drift_models._ValidatingDriftRun,
) -> None:
    # What the resume quoted is recorded as answered for every outcome that
    # reached an agent -- the push below, the ACK, the timeout and question
    # parks -- and for none that did not: delivery says the developer was
    # handed those words, never that they are resolved.
    if _resume_batch._counts_as_delivered(run.agent_result, run.paused):
        run.delivery.settle(state)
    owed = _rounds._spends_next_round(state)
    outcome = _outcomes._post_user_content_change_result(
        gh,
        spec,
        issue,
        state,
        run.worktree,
        run.agent_result,
        run.before_sha,
        spends=owed,
        handed=_records.HandedRun(
            WorkflowLabel.VALIDATING, run.delivery.requirements_revision,
        ),
    )
    if _guards._ignore_if_interrupted(issue, run.agent_result):
        return
    if outcome == _state._OUTCOME_PUSHED:
        _rounds._bump_review_round(state, owed)
    gh.write_pinned_state(issue, state)
    if outcome in _state._REPORTING_OUTCOMES:
        _report_settlement._settles_the_report(
            gh, spec, issue, state, WorkflowLabel.VALIDATING,
        )


def _resume_dev_on_validating_drift(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    parked: _models._AwaitingValidation | None = None,
) -> bool:
    """Resume the dev session when a human edited the issue title/body while the
    reviewer was running.

    Re-decomposing now would discard the dev's already-pushed work, so notify
    the human, resume the dev session on its locked backend with the new body,
    and on a successful pushed fix bump `review_round` while staying on
    `validating` (no relabel emitted) so the reviewer re-evaluates the updated
    body + new diff on the next tick. An ACK reply (no commit) keeps the issue
    on `validating`, and so does a report with no commit, which is published
    onto the unchanged head without spending a round. On a failed resume
    (timeout, dirty, no commit), the standard park flags land via
    `_post_user_content_change_result`.

    Returns True when a drift was detected and fully handled (caller must
    return). Returns False when there is no drift, or when the issue is parked
    with a reviewer-side reason (`reviewer_timeout` / `reviewer_failed`) or on
    the review-round cap (`review_cap`) -- those defer to the awaiting-human
    branch. A human "retry" comment on a reviewer-side park must re-spawn the
    REVIEWER, not the dev: the failure produced no review output for the dev to
    act on, and the reviewer re-reads the updated `issue.body` + comments via
    `_build_review_prompt` when it runs. For `review_cap`, the cap has consumed
    every round, so resuming the dev would re-park on the cap next tick; the
    operator's `/orchestrator add-review-rounds` command lives in the
    awaiting-human branch, and the command comment itself bumps the user-content
    hash, so without this bypass the drift block would fire first and the
    command would never be parsed. A deferral records nothing about the edit:
    it delivered the edit to nobody, and the reply it stands down for is
    recorded as answered by that reply's own frozen batch.

    `parked` is the awaiting context a parked tick built first. Its frozen
    batch says what the park had already read, and the requirements are
    measured by that: the replies past it are that batch's to deliver and
    settle, so they are no edit here.

    What the resume itself delivers is frozen with its prompt and settled by
    `_finish_validating_drift`, and that settlement is the only thing on this
    road that records a new baseline. A live pause, a shutdown kill, and a
    launch the run circuit turned away each return without writing pinned
    state, so every road that delivered nothing -- the three deferrals
    included -- leaves the edit as unanswered as it found it.
    """
    new_hash = _engine_drift._detect_user_content_change(
        gh, issue, state,
        answered=None if parked is None else parked.batch.answered,
    )
    if new_hash is None:
        return False
    if _defer_validating_drift(state):
        # Nothing about the edit is recorded here -- it has been delivered to
        # nobody -- but the round being stood down for is, so the tick that
        # clears the park carries it and the drift road stays behind the
        # reviewer rather than overtaking it the moment the flags come off.
        #
        # Only where no claim already stands. A reply that bought the round
        # named itself in this note, and that round owes it a settlement
        # wherever it runs; a deferral writing over the name would leave the
        # round with nothing to record and the reply unread forever.
        if not state.get(_state._REVIEWER_OWES_A_ROUND):
            state.set(_state._REVIEWER_OWES_A_ROUND, True)
        return False

    _comments._post_issue_comment(
        gh, issue, state,
        ":pencil2: issue body changed; resuming dev session.",
    )
    run = _run_validating_drift(gh, spec, issue, state)
    state.set("last_agent_action_at", _usage._now_iso())
    if _guards._ignore_if_never_invoked(issue, run.agent_result):
        # The run circuit turned the launch away: no process read the prompt,
        # so the refusal it recorded where it was decided is the whole of what
        # this tick says. Returning here leaves the round, the park flags and
        # the baseline exactly as they were, and the next tick re-detects the
        # same edit for whatever finally answers it.
        return True
    if run.paused:
        # Live pause applied during the drift resume: the helper already
        # stopped before persisting the session id or clearing
        # `awaiting_human`. Return WITHOUT running the result handler (which
        # would post / push / advance the round) or writing pinned state, so
        # the drift bookkeeping staged above stays unrecorded and the committed
        # work stays on the branch; the next tick re-detects the drift once the
        # label is removed.
        return True
    # Custom result handler: a no-commit-with-message reply is the dev
    # confirming the existing work already satisfies the edit, and the resume
    # prompt explicitly invites that response. `_handle_dev_fix_result` would
    # park on it via `_on_question`; use the user-content-specific helper so a
    # harmless clarification does not stall the issue.
    _finish_validating_drift(gh, spec, issue, state, run)
    return True
