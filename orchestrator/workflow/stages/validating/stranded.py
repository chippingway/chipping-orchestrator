# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One reading of a fix branch against its publication, and what it proved.

A commit a parked run left on the branch reads exactly like "the agent did
nothing" on every later resume -- `after_sha == before_sha` -- so without a
probe of its own the commit never reaches the pull request and the issue
ping-pongs between awaiting-human parks forever. Four routes ask that
question: the shared dev-fix disposition, the fixing ACK fast path that must
stand down on it, the transient recovery of a timed-out round -- which asks it
whether that run committed or not, for the clear and for the two ends of the
push it may license -- and the no-feedback bounce that is the validating
route's last tick to publish it.

A fifth asks the same reading for the opposite answer, by the road that
publishes without pushing: a report of the work the pull request already
carries needs the branch PROVED to be standing where that pull request is.

It is one reading rather than one per road because the refusals are the whole
contract. A tree nobody could read, a tree carrying loose work, a fetch that
failed, a divergence git refused, a remote that moved, and a checkout that
moved under the reading itself are each a branch that MAY be carrying a commit
the pull request has not got -- and a route that reimplemented the shape would
be one refusal short of the others without anything saying so.

What it answers with is which of those it found, because "nothing proved" and
"nothing to publish" are opposite facts and a caller reading one for the other
either publishes blind or hands a reviewer a head the pull request never
received. Only `stranded` and `in_sync` are readings that HAPPENED; every
other finding is a refusal, and every caller is expected to take its own
no-publish road on one rather than to read it as an empty branch.

BOTH ends of the count ride on the answer, because what a caller does next is
a push and a push has two of them. The remote head the proof was taken AGAINST
is what the push replaces: handed on, the size gate is pinned to it, and a
pull request somebody moved between this probe and that push refuses instead
of being adopted as the lease and force-overwritten. The LOCAL commit the
count was taken over is what goes out, and it is frozen BEFORE the count and
re-proved after it: `HEAD` is a symbol every command re-resolves, so counting
against it and naming a commit afterwards can describe two different ones.
Frozen, the numbers are about the commit handed on; re-proved, a checkout
something moved mid-reading refuses instead of having whatever it points at
measured, pushed and receipted as the work this reading placed.

That head is why the dev-fix disposition takes this reading for a run that
COMMITTED as well, where the ahead/behind answer decides nothing: the commit
in hand is publishable either way, but the pull request stands below whatever
an earlier tick stranded under it, and the lease has to name the head that
publication actually carries rather than the one the agent started on.

An `in_sync` finding is taken only where the checkout's own HEAD was read and
IS the tip the counts were taken against. The counts already say the two
agree, so that second reading buys one thing -- a checkout something moved
between the two commands -- and it is a refusal of its own rather than a head
left off an agreement: a caller told the branch is settled would clear a
report debt, hand a round back, or re-arm a ready ping on the strength of a
race this reading had already watched happen.

What each refusal MEANS is this module's vocabulary too, and is read off
`_REFUSAL_DETAILS` rather than worded at the roads: a caller that spelled one
for itself would be describing a reading it never took, and two callers would
word the same condition differently on the same issue.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState

# The branch is carrying a commit the remote pull-request branch has not got,
# and is behind nothing: the one finding that licenses a push.
_STRANDED = "stranded"

# The branch and its remote agree exactly: nothing is waiting to be published.
_IN_SYNC = "in_sync"

# `git status` established nothing about the checkout at all.
_UNREADABLE_TREE = "unreadable_tree"

# The checkout is carrying work nothing has committed, so what the branch
# holds is not the whole of what is there.
_LOOSE_TREE = "loose_tree"

# The pull request's branch could not be fetched, so the tip every count below
# would be taken against is whatever was last on disk.
_FETCH_FAILED = "fetch_failed"

# git would not say how far the checkout stands from that tip.
_UNREADABLE_DIVERGENCE = "unreadable_divergence"

# The remote carries commits the checkout has not got. Pushing would race a
# head nobody reconciled, and the branch may be ahead of it as well.
_REMOTE_MOVED = "remote_moved"

# The checkout's own HEAD did not read, or -- where the counts said it and its
# remote agree -- read as something other than the tip they were taken against.
# Either way the geometry those counts describe is about a commit this reading
# cannot name, so there is no end for a publication to be pinned to.
_MOVED_CHECKOUT = "moved_checkout"

# The clause each refusal owes a caller that has to say why its road stopped.
# Spelled here rather than at the roads, because what a finding MEANS is this
# module's to say: a caller that worded it for itself would be describing a
# reading it did not take, and two callers would word the same refusal
# differently on the same issue.
_REFUSAL_DETAILS = MappingProxyType({
    _UNREADABLE_TREE: (
        "this orchestrator could not read the state of the checkout the "
        "branch is in"
    ),
    _LOOSE_TREE: (
        "the checkout is carrying work nothing has committed, so what would "
        "be published is not the whole of what is there"
    ),
    _FETCH_FAILED: "the pull request's branch could not be fetched",
    _UNREADABLE_DIVERGENCE: (
        "git would not say how far the checkout stands from the pull "
        "request's branch"
    ),
    _REMOTE_MOVED: (
        "the pull request's branch carries commits this checkout has not "
        "got, so nothing here may be pushed over it"
    ),
    _MOVED_CHECKOUT: (
        "the checkout moved while it was being read, so nothing this "
        "orchestrator counted is about the commit it is standing on now"
    ),
})


@dataclass(frozen=True)
class _StrandedEvidence:
    """Where one reading proved a fix branch stands against its publication.

    `finding` is the whole answer and is deliberately not a bool: "the branch
    is carrying nothing unpublished" and "nothing about the branch could be
    read" are opposite facts, and a caller that collapsed them would either
    publish over a head nobody reconciled or hand a reviewer a head the pull
    request never received.

    `head` is the remote tip the reading was taken against, carried so a
    caller's next push is pinned to the same commit the proof was about, and
    empty on every refusal. So a finding that PROVED something always names
    its commit: there is no shape here that says "the branch is placed" and
    cannot say where, because a caller handed one would be acting on a reading
    that had already seen the ground move.

    `candidate` is the other end of that same claim: the LOCAL commit the
    ahead/behind count was taken over. Both ends are needed because a caller's
    next step is a push and the push has two halves -- what goes out and what
    it replaces -- and only the second is on the remote. Left unnamed, the
    checkout is writable between this reading and the size gate's own proof of
    it, so a commit landing in that window is what the gate measures, pushes
    and receipts, while the route that reached this answer goes on as if the
    commit it counted had gone out. Handed on, the two are one decision and a
    gate finding the checkout anywhere else refuses instead.
    """

    finding: str
    head: str = ""
    candidate: str = ""

    @property
    def stranded(self) -> str:
        """The remote head an unpublished commit is proved to be ahead of."""
        return self.head if self.finding == _STRANDED else ""

    @property
    def in_sync(self) -> str:
        """The head the checkout and its remote are proved to AGREE on."""
        return self.head if self.finding == _IN_SYNC else ""

    @property
    def settled(self) -> bool:
        """Whether the branch proved it is carrying nothing unpublished.

        What the roads that only have to decide against publishing ask, and
        the reason it is not `not self.stranded`: every refusal answers no
        stranded head too, and each of them is a branch that may be holding a
        commit the pull request has not got.
        """
        return bool(self.in_sync)

    @property
    def refusal(self) -> str:
        """Why this reading proved nothing, or "" where it proved something.

        What a road that stops on a refusal owes whoever has to clear it. The
        six are not one condition: a checkout holding loose work and a remote
        that moved past it are somebody's to act on, while an unreadable
        status, a failed fetch and a divergence git would not count may be one
        request that did not return -- and an operator reading "could not be
        established" cannot tell which without being told.
        """
        return _REFUSAL_DETAILS.get(self.finding, "")


def _stranded_evidence(
    spec: _config_models.RepoSpec, wt: Path, state: PinnedState, issue: Issue
) -> _StrandedEvidence:
    """Read where this checkout stands against the branch its pull request is on.

    Fail-closed at every step: each reading has to have HAPPENED and to say
    what the next one is asked on top of. The tree is proved clean because a
    branch published out of a checkout holding loose work publishes less than
    what is there; the local commit is FROZEN before anything counts it, so
    the numbers and the commit handed on are the same one; the fetch has to
    have returned, because the counts below are taken against the ref it
    writes; and the divergence has to be one git counted rather than one it
    declined. The tree and the commit are then both proved AGAIN, since
    everything between the two readings is time the checkout is writable in.

    The shape arises when a publish was blocked at commit time -- a
    dirty-worktree park whose stray files a human later had the dev clean up,
    a run the shutdown sweep killed between its commit and its push -- so
    every later resume sees `after_sha == before_sha`, and without this the
    stranded commit never reaches the pull request.
    """
    unclean = _tree_refusal(wt)
    if unclean:
        return _StrandedEvidence(unclean)
    # The local end, FROZEN before anything is counted. `HEAD` is a symbol
    # every command re-resolves, so a count taken against it and a commit read
    # afterwards can be two different commits -- and the second is what a
    # caller would publish. Named here, the count below is about this id and
    # nothing else.
    frozen = _verification_probes._head_sha(wt)
    if not frozen:
        return _StrandedEvidence(_MOVED_CHECKOUT)
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    fetch = _branch_transport._authed_fetch(
        spec,
        f"+refs/heads/{branch}:refs/remotes/{spec.remote_name}/{branch}",
        cwd=wt,
    )
    if fetch.returncode != 0:
        return _StrandedEvidence(_FETCH_FAILED)
    return _counted_against_the_remote(spec, wt, branch, frozen)


def _tree_refusal(wt: Path) -> str:
    """Why this checkout may not be published from, or "" where it may.

    One reading, asked twice: once before the branch is placed and once after,
    since the whole placement is network and subprocess time and a tree that
    picks up loose work in it is one a publication would leave short of what
    is there. Named rather than answered with a bool, because a status nobody
    could take and a status that named paths are different things to say to
    whoever has to clear it.
    """
    tree = _worktree_status._worktree_status(wt)
    if not tree.readable:
        return _UNREADABLE_TREE
    return _LOOSE_TREE if tree.paths else ""


def _counted_against_the_remote(
    spec: _config_models.RepoSpec, wt: Path, branch: str, frozen: str,
) -> _StrandedEvidence:
    """Count one frozen commit against the fetched tip, and re-prove it.

    `behind` is answered before `ahead` because it outranks it: a branch that
    is ahead AND behind is carrying unpublished work over a head nobody
    reconciled, which is the one shape where publishing would lose somebody
    else's commit. Named as the moved remote it is, the caller holds rather
    than reading a refusal as an empty branch.

    The count names `frozen` rather than the checkout's symbolic `HEAD`, so
    what the numbers describe is the commit this reading is about however many
    times the worktree is written while git walks it. The checkout is then
    re-proved -- both halves, the commit it stands on and the tree around it --
    which is what says the opening reading, the count, and the evidence handed
    to the caller are one world rather than several readings of a moving one.
    """
    divergence = _publication_probes._branch_divergence(
        spec, wt, branch, frozen,
    )
    if not divergence.readable:
        return _StrandedEvidence(_UNREADABLE_DIVERGENCE)
    if divergence.behind:
        return _StrandedEvidence(_REMOTE_MOVED)
    return _placed_at(divergence, frozen, wt)


def _placed_at(
    divergence: _publication_probes._BranchDivergence, frozen: str, wt: Path,
) -> _StrandedEvidence:
    """Name the two ends one count placed the branch between, or refuse.

    A checkout that is no longer standing on the commit the count was taken
    over is the ground moving between two commands rather than a branch
    standing still -- and the refusal is the whole point of freezing: the
    count is sound either way, but the caller's push would go out over a
    worktree nothing here has read. A HEAD that does not read answers the
    same, since the re-proof is what it was for.

    The TREE is re-proved beside it, because the commit is only half of what a
    publication is taken over and a checkout can pick up loose work without
    moving its head at all. The fetch and the count are network and subprocess
    time -- an agent, an operator, a stray descendant -- so a tree proved
    clean before them says nothing about the one this evidence is handed on
    for. Settled over a dirty tree, the bounce clears its bookmarks and hands
    a reviewer a pull request that is short of whatever is lying in the
    worktree.

    On the in-sync finding the frozen commit is an identity claim as well as
    an end, and it is asserted rather than assumed: zero both ways means the
    two ARE the same commit, so a tip that says otherwise is a count nothing
    here can make sense of.
    """
    head = _verification_probes._head_sha(wt)
    if head != frozen or (not divergence.ahead and frozen != divergence.tip):
        return _StrandedEvidence(_MOVED_CHECKOUT)
    unclean = _tree_refusal(wt)
    if unclean:
        return _StrandedEvidence(unclean)
    return _StrandedEvidence(
        _STRANDED if divergence.ahead else _IN_SYNC, divergence.tip, frozen,
    )
