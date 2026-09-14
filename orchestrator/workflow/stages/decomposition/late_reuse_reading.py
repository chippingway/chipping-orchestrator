# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Snapshot reuse verdicts from reclamation receipts, lineage, mirrors, and remote refs.

A receipt takes precedence over a surviving local mirror. Unreadable
evidence defers dispatch, and a remote ref must still carry its exact commit.
"""
from __future__ import annotations

import logging
from enum import Enum
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.snapshots import mirrors as _snapshot_mirrors, refs as _snapshot_refs
from orchestrator.github import client as _client, comments as _comments
from orchestrator.workflow.late_split import ancestry as _ancestry, lineage as _lineage, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration

log = logging.getLogger("orchestrator.workflow")



class _Reuse(Enum):
    """What one dispatch may do with the snapshot a child was cut from.

    Four answers rather than a boolean, because the three that stop the child
    are stopped in different ways: two are verdicts a human has to act on and
    are parked with the pointer dropped, and the third is the absence of a
    verdict, which is held for the next tick and writes nothing at all.
    """

    ALLOWED = "allowed"
    DEFERRED = "deferred"
    RECLAIMED = "reclaimed"
    REPOINTED = "repointed"


# What the remote's reading of the ref means for the child that names it.
# `PRESENT` is the only reading that lets work start; every reading this table
# does not name -- an outage, an answer a later transport adds -- holds the
# dispatch instead, because the question here is whether a promise still
# stands and nothing but an answer may settle it.
_OBSERVED_VERDICTS = MappingProxyType({
    _snapshot_refs.SnapshotOutcome.PRESENT: _Reuse.ALLOWED,
    _snapshot_refs.SnapshotOutcome.ABSENT: _Reuse.RECLAIMED,
    _snapshot_refs.SnapshotOutcome.MISMATCH: _Reuse.REPOINTED,
})


def _unrecorded_verdict(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    claimed: _ancestry.LateAncestry,
) -> tuple[_Reuse, _ancestry.LateAncestry | None]:
    """What an issue whose BODY claims a lineage may do, and on whose word.

    The receipt first, and on its own terms: it is a comment of ours, so it is
    the one claim about this issue that nobody outside this orchestrator can
    make. It also answers for a lineage the ledger below can no longer
    corroborate -- an owner that has since minted another cycle keeps no
    record of the one this issue was cut from, while the receipt it left
    stays exactly where it was posted. A thread this tick could not read
    holds the dispatch there and then, for the reason it does above: what it
    may be hiding outranks everything asked after it.

    Then the owner's own generation, read fresh, because the marker is the one
    lineage claim in this workflow that comes out of a field the world can
    write. A claim that record does not vouch for is a claim about nothing:
    the guard steps aside, since parking an issue -- comment, mention, and
    all -- on the strength of a sentence somebody typed into its body is the
    denial of service that reading it as authority buys. That is also the
    honest answer for the OTHER crash window, the child created before its
    number was recorded: the owner cannot reclaim a ref while its own ledger
    may be short one child, so a ref nothing vouches for is a ref nothing has
    taken.

    A record that could not be read, or one whose consumer list this binary
    cannot type, vouches for nothing either -- and that is not the same
    answer. There the claim may be perfectly true and this tick simply cannot
    tell, so the dispatch is held rather than released. An issue stalled that
    way is one whose own body says it came from a split; the way out is the
    owner's ledger becoming readable, or the marker not being there.

    What a vouched claim yields is the whole pointer the failed seed never
    wrote -- the ref the identity mints, the commit the owner recorded
    preserving -- and the remote is asked about exactly that.
    """
    receipt = _receipt_verdict(gh, issue, claimed)
    if receipt is not None:
        return receipt, None
    try:
        owner = gh.read_pinned_state(gh.get_issue(claimed.parent_issue))
    except Exception:
        log.exception(
            "issue=#%s could not read the split on #%s its body claims",
            issue.number, claimed.parent_issue,
        )
        return _Reuse.DEFERRED, None
    recorded = _late_state.read_late_generation(owner)
    vouched = _lineage.vouched_lineage(claimed, issue.number, recorded)
    if vouched is None:
        return _unvouched_verdict(recorded), None
    return _asked_verdict(spec, vouched), vouched


def _unvouched_verdict(recorded: LateGeneration) -> _Reuse:
    """What a claim the owner's record does not vouch for is worth.

    Two states wear the same absence. A record that answered and does not
    name this issue REFUTES the claim, and an issue no split created is one
    this guard has nothing to say about. A record whose consumer list this
    binary could not type, or one that names no candidate to hold a ref to,
    answered nothing at all -- and an answer nobody gave may not release a
    child either.
    """
    if recorded.opaque_consumers is not None:
        return _Reuse.DEFERRED
    if recorded.is_present and not recorded.candidate_sha:
        return _Reuse.DEFERRED
    return _Reuse.ALLOWED


def _verdict(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    ancestry: _ancestry.LateAncestry,
) -> _Reuse:
    """What this child may do with the snapshot it names, decided once.

    The receipt first and on its own terms: it records that the reclamation
    HAPPENED, which no later reading of the ref can contradict. A mirror this
    host has not dropped and a ref pushed again at the same commit both make
    the world look untouched, and neither brings back the guarantee the child
    was given -- that what it reuses provably came from one adjudicated
    candidate. Which is also why a thread nobody could read stops here rather
    than falling through: the readings below it are exactly the ones a receipt
    would have overruled.

    Reading it costs one walk of the child's own thread, per tick, for as long
    as the child names a ref. That is the price of an answer a concurrent
    writer cannot take away, and it is paid only by issues a split created.

    What the world says is the fallback, for the reclamation whose receipt
    never landed -- a crash, a thread it could not post to. This host answers
    it first, and only where the pointer says that is worth anything: the
    reclamation drops the local mirror BEFORE it touches the remote ref and
    refuses to touch it at all while the mirror stands, so a mirror still here
    says no reclamation has happened -- which is what keeps a per-tick guard
    off the network for every child of a live split. A pointer written before
    that ordering existed says nothing of the kind and skips straight to the
    ask, and so does a copy standing at any commit but the one this child was
    promised -- the mirror is a ref in the store the agents write, so what it
    resolves TO is the whole of what it proves.

    Both shapes of ancestry come through here, and both arrive whole: the one
    whose seed failed carries the ref its own identity mints and the commit
    the OWNER's ledger recorded preserving, so the question asked of the
    remote is the same question either way.
    """
    receipt = _receipt_verdict(gh, issue, ancestry)
    if receipt is not None:
        return receipt
    if ancestry.trusts_the_mirror and _mirrored(spec, ancestry):
        return _Reuse.ALLOWED
    return _asked_verdict(spec, ancestry)


def _asked_verdict(
    spec: _config_models.RepoSpec, ancestry: _ancestry.LateAncestry,
) -> _Reuse:
    """What the remote says about the ref one whole pointer names.

    The read-only half of both readings above, and it is named against the
    exact commit the pointer carries: what a child needs to know is whether
    THIS candidate is still obtainable, not whether something occupies the
    name. A ref carrying another commit answers that question -- no -- rather
    than failing to answer it, and a remote nobody could reach answers
    nothing and holds the dispatch.
    """
    try:
        observed = _snapshot_refs.observed_snapshot_ref(
            spec, spec.target_root,
            ref=ancestry.snapshot_ref, sha=ancestry.snapshot_sha,
        )
    except Exception:
        log.exception(
            "could not ask the remote about snapshot %r", ancestry.snapshot_ref,
        )
        return _Reuse.DEFERRED
    return _OBSERVED_VERDICTS.get(observed, _Reuse.DEFERRED)


def _receipt_verdict(
    gh: _client.GitHubClient, issue: Issue, ancestry: _ancestry.LateAncestry,
) -> _Reuse | None:
    """What this child's own thread says about its snapshot, if anything.

    Both halves of the marker matter and both come off the ancestry: it has to
    name the owner, cycle, and generation this child was born of, so a later
    reclamation's receipt is not read as this one's. The AUTHOR is checked with
    it, as every receipt in this repository is: a hidden comment is invisible
    in the rendered thread and trivially copied, so without it a third party
    could park any child of any split by pasting one.

    Three answers, and no caller may collapse two of them. A receipt is the
    reclamation itself and outranks every later reading of the ref, so it is
    `RECLAIMED`. A thread read to the end with no receipt on it says nothing
    at all, and hands the question to the readings behind this one -- `None`,
    which is not a verdict. A thread that could NOT be read is neither: it is
    the one state where the authoritative answer may exist and be unseen,
    while everything behind it can look untouched -- a mirror nobody dropped,
    a ref pushed again at the same commit -- so it holds the dispatch instead
    of falling through to them.
    """
    marker = _ancestry.release_marker(
        owner=ancestry.parent_issue,
        cycle=ancestry.cycle_id,
        generation=ancestry.generation,
    )
    try:
        receipted = _comments.carries_own_marker(
            issue.get_comments(), marker,
            bot_login=getattr(gh, "_bot_login", None),
        )
    except Exception:
        log.exception(
            "issue=#%s comments could not be read for a reclamation receipt",
            getattr(issue, "number", "?"),
        )
        return _Reuse.DEFERRED
    return _Reuse.RECLAIMED if receipted else None


def _mirrored(
    spec: _config_models.RepoSpec, ancestry: _ancestry.LateAncestry,
) -> bool:
    """Whether this host still holds this child's own candidate, asked locally.

    Named against the commit the ancestry records, not merely against the ref:
    the mirror lives in the object store every agent's worktree shares, so a
    name that resolves to something proves nothing about WHAT it resolves to.
    A copy carrying another commit is not this child's snapshot, and treating
    it as one would both start the child on work nobody adjudicated and skip
    the remote read that would have parked it.
    """
    try:
        return _snapshot_mirrors.local_snapshot_present(
            spec, spec.target_root,
            ref=ancestry.snapshot_ref, sha=ancestry.snapshot_sha,
        )
    except Exception:
        log.exception(
            "could not read this host's copy of snapshot %r",
            ancestry.snapshot_ref,
        )
        return False
