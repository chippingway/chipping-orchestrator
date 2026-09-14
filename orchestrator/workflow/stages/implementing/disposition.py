# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finished dev run leaves behind, and the timeout's second chance.

`before_sha` -- the pre-agent HEAD -- is what these four share. A timed-out run
is not automatically a failure: the implementer can commit clean work and then
be killed by the timeout, or a descendant can finish the commit during cleanup,
so the disposition asks whether HEAD MOVED rather than whether the run exited
well. `_has_new_commits` cannot answer that (it compares against
`origin/<base>`, so carried-over commits from an earlier tick look identical),
which is the whole reason the watermark is threaded this far.

Neither reading answers it alone, and both of the timeout's readers are where
that costs something. A watermark difference says the checkout moved and not
what it moved TO: a run that timed out having committed nothing leaves a
branch with nothing ahead of base, so anything that advances the checkout onto
that base -- an agent rebasing or resetting mid-run, the refresh between two
ticks -- produces the difference with no developer having written a line. So
the disposition and the recovery both ask both questions -- the head is not
where the run started, AND the branch carries something the base does not --
and publish only where both hold.

When HEAD did not move, the park persists that same watermark as
`pre_implement_sha`, and that is why the recovery lives here rather than beside
the other preflight checks: it is the only reader of what the park wrote, and it
republishes through the normal commit path -- the ":sparkles: PR opened" comment
included -- because publishing the branch IS the recovery. It must never spawn
an agent, and it stays parked on anything it cannot vouch for: a reaped
worktree, a tree that is dirty or that nothing could read, a watermark that
names no commit, an unmoved HEAD, or a head standing on a base this branch
adds nothing to.

Both dispositions route a committed worktree through one place, so a dirty tree
refuses the push identically whether it came from a clean exit, a timeout, or a
drift resume -- and so does an oversized one. That single seam is where the
size gate beside this owner runs, which is what lets one measurement stand
between every clean committed candidate and the branch it would be published
on.

The parks that gate takes are recovered from `late_recovery` rather than from
here, and the split is what each park is waiting FOR. The timeout's is this
owner's because the watermark it persists is this owner's own reading, which
nothing else has any claim on. The gate's three are waiting on a reading, a
checkout, or an operator's decision -- none of them a fact about the run that
finished -- so what they share is not the disposition but the seam they hand
their answer back to, which is `_publish_committed_work` below.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    paths as _worktree_paths,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.implementing import (
    late_evidence as _late_evidence,
    late_gate as _late_gate,
    late_parks as _late_parks,
    models as _models,
    parks as _parks,
    publication as _publication,
    session_read as _session_read,
    state as _state,
)


def _publish_committed_work(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    work: _models._AgentWork,
) -> None:
    """Publish a worktree that carries a new commit.

    A clean tree pushes/opens the PR via `_on_commits`; a tree with
    uncommitted edits parks via `_on_dirty_worktree` (pushing would publish a
    branch that omits the dirty files). Shared by the fresh-completion, timeout,
    and user-content-drift dispositions so each handles a committed worktree
    identically.

    Clean is PROVED here rather than inferred from an empty answer. The list
    form of the status read maps its own failure to "no paths", which is the
    right shape for a caller refusing on what git DID name and the wrong one
    for this caller: what follows is a push, so a reading that never happened
    would publish a branch nobody could show matched the work. The status form
    keeps the two apart, and both halves of "not provably clean" park.

    Reaching here retires the read-only baseline. It named the tip a handoff
    was certified at so a run that committed nothing could be told from one
    that did, and there is committed work here either way -- while a baseline
    left behind would go on freezing this branch out of the base refresh long
    after the stage that needed it still holds the issue.

    The size gate sits between the two, and only a CLEAN tree reaches it: a
    candidate measured beside uncommitted changes is not the candidate a push
    would publish, and the diff it would be adjudicated on is not the one a
    human would read. Being the one seam all three dispositions publish
    through is what makes the gate a contract rather than a check -- an
    oversized candidate is held here whether it came from a clean exit, a
    timeout that committed first, or a branch a crash stranded.

    What the gate hands back is the COMMIT it let through, not merely its
    permission, and the push is named against it. Between the reading and the
    write another tick, an operator, or a descendant the timeout cleanup
    raced can move `HEAD` -- and a push that named nothing would publish
    whatever it had become, while the record named the commit that passed.

    A `_RecoveredWork` says this call is answering a reading a previous tick
    recorded rather than disposing what a run just produced. No developer ran
    on those paths, so the switch's bypass and a head that moved both mean
    something different there, and the gate is told which kind of tick it is
    by the work it is handed rather than left to guess from a checkout that
    cannot say.
    """
    state.set(_state._READ_ONLY_BASELINE_SHA, None)
    tree = _worktree_status._worktree_status(work.worktree)
    if not tree.is_clean:
        _parks._on_unpublishable_tree(
            gh, issue, state, work.agent_result, tree,
        )
        return
    verdict = _late_gate._holds_committed_work(
        gh, spec, issue, state, work,
    )
    if verdict.held:
        return
    _publication._on_commits(
        gh, spec, issue, state,
        _models._ApprovedWork(
            work.agent_result, work.worktree, verdict.candidate_sha,
            verdict.delivered_pr,
        ),
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
    """
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent timed out after "
        f"{config.AGENT_TIMEOUT}s, manual intervention needed.",
        reason=_state._AGENT_TIMEOUT,
    )
    state.set(_state._PARK_REASON, _state._AGENT_TIMEOUT)
    state.set(_state._PRE_IMPLEMENT_SHA, before_sha or "")


def _carries_a_late_commit(
    spec: config.RepoSpec, state: PinnedState, worktree: Path,
) -> bool:
    """Whether this checkout really holds a commit the timeout stranded.

    Every reading the silent recovery has to take before it may publish, and
    all of them refuse the same way: the issue is parked already, so what a
    refusal owes is silence rather than a second notice on the thread.

    The tree comes first and is PROVED clean -- uncommitted edits would make
    the push publish an incomplete branch, and a `git status` that established
    nothing is not a clean tree. Then the watermark, which has to name a
    commit at all: the park persists it from the pre-agent head read, and that
    read can itself have failed and written "", against which every readable
    head compares as "moved". Then the head, which has to differ from it --
    the older question, and the whole reason the watermark is kept.

    And then the one the difference alone cannot answer: WHAT the head moved
    to. A run killed before its first commit leaves a branch with nothing
    ahead of base, so any advance of the base fast-forwards this checkout onto
    the new tip -- the head differs from the watermark, and no developer wrote
    a line. Published on that reading the issue gets a branch and a pull
    request with no diff in them. The pre-tick refresh freezes a branch parked
    like this so the rewrite does not happen at all; this reading is what
    answers for the one it did not perform -- an operator's, another
    process's, or a rebase from before that freeze existed. It fails closed
    for the reason the tree read does: a comparison nobody could run is not
    evidence of a commit either.
    """
    if not worktree.exists():
        # Worktree reaped: the local commit is gone, nothing to publish.
        return False
    if not _worktree_status._worktree_status(worktree).is_clean:
        return False
    pre_sha = state.get(_state._PRE_IMPLEMENT_SHA)
    if not isinstance(pre_sha, str) or not pre_sha:
        return False
    now_sha = _verification_probes._head_sha(worktree)
    if not now_sha or now_sha == pre_sha:
        return False
    return _worktree_creation._has_new_commits(spec, worktree)


def _try_recover_implementing_timeout_park(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState
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
    if not _carries_a_late_commit(spec, state, wt):
        return _state._REASON_STUCK
    # A clean commit this branch owns advanced past the pre-timeout SHA. Clear
    # the park flags and publish it through the normal commit path.
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    state.set(_state._PRE_IMPLEMENT_SHA, None)
    _, _, _, dev_sid = _session_read._read_dev_session(state)
    agent_result = AgentResult(
        session_id=dev_sid,
        last_message=(
            "(orchestrator recovery: publishing commit produced around the "
            "agent timeout)"
        ),
        exit_code=0,
        timed_out=False,
        stdout="",
        stderr="",
    )
    _publish_committed_work(
        gh, spec, issue, state, _models._AgentWork(agent_result, wt),
    )
    return "pushed"


def _holds_approved_commit(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> bool:
    """Finish the publication an approval licensed, or park for its checkout.

    The crash window an approval opens, answered where the restored checkout
    can finally be read. The write that approves a candidate drops the
    generation naming it and the push it licenses runs after that write, so a
    tick that died in between leaves committed work on the branch, an
    `late_approved_sha` naming it, and nothing else saying the workflow is
    waiting for anything.

    Which is why this owns the tick outright rather than proving the checkout
    and handing it back. What it would be handed back to is the ahead-of-base
    shortcut, and every one of that shortcut's answers is wrong here. A branch
    whose base has since absorbed the commit -- or a probe that simply could
    not answer -- reads as an issue with nothing to publish and buys a second
    developer run for an implementation that is already written. A branch that
    does read as ahead goes through the gate as a fresh candidate: measured
    again, against a base that has moved, and routed to an adjudication a
    human may already have answered -- or, with the switch off, published
    under whatever the CHECKOUT names, which is a head shipped against a
    decision taken about a different commit.

    So the recorded SHA is carried through to the publication instead, exactly
    as a stranded pair is: the commit is disposed against the record that
    names it, the gate recognizes it as the one it already approved, and the
    push is named against it. Nothing is spawned, because the run that
    produced this commit finished before the crash.
    """
    if not _late_parks._approved_commit(state):
        return False
    if _late_evidence._holds_unpublished_commit(gh, issue, state, worktree):
        return True
    _dispose_approved_commit(gh, spec, issue, state, worktree)
    return True


def _dispose_approved_commit(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> None:
    """Publish the approved commit through the seam every disposition uses.

    A `_RecoveredWork` because no developer ran on this tick: the head is held
    to the record for the whole of it, and the switch's bypass is not an
    answer to a question the gate already asked.

    Held to the record means NAMED on the work, not merely proved above it.
    The proof that the checkout stands on the approved commit is taken before
    this call and the gate reads the head again for itself, and the worktree
    is writable in between: a commit landing there is measured as this tick's
    candidate, approved in the original's place, and pushed -- so the approval
    a human or a reading stood behind is cleared for a commit neither ever
    saw. Named, the gate refuses it before anything is persisted or pushed.
    """
    _, _, _, dev_sid = _session_read._read_dev_session(state)
    agent_result = AgentResult(
        session_id=dev_sid,
        last_message=(
            "(orchestrator recovery: publishing the approved commit)"
        ),
        exit_code=0,
        timed_out=False,
        stdout="",
        stderr="",
    )
    _publish_committed_work(
        gh, spec, issue, state, _models._RecoveredWork(
            agent_result, worktree, _late_parks._approved_commit(state),
        ),
    )


def _holds_unreconciled_candidate(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """Prove a recorded candidate is here before this tick spawns anything.

    The crash window the persist-before-count ordering opens: the pair went
    down durably and the tick died before it was counted or parked, so the
    record names a frozen commit and nothing on the issue says the workflow is
    waiting for anything. On the host that froze it the next tick simply
    measures again. On another one -- a rebuilt host, a restored deployment --
    the checkout is recreated at base, the recorded commit is nowhere in it,
    and the ordinary flow would spawn a SECOND developer against an issue
    whose first one already finished and whose work is recorded.

    So the record is reconciled ahead of the spawn: the worktree has to be
    there and BOTH ends of the pair readable in it. None of the three is a
    thing a fresh run could supply -- the recorded commits are the evidence --
    so a host without them parks and asks for the checkout back.

    And where they are all there, the tick finishes what the crashed one
    started rather than handing the issue to the ordinary flow. That is the
    other half of the same bug: "is there work to publish" is answered
    downstream by asking whether the branch is ahead of the CURRENT base, and
    a base that has since absorbed the candidate -- or a probe that simply
    could not answer -- reads as a branch carrying nothing, which spawns a
    second developer over work the first one already committed. The record
    names the pair outright, so it is disposed against that pair directly and
    no heuristic is consulted at all.

    Returns False for every issue that has no frozen candidate to reconcile,
    which is all of them outside that window, and for one already parked --
    there the park owns the tick and the reply to it decides what happens
    next.
    """
    if state.get(_state._AWAITING_HUMAN):
        return False
    if not _late_parks._recorded_candidate(state):
        return False
    wt = _worktree_paths._worktree_path(spec, issue.number)
    if not wt.exists():
        _late_evidence._holds_missing_candidate(gh, spec, issue, state, wt)
    elif not _reconcilable(gh, spec, issue, state, wt):
        _dispose_recorded_candidate(gh, spec, issue, state, wt)
    gh.write_pinned_state(issue, state)
    return True


def _reconcilable(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> bool:
    """Whether anything about the recorded pair stops this reconciliation.

    Three proofs, and the middle one is the reason the other two are not
    enough. Both objects being readable says the evidence survived; it says
    nothing about what the checkout is ON. And no developer ran on this path
    -- the run whose work this is finished before the crash -- so a head
    somewhere else is not fresh output to be measured in the recorded
    candidate's place. It is a checkout somebody or something moved, and
    measuring it would answer the size question about a commit nobody froze
    while the record naming the real one was discarded.
    """
    if _late_evidence._holds_absent_candidate(gh, spec, issue, state, worktree):
        return True
    if _late_evidence._holds_moved_candidate(gh, spec, issue, state, worktree):
        return True
    return _late_evidence._holds_absent_base(gh, spec, issue, state, worktree)


def _dispose_recorded_candidate(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> None:
    """Finish the disposition the crashed tick was in the middle of.

    Both ends of the pair are proved here, so what is left is exactly what the
    tick that froze them was about to do: measure, and publish or hold on the
    answer. It goes through the shared committed-work seam like every other
    disposition, which is what makes the outcomes the same ones -- and it
    spawns nothing, because the run that produced this commit already
    finished.

    The candidate those proofs were about is named on the work for the reason
    every other recovery names one: the gate reads the head again, the
    worktree is writable in between, and a commit landing there is a candidate
    no reading covers -- measured and published under a record naming the one
    the crashed tick froze.
    """
    _, _, _, dev_sid = _session_read._read_dev_session(state)
    agent_result = AgentResult(
        session_id=dev_sid,
        last_message=(
            "(orchestrator recovery: reconciling the frozen candidate)"
        ),
        exit_code=0,
        timed_out=False,
        stdout="",
        stderr="",
    )
    _publish_committed_work(
        gh, spec, issue, state, _models._RecoveredWork(
            agent_result, worktree, _late_parks._recorded_candidate(state),
        ),
    )


def _run_left_commits(
    spec: config.RepoSpec, state: PinnedState, prepared: _models._PreparedDevRun,
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
    """
    if not _worktree_creation._has_new_commits(spec, prepared.worktree):
        return False
    if prepared.recovered:
        return True
    head = _verification_probes._head_sha(prepared.worktree)
    if not _attributable_run(prepared, head):
        return False
    return head != _inherited_floor(state) and head != prepared.before_sha


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
        _late_parks._recorded_candidate(state)
        or _late_parks._approved_commit(state)
    )


def _timeout_left_commits(
    spec: config.RepoSpec,
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
    if not _attributable_run(prepared, after_sha):
        return False
    if after_sha == prepared.before_sha:
        return False
    return _worktree_creation._has_new_commits(spec, prepared.worktree)


def _dispose_agent_result(
    gh: GitHubClient,
    spec: config.RepoSpec,
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
    """
    if prepared.agent_result.timed_out:
        # The implementer can commit clean work and then get killed by the
        # timeout (or a descendant finishes the commit during cleanup). Don't
        # strand that commit behind `awaiting_human`: publish it if this run
        # really left a commit and the tree is clean, park a dirty tree for
        # inspection, or park as a timeout when it left nothing.
        after_sha = _verification_probes._head_sha(prepared.worktree)
        if _timeout_left_commits(spec, prepared, after_sha):
            _publish_committed_work(
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

    if _run_left_commits(spec, state, prepared):
        _publish_committed_work(
            gh,
            spec,
            issue,
            state,
            _models._AgentWork(prepared.agent_result, prepared.worktree),
        )
    else:
        _parks._on_question(gh, issue, state, prepared.agent_result)
    gh.write_pinned_state(issue, state)
