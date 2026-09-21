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

`_published_head_in_sync` beside it is the same reading asked for the opposite
answer, by the roads that publish without pushing: a report of the work the pull
request already carries needs the branch PROVED to be standing where that pull
request is, and "nothing was proved stranded" is not that -- every refusal below
is also a branch that may be carrying a commit nobody published. Two callers ask
it, the round that reports without committing and the fixing recovery that hands
such a report on, and they ask it of the same checkout for the same reason.

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

That head is why the dev-fix disposition takes this reading for a run that
COMMITTED as well, where the ahead/behind answer decides nothing: the commit
in hand is publishable either way, but the pull request stands below whatever
an earlier tick stranded under it, and the lease has to name the head that
publication actually carries rather than the one the agent started on.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState


def _published_head_in_sync(
    spec: _config_models.RepoSpec, wt: Path, state: PinnedState, issue: Issue
) -> str:
    """The head this branch and its remote provably AGREE on, or "" for none.

    The affirmative half of the probe below, for the roads that publish
    without pushing: a report of the work a pull request already carries, and
    the recovery that hands one on. Those need the opposite of a stranded
    commit -- proof that the checkout is
    standing exactly where the remote branch is -- and "nothing was proved
    stranded" is not that proof. The probe below answers "" for a tree nobody
    could read, a fetch that failed, a divergence git refused, and a remote
    that moved, and every one of those is a branch that may be carrying a
    commit the pull request has not got. A report published over one describes
    a head the reviewer will never see.

    So every reading is required to have HAPPENED and to say the same thing:
    a clean tree, a fetch that returned, a divergence git counted as zero both
    ways, a tip that reads, and a local HEAD that reads and IS that tip. What
    comes back is that head, so the caller holds the rest of its evidence --
    the publication receipt, the pull request the report is about -- to one
    commit rather than to two readings that could differ.
    """
    tree = _worktree_status._worktree_status(wt)
    if not tree.is_clean:
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
    if not divergence.readable or divergence.ahead or divergence.behind:
        return ""
    head = _verification_probes._head_sha(wt)
    return divergence.tip if head and head == divergence.tip else ""


def _stranded_fix_unpushed(
    spec: _config_models.RepoSpec, wt: Path, state: PinnedState, issue: Issue
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
