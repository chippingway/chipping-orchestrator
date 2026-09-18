# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Commit-pinned implementation recovery and admission through the size gate.

An approved or frozen candidate names the exact work recovery must prove.
A missing, moved, or unreadable candidate remains held. Every publication
checks the tree and passes the size gate before handing approved work on.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    paths as _worktree_paths,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    report_delivery as _report_delivery,
)
from orchestrator.workflow.stages.implementing import (
    checkout_parks as _checkout_parks,
    late_approval_reading as _late_approval_reading,
    late_evidence as _late_evidence,
    late_gate as _late_gate,
    late_park_state as _late_park_state,
    publication as _publication,
    state as _state,
    unreported_recovery as _unreported_recovery,
)
from orchestrator.workflow.stages.implementing.models import _AgentWork, _ApprovedWork, _RecoveredWork


def _publish_committed_work(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    work: _AgentWork,
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

    The report the run wrote is recorded between the tree and the gate, and
    the placement is the whole of what makes it recoverable. Past this line
    the candidate can be frozen for a human to adjudicate, the push can fail,
    and the process can die -- and on every one of those the session that
    wrote the report is gone, so a report only held in memory is a report
    nothing can ever get back. Behind the tree reading because a tree that
    cannot publish is one this disposition is not finishing at all. Ahead of
    the gate because the gate is the first thing that can hold the work for a
    human. A run that produced no report records nothing and pays nothing,
    which is every recovery that reaches this seam.

    A report this build cannot record HOLDS the tick there, and holding it at
    this line is what makes the refusal cheap: nothing has been measured,
    nothing pushed, no pull request opened, so the commit is exactly where the
    developer left it and a reply resumes the session that writes the report
    again. Waved through instead, the code would reach review with no report
    and no record of what the run said.

    A `_RecoveredWork` records nothing there -- no developer ran -- so what
    describes it has to be on the comment already, and `unreported_recovery`
    holds it where nothing is: every road that republishes a candidate a gate
    record named asks that, not only the restart shortcut. A run that did not
    complete records nothing either, by design, and the commit it left is
    written down here so a later recovery of that commit is not held for a
    report no run was ever going to write -- unless a report an earlier run
    recorded is still waiting to go out, which describes the branch before
    that commit and is never bound to it: the commit is held there instead.
    """
    state.set(_state._READ_ONLY_BASELINE_SHA, None)
    tree = _worktree_status._worktree_status(work.worktree)
    if not tree.is_clean:
        _checkout_parks._on_unpublishable_tree(
            gh, issue, state,
            _guards._ParkedRun(
                work.agent_result,
                _guards._ROUTE_CANDIDATE_PUBLICATION,
            ),
            tree,
        )
        return
    if _report_delivery.recording_stops_the_tick(
        gh, issue, state, work.agent_result, _state._REPORT_ROUTE,
    ):
        return
    _unreported_recovery._waives_an_incomplete_run(state, work)
    if _unreported_recovery._holds_an_unfinished_run(gh, issue, state, work):
        return
    if isinstance(work, _RecoveredWork) and (
        _unreported_recovery._holds_unreported_work(
            gh, spec, issue, state, work.candidate_sha,
        )
    ):
        return
    verdict = _late_gate._holds_committed_work(
        gh, spec, issue, state, work,
    )
    if verdict.held:
        return
    _publication._on_commits(
        gh, spec, issue, state,
        _ApprovedWork(
            work.agent_result, work.worktree, verdict.candidate_sha,
            verdict.delivered_pr,
        ),
    )


def _carries_a_late_commit(
    spec: _config_models.RepoSpec, state: PinnedState, worktree: Path,
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


def _holds_approved_commit(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
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
    if not _late_approval_reading._approved_commit(state):
        return False
    if _late_evidence._holds_unpublished_commit(gh, issue, state, worktree):
        return True
    _dispose_approved_commit(gh, spec, issue, state, worktree)
    return True


def _dispose_approved_commit(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
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
    _publish_committed_work(
        gh, spec, issue, state, _RecoveredWork(
            _unreported_recovery._recovery_result(
                state, "(orchestrator recovery: publishing the approved commit)",
            ),
            worktree,
            _late_approval_reading._approved_commit(state),
        ),
    )


def _holds_unreconciled_candidate(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
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
    if not _late_park_state._recorded_candidate(state):
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
    spec: _config_models.RepoSpec,
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
    spec: _config_models.RepoSpec,
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
    _publish_committed_work(
        gh, spec, issue, state, _RecoveredWork(
            _unreported_recovery._recovery_result(
                state, "(orchestrator recovery: reconciling the frozen candidate)",
            ),
            worktree,
            _late_park_state._recorded_candidate(state),
        ),
    )
