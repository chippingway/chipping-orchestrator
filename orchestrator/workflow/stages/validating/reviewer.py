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
the reviewer is handed beside it, in a guarded commit of their own ahead of the
launch (`review_writes.lands_the_launch`), decided on the report records, the
pull request, and the returned-verdict record the subject was bound over, and on
the spec and subject themselves as that reading spelled them, so a launch
repeated over a subject already recorded never runs beside another road's. A
backend hiccup that yields no session id, or a round that dies mid-review,
still leaves a durable record of which spec ran that round and what it was
shown, and a config flip mid-flight cannot retroactively rewrite the history.
Overwriting both every round is correct here precisely because the reviewer is
spawned fresh each time rather than resumed. A commit that does not land -- one
of those records moved, a comment that will not read, an edit nobody confirmed
-- spawns no reviewer that tick. Ahead of that commit, the reading the subject
was bound to is laid over the state in hand, measured from the comment as the
tick read it (`review_comment._ResolvedSubject.lays_over`), and so, behind it,
is whatever the commit landed over, measured from that reading: a run another
road charged and folded, or a notice it posted, while the subject was resolved
is kept by every write of the round rather than written back over. The workflow
verification evidence current for that subject is asked behind the commit
(`review_evidence`), since evidence is held to the subject the launch records,
and handed over beside the report: the prompt quotes it under its revision and
teaches the declaration the reviewer closes on -- the commands it ran on the
head it is handed, or the exact revision of that evidence it reused. The
launch charge the run circuit writes behind them is the round's own write as
well, and is taken into the reading the round's return is measured against
(`_launches`), so a run another road charges while the reviewer runs is kept
the same way.

After the run, two refusals stand between the reviewer and any disposition,
and their order is the contract. The live-pause check runs first, and the
interruption check behind it, because a shutdown-killed reviewer emits
nothing: read as a verdict it would park the issue as a reviewer failure AND
persist the usage it ran up. Both return before usage is folded or the
session recorded, so an operator who pauses mid-review leaves durable state
exactly as the prior tick wrote it, and nothing is stranded -- the reviewer is
read-only and starts over next tick.

The verdict itself fans out to two owners. A timeout or a missing VERDICT line
parks, its return -- usage, session, and the subject it read -- recorded by
the park's own guarded commit, prepared before its notice is posted
(`review_writes.parks_the_return`); an approval or a change request goes to
`review_disposition`, which records that return over its own last reading,
persists the verdict with the evidence its declaration earned before
publishing that evidence or acting on either verdict, and lets an approval
reach the approval arc only over settled evidence that passed and covers every
configured `VERIFY_COMMANDS` command -- parking one that does not under
`reviewer_unverified`. A change request goes to its one developer from there,
its feedback the reviewer's findings with that declaration set aside once it
is read, save each check not shown passing.
The event is emitted for all of them, before the fan-out, so the analytics
record exists even for the paths that park. An approval and a change request
alike are acted on only while the whole subject the reviewer was handed --
pull request, head, requirements, and report -- still stands; otherwise the
run is recorded and the next tick's reviewer is handed the subject as it
stands. The pinned comment is read again as the reviewer returns, before any
of that is written, for that reason: a report settling, the issue pointed at
another pull request, or another round's verdict persisted while the reviewer
runs is recorded there and nowhere in the state this tick holds, and every
write the run makes from that state has to lay itself over that rather than
undo it -- where the comment will not read, nothing is written at all. Each of
those writes is a guarded commit captured over that reading
(`review_writes`), so what another road writes after it is kept, or -- where
it moved a record the write was decided on -- refuses the write. The
disposition resolves the subject again for a verdict, and reads the comment
once more behind that, before it persists anything. Failed-run parks (timeout and unknown verdict) enrich the
shared park funnel with typed correlation fields (`agent_role`, `session_id`,
`review_round`, `retry_count`, `pr_number`).
"""
from __future__ import annotations

from dataclasses import replace

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_verdicts as _completion_verdicts,
    guards as _guards,
    prompt_context as _prompt_context,
    review_prompts as _review_prompts,
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import session_read as _dev_session_read
from orchestrator.workflow.stages.validating import (
    models as _models,
    requested_changes as _requested_changes,
    review_comment as _review_comment,
    review_disposition as _review_disposition,
    review_evidence as _review_evidence,
    review_report as _review_report,
    review_writes as _review_writes,
    state as _state,
)


def _run_reviewer_round(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    read: dict,
) -> _models._ReviewerRun | None:
    """One round over the pull request the tick read the issue pointed at; None to end the tick unwritten.

    `read` is the pinned comment as the tick read it. The reading the round's
    subject is bound to is laid over `state` measured from it before anything
    of the round is written (`review_comment._ResolvedSubject.lays_over`): a
    run another road charged and folded while the subject was resolved is on
    that reading and nowhere in hand, and every later reading of the round is
    measured from it, so no later one would see it move. A launch whose commit
    did not land ends the tick with no reviewer spawned.
    """
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
        gh, issue, state, read.get("pr_number"), delivered,
    )
    if handover is None:
        return None
    handover.lays_over(state, read)
    handover = _writes_the_launch(gh, spec, issue, state, handover)
    if handover is None:
        return None
    agent_result, handover = _launches(
        gh, issue, state, handover,
        agent_role="reviewer",
        stage="validating",
        backend=config.REVIEW_AGENT,
        prompt=_review_prompt(
            spec, issue, state, delivered.rendered_text, handover,
        ),
        cwd=wt,
        agent_spec=config.REVIEW_AGENT_SPEC,
        timeout=config.REVIEW_TIMEOUT,
        extra_args=config.REVIEW_AGENT_ARGS,
        review_round=round_n,
        retry_count=state.get("retry_count"),
    )
    return _read_again_on_return(gh, issue, state, _models._ReviewerRun(
        wt=wt,
        round_n=round_n,
        pr_number=read.get("pr_number"),
        agent_result=agent_result,
        delivery=delivered,
        subject=handover.subject,
        resolved_over=handover.resolved_over,
        evidence=handover.evidence,
    ))


def _writes_the_launch(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    handover: _review_comment._ResolvedSubject,
) -> _review_comment._ResolvedSubject | None:
    """Commit the reviewer spec and its subject BEFORE the spawn; the subject over that commit, its evidence beside it.

    The launch charge writes only the fields it took, so without a write of
    their own nothing would put these two down until the reviewer returned,
    and a round that died mid-review would leave no record of which spec ran
    or what it was shown. They are committed over the comment as
    `review_report` bound it an instant ago -- carrying the report records,
    the pull request, and the verdict record in hand -- rather than as the
    state in hand (`review_writes.lands_the_launch`): that state carries what
    this tick staged for the round's own write, a cleared park and a cap
    grant's round reset among them, and a launch the run circuit refuses
    discards those, which is what lets the grant be honored again once an
    agent-run grant hands the park back. Whatever the commit landed over -- a
    run another road charged since the binding, say -- is carried onto the
    state in hand with the launch's own two fields, measured from the binding
    reading (`review_comment._ResolvedSubject.lays_over`). None where the
    commit did not land: a record the round was decided on moved, the comment
    would not read, or the edit was never confirmed, and no reviewer is
    spawned this tick.

    The evidence the reviewer is handed is asked only behind that, since the
    proof holds evidence this orchestrator executed to the subject the launch
    records, and reviewer-reported evidence to the subject the last returned
    reviewer read -- this one's only where nothing moved since.
    """
    landed = _review_writes.lands_the_launch(gh, issue, state, handover)
    if landed is None:
        return None
    launched = replace(handover, resolved_over=landed)
    launched.lays_over(state, handover.resolved_over)
    return replace(
        launched,
        evidence=_review_evidence.handed_evidence(gh, spec, issue, state, handover.subject),
    )


def _launches(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    handover: _review_comment._ResolvedSubject,
    **request,
) -> tuple[AgentResult, _review_comment._ResolvedSubject]:
    """Run the reviewer `request` describes, charged; its result, and the reading its return is measured against.

    The run circuit charges the launch on the comment behind the launch's
    write, and merges onto `state` only the fields the charge moved. Those are
    the round's own write as well, so the comment the verdict's return is
    measured against is the launch's write with them taken into it
    (`review_comment._ResolvedSubject.carrying`): left out of it, the count
    would read as a field this tick staged and never wrote, and a reading that
    keeps this tick's own moves over records that stand would keep this
    charge's count over a newer one another road's charge wrote meanwhile, and
    write it back.
    """
    before = dict(state.data)
    ran = _usage._run_agent_tracked(
        gh, _run_charge_state.AgentRunBudget(issue=issue, state=state), **request,
    )
    return ran, handover.carrying(before, state)


def _read_again_on_return(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    reviewer_run: _models._ReviewerRun,
) -> _models._ReviewerRun | None:
    """The run, the pinned comment read again behind it; None to end the tick unwritten.

    A run an operator paused under, or one the shutdown sweep killed, ends the
    tick before that, in that order, with nothing of its return staged.

    The comment is read before anything the run leaves is written -- a park
    for a timeout or a missing verdict as much as the record of a verdict --
    since each of those writes goes out from the state in hand, and a report
    that settled while the reviewer ran is on the comment and nowhere in it.
    What the comment changed is carried onto that state first, and a report
    record, the pull request the issue points at, or the returned verdict
    another round persisted, moved there marks the verdict as one of a subject
    that no longer stands: the disposition measures from this reading on, so a
    verdict persisted during the run, left unwatched here, is one it would
    write this run's verdict over. The run is measured
    from then on against the comment as that reading found it, so a later
    reading of the round does not keep a second time what this one already
    kept of both roads' moves. A comment
    that will not read or parse ends the tick with nothing written, as an
    interrupted run does: the next tick spawns a reviewer over whatever the
    comment carries then.
    """
    # Live pause: an operator applied `paused` / `backlog` while the reviewer
    # ran. Dispatch only saw the pre-run labels, so re-check a freshly fetched
    # issue and return WITHOUT folding usage, recording the review session,
    # parking, or relabeling -- durable GitHub state stays exactly as the prior
    # tick left it and the next tick re-spawns a fresh reviewer once the label
    # is removed. Nothing is stranded: the reviewer is read-only and spawns
    # fresh each round.
    if _guards._paused_during_agent_run(gh, issue):
        return None

    # Shutdown-sweep interruption: a reviewer run the orchestrator killed
    # mid-flight has no trustworthy verdict. Its empty output would otherwise
    # fall through to the `unknown` -> `reviewer_failed` park below and, on
    # the ensuing `write_pinned_state`, persist the usage it ran up (and the
    # session / `last_review_at` it returned with). Ignore it and return
    # WITHOUT writing, and the next process re-spawns the reviewer. Must
    # precede the timeout/verdict branches.
    if _guards._ignore_if_interrupted(issue, reviewer_run.agent_result):
        return None
    reread = _review_comment._records_stand(
        gh, issue, state, reviewer_run.resolved_over, persisted=True,
    )
    if reread is None:
        return None
    return replace(reviewer_run, subject_moved=not reread.stood, resolved_over=reread.read)


def _review_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    thread_text: str,
    handover: _review_comment._ResolvedSubject,
) -> str:
    """The prompt one round's reviewer is handed, over the subject and evidence the round resolved."""
    _, dev_backend, _, _ = _dev_session_read._read_dev_session(state)
    return _review_prompts._build_review_prompt(
        spec, issue, thread_text, config.default_repo_specs(),
        _review_prompts.ReviewHandover(
            dev_backend=dev_backend, subject=handover.subject, evidence=handover.evidence,
        ),
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
    """Route a finished reviewer run and enrich failed-run parks with context.

    A run that leaves no verdict has its return recorded by its park's guarded
    commit (`review_writes.parks_the_return`); one that does leaves it to the
    disposition, which records it over the reading it persists the verdict
    behind, so the usage is folded once.
    """
    review = reviewer_run.agent_result
    pr_num = _guards._safe_int(reviewer_run.pr_number)
    if review.timed_out:
        # Tagged as transient so the next tick re-spawns the reviewer instead
        # of waiting for a human comment that the timeout itself does not
        # produce.
        _review_writes.parks_the_return(gh, issue, state, reviewer_run, (
            _state._REASON_REVIEWER_TIMEOUT,
            lambda: _guards._park_awaiting_human(
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
            ),
        ))
        return

    verdict, body = _completion_verdicts._parse_review_verdict(
        review.last_message,
    )
    gh.emit_event(
        "review_verdict",
        issue_number=issue.number,
        stage="validating",
        verdict=verdict,
        review_round=reviewer_run.round_n,
        pr_number=pr_num,
        session_id=review.session_id,
    )

    if verdict == "unknown":
        _requested_changes._park_reviewer_no_verdict(gh, issue, state, reviewer_run)
        return

    # A verdict is persisted with the evidence its declaration earned, that
    # evidence published, and only then acted on: a change request handed to
    # its developer, an approval to the approval arc once the evidence it
    # relies on settled, passed, and covers every configured command -- and
    # parked under `reviewer_unverified` where it does not. One of a subject
    # that moved while the reviewer ran is recorded and not acted on.
    _review_disposition.disposes_of_the_verdict(
        gh, spec, issue, state, _models._ReviewerDecision(reviewer_run, verdict, body),
    )
