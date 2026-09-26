# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One reviewer round: the cap that guards it, and the verdict it produces.

The round-cap check comes before the worktree and the spawn, because the cap
is what stops a review loop that cannot converge from spending agent runs
forever; parking on it leaves the PR and worktree intact so an operator can
grant more rounds instead of restarting the issue.

The developer report the reviewer is handed is resolved next, still ahead of
the spawn: `review_report` re-reads the report this issue last settled from
the location it settled at and quotes it whole, beside the issue and the
commands that inspect the branch, so what the reviewer judges is the report the
pull request actually carries rather than whichever one it would have fetched.
A report that cannot be handed over -- refused for good, or unreadable this
tick -- ends the tick there with no reviewer spawned.

The configured reviewer spec is persisted BEFORE the spawn, and the subject
the reviewer is handed beside it, in a write of their own ahead of the launch
(`review_records`). A backend hiccup that yields no session id, or a round that
dies mid-review, still leaves a durable record of which spec ran that round and
what it was shown, and a config flip mid-flight cannot retroactively rewrite
the history. Overwriting both every round is correct here precisely because
the reviewer is spawned fresh each time rather than resumed.

After the run, two refusals stand between the reviewer and any disposition,
and their order is the contract. The live-pause check runs first and returns
before usage is folded or the session recorded, so an operator who pauses
mid-review leaves durable state exactly as the prior tick wrote it. The
interruption check runs after that fold but before the timeout and verdict
branches, because a shutdown-killed reviewer emits nothing: read as a verdict
it would park the issue as a reviewer failure AND persist the counters just
folded. Both return without writing, and nothing is stranded -- the reviewer is
read-only and starts over next tick.

The verdict itself fans out to three owners: approved goes to the approval
arc, a missing VERDICT line to the no-verdict park, and CHANGES_REQUESTED to
the fix route. The event is emitted for all of them, before the fan-out, so
the analytics record exists even for the paths that park. An approval and a
change request alike are acted on only while the whole subject the reviewer
was handed -- head, requirements, and report -- still stands; otherwise the
run is recorded and the next tick's reviewer is handed the subject as it
stands. The pinned comment is read again as the reviewer returns, before any
of that is written, for that reason: a report settling while the reviewer
runs is recorded there and nowhere in the state this tick holds, and every
write the run makes has to lay itself over that settlement rather than undo
it -- where the comment will not read, nothing is written at all. Failed-run
parks
(timeout and unknown verdict) enrich the shared park funnel with typed
correlation fields (`agent_role`, `session_id`, `review_round`, `retry_count`,
`pr_number`).
"""
from __future__ import annotations

from dataclasses import replace

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_verdicts as _completion_verdicts,
    guards as _guards,
    prompt_context as _prompt_context,
    review_prompts as _review_prompts,
    review_subjects as _review_subjects,
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    late_records as _late_records,
    session_read as _dev_session_read,
)
from orchestrator.workflow.stages.validating import (
    approval as _approval,
    models as _models,
    requested_changes as _requested_changes,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_records as _review_records,
    review_report as _review_report,
    state as _state,
)


def _run_reviewer_round(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    pr_number,
) -> _models._ReviewerRun | None:
    round_n = int(state.get(_state._REVIEW_ROUND) or 0)
    if round_n >= config.MAX_REVIEW_ROUNDS:
        _requested_changes._park_review_cap(gh, issue, state, round_n)
        return None

    wt = _worktree_creation._ensure_worktree(
        spec, issue.number,
        branch=_naming._resolve_branch_name(state, spec, issue.number),
    )
    delivered = _prompt_context._delivered_thread(gh, issue, state)
    handover = _review_report._resolves_the_subject(
        gh, issue, state, pr_number, delivered,
    )
    if handover is None:
        return None
    handover = _persists_the_launch(gh, issue, state, handover)
    reviewer_run = _models._ReviewerRun(
        wt=wt,
        round_n=round_n,
        pr_number=pr_number,
        agent_result=_usage._run_agent_tracked(
            gh, _run_charge_state.AgentRunBudget(issue=issue, state=state),
            agent_role="reviewer",
            stage="validating",
            backend=config.REVIEW_AGENT,
            prompt=_review_prompt(
                spec, issue, state, delivered.rendered_text, handover.subject,
            ),
            cwd=wt,
            agent_spec=config.REVIEW_AGENT_SPEC,
            timeout=config.REVIEW_TIMEOUT,
            extra_args=config.REVIEW_AGENT_ARGS,
            review_round=round_n,
            retry_count=state.get("retry_count"),
        ),
        delivery=delivered,
        subject=handover.subject,
        resolved_over=handover.resolved_over,
    )
    # Live pause: an operator applied `paused` / `backlog` while the reviewer
    # ran. Dispatch only saw the pre-run labels, so re-check a freshly fetched
    # issue and return WITHOUT folding usage, recording the review session,
    # parking, or relabeling -- durable GitHub state stays exactly as the prior
    # tick left it and the next tick re-spawns a fresh reviewer once the label
    # is removed. Nothing is stranded: the reviewer is read-only and spawns
    # fresh each round.
    if _guards._paused_during_agent_run(gh, issue):
        return None
    _review_records._records_the_return(
        state,
        reviewer_run.agent_result.usage,
        reviewer_run.agent_result.session_id,
        reviewer_run.subject,
    )

    # Shutdown-sweep interruption: a reviewer run the orchestrator killed
    # mid-flight has no trustworthy verdict. Its empty output would otherwise
    # fall through to the `unknown` -> `reviewer_failed` park below and, on
    # the ensuing `write_pinned_state`, persist the usage counters just folded
    # above (and the session / `last_review_at` mutations). Ignore it and
    # return WITHOUT writing so those in-memory mutations are discarded and the
    # next process re-spawns the reviewer. Must precede the timeout/verdict
    # branches.
    if _guards._ignore_if_interrupted(issue, reviewer_run.agent_result):
        return None
    return _read_again_on_return(gh, issue, state, reviewer_run)


def _persists_the_launch(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    handover: _review_comment._ResolvedSubject,
) -> _review_comment._ResolvedSubject:
    """Write the reviewer spec and its subject BEFORE the spawn; stage both too.

    The launch charge writes only the fields it took, so without a write of
    their own nothing would put these two down until the reviewer returned,
    and a round that died mid-review would leave no record of which spec ran
    or what it was shown. They are written onto the comment as `review_report`
    read it an instant ago -- carrying the report records in hand -- rather
    than as the state in hand: that state carries what this tick staged for
    the round's own write, a cleared park and a cap grant's round reset among
    them, and a launch the run circuit refuses discards those, which is what
    lets the grant be honored again once an agent-run grant hands the park
    back. What was written is what the verdict's return is measured against.
    """
    durable = PinnedState(
        comment_id=state.comment_id, state_data=dict(handover.resolved_over),
    )
    _review_records._records_the_launch(durable, handover.subject)
    gh.write_pinned_state(issue, durable)
    # The comment this write landed on is the one every later write of the
    # round has to reach, rather than a second one pinned beside it.
    state.comment_id = durable.comment_id
    _review_records._records_the_launch(state, handover.subject)
    return replace(handover, resolved_over=dict(durable.data))


def _read_again_on_return(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    reviewer_run: _models._ReviewerRun,
) -> _models._ReviewerRun | None:
    """The run, once the pinned comment is read again; None to end the tick unwritten.

    Read before anything the run leaves is written -- a park for a timeout or
    a missing verdict as much as the record of a verdict -- since each of
    those writes goes out from the state in hand, and a report that settled
    while the reviewer ran is on the comment and nowhere in it. What moved is
    carried onto that state first, and marks the verdict as one of a subject
    that no longer stands. A comment that will not read or parse ends the tick
    with nothing written, as an interrupted run does: the next tick spawns a
    reviewer over whatever the comment carries then.
    """
    stood = _review_comment._records_stand(
        gh, issue, state, reviewer_run.resolved_over,
    )
    if stood is None:
        return None
    return replace(reviewer_run, report_moved=not stood)


def _review_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    thread_text: str,
    subject: _review_subjects.ReviewSubject,
) -> str:
    """The prompt one round's reviewer is handed, over what the round resolved."""
    _, dev_backend, _, _ = _dev_session_read._read_dev_session(state)
    return _review_prompts._build_review_prompt(
        spec, issue, thread_text, config.default_repo_specs(),
        _review_prompts.ReviewHandover(dev_backend=dev_backend, subject=subject),
    )


def _settles_what_bought_the_round(
    state: PinnedState,
    parked: _models._AwaitingValidation | None,
    reviewer_run: _models._ReviewerRun,
) -> None:
    """Record the reply that bought this round, now that the round has run.

    A reviewer-side park is lifted by a human's retry and a spent cap by an
    operator's grant; what either buys is this round, so what it delivered is
    recorded by the run that happened and by nothing ahead of it. A launch the
    run circuit turned away invoked no reviewer: the refusal was recorded
    where it was decided, and the reply stays unread for the round a grant
    finally buys.

    What is recorded is THIS round's own snapshot rather than the batch the
    park froze. The two are different reads under different bounds -- the
    batch is unbounded and quotes the replies past the park's watermark, this
    prompt is bounded and quotes the whole thread -- so a mark taken from the
    batch would cross a reply this prompt cut short, and the words that never
    reached anybody would be read by nobody ever again. Taken from the
    round's own record, an excerpt that stopped short holds the watermark
    below it and the scan that owns the issue thread still delivers it.

    Only a reply that bought a round is recorded at all: an ordinary round
    reads the thread like any other reader and answers nobody, so it consumes
    nothing. The reply is the round's whether or not the park outlived the
    tick that cleared it -- a report still owed holds the reviewer behind a
    clear that is already written, and the round runs a tick or more later --
    so the note that road left says who is owed a settlement when the context
    the park was read from is long gone.

    The round a deferral stood down for is discharged here for the same
    reason -- it has now run -- but a deferral delivered nothing to record,
    which is what lets an edit nobody has carried take the developer's road
    on the next tick.
    """
    owed = state.get(_state._REVIEWER_OWES_A_ROUND)
    if not reviewer_run.agent_result.invoked:
        return
    _state._discharges_the_owed_round(state)
    if parked is not None or owed == _state._ROUND_BOUGHT_BY_A_REPLY:
        reviewer_run.delivery.settle(state)


def _dispatch_reviewer_result(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    reviewer_run: _models._ReviewerRun,
) -> None:
    """Route a finished reviewer run and enrich failed-run parks with context."""
    review = reviewer_run.agent_result
    pr_num = _guards._safe_int(reviewer_run.pr_number)
    if review.timed_out:
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} reviewer timed out after "
            f"{config.REVIEW_TIMEOUT}s; manual intervention needed.",
            reason=_state._REASON_REVIEWER_TIMEOUT,
            agent_role="reviewer",
            session_id=review.session_id,
            review_round=reviewer_run.round_n,
            retry_count=_guards._safe_int(state.get("retry_count")),
            pr_number=pr_num,
            bounded=True,
        )
        # Tag as transient so the next tick re-spawns the reviewer instead
        # of waiting for a human comment that the timeout itself does not
        # produce.
        state.set(_state._PARK_REASON, _state._REASON_REVIEWER_TIMEOUT)
        gh.write_pinned_state(issue, state)
        return

    verdict, body = _completion_verdicts._parse_review_verdict(
        review.last_message,
    )
    decision = _models._ReviewerDecision(reviewer_run, verdict, body)
    gh.emit_event(
        "review_verdict",
        issue_number=issue.number,
        stage="validating",
        verdict=verdict,
        review_round=reviewer_run.round_n,
        pr_number=pr_num,
        session_id=review.session_id,
    )

    if decision.verdict == "unknown":
        _requested_changes._park_reviewer_no_verdict(
            gh, issue, state, review, reviewer_run=reviewer_run,
        )
        return

    # A verdict of a subject that no longer stands as it was handed -- a head
    # pushed, the issue edited, the report edited, removed, or replaced by a
    # later settlement while the reviewer ran -- is about work that is not
    # there: an approval would hand it on, and a change request would pay a
    # developer to answer a review of words the pull request no longer
    # carries. The run is recorded over whatever settled meanwhile, and the
    # next tick's reviewer is handed the subject as it stands, or refused.
    if reviewer_run.report_moved or not _review_coverage._subject_still_stands(
        gh, issue, state, reviewer_run.subject,
    ):
        gh.write_pinned_state(issue, state)
        return

    if decision.verdict == "approved":
        # The subject the size gate decides about is built on the road that
        # holds every part of it -- this run's checkout included -- rather
        # than rebuilt a layer down from the pieces.
        _approval._finalize_validating_approval(
            _late_records._gate(gh, spec, issue, state, reviewer_run.wt),
            reviewer_run,
            _naming._resolve_branch_name(state, spec, issue.number),
        )
        return

    # CHANGES_REQUESTED: post the reviewer feedback, flip to `fixing`, and
    # resume the dev. On a pushed fix the handler bumps `review_round` and
    # relabels back to `validating` so the reviewer re-evaluates the new head;
    # on any park the issue stays on `fixing` and the fixing handler owns the
    # awaiting-human rescan.
    _requested_changes._handle_validating_changes_requested(
        gh, spec, issue, state, decision,
    )
