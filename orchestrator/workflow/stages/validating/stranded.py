# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The fix an earlier run committed and never published, and what proves it.

A commit a parked run left on the branch reads exactly like "the agent did
nothing" on every later resume -- `after_sha == before_sha` -- so without a
probe of its own the commit never reaches the pull request and the issue
ping-pongs between awaiting-human parks forever. Three routes ask that
question: the shared dev-fix disposition, the fixing ACK fast path that must
stand down on it, and the no-feedback bounce that is the validating route's
last tick to publish it.

It is one probe rather than three because the refusals are the whole contract.
A dirty tree, a fetch that failed, a divergence nothing could read, and a
remote that moved all answer "nothing proved", because pushing over a head
nobody reconciled is worse than one more park -- and a route that reimplemented
the shape would be one refusal short of the others without anything saying so.

The answer is the remote head the proof was taken AGAINST rather than a bare
yes, because what the caller does next is a push and the claim this took is
about one commit: the branch is ahead of THAT head and behind nothing. Handed
on, the size gate is pinned to it, and a pull request somebody moved between
this probe and that push refuses instead of being adopted as the lease and
force-overwritten.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState


def _stranded_fix_unpushed(
    spec: config.RepoSpec, wt: Path, state: PinnedState, issue: Issue
) -> str:
    """The remote head a stranded fix is proved ahead of, or "" where none is.

    A clean worktree HEAD strictly ahead of the remote PR branch is a fix an
    earlier parked run committed and never published.

    The shape arises when the publish was blocked at commit time (e.g. a
    dirty-worktree park whose stray files a human later had the dev clean
    up): every later resume sees `after_sha == before_sha`, so without
    this check the stranded commit can never reach the PR and the issue
    ping-pongs between `awaiting_human` parks forever.

    Conservative by construction: a dirty tree, a failed fetch, or a
    remote that moved (`behind > 0` -- pushing would race a head we have
    not reconciled) all report "", so the caller takes whichever
    no-publish path it owns -- the question park in the dev-fix
    disposition, the bounce back to `validating` in the fixing handler's
    no-feedback exit -- instead of pushing blind.

    What comes back is the head the comparison was taken AGAINST rather than
    a bare yes. The caller's next step is a push, and the proof this took is
    a claim about one commit: the branch is ahead of THAT head and behind
    nothing. Handed on, the gate is pinned to it and a pull request somebody
    moved between this probe and that push refuses instead of being adopted
    as the lease and force-overwritten. A tip nothing could read is no head
    either, and refuses here rather than publishing against one.
    """
    if _worktree_status._worktree_dirty_files(wt):
        return ""
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    fetch = _branch_transport._authed_fetch(
        spec,
        f"+refs/heads/{branch}:refs/remotes/{spec.remote_name}/{branch}",
        cwd=wt,
    )
    if fetch.returncode != 0:
        return ""
    divergence = _publication_probes._branch_divergence(spec, wt, branch)
    if not divergence.readable or divergence.ahead <= 0 or divergence.behind:
        return ""
    return divergence.tip
