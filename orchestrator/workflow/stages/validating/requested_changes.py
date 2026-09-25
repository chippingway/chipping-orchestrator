# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two verdicts that are not an approval.

CHANGES_REQUESTED runs its dev fix under the `fixing` label rather than
`validating`, so the active job reads as what it is instead of as reviewer
work. The relabel happens BEFORE the spawn on purpose: a crash inside the
spawn then leaves the issue on `fixing` with `awaiting_human` still false,
which the next tick's fixing handler reads as "no feedback" and bounces back
to `validating` -- whereas a crash after a spawn under the old label would
leave an issue nobody re-enters. A pushed fix bumps the round and relabels
back; any park leaves the issue on `fixing`, whose handler owns the
awaiting-human rescan from there.

What that run hands back is a report as well as, perhaps, a commit, and
`fix_reports` beside this owner holds it to both: the report is recorded ahead
of the size gate, a report with no code in it reaches the pull request on the
head it already carries, and a commit with no report is withheld. Either
handover bumps the round and relabels back, because the next reviewer reads the
report as well as the diff -- but WHEN that round is spent differs: a pushed fix
spent it on a commit the pull request now carries, while a report with no code in
it has bought nothing until it lands, so its round and its replay anchor ride
the record and are closed by the write that settles the report.

The reviewer-feedback comment's id is recorded because a session-failure park
on this route has to be retryable by `/orchestrator continue`, and the fixing
handler replays that exact comment to reconstruct the batch. It is a
standalone key rather than part of the in_review bookmark pair, since
`pending_fix_at` is what tells that route's round RESET from this route's
bump.

A reviewer that emitted no VERDICT line is the other verdict, and it splits by
whose failure it was. An empty last message with a non-zero exit is a crash,
and a message that opens with a transient provider refusal is an outage
wearing the reviewer's output slot; both are tagged transient so the next tick
re-spawns the reviewer -- waking the dev on a human "retry" would hand the
wrong agent a prompt with no review in it. Real text that merely omitted the
marker is left for a human, and the stderr tail is suppressed there because
the human is already reading model output. Unknown-verdict and reviewer-failure
parks forward typed correlation fields (`agent_role`, `session_id`,
`review_round`, `retry_count`, `pr_number`) through the shared park funnel.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents import provider_failures as _provider_failures
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    agent_diagnostics as _agent_diagnostics,
    comments as _comments,
    guards as _guards,
    messages as _messages,
    prompts as _prompts,
    report_records as _records,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    resume as _dev_resume,
)
from orchestrator.workflow.stages.validating import (
    fix_reports as _fix_reports,
    models as _models,
    report_settlement as _report_settlement,
    rounds as _rounds,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")


def _reviewer_no_verdict_park(review) -> tuple[str, str]:
    """Name the park a verdict-less reviewer run earns, and what it is told.

    Two shapes are the provider's failure rather than the reviewer's. A silent
    crash (empty last message + non-zero exit -- codex-side error, network
    blip) leaves no review output the dev could act on. A transient provider
    refusal (`API Error: 529 Overloaded` and its 5xx siblings) leaves a
    NON-EMPTY message that is the server's words, not the reviewer's, and
    reading it as a missing verdict would send an outage to manual
    adjudication. Both are `reviewer_failed`, so the next tick's
    transient-recovery branch re-spawns the reviewer rather than waking the dev
    on a human "Retry" comment -- `_resume_developer_on_human_reply` would
    otherwise hand the wrong agent a do-nothing prompt.

    A reviewer that emitted real text and merely omitted the VERDICT line is
    the one park a human has to read, and it stays `reviewer_no_verdict`.
    """
    if _provider_failures.is_transient_provider_failure(review):
        outage = (
            "the model provider is temporarily unavailable and the review "
            "will be retried on a later tick."
        )
        return _state._REASON_REVIEWER_FAILED, outage
    if not (review.last_message or "").strip() and review.exit_code != 0:
        return _state._REASON_REVIEWER_FAILED, "manual adjudication needed."
    return "reviewer_no_verdict", "manual adjudication needed."


def _park_reviewer_no_verdict(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    review,
    *,
    reviewer_run: _models._ReviewerRun | None = None,
) -> None:
    """Park `validating` when the reviewer produced no VERDICT line.

    `_reviewer_no_verdict_park` splits the transient failures from the one
    that needs a human; the reason it returns is set back on the pinned state
    because `_park_awaiting_human` clears the field by contract. stderr
    diagnostics ride along only when there was no model output at all -- a
    human reading real reviewer text does not need the subprocess tail too.
    Enriches the emitted park event with typed correlation fields
    (`agent_role`, `session_id`, `review_round`, `retry_count`, `pr_number`)
    drawn from the reviewer run and state.
    """
    outcome = _reviewer_no_verdict_park(review)
    raw = (review.last_message or "").strip() or "(reviewer produced no final message)"
    diag = (
        ""
        if (review.last_message or "").strip()
        else _agent_diagnostics._format_stderr_diagnostics(review, "Reviewer")
    )
    round_val = state.get(_state._REVIEW_ROUND) if reviewer_run is None else reviewer_run.round_n
    pr_val = state.get("pr_number") if reviewer_run is None else reviewer_run.pr_number
    _guards._park_awaiting_human(
        gh,
        issue,
        state,
        f"{config.HITL_MENTIONS} reviewer did not emit a VERDICT line; "
        f"{outcome[1]}\n\n_Last reviewer message:_\n\n"
        f"{_messages._as_blockquote(raw)}{diag}",
        reason=outcome[0],
        agent_role="reviewer",
        session_id=review.session_id,
        review_round=_guards._safe_int(round_val),
        retry_count=_guards._safe_int(state.get("retry_count")),
        pr_number=_guards._safe_int(pr_val),
        bounded=True,
    )
    if outcome[0] == _state._REASON_REVIEWER_FAILED:
        state.set(_state._PARK_REASON, _state._REASON_REVIEWER_FAILED)
    log.warning(
        "issue=#%s reviewer emitted no VERDICT; exit_code=%d "
        "timed_out=%s stderr_tail=%r",
        issue.number, review.exit_code, review.timed_out,
        _agent_diagnostics._stderr_log_tail(review),
    )
    gh.write_pinned_state(issue, state)


def _post_reviewer_feedback(context: _models._RequestedChanges) -> None:
    reviewer_run = context.decision.run
    if reviewer_run.pr_number is None:
        return
    round_display = reviewer_run.round_n + 1
    feedback = context.decision.feedback
    try:
        reviewer_comment = _comments._post_pr_comment(
            context.gh,
            int(reviewer_run.pr_number),
            context.state,
            f":eyes: {config.REVIEW_AGENT} review "
            f"(round {round_display}/"
            f"{config.MAX_REVIEW_ROUNDS}) requested changes:\n\n"
            f"{feedback}",
        )
    except Exception:
        log.exception(
            "issue=#%s could not post review to PR #%s",
            context.issue.number,
            reviewer_run.pr_number,
        )
        return
    anchor_id = getattr(reviewer_comment, "id", None)
    if anchor_id is not None:
        context.state.set("pending_fix_reviewer_comment_id", int(anchor_id))


def _run_requested_fix(context: _models._RequestedChanges) -> _models._AwaitingDevAttempt:
    before_sha = _verification_probes._head_sha(context.decision.run.wt)
    # The caller flipped the label validating -> fixing just before this.
    # Pass `fixing` explicitly rather than let the resume helper read the
    # label back off the issue: on any object that flip did not go through it
    # still reads `validating`, which would attribute this developer run to
    # the reviewer's stage.
    worktree, agent_result, paused = _dev_resume._resume_dev_with_text(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        _prompts._build_fix_prompt(context.decision.feedback),
        stage=stage_name(WorkflowLabel.FIXING),
        pause_guard=True,
    )
    context.state.set("last_agent_action_at", _usage._now_iso())
    return _models._AwaitingDevAttempt(
        _models._DevFixRun(worktree, agent_result, before_sha), paused,
    )


def _finish_requested_fix(
    context: _models._RequestedChanges, attempt: _models._AwaitingDevAttempt,
) -> None:
    """Read what the fix round left, and hand the pull request back with it.

    The round is spent by a report reaching the pull request exactly as it is
    by a commit, because both are a handover the next reviewer has to read
    afresh: a report round that spent nothing would let a developer answer the
    same reviewer forever without `MAX_REVIEW_ROUNDS` ever counting it.

    WHEN it is spent is what tells the two apart. A pushed fix spent it on a
    commit that reached the pull request, so the write the size gate made beside
    its own receipt is where it is durable, and this caller only re-applies the
    same frozen pair for the one push that write could not carry. A report with
    no code in it has bought nothing until that report is on the pull request --
    so nothing of the handover is written here at all: the pair rides the record
    and is closed by the write that settles it, confirmed or replayed, and a
    post GitHub refused, a re-read that failed, or a crash leaves the round
    unspent and the replay anchor intact for the round to be finished again.

    The label moves either way, and moves BEFORE the binding. It is the only
    road to confirmation: `validating`'s report hold is what binds a delivery
    and settles it, and it refuses every reviewer for as long as the report is
    owed -- so the move hands the issue to the owner that finishes the
    transaction rather than presenting unconfirmed work to anybody. Moved after
    the binding instead, a settled report would stand beside a label still
    claiming the round it closed.
    """
    if attempt.paused:
        return
    owed = _rounds._spends_a_requested_round(context.decision.run.round_n)
    outcome = _fix_reports._post_requested_fix_result(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        attempt.run.worktree,
        attempt.run.agent_result,
        attempt.run.before_sha,
        # The caller flipped this issue to `fixing` remotely before the spawn,
        # and the size gate reading the label off an object that flip did not
        # go through would freeze `validating` -- the state the issue has
        # LEFT -- and a settled adjudication would continue there instead of
        # finishing the fix loop. Named for the same reason the resume above
        # is.
        stage=WorkflowLabel.FIXING,
        # The round this route counts, handed to the gate for the exit where
        # this caller never reaches the lines below: a hold relabels to the
        # adjudication, and an authorized settlement publishes the accepted
        # commit itself, so nothing behind here counts it.
        spends=owed,
        # The road this run came down, which is what holds it to the report
        # contract, and the same frozen pair above -- which on the road with no
        # code in it is the ONLY thing that carries the round, since the write
        # that settles the report is the first write a handover nothing
        # published has earned. The revision is left to the pinned baseline: no
        # drift check snapshotted one for this route, and the reviewer round
        # runs behind the one the tick's own drift check left.
        handed=_records.HandedRun(WorkflowLabel.FIXING, spends=owed.fields),
    )
    if outcome not in _state._REPORTING_OUTCOMES:
        if not _guards._ignore_if_interrupted(
            context.issue, attempt.run.agent_result,
        ):
            context.gh.write_pinned_state(context.issue, context.state)
        return
    if outcome == _state._OUTCOME_PUSHED:
        _late_gate_models._spend(context.state, owed)
    context.gh.set_workflow_label(context.issue, WorkflowLabel.VALIDATING)
    context.gh.write_pinned_state(context.issue, context.state)
    _report_settlement._settles_the_report(
        context.gh, context.spec, context.issue, context.state,
        WorkflowLabel.VALIDATING,
    )


def _handle_validating_changes_requested(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    decision: _models._ReviewerDecision,
) -> None:
    """CHANGES_REQUESTED: post the reviewer feedback on the PR, flip to
    `fixing`, and resume the dev.

    The dev-fix subphase runs under the `fixing` label so the active job is
    observably "fixing reviewer-requested changes" rather than "validating"
    (which reads as reviewer/verify work only); `fixing` thereby extends to
    automated reviewer feedback in addition to its original in_review
    human-feedback duty. The label is flipped BEFORE the dev spawn so a crash
    inside the spawn still leaves the issue on `fixing` with stale
    awaiting_human=False, which the next tick's fixing handler treats as
    no-feedback and bounces back to `validating`. On a successful pushed fix, and
    on a report the round delivers with no code in it, we bump `review_round`
    and relabel to `validating`; on any park the issue stays on `fixing` and the
    fixing handler owns the awaiting-human rescan. `MAX_REVIEW_ROUNDS`,
    dev-session pinning, and the final-docs handoff are unchanged -- only the
    visible label moves with the active work.

    The id of the reviewer-feedback PR comment is recorded in
    `pending_fix_reviewer_comment_id` so a session-failure park on this route
    (`agent_silent` / `agent_timeout` / `agent_execution_failed`) is retryable by `/orchestrator continue`:
    the fixing handler's `_reconstruct_pending_fix_batch` replays that exact
    comment. `pending_fix_at` is deliberately NOT set (it discriminates the
    in_review route's review-round reset from this route's bump), so the anchor
    is a standalone key cleared on the pushed-fix exit here and inside
    `_clear_pending_fix_bookmarks`.
    """
    context = _models._RequestedChanges(gh, spec, issue, state, decision)
    _post_reviewer_feedback(context)
    gh.set_workflow_label(issue, WorkflowLabel.FIXING)
    gh.write_pinned_state(issue, state)
    _finish_requested_fix(context, _run_requested_fix(context))


def _park_review_cap(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    round_n: int,
) -> None:
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} review still has comments after "
        f"{round_n} round(s); manual intervention needed. To grant "
        "more rounds without losing the PR/worktree, reply with "
        "`/orchestrator add-review-rounds N` "
        "(N = additional rounds, e.g. `1`).",
        reason=_state._REASON_REVIEW_CAP,
        bounded=True,
    )
    # `_park_awaiting_human` clears `park_reason` by contract; the
    # awaiting-human branch needs this transient reason to route the
    # operator's `/orchestrator add-review-rounds` command.
    state.set(_state._PARK_REASON, _state._REASON_REVIEW_CAP)
    gh.write_pinned_state(issue, state)
