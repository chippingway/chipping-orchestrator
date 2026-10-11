# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two verdicts that are not an approval.

CHANGES_REQUESTED runs its dev fix -- handed over by `review_handoffs`, through
the feedback post, the run, and its finish here -- under the `fixing` label
rather than `validating`, so the active job reads as what it is instead of as
reviewer work. The relabel happens BEFORE the spawn on purpose: a crash inside
the spawn then leaves the issue on `fixing` with the persisted change request
still marked handed, which the next tick's fixing handler answers ahead of its
feedback scan (`review_resume.finishes_a_handed_request`) -- a launch still
owed is made then, and one that may have started is never made again: the
request is dropped where the subject moved or the branch shows the developer's
own work, and the launch parks for `/orchestrator continue` where nothing shows
(`review_launch_park`) -- whereas a crash after a spawn under the old
label would leave an issue nobody re-enters. A pushed fix bumps the round and
relabels back; any park leaves the issue on `fixing`, whose handler owns the
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
handler replays that exact comment to reconstruct the batch, quoting its
findings formatted (`feedback_posts`) whatever words it was posted in. It is
the one durable copy of the feedback once the persisted verdict is handed on,
so the handoff (`review_handoffs`) goes on only behind a post whose id it read
-- or, on a later tick, that it found by the words and the receipt it posts
for that very request (`feedback_posts.finds`), where an earlier tick's post
never named its id.
It is a standalone key rather than part of the in_review bookmark pair, since
`pending_fix_at` is what tells that route's round RESET from this route's bump.

A reviewer that emitted no VERDICT line is the other verdict, and it splits by
whose failure it was. An empty last message with a non-zero exit is a crash,
and a message that opens with a transient provider refusal is an outage
wearing the reviewer's output slot; both are tagged transient so the next tick
re-spawns the reviewer -- waking the dev on a human "retry" would hand the
wrong agent a prompt with no review in it. A Codex run its account's usage
limit stopped has the crash's shape and never arrives here: the reviewer's
dispatch parks it under `reviewer_usage_limit` before any VERDICT is parsed,
since retrying it on the next tick would only spend a launch on a quota
nothing says has reset. Real text that merely omitted the
marker is left for a human, and the stderr tail is suppressed there because
the human is already reading model output. Unknown-verdict and reviewer-failure
parks forward typed correlation fields (`agent_role`, `session_id`,
`review_round`, `retry_count`, `pr_number`) through the shared park funnel, and
land with the run's own records in one guarded commit prepared before the
notice is posted (`review_writes.parks_the_return`), as a reviewer timeout's
park does.
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
    report_record_values as _record_values,
    report_records as _records,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    resume as _dev_resume,
)
from orchestrator.workflow.stages.validating import (
    feedback_posts as _feedback_posts,
    fix_reports as _fix_reports,
    models as _models,
    report_settlement as _report_settlement,
    review_verdicts as _verdicts,
    review_writes as _review_writes,
    rounds as _rounds,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

# The mark a fixing round's settlement raises, carried on this route's record
# as it is on the fixing stage's own. The relabel back to `validating` is taken
# BEFORE the binding, so this record ordinarily settles under that label, where
# the fixing stage retires the mark unplaced. A relabel that never landed -- a
# process that died on it, a label write GitHub refused -- leaves the record
# unbound on `workflow:fixing` instead, and the fixing stage's recovery binds it
# there. Without the mark that settlement closes the round and hands nothing
# back, so the next scan reads whatever arrived since under a route the
# settlement has just cleared.
_SETTLES_THE_ROUND = ((_records.SETTLED_ROUND, True),)

# What the round's own report answers: the persisted change request it was
# launched for, retired in the very commit that records that report.
_RETIRES = ((_verdicts.RETURNED_VERDICT, None),)


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
    otherwise hand the wrong agent a do-nothing prompt. A Codex run its usage
    limit stopped is no crash for this split to read: the dispatch parks it
    under `reviewer_usage_limit` before the verdict is parsed.

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
    reviewer_run: _models._ReviewerRun,
) -> None:
    """Park `validating` when the reviewer produced no VERDICT line, with what its run returned.

    `_reviewer_no_verdict_park` splits the transient failures from the one
    that needs a human; the reason it returns is set back on the pinned state
    because `_park_awaiting_human` clears the field by contract. stderr
    diagnostics ride along only when there was no model output at all -- a
    human reading real reviewer text does not need the subprocess tail too.
    Enriches the emitted park event with typed correlation fields
    (`agent_role`, `session_id`, `review_round`, `retry_count`, `pr_number`)
    drawn from the reviewer run and state. The run's records and the park
    land in one guarded commit, prepared before the notice is posted
    (`review_writes.parks_the_return`).
    """
    review = reviewer_run.agent_result
    outcome = _reviewer_no_verdict_park(review)
    raw = (review.last_message or "").strip() or "(reviewer produced no final message)"
    diag = (
        ""
        if (review.last_message or "").strip()
        else _agent_diagnostics._format_stderr_diagnostics(review, "Reviewer")
    )
    log.warning(
        "issue=#%s reviewer emitted no VERDICT; exit_code=%d "
        "timed_out=%s stderr_tail=%r",
        issue.number, review.exit_code, review.timed_out,
        _agent_diagnostics._stderr_log_tail(review),
    )
    kept = outcome[0] if outcome[0] == _state._REASON_REVIEWER_FAILED else None
    _review_writes.parks_the_return(gh, issue, state, reviewer_run, (
        kept,
        lambda: _guards._park_awaiting_human(
            gh,
            issue,
            state,
            f"{config.HITL_MENTIONS} reviewer did not emit a VERDICT line; "
            f"{outcome[1]}\n\n_Last reviewer message:_\n\n"
            f"{_messages._as_blockquote(raw)}{diag}",
            reason=outcome[0],
            agent_role="reviewer",
            session_id=review.session_id,
            review_round=_guards._safe_int(reviewer_run.round_n),
            retry_count=_guards._safe_int(state.get("retry_count")),
            pr_number=_guards._safe_int(reviewer_run.pr_number),
            bounded=True,
        ),
    ))


def _post_reviewer_feedback(
    context: _models._RequestedChanges, held: _verdicts.ReturnedVerdict, *, finds: bool = False,
) -> int | None:
    """Post the reviewer's feedback on the PR for the persisted request `held`; the id it landed as, or None.

    The post is in the words `feedback_posts.posted` writes, below them the
    receipt naming `held` (`feedback_posts.receipted`), which that owner also
    reads back where a replay shows the post (`feedback_posts.ShownPost`).
    The id is the replay anchor a `/orchestrator continue` on a later park of
    this route hands a fresh developer, and it is its caller's to stage: this
    route stages it at once, while a persisted verdict's handoff goes on only
    behind one and stages it beside the handoff, once the subject is held
    again behind the post (`review_handoffs`). An issue with no pull request
    to post on, a post that failed, and one whose response named no comment
    -- no positive whole id, that is -- all answer None. Only the post's entry
    in the orchestrator's comment ledger is staged here.

    `finds` is a later tick's handoff of a request an earlier one may already
    have posted for -- its response lost, or its handoff refused behind it --
    so the pull request is read for that post first (`feedback_posts.finds`)
    and one found is taken, its ledger entry staged, with nothing posted: one
    receipted for `held` itself, or one a tick before receipts posted that
    stands where `held`'s own would (`feedback_posts.finds`). A thread that
    will not read posts nothing either, and answers None.
    """
    if context.pr_number is None:
        return None
    words = _feedback_posts.posted(context.round_n, context.feedback)
    pr_number = int(context.pr_number)
    try:
        found = _feedback_posts.finds(
            context.gh, pr_number, words, held, context.state,
        ) if finds else None
    except Exception:
        log.exception(
            "issue=#%s could not read PR #%s for the review an earlier tick may have posted",
            context.issue.number,
            context.pr_number,
        )
        return None
    if found is not None:
        _comments._track_orchestrator_comment(context.state, found)
        return found
    try:
        reviewer_comment = _comments._post_pr_comment(
            context.gh, pr_number, context.state, _feedback_posts.receipted(words, held),
        )
    except Exception:
        log.exception(
            "issue=#%s could not post review to PR #%s",
            context.issue.number,
            context.pr_number,
        )
        return None
    # A whole, positive comment id and nothing else: a flag or a fraction
    # coerced to one would anchor a replay to some other comment.
    return _record_values.as_recorded_number(getattr(reviewer_comment, "id", None))


def _run_requested_fix(
    context: _models._RequestedChanges, **resume: object,
) -> _models._AwaitingDevAttempt:
    """Resume the developer on the reviewer's feedback under `workflow:fixing`.

    `resume` is what a persisted request's handoff (`review_handoffs`) adds to
    the resume: `owed`, the launch it owes once -- the run count it was handed
    at and what it stands on -- which the run circuit holds the launch to on
    the readings it charges and starts it from. The live round adds nothing,
    since it owes the launch once by construction.
    """
    before_sha = _verification_probes._head_sha(context.wt)
    # The caller flipped the label validating -> fixing just before this -- or,
    # recovering a launch a handed request still owes, found the issue on
    # `fixing` already and made no flip. Pass `fixing` explicitly rather than
    # let the resume helper read the label back off the issue: on any object a
    # flip did not go through it still reads `validating`, which would
    # attribute this developer run to the reviewer's stage.
    worktree, agent_result, paused = _dev_resume._resume_dev_with_text(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        _prompts._build_fix_prompt(context.feedback),
        stage=stage_name(WorkflowLabel.FIXING),
        pause_guard=True,
        **resume,
    )
    context.state.set("last_agent_action_at", _usage._now_iso())
    return _models._AwaitingDevAttempt(
        _models._DevFixRun(worktree, agent_result, before_sha), paused,
    )


def _finish_requested_fix(
    context: _models._RequestedChanges,
    attempt: _models._AwaitingDevAttempt,
    handed: _verdicts.ReturnedVerdict,
) -> None:
    """Read what the fix round left, and hand the pull request back with it, the request `handed` retired.

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
    claiming the round it closed. A move that never lands leaves the record
    unbound on `fixing`, and the settled-round mark it carries is what lets the
    fixing stage's recovery finish the hand-back there.

    The persisted change request `handed` -- the one this round answers -- is
    retired in the first write that records what the round left, and only in
    a guarded commit decided on that request, the pull request the issue
    points at, the start of its developer's launch, the feedback anchor its
    continue replays, and the park's flags: the commit recording its report
    (`report_records.HandedRun.retires` and `decided_on`), so a move there
    publishes, pushes, relabels, and spends nothing; the park a round that
    parks instead takes -- a timeout, a question, a tree or a push it could not
    publish, or a report it still owes, whose park writes the retirement itself
    (`report_delivery.parks_the_debt`) -- or, behind the relabel, the hand-back
    ahead of the report's settlement where no report was recorded first
    (`_answers`). Each keeps another road's write while the developer ran or
    the label moved, and nothing is settled or posted behind a hand-back that
    did not land. Until then the request stays on the comment beside what the
    round recorded, the obligation a later tick answers it by. A paused run,
    and one the shutdown sweep killed, write nothing.
    """
    if attempt.paused:
        return
    owed = _rounds._spends_a_requested_round(context.round_n)
    outcome = _fix_reports._post_requested_fix_result(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        attempt.run.worktree,
        attempt.run.agent_result,
        attempt.run.before_sha,
        # The issue is on `fixing` by the spawn -- flipped there remotely by
        # the caller, or already there where the fixing stage's recovery
        # launched a developer a handed request still owed -- and the size gate
        # reading the label off an object a flip did not go through would
        # freeze `validating` -- the state the issue has LEFT -- and a settled
        # adjudication would continue there instead of finishing the fix loop.
        # Named for the same reason the resume above is.
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
        # published has earned. The mark rides beside it for the relabel below
        # that may not land. The revision is left to the pinned baseline: no
        # drift check snapshotted one for this route, and the reviewer round
        # runs behind the one the tick's own drift check left.
        handed=_records.HandedRun(
            WorkflowLabel.FIXING,
            spends=owed.fields + _SETTLES_THE_ROUND,
            retires=_RETIRES,
            decided_on=_review_writes.ANSWERED.decided_on,
        ),
    )
    if outcome not in _state._REPORTING_OUTCOMES:
        if not _guards._ignore_if_interrupted(context.issue, attempt.run.agent_result):
            _answers(context, handed)
        return
    if outcome == _state._OUTCOME_PUSHED:
        _late_gate_models._spend(context.state, owed)
    context.gh.set_workflow_label(context.issue, WorkflowLabel.VALIDATING)
    if _answers(context, handed):
        _report_settlement._settles_the_report(
            context.gh, context.spec, context.issue, context.state,
            WorkflowLabel.VALIDATING,
        )


def _answers(context: _models._RequestedChanges, handed: _verdicts.ReturnedVerdict) -> bool:
    """Land what the round left with the request `handed` retired beside it, in one guarded commit; whether it landed.

    Over the comment read afresh (`review_writes.ANSWERED`), so every field
    another road wrote meanwhile is kept, and a request, a repoint, a start,
    an anchor, or a park it moved refuses it with nothing written. A request
    the report's own record already retired is dropped there once. A state
    withheld behind a write that did not land -- the report's own record
    refused or never confirmed -- writes nothing: that record is what a later
    tick finishes.
    """
    if context.state.withheld:
        return False
    _verdicts.drops_the_verdict(context.state, only=handed)
    return _review_writes.lands(context.gh, context.issue, context.state, _review_writes.ANSWERED)


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
