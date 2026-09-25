# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Attribute an implementation run's output and settle its timeout or result.

Both ends of a run must be readable before a changed head counts as its
work. The inherited floor remains separate from the run's starting head.
A timeout with proved commits publishes through candidate recovery; a run
that left no attributable commits parks or presents its question.
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
    guards as _guards,
    report_redelivery as _report_redelivery,
)
from orchestrator.workflow.stages.implementing import (
    candidate_recovery as _candidate_recovery,
    late_approval_reading as _late_approval_reading,
    late_park_state as _late_park_state,
    models as _models,
    parks as _parks,
    state as _state,
    unreported_recovery as _unreported_recovery,
)


def _park_agent_timeout(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    before_sha: str | None,
) -> None:
    """Park an implementer timeout that produced no publishable commit.

    Tags the park `agent_timeout` and persists the pre-agent SHA so the
    next-tick recovery (`_try_recover_implementing_timeout_park`) can publish a
    commit a lingering descendant finishes after this point without waiting for
    a human reply.

    The park is bounded because a timeout is a run that ENDED after
    `AGENT_TIMEOUT` seconds: its notice lands above anything a human wrote in
    that window, and the quiet recovery that fires only on a thread with
    nothing new on it would otherwise run over the reply meant to end the park.
    """
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent timed out after "
        f"{config.AGENT_TIMEOUT}s, manual intervention needed.",
        reason=_state._AGENT_TIMEOUT,
        bounded=True,
    )
    state.set(_state._PARK_REASON, _state._AGENT_TIMEOUT)
    state.set(_state._PRE_IMPLEMENT_SHA, before_sha or "")


def _try_recover_implementing_timeout_park(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
) -> str:
    """Quietly publish a clean commit stranded by an implementer timeout.

    Implementing-stage counterpart to validating's
    `_try_recover_validating_transient_park`. An `agent_timeout` park can
    still carry a clean commit: a descendant the timeout cleanup raced
    finished writing it after disposition (the #77 shape, where the commit
    timestamp landed after the timeout event). Republish it through the
    normal commit path so a human does not have to manually clear
    `awaiting_human` to unstick the issue.

    Returns:
      * ``"pushed"`` -- a clean commit advanced past `pre_implement_sha` and
        was handed to the shared publication seam (park flags cleared, then
        the size gate and, past it, `_on_commits`: branch pushed, PR
        opened/reused, label -> validating). Caller writes state.
      * ``"stuck"`` -- nothing safely recoverable (worktree reaped, a tree
        that is dirty or unreadable, a missing watermark, a HEAD that did not
        move, or one that moved onto a base this branch adds nothing to).
        Caller stays parked.

    The publish goes through `_publish_committed_work` rather than around it,
    which is what makes a commit recovered from a timeout the same kind of
    candidate as one a run returned with: it is measured before it is pushed,
    and an oversized one is held for adjudication instead. "Pushed" is
    therefore the recovery having ACTED -- the caller's job either way is to
    persist what it left, whether that is a published branch, a held
    candidate, or a park of its own.

    Unlike validating's silent reviewer-rerun recovery this DOES post the
    normal ":sparkles: PR opened" comment via `_on_commits` -- publishing the
    branch is the entire point of the recovery. It must not spawn the agent.
    """
    wt = _worktree_paths._worktree_path(spec, issue.number)
    if not _candidate_recovery._carries_a_late_commit(spec, state, wt):
        return _state._REASON_STUCK
    # A clean commit this branch owns advanced past the pre-timeout SHA. Clear
    # the park flags and publish it through the normal commit path.
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    state.set(_state._PRE_IMPLEMENT_SHA, None)
    work = _models._AgentWork(_unreported_recovery._recovery_result(
        state,
        "(orchestrator recovery: publishing commit produced around the agent "
        "timeout)",
    ), wt)
    # The commit a timeout stranded is an incomplete run's, owed no report --
    # recorded before the gate, so a retry of a reading it fails is not held.
    _unreported_recovery._waives_an_incomplete_run(
        gh, issue, state, work, stranded=True,
    )
    _candidate_recovery._publish_committed_work(gh, spec, issue, state, work)
    return "pushed"


def _run_left_commits(
    spec: _config_models.RepoSpec, state: PinnedState, prepared: _models._PreparedDevRun,
) -> bool:
    """True when there is committed work for THIS disposition to publish.

    Ahead-of-base answers this for every issue that reached the stage the
    ordinary way: it spawns only on a branch carrying nothing, so commits found
    afterwards are the run's. Two states break that assumption, and each leaves
    a floor behind for exactly this reading.

    A branch a read-only relabel certified and handed on was already ahead of
    base when the agent started, and `read_only_baseline_sha` names the tip it
    vouched for. A candidate the size gate froze is the same shape one step
    later: the park it took leaves committed work on the branch, and the
    developer a human's guidance resumes runs on top of it. HEAD still sitting
    on either floor means the only commits present are the ones that were
    already there -- and an agent that came back with a clarifying question
    rather than an implementation would otherwise have that work pushed, a PR
    opened over it, and the issue routed to review instead of parking on the
    question it asked. Worse for the frozen one: the work published that way
    is the very candidate whose size nobody could read.

    The RUN's own watermark is asked beside the floor, and it is the half
    that catches a resumed developer. The floor says which tip the branch
    inherited; `before_sha` says which tip this run started from, and those
    are different commits whenever a human's guidance resumed a developer on
    top of inherited work -- most sharply after a handoff refused a checkout
    sitting on a descendant of the approved commit. A head that has not moved
    since the run began is a run that committed nothing, whatever else is on
    the branch, so publishing there would push the very commit the guidance
    was asked ABOUT and drop the question the developer came back with.

    It is asked whether or not a floor exists, because the state with no
    floor at all is one of the ways to reach exactly that: a size reading
    that failed before it could freeze a candidate leaves a park and no
    record, and the guidance answering it resumes a developer on a branch
    that already carries commits nothing on the issue names. The floor is
    still asked first where there is one -- it is the narrower claim, and a
    head sitting on it is carried-over work even where this run did move the
    head onto it.

    Both questions are comparisons, so both ends have to have been READ, and
    a run either end cannot be established for publishes nothing. That is what
    `_attributable_run` refuses on, and a recovered run is the one road past
    it -- it is defined by commits that predate the tick, so there is no run
    here to attribute anything to.

    A head that did not move has one exception, and it is the park this stage
    takes over a report it could not deliver. Such an issue was never waiting
    for code: the commits are on the branch already, published or not, and
    what was asked for was a report this workflow could record and bind. So a
    run that comes back with one is publishing rather than asking, and the
    seam below records its report in place of the one nothing could deliver
    and carries the same commits through. What that exception is held to
    belongs to the owner that spells it -- a debt owed, a report outcome, and
    a branch that carries something -- so an ordinary reply, a question, or a
    run that fell short is read here exactly as it always was.
    """
    if not _worktree_creation._has_new_commits(spec, prepared.worktree):
        return False
    if prepared.recovered:
        return True
    head = _verification_probes._head_sha(prepared.worktree)
    if not _attributable_run(prepared, head):
        return False
    if head != _inherited_floor(state) and head != prepared.before_sha:
        return True
    return _report_redelivery.redelivers_an_owed_report(
        spec, state, prepared.agent_result, prepared.worktree,
    )


def _attributable_run(
    prepared: _models._PreparedDevRun, after_sha: str,
) -> bool:
    """Whether this run's own output can be told from what it started on.

    Both dispositions decide by COMPARING two tips -- where the run began and
    where it ended -- so a comparison missing an end is not a weaker answer,
    it is no answer. `_head_sha` reports its own failure as "", which is the
    one value that cannot be a commit, so an unread end reaches here looking
    exactly like a checkout with nothing on it.

    Published on that, the difference is decided by whichever end DID read: a
    run whose starting tip could not be read differs from every head there is,
    and a run whose ending tip could not be read differs from every watermark.
    Either way the branch is ahead of base -- that is the only other reading,
    and it is true of every branch this stage was handed already carrying
    work: one a read-only relabel certified, one a size-gate park left a
    candidate on, one a human's guidance resumed a developer over. So a run
    that committed nothing publishes the commits it was asked ABOUT, with the
    question it came back with dropped, or hands the size gate a candidate
    nobody made.

    Which is why the failed probe parks rather than publishes here, though it
    parks a finished run's commits behind a reading nobody got. That cost is
    bounded and visible: the commit is still in the worktree, the branch is
    untouched, and the park says so. The other way round is neither -- what
    goes out is somebody else's work under this issue's name, already pushed
    and already reviewed by the time anyone can look.
    """
    return bool(prepared.before_sha) and bool(after_sha)


def _inherited_floor(state: PinnedState) -> str:
    """The tip this branch already carried before the run being disposed.

    The read-only baseline first, because it is the narrower claim -- a
    handoff certified that exact tip -- then the frozen candidate, which says
    the same thing about a branch the size gate parked over, and the approved
    commit behind both.

    That last one is the size gate's own parks one step later, and it is the
    same claim with the generation already gone: a commit the gate approved
    and has not pushed is committed work sitting on the branch, so a run
    resumed on top of it starts ahead of base by definition. Without it, an
    agent that came back with a clarifying question rather than an
    implementation would have the commit it was asked ABOUT pushed, a pull
    request opened over it, and the issue handed to review -- with the
    question nobody answered dropped on the floor.
    """
    baseline = state.get(_state._READ_ONLY_BASELINE_SHA)
    if baseline:
        return str(baseline)
    return (
        _late_park_state._recorded_candidate(state)
        or _late_approval_reading._approved_commit(state)
    )


def _timeout_left_commits(
    spec: _config_models.RepoSpec,
    prepared: _models._PreparedDevRun,
    after_sha: str,
) -> bool:
    """True when a killed run really left committed work to publish.

    The timeout's half of the question `_run_left_commits` answers for a
    clean exit, and it asks the same two things in the same order for the
    same reason: ahead-of-base says the branch carries something the base
    does not, and the watermark says THIS run is what put it there. Either
    alone publishes work nobody made.

    Ahead-of-base is the reading a killed run cannot do without. A timeout
    that produced no commit leaves the branch exactly where the run started,
    so anything that moves the checkout without committing -- an agent that
    rebased or reset onto a base that advanced under it, a `git pull` in its
    own tooling, another process touching the worktree across an hour-long
    run -- moves the head with nothing written. Read as a difference alone
    that is a commit to publish, and what goes out is the base branch: a push,
    a pull request with no diff in it, and the issue handed to review under
    this issue's name.

    The watermark is the reading it cannot do without either, and it is why
    ahead-of-base is not simply substituted for it: a branch can arrive at
    this stage already ahead of base -- a read-only relabel hands one over,
    and a size-gate park leaves committed work a resumed developer runs on
    top of -- so the base comparison alone would publish carried-over work as
    a killed run's own.

    An end that could not be read at all fails the comparison outright, on
    the same terms the clean half now refuses it: a tip nobody established is
    not a tip, and both ends of this one can fail -- the pre-agent read that
    became `before_sha`, and the post-run read taken here. Either missing
    makes the difference an artefact of the probe rather than of the run, and
    on a branch that was already ahead of base that difference publishes work
    the run never made.
    """
    if prepared.agent_result.unfinished_steps:
        return False
    if not _attributable_run(prepared, after_sha):
        return False
    if after_sha == prepared.before_sha:
        return False
    return _worktree_creation._has_new_commits(spec, prepared.worktree)


def _dispose_agent_result(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    prepared: _models._PreparedDevRun,
) -> None:
    """Dispose a completed implementing run and write pinned state.

    A timed-out run publishes a commit produced by THIS run (clean tree), parks
    a dirty tree for inspection, or parks `agent_timeout` when the run left no
    commit. A clean exit publishes what this run committed or parks the
    agent's question. Both halves ask the same pair of questions and neither
    can be answered by one of them: `_has_new_commits` only compares to
    `origin/<base>`, and a branch can arrive here already ahead of it, while a
    head that merely MOVED says nothing about what it moved onto -- a base
    that advanced under an hour-long run answers that comparison with no
    commit having been made. So the base reading is taken beside a watermark:
    `before_sha` on the timeout half (`_timeout_left_commits`), and the
    certified baseline a read-only relabel left beside it on the clean one
    (`_run_left_commits`).

    A RECOVERED run is the clean half's own exception, and what it turns on is
    the pinned comment rather than the tree. No agent ran on this tick: the
    commits are a developer's from an earlier one, and that run's report is on
    the comment or nowhere, because recording it is the first thing that
    happens after a run returns and it happens before the size gate and the
    push. So committed work with no report recorded means the tick that made
    it never got the record out -- a pinned write that failed, or a restart
    between the run and it -- and the session that could say what it did has
    ended. Published, that is a reviewer handed an implementation nobody
    described; held, it is a reply away from the report it is missing.

    What counts as a report of it -- a debt still owed, or a settled pair
    about this very head -- is `unreported_recovery`'s, which every other
    recovery that republishes an earlier run's commits asks too.
    """
    if prepared.agent_result.timed_out:
        after_sha = _verification_probes._head_sha(prepared.worktree)
        if _timeout_left_commits(spec, prepared, after_sha):
            _candidate_recovery._publish_committed_work(
                gh,
                spec,
                issue,
                state,
                _models._AgentWork(prepared.agent_result, prepared.worktree),
            )
        else:
            _park_agent_timeout(gh, issue, state, prepared.before_sha)
        gh.write_pinned_state(issue, state)
        return

    if prepared.agent_result.unfinished_steps or not _run_left_commits(spec, state, prepared):
        _parks._on_question(
            gh, issue, state,
            _guards._ParkedRun(
                prepared.agent_result, _guards._ROUTE_DEV_RUN,
            ),
        )
        gh.write_pinned_state(issue, state)
        return
    if prepared.recovered and _unreported_recovery._holds_unreported_work(
        gh, spec, issue, state, prepared.before_sha,
    ):
        return
    _candidate_recovery._publish_committed_work(
        gh,
        spec,
        issue,
        state,
        _models._AgentWork(prepared.agent_result, prepared.worktree),
    )
    gh.write_pinned_state(issue, state)
