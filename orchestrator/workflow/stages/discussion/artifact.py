# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the branch carries, read once from the checkout the round ran in.

This stage publishes from an artifact rather than from a claim. The agent is
told to write `plans/issue-N.md` only after a human confirms on the thread that
the two of them understand the design the same way, and nothing here can check
that a human said so -- what it can check is what the branch now carries. So
the check IS the contract: a tree that could be read and is clean, a
base-relative diff of exactly that one path, and the plan itself present in
HEAD. A missing plan, a deleted one, a second one, a code or configuration
change, anything left uncommitted beside it, or a worktree that could not be
inspected at all means the round did something other than write down what was
agreed -- or that nothing here can tell -- and none of those is pushed.

`_plan_artifact` takes that reading once and hands it around whole, because the
same paths that decide are the paths the refusal quotes -- and because the tree
that was inspected has to be the tree that is pushed. It reads the checkout the
round ran in, restoring one only when the directory has gone: a dirty tree is
never recreated over, since it is the evidence the operator was parked to look
at.

What the REMOTE's tip means is left to each owner that asks for one, since a
tip that has moved is a publication already finished to one of them and a
branch nobody may overwrite to another. Making that tip askable at all is here
all the same: what `_readable_remote_tip` establishes is an object in THIS
checkout's store, so it belongs beside the worktree the artifact was taken from
rather than beside any one reading of it.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import naming as _naming, paths as _worktree_paths
from orchestrator.workflow.stages.discussion import (
    models as _models,
    run as _run,
    state as _state,
)


def _plan_artifact(run: _models._DiscussionRun) -> _models._PlanArtifact:
    """Read what the branch is carrying, in one pass, before anything moves.

    Every probe is taken, not just enough of them to reach a verdict, because
    the reading is also what the refusal quotes: an operator told only the
    first thing that was wrong would fix it and be refused again for the next.
    They are three different questions -- what is loose in the tree, what the
    commits change against base, and whether the plan is in the commit at all
    -- and a branch can pass any two of them and still not be a design anyone
    agreed to.

    Whether HEAD is the BRANCH is read beside it, because what the push sends
    is a SHA and where it sends it is `refs/heads/<branch>`. A commit an agent
    made on a detached HEAD is a real commit in a real tree, and every other
    check here would pass it -- but the branch would still be where it was, so
    the ref this stage records, the ref the relabel guard measures, and the ref
    a lost checkout is rebuilt from would all be behind what the pull request
    carries. The reading is what refuses that rather than moving somebody
    else's ref to make it true.

    The tip is read once and then NAMED to the two commit-level probes rather
    than each re-reading `HEAD`. It is the commit this reading decides about
    and the commit the push publishes, and every `git` invocation between them
    is a moment the branch could move under: asked of `HEAD`, the checks could
    answer for one commit while the push sent another.

    The other end of that diff comes from pinned state, not from a ref. The
    round recorded what the remote said the base was before it spawned, and
    reading `<remote>/<base>` here instead would ask a local ref the agent's
    own worktree can move -- which is how a branch carrying a code commit and a
    plan commit could be made to look like a branch carrying only the plan.
    """
    branch = _naming._resolve_branch_name(
        run.state, run.spec, run.issue.number,
    )
    return _probe_plan_branch(run, branch, _plan_worktree(run, branch))


def _probe_plan_branch(
    run: _models._DiscussionRun, branch: str, worktree: Path,
) -> _models._PlanArtifact:
    """Take every probe the verdict and the refusal are both built from."""
    plan_path = _state._plan_path(run.issue.number)
    head_sha = _verification_probes._head_sha(worktree)
    base_sha = str(run.state.get(_state._BASE_SHA) or "")
    tree_status = _worktree_status._worktree_status(worktree)
    return _models._PlanArtifact(
        branch=branch,
        worktree=worktree,
        plan_path=plan_path,
        head_sha=head_sha,
        head_attached=_verification_probes._head_on_branch(worktree, branch),
        base_sha=base_sha,
        tree_readable=tree_status.readable,
        plan_in_head=_verification_probes._revision_contains_path(
            worktree, head_sha, plan_path,
        ),
        dirty_files=tree_status.paths,
        changed_paths=tuple(
            _verification_probes._committed_paths_since(
                worktree, base_sha, head_sha,
            ),
        ),
    )


def _plan_worktree(run: _models._DiscussionRun, branch: str) -> Path:
    """The checkout the artifact is read and pushed from, restored if gone.

    A checkout still on disk is taken exactly as it stands -- it is what the
    round wrote into, and recreating it is how a dirty tree that carries no
    commits gets destroyed. Only a directory that has gone is rebuilt, which
    is the same case a round opening on a pruned branch handles and goes
    through the same restorer: a commit can outlive its worktree on the local
    branch -- and, once it is pushed, both of them on the remote -- so the
    crash that took the directory must not also take the plan.
    """
    worktree = _worktree_paths._worktree_path(run.spec, run.issue.number)
    if worktree.exists():
        return worktree
    return _run._ensure_round_worktree(run, branch)


def _readable_remote_tip(
    run: _models._DiscussionRun,
    artifact: _models._PlanArtifact,
    remote_tip: str,
) -> bool:
    """Make the remote's tip an object this checkout can be asked about.

    Every reading that judges a tip runs `_commit_contains`, which is a local
    command over local objects -- and the id it is handed is the remote's own
    answer about a branch this host may not have fetched since. A commit
    somebody pushed after this checkout was made is one git here cannot
    resolve, and an unresolvable id answers the same "no" a branch that really
    diverged does. That is the right answer for the caller about to overwrite a
    ref and the wrong one for the caller asking whether its own work is already
    out there: a publication whose pull request a human wrote on top of would
    be read as a divergence, refused for a commit nothing ever went to get, and
    parked again on every retry with the PR number still unrecorded.

    The fetch's exit status is deliberately not the answer, for the same reason
    the round's base read does not take it: a fetch that reported success
    without bringing this commit -- the branch moved again between the two
    commands, or was rewritten under them -- leaves the caller exactly where a
    failed one does, so the store is asked again either way. False means
    nothing about that tip can be established here, and each caller says what
    it does with that.
    """
    if _verification_probes._commit_present(artifact.worktree, remote_tip):
        return True
    _branch_transport._authed_target_fetch(run.spec, artifact.branch)
    return _verification_probes._commit_present(artifact.worktree, remote_tip)
