# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a split still owes a remote, and the one boundary that can settle it.

A split leaves two things behind: the branch its superseded candidate was
committed on, and the immutable ref that candidate was preserved under. Neither
is a precondition for the children -- children held back until a remote delete
succeeded would be work stalled on housekeeping -- so the transaction records
both and lets the children run whatever the first attempt said.

What that costs is an obligation nobody would otherwise come back to, because
the issue is an umbrella by then and an umbrella polls its children and nothing
else. So this owner is asked at the boundary where an unsettled obligation
still matters and where the condition to settle it has just become true: the
umbrella's all-children-resolved branch. The narrow closed-owner sweep beside
it asks the same question of an issue a human closed mid-cycle, which is the
one other way a live ledger stops being visited -- same rules, same ledger.
That issue's own terminal belongs to the cancellation owner the sweep reaches
these rules through; nothing here decides one.

**The branch is unconditional.** It is superseded the moment the split lands,
so every visit retries whatever is not yet reconciled -- and "the branch" is
every surface it exists on: the remote ref, the local ref, and the checkout
holding it. A remote delete that succeeded beside a worktree that would not
come down is not a settled obligation, because what is left behind is a
checkout the per-tick base refresh goes on merging into. So the entry reads
`reconciled` only once all three are provably gone, and the proof is a read
rather than an exit code: `git worktree remove` and `git branch -D` are
best-effort by design, and a caller that has to RECORD the teardown asks
afterwards instead of trusting them.

**Only this issue's own targets are deleted.** Both come off a ledger a human
can edit and both are spent on destructive calls, so each is matched against
what this issue's own record would name -- exactly, not by shape. A branch has
to BE one of the two names this spec publishes this issue under, because
`orchestrator/<anything>/issue-41` is also another repository's branch for its
own issue 41 and two specs sharing a `target_root` is the ordinary case; a
snapshot ref has to BE the one the namespace mints for this issue, cycle, and
generation, because every generation in a lineage names the same commit and so
namespace-and-SHA is not identity. The issue number is taken from the issue
being walked rather than from the record, so a hand-edited identity cannot aim
either delete. A target that does not match is recorded `failed` and holds the
terminal open for a human, which is the one answer that neither deletes
somebody else's work nor quietly forgets the obligation.

**Except while the change it was superseded under is back.** A branch is taken
away from a pull request a split closed, so a human who reopened that change
has one pointing at a ref this pass would remove out from under them -- and
that is the one answer here no later visit could put back. What still names
the pull request is the record: the split's retirement keeps the publication
group for exactly this. Nothing is attempted and nothing is recorded `failed`,
since no delete went out; the entry stays owed, which holds the terminal, and
the log line beside it is what says why.

Asked immediately in front of the delete rather than while the work list is
built, and the difference is a request: the snapshot rule below may spend a
read-only probe deciding whether an ordered ref is already gone, and a human
can reopen a pull request inside it. An answer good enough to build a list
with is not one good enough to delete on.

**The snapshot is not.** A ref may be deleted only once every recorded direct
consumer has ENDED, and all-children-resolved is exactly when that becomes
true for the consumers this split created. Ended is read off the consumer's
own state rather than its label, on a scan taken by the visit that acts on it
-- the umbrella hands over the one it already took, the sweep takes its own.
All three dispositions that end a consumer close the issue and none of them
survives a reopen, while a label does: a child reopened while still wearing
`done` is live again, and a reading taken off the label would delete the only
copy of the work it came back for. Anything that cannot be proved -- a
consumer missing from the scan, one whose read failed, a consumer ledger this
binary could not type -- keeps the ref.

All of which is about the consumers the ledger NAMES, so the prior question is
whether it names all of them, and the record's own phase is what answers it. A
child is created and then recorded in two writes -- it must be, since a child
on GitHub the parent does not record is a child nothing would come back to --
so while `splitting` stands the list may be short by one that already exists,
and how long the list is decides nothing: a set of ended consumers says as
little about the child it has not reached as an empty one does. Nothing on the
ref is reclaimed in that window. Either side of it the list is whole -- before
the split nothing has been created, and past it the loop ran to the end -- and
that is also what makes an EMPTY list a fact rather than a gap: the ref is
retained ahead of the first child, so an owner closed in that interval has no
consumers because there are none. A cancelled cycle answers with the boundary
it kept rather than with `cancelling`, which is a boundary of its own and
would say nothing about the loop.

**A reclamation is decided once, then retried until it lands.** The proof
above is a reading of live issues and cannot be reproduced, so the entry is
written `reclaiming` before the delete, the consumers are read once more past
that write, and a later visit acts on the RECORD rather than on a proof it
cannot repeat -- for one thing only, and only for a ref the remote no longer
has. What follows the delete is each child being told, in one comment and
nothing else: this owner may not write a consumer's pinned state at all, so
what a child does about it is the child's own to decide on its own dispatch
(`late_reuse`). The telling runs ahead of the entry that records the delete,
so a tick that dies in between repeats it -- harmlessly, since a child already
holding this reclamation's receipt is skipped.

A CANCELLED cycle tells none of them and reconciles on the delete alone. The
receipt is what a live split owes children it is still driving; an ending a
human's close forced drives none of them, and leaves each exactly as it found
it. What the child would have read the receipt FOR still reaches it: the
transport drops this host's copy of the ref before it touches the remote and
refuses the reclamation outright if that copy cannot be proved gone, so a
child reopened afterwards asks the remote once and its own guard stops it.

**And the terminal is held by one thing the ledger cannot hold it by.** A
split entered past publication owes an answer as well as its obligations:
whether the pull request it closed is still closed. The two can disagree
exactly where it matters -- a reclamation that FINISHED leaves nothing owed,
so a human who restores the branch and reopens the change afterwards finds
every entry settled and the terminal free. What that terminal writes is `done`
and a close, and the write ahead of it drops the publication group, so nothing
would ask again and an open change carrying superseded work would be left
under a parent this workflow had declared finished. The answer is not written
back to the ledger: nothing IS owed the remote there, and an entry claiming
otherwise would send a later pass to delete a branch a human put back on
purpose.

**Nothing that cannot be proved settled lets a terminal fire.** An obligation
ledger this binary could not fully type blocks outright: the entries it could
not read are still obligations, and reclaiming around them would close an
umbrella over whatever they name. So does a ledger holding anything at all on
a record whose cycle identity is damaged -- there is nothing to correlate a
reclamation to, and no issue number to prove a branch belongs to this
generation, so the only safe answer is to say so loudly and stay open.

**Every state except `reconciled` is owed, for a ref exactly as for a branch.**
There is no reading under which an object still on the remote is settled: a ref
kept because a consumer could not be proved ended is one this repository is
holding, and an umbrella closed over it is an object nothing would ever come
back for, because the parent is `done` by then and no pass revisits it. So the
label staying put IS the retry, and the reason it is held is logged on every
tick that holds -- a terminal that will not fire and never says why is the one
shape an operator cannot act on.

The ledger takes any state the vocabulary defines from any writer, which is why
the reading is "not reconciled" rather than a list of the states this binary
writes: a state read as neither owed nor settled would be an object left on the
remote by an umbrella that closed saying it owed nothing.

Idempotent by construction, for the reason the transport underneath is: both
deletes treat an absent target as success, so a retry after a crash between the
call and the write that recorded it costs one request and reports the same
answer.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.git.snapshots import namespace as _namespace, refs as _snapshot_refs
from orchestrator.git.worktrees import cleanup as _worktree_cleanup, naming as _naming, paths as _worktree_paths
from orchestrator.github import comments as _comments
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.late_split import (
    events as _events,
    formats as _formats,
    lineage as _lineage,
    state as _late_state,
    telemetry as _telemetry,
)
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.stages.decomposition import (
    late_publication as _late_publication,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan
from orchestrator.workflow.state import stage_name

# Resolved at call time: the cancellation owner imports this module for the
# reclamation rules it reuses unchanged, so a module-scope bind here would be
# a cycle.
_CANCELLATION_OWNER = (
    "orchestrator.workflow.stages.decomposition.late_cancellation"
)

log = logging.getLogger("orchestrator.workflow")

_BRANCH = LateResourceKind.BRANCH

# The count the split transaction writes before it creates its first child,
# in the same write as `splitting`. It is the stage's own key rather than this
# domain's, and it is read here for one reason: it is durable evidence that a
# transaction began which no later write of the PHASE can erase.
_EXPECTED_CHILDREN = "expected_children_count"

_SNAPSHOT = LateResourceKind.SNAPSHOT_REF

# The typed failure each refused reclamation is reported under. The plan pull
# request is here rather than beside the cancellation that settles it, because
# what reports it is the emission below: a kind this map does not carry is an
# entry no sink could name the failure of.
_FAILURES = MappingProxyType({
    _BRANCH: LateFailure.BRANCH_CLEANUP_FAILED,
    _SNAPSHOT: LateFailure.SNAPSHOT_DELETE_FAILED,
    LateResourceKind.PLAN_PR: LateFailure.PR_RECONCILE_FAILED,
})

# The two states an entry reaches once the decision to reclaim it is durable.
# Both are retryable past the consumer proof, but only for a ref the remote no
# longer has: a decision already carried out has to be finished, while one
# that never reached the remote is still a decision about a ref a consumer may
# have come back for.
_ORDERED = frozenset((
    LateResourceState.RECLAIMING, LateResourceState.FAILED,
))

# What a child is told when the snapshot it was created to reuse is reclaimed.
# Said once, at the moment it becomes true, so an issue reopened long after
# its owner closed still reads it rather than following a pointer to nothing.
# It is a comment and only a comment -- see `_release` for why this owner may
# not write a consumer's pinned state at all.
_RELEASED_NOTICE = (
    "{mentions} the immutable snapshot this issue was created to reuse (from "
    "the split on #{owner}) has been reclaimed, now that every issue cut from "
    "it has ended. That ref is never recreated -- what made it worth reusing "
    "was that it provably carried one exact commit, and a ref pushed again "
    "from whatever is reachable now proves nothing. If this issue is "
    "reopened, it is parked before any implementation starts: continuing "
    "means an ordinary change, or an explicit new split cycle on #{owner}, "
    "which preserves a candidate of its own.\n\n{marker}"
)

# What a terminal is blocked by when the ledger itself is the thing that
# cannot be read. It names no resource because there is no resource to name --
# only the fact that what is owed is unknown.
_OPAQUE = "an obligation this orchestrator cannot read"

# What is logged where a branch is owed and the change it was superseded under
# is open again. Said on every visit that holds, for the reason the held
# terminal is: a reclamation that will not happen and never says why is the
# one shape an operator cannot act on.
_HELD_BACK_BRANCH = (
    "issue=#%d %s, so branch %s was left on the ledger rather than deleted "
    "out from under a change that points at it"
)

# The phases that come BEFORE the split loop, where the whole account of the
# children cut from this generation's ref is "there are none yet": `splitting`
# goes down and is persisted ahead of the first create, so a record standing
# earlier has made no child at all.
#
# That is a claim about the record as much as about the phase, and it is held
# to the record rather than taken on the phase's word -- because a phase is
# not only written forwards. The post-agent owner check writes `owner_check`
# over whatever boundary it interrupts, so a transaction re-entered after a
# crash reads as one of these with a half-filled ledger standing behind it,
# and believing the phase there would delete the ref out from under whichever
# child the loop had already created. So a record naming any child at all is
# not one of these however it is labelled.
_PRE_SPLIT_PHASES = frozenset((
    LatePhase.MEASURING,
    LatePhase.HOLDING_PLAN_PR,
    LatePhase.ADJUDICATING,
    LatePhase.OWNER_CHECK,
    LatePhase.SNAPSHOTTING,
))

# The phases PAST the loop, where the ledger is whole whatever it holds: the
# transaction moves on only once every child has been created AND recorded,
# and one that could not be leaves the record parked where it stands. These
# are the only boundaries whose word is enough on its own.
_SETTLED_SPLIT_PHASES = frozenset((
    LatePhase.SUPERSEDING,
    LatePhase.CLEANING_UP,
))

# The two transport answers that mean the ref is gone: one this call deleted,
# and one an earlier call already had.
_RECLAIMED = frozenset((
    _snapshot_refs.SnapshotOutcome.DELETED,
    _snapshot_refs.SnapshotOutcome.ABSENT,
))


@dataclass(frozen=True)
class _Pass:
    """One issue's reclamation pass, and what it reads its rules against.

    Held together because the steps below are not independent: the delete is
    ordered on the record, carried out against the remote, announced on the
    consumers, and only then recorded -- and every one of those needs the same
    issue, the same pinned comment, and the same scan.
    """

    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    scan: _ChildScan

    def persist(self, generation: LateGeneration) -> None:
        """Make one step of this pass durable before the next one acts."""
        _late_state.write_late_generation(self.state, generation)
        self.gh.write_pinned_state(self.issue, self.state)


@dataclass(frozen=True)
class _Reclamation:
    """What one pass over this issue's obligations settled, and what it did not.

    `entries` holds every obligation this pass ACTED on, in the state the
    record now gives them, and it is what the per-visit log line is drawn
    from: a visit that keeps happening is happening for one of these, and
    saying so on each of them is what makes an unreclaimable object visible.

    `moved` is the subset whose recorded state this visit actually CHANGED,
    and it is what the sinks and the pinned write are drawn from instead. The
    two differ exactly where a retry keeps giving the same answer -- a remote
    that goes on refusing one delete, a consumer that goes on being live --
    and that is the shape a per-visit record would repeat forever: one
    `late_cleanup`, one `late_failure`, and one comment write per sweep, for
    as long as the refusal lasts. The transition is the news; the standing
    state is what the log and the held terminal already say.
    """

    generation: LateGeneration
    entries: tuple[LateResource, ...] = ()
    moved: tuple[LateResource, ...] = ()

    @property
    def attempted(self) -> bool:
        """Whether anything was asked of the remote at all."""
        return bool(self.entries)


def _owed_branches(generation: LateGeneration) -> tuple[str, ...]:
    """The superseded branches this generation has not seen reclaimed.

    Everything but `reconciled`, rather than the states this binary writes.
    A branch is owed until the remote is known to have let it go, and the
    ledger takes any state the vocabulary defines from any writer -- so an
    entry a newer binary, an older one, or a human left as `retained` is a
    branch nothing would ever retry and nothing would report as outstanding,
    which is a terminal closing over a branch still on the remote. The one
    reading that cannot do that is the one that treats every state except the
    settled one as unfinished.
    """
    return tuple(
        entry.target
        for entry in generation.resources
        if entry.kind == _BRANCH
        and entry.resource_state != LateResourceState.RECONCILED
    )


def _held_snapshots(generation: LateGeneration) -> tuple[str, ...]:
    """The snapshot refs this generation still holds the remote to."""
    return tuple(
        entry.target
        for entry in generation.resources
        if entry.kind == _SNAPSHOT
        and entry.resource_state != LateResourceState.RECONCILED
    )


def _reclaimable(
    state: PinnedState, generation: LateGeneration, scan: _ChildScan,
) -> bool:
    """Whether every direct consumer this snapshot records is terminal.

    Asked of a scan taken this tick, and asked again from scratch on every
    visit -- a consumer read as closed once is not a fact this ledger latches.
    A human who reopens one before the delete lands has a live consumer again,
    and the answer the next reading gives is the one that decides.

    Fail-closed: a consumer the scan does not carry, one whose read failed, or
    a consumer ledger this binary could not type is a consumer that may still
    be cutting from the ref, and deleting on the strength of a reading nobody
    gave would destroy the only copy of work a child was told to reuse.

    All of which is about the consumers the ledger NAMES, and the prior
    question is whether it names all of them -- see `_whole_ledger`. Asked
    first, because every proof below is only as complete as the list it walks.
    """
    if _unwritable(generation) or generation.has_opaque_ledger:
        return False
    if not _whole_ledger(state, generation):
        return False
    return all(_ended(scan, consumer) for consumer in generation.consumers)


def _whole_ledger(state: PinnedState, generation: LateGeneration) -> bool:
    """Whether the ledger names every child cut from this generation's ref.

    The question the per-consumer proof rests on, and the record's own phase
    is what answers it. The split creates a child issue and records it in two
    steps -- it must, since a child on GitHub the parent does not record is a
    child nothing would come back to -- so while `splitting` stands the list
    may be short by one that already exists, and a list of ended consumers
    proves nothing about the child it has not reached. That window is where a
    partial ledger would otherwise authorize the delete, unread and untold.
    Either side of it the list is whole: nothing has been created yet, or the
    loop ran to the end and the transaction moved on.

    It is also what makes an EMPTY ledger a fact rather than a gap, which is
    what left a ref nothing would ever reclaim: the snapshot is retained
    before the first child exists, so an owner a human closed in that interval
    has no consumers because there are none, and `all(())` settles it.

    A loop the RECORD proves finished is whole at any boundary, which is
    asked before the phase is consulted at all -- see `_every_child_recorded`.
    Two writers make that necessary and neither is a bug: `splitting` is
    written before the first create and again beside every child recorded, so
    the phase alone cannot say which end of the loop a record sits at; and a
    retried transaction rewrites `snapshotting` over whatever it reached, so a
    finished split can come back wearing the boundary it started from.

    A boundary before the loop is believed only as far as the record bears it
    out -- see `_split_began`. A pinned comment written by a binary that
    rewound its own phase is exactly what that reading is for: the guard on
    the record stops new rewinds and migrates nothing, so what has to answer
    for one already in flight is evidence no phase write ever touched. Past
    the loop the phase needs no corroboration: the transaction reaches
    `superseding` only once every child is created and recorded.

    A SEALED ledger answers ahead of all of it. The count can only ever be
    reached by a loop that ran to the end of its manifest, and a cancelled one
    never will: the children it did not make are ones nothing is going to
    make. So the loop that stopped writes down that its register is final --
    which it only does where every child that exists is already on it -- and
    that is a stronger reading than the count, not a weaker one.

    Believed only for the cycle it NAMES. The seal is a decomposition key
    rather than a late one, so no write that ends a generation drops it, and
    a later cycle on the same issue reads a seal its own split never wrote. A
    partial register would then look final, and the delete below would take
    the ref that cycle's unrecorded children were cut from.

    Which phase answers, for a cycle whose own `phase` field has been taken
    over by its cancellation, is `_accounted_at`'s question.
    """
    boundary = _accounted_at(generation)
    if boundary in _SETTLED_SPLIT_PHASES:
        return True
    if _state._ledger_is_sealed(
        state.get(_state._SPLIT_LEDGER_SEALED), generation.cycle_id,
    ):
        return True
    if _every_child_recorded(state, generation):
        return True
    if boundary not in _PRE_SPLIT_PHASES:
        return False
    return not _split_began(state, generation)


def _every_child_recorded(
    state: PinnedState, generation: LateGeneration,
) -> bool:
    """Whether the split loop reached the end of the manifest it was given.

    Asked of every boundary, because more than one of them is ambiguous.
    `splitting` is written before the first create AND again beside every
    child recorded, the last one included, so a record standing there is
    either a loop mid-flight or one that finished and died before the step
    that would have moved it on. `snapshotting` is the same question one
    retry later: a transaction resumed after a park rewrites it over whatever
    boundary it had reached, so a finished split comes back wearing the one it
    started from. Reading either as mid-flight retains a ref no later pass can
    ever release, because nothing revisits a cancelled owner to move a phase
    for it.

    What separates them is the count the transaction wrote ahead of its first
    create, against the positional register it appends to as each child is
    recorded. The register is written in the SAME step as the consumer and
    the child obligation, so reaching the count means every child exists and
    every one of them is on the ledgers this proof walks.

    Fail-closed on anything else. A count that is not a positive whole number
    is a field this binary cannot act on, and a register short of it is the
    window this whole question exists for.
    """
    expected = state.get(_EXPECTED_CHILDREN)
    if not _formats.whole_number(expected) or expected <= 0:
        return False
    return len(generation.split_children) >= expected


def _split_began(state: PinnedState, generation: LateGeneration) -> bool:
    """Whether this record shows a split transaction that already started.

    Two signs, and only one of them survives a phase somebody moved. The
    ledgers are the obvious one: a consumer or a split child recorded here is
    a child this generation made, whatever boundary the record is wearing.

    The other is the one that matters, because the window this question exists
    for is the window where the ledgers say NOTHING. A child is created before
    the write that records it, so a loop that died between the two leaves an
    empty ledger and a real issue on GitHub -- and the count the transaction
    puts down BEFORE its first create, in the same write as `splitting`, is
    then the only thing left. A binary that rewound the phase over it (which
    is what every record already in flight was written by) left that count
    exactly where it was, so this is what upgrades one rather than believing
    the boundary it now wears.

    A stale count from an ordinary decomposition of the same issue reads the
    same way, and is meant to: an issue that split into children became an
    umbrella with no implementation of its own, so reaching the late gate at
    all takes a human moving its label -- and being wrong in that direction
    keeps a ref, holds a terminal, and says so on every visit, where being
    wrong in the other deletes the only copy of a child's work.
    """
    if state.get(_EXPECTED_CHILDREN) is not None:
        return True
    return bool(generation.consumers or generation.split_children)


def _accounted_at(generation: LateGeneration) -> LatePhase | None:
    """The boundary whose account of the consumers this ref is judged by.

    Ordinarily the phase the record stands at. A cancelled cycle is the one
    that needs asking, because `cancelling` is itself a boundary and it
    overwrites the one the cancellation interrupted -- a generation cancelled
    while its split loop was running and one cancelled long past it would
    otherwise read alike, and the reading they would share proves nothing, so
    every ref either of them holds would be retained for good.

    So the cancellation keeps the phase it interrupted, and that is what is
    asked here. A cancelled record that kept none -- one an older binary
    marked, or one whose own field was damaged -- answers with something
    outside the set, which retains the ref: a cancellation is exactly when
    nobody is coming back to prove a partial ledger whole.
    """
    if generation.cancelled:
        return generation.cancelled_phase
    return generation.phase


def _ended(scan: _ChildScan, consumer: int) -> bool:
    """Whether a fresh read says this recorded consumer has ended.

    The issue's own state, not its label. All three dispositions that end a
    consumer -- reaching `done`, being `rejected`, and a human closing it --
    close the issue, and none of them survives a reopen. A LABEL does:
    reopening a child leaves `done` or `rejected` exactly where it was, so a
    reading taken off the label would call a child that is live again terminal
    and delete the only copy of the work it came back for.

    `done` still covers a nested split, for the reason it always did: a child
    that reached it has published, so its own descendants are past needing the
    ancestor -- and it reached it by being finished and closed.

    The close is asked through the shared predicate rather than by reading an
    attribute here, because the only spelling a real issue carries it under is
    `state`. A consumer the scan never fetched is `None`, which is not closed,
    so an unknown or unreadable consumer keeps the ref.
    """
    return issue_is_closed(scan.issues.get(int(consumer)))


def _ours(
    spec: _config_models.RepoSpec, issue_number: int, branch: str,
) -> bool:
    """Whether a recorded target is one of THIS issue's own branches.

    Asked before anything is deleted by it, because the target comes off a
    ledger a human can edit and the call it is spent on is destructive: an
    entry naming `main` would otherwise delete an unprotected `main`.

    An exact match against the names this spec publishes this issue under,
    not a namespace test. `orchestrator/` with an `/issue-<n>` tail is also
    the shape of ANOTHER repository's branch for another issue that shares the
    number -- `orchestrator/other-repository/issue-41` passes a prefix-and-
    tail reading -- and two specs sharing one `target_root` is the ordinary
    case, not a contrived one. The number comes from the issue being walked
    rather than from the record, so a hand-edited identity cannot point the
    delete at a branch of somebody else's.
    """
    if not isinstance(branch, str):
        return False
    return branch in _naming._issue_branch_names(spec, issue_number)


def _reclaim_branch(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    generation: LateGeneration,
    branch: str,
) -> LateGeneration:
    """Take down every surface this branch exists on, and record the answer.

    Three surfaces, one obligation: the remote ref, the checkout holding the
    branch, and the local ref itself. A remote delete that succeeded beside a
    worktree that would not come down is not settled -- what is left is a
    checkout on a superseded branch that the per-tick base refresh treats as a
    pre-PR tree and goes on merging into.

    The two halves are attempted independently, and the entry is what BOTH
    said. A remote that refuses is a permission or ruleset problem only an
    operator can clear, so a local teardown conditioned on it is one that
    waits for a human to take down a checkout the refresh is merging into
    every tick meanwhile -- and the local half needs nothing from the remote
    to succeed. The identity check is the one thing that does gate it: a
    target this issue is not published under aims both deletes at somebody
    else's branch, so nothing is attempted at all.

    The local half is verified rather than trusted. Its two helpers are
    best-effort by design and report nothing, so what decides the entry is a
    read taken afterwards, and that read fails closed.

    Recorded whichever way it went: a `failed` obligation is still an
    obligation, and writing it is what keeps the retry pointed at the same
    branch rather than at whatever the resolver would name later.
    """
    if not _ours(spec, issue_number, branch):
        log.error(
            "issue=#%d recorded branch %r is not one this issue is published "
            "under; refusing to delete it", issue_number, branch,
        )
        return _recorded(generation, _BRANCH, branch, LateResourceState.FAILED)
    try:
        deleted = gh.delete_remote_branch(branch)
    except Exception:
        log.exception("superseded branch %r delete raised", branch)
        deleted = False
    local_gone = _local_gone(spec, issue_number, branch)
    return _recorded(generation, _BRANCH, branch, (
        LateResourceState.RECONCILED if deleted and local_gone
        else LateResourceState.FAILED
    ))


def _local_gone(
    spec: _config_models.RepoSpec, issue_number: int, branch: str,
) -> bool:
    """Take the local checkout and ref down, and say whether they are gone."""
    _worktree_cleanup._remove_issue_worktree(spec, issue_number)
    _worktree_cleanup._delete_local_issue_branch(spec, issue_number, branch)
    if _worktree_paths._worktree_path(spec, issue_number).exists():
        log.warning(
            "issue=#%d worktree is still on disk after the teardown; the "
            "branch obligation stays owed", issue_number,
        )
        return False
    if _worktree_cleanup._local_branch_present(spec, branch):
        log.warning(
            "issue=#%d local branch %r survived the teardown; the branch "
            "obligation stays owed", issue_number, branch,
        )
        return False
    return True


def _reclaim_snapshot(
    walk: _Pass, generation: LateGeneration, ref: str,
) -> LateGeneration:
    """Order, carry out, and announce the reclamation of one snapshot ref.

    Four steps, and the order is the whole crash-safety argument.

    **The decision goes down first.** Reaching here means every recorded
    consumer was just proved ended, and that proof is not repeatable: a human
    can reopen one at any moment. So the entry is written `reclaiming` BEFORE
    the delete, which is what stops a tick that died after the push from
    leaving a ref the ledger says is retained and the remote does not have.
    What the entry does not buy is a later visit acting on this visit's proof:
    the consumers are read again ahead of every delete, and only a ref the
    remote no longer has finishes without one -- there the delete has already
    happened, and a consumer that came back to it is answered by the receipt
    and the child's own guard.

    **The delete is named against the commit this generation preserved**, so a
    ref somebody re-pointed is refused rather than reclaimed, and an absent
    one is a success -- which is what makes the retry cost one read.

    **The children are told before the entry is closed.** A child that reads
    its ancestry after this owner has gone quiet would otherwise follow a
    pointer to nothing, so each is sent one comment saying the ref is gone and
    what continuing takes. It runs behind a delete the remote accepted and
    ahead of the record of it, so a tick that dies in between re-enters
    through `reclaiming` and repeats it; a child already holding this
    reclamation's receipt is skipped, which is what keeps the sentence to one.
    Nothing here touches a consumer's pinned state -- what acts on the receipt
    is the child's own guard, on the child's own dispatch.

    Refused outright unless the target IS this generation's ref. The transport
    proves the namespace and the commit, and neither is identity: every
    generation of every issue in a lineage cut from the same candidate names
    the same SHA, so a hand-edited entry naming a sibling's ref would pass
    both tests and destroy the only copy of what that sibling was told to
    reuse. The name is re-derived here from the issue being walked and the
    record's own counters, and nothing else is deleted.
    """
    issue_number = walk.issue.number
    if not _our_snapshot(issue_number, generation, ref):
        log.error(
            "issue=#%d recorded snapshot %r is not the ref this generation "
            "preserved; refusing to delete it", issue_number, ref,
        )
        return _recorded(
            generation, _SNAPSHOT, ref, LateResourceState.FAILED,
        )
    ordered = _ordered(walk, generation, ref)
    proven = _consumer_scan(walk.gh, walk.issue, generation)
    if not _may_take(walk, generation, ref, proven):
        log.info(
            "issue=#%d is not taking %s this visit: a consumer it records is "
            "live again", issue_number, ref,
        )
        return ordered
    # The scan above is a request per consumer and the probe behind it is
    # another, so the poll can observe the close anywhere in there -- and what
    # stands next is the delete itself. The mark goes down BEFORE it, because
    # a ref that is gone while the record still reads live is a reclamation
    # nothing afterwards can attribute to the cancellation that earned it.
    ordered = _observed_close(walk, ordered)
    return _taken(walk, ordered, ref, proven)


def _may_take(
    walk: _Pass, generation: LateGeneration, ref: str, proven: _ChildScan,
) -> bool:
    """The last reading before the delete, taken as late as one can be.

    The scan the pass qualified this ref on was taken before the branch half
    ran and before anything was written, and every one of those steps is a
    request a human can reopen a consumer during. So the consumers are read
    ONE more time, past the write that records the decision and immediately
    ahead of the delete it authorizes -- which leaves the delete request
    itself as the only window, and that one is irreducible.

    A ref the remote no longer has is the one case that needs no proof: what
    is left is finishing a delete that already happened, and a consumer that
    came back to it is answered by the receipt and the child's own guard
    rather than by keeping a ref nobody has.

    A refusal leaves the entry `reclaiming` rather than putting it back. The
    decision was taken and not carried out, which is exactly what that state
    means -- and it is read back by the rule that probes the ref before acting
    on it, so a ref still on the remote is kept until the consumers end again.
    """
    if _reclaimable(walk.state, generation, proven):
        return True
    return _already_gone(walk, generation, ref)


def _taken(
    walk: _Pass, ordered: LateGeneration, ref: str, proven: _ChildScan,
) -> LateGeneration:
    """Carry out a delete this pass has just proved it may take."""
    if _deleted(walk, ordered, ref) not in _RECLAIMED:
        return _recorded(ordered, _SNAPSHOT, ref, LateResourceState.FAILED)
    # The delete is a request, and what stands immediately behind it is the
    # one cleanup effect that WRITES to somebody else's issue. A close
    # observed inside the delete makes this a cancelled cycle, which owes its
    # children nothing at all -- so the reading is taken before the receipts
    # rather than after them.
    ordered = _observed_close(walk, ordered)
    ordered, told = _release_consumers(walk, ordered, ref, proven)
    if not told:
        # The ref is gone and a child still records it. Leaving the entry
        # `reclaiming` is what keeps that obligation alive: it holds the
        # terminal and keeps the sweep visiting, and the next pass finds the
        # ref absent and delivers the receipt it could not.
        return ordered
    return _recorded(ordered, _SNAPSHOT, ref, LateResourceState.RECONCILED)


def _deleted(
    walk: _Pass, generation: LateGeneration, ref: str,
) -> _snapshot_refs.SnapshotOutcome:
    """Ask the remote to let go of one ref, reading a raise as a refusal.

    The transport answers every refusal it can name, but a caller that must
    RECORD the attempt cannot let one it could not name escape: an exception
    here would abandon the pass with the decision written and nothing said,
    which is the one outcome that produces no typed failure for an operator
    to see. A raise is therefore the same answer a refused push is, and takes
    the same `snapshot_delete_failed` with it.
    """
    try:
        return _snapshot_refs.delete_snapshot_ref(
            walk.spec, walk.spec.target_root,
            ref=ref, sha=generation.candidate_sha,
        )
    except Exception:
        log.exception("snapshot %r delete raised", ref)
        return _snapshot_refs.SnapshotOutcome.REFUSED


def _ordered(
    walk: _Pass, generation: LateGeneration, ref: str,
) -> LateGeneration:
    """Record that this ref is going, before anything makes it so.

    The proof that let the decision be taken is a reading of live issues, and
    a reading is not a thing a retry can reproduce. What a retry CAN act on is
    a decision somebody durably took, so it is written down first and the
    delete underneath it is idempotent.

    Written once, though, and not on every retry of it. A record that already
    reads `reclaiming` or `failed` already carries the decision -- both are
    what the retry rule reads a decision back out of -- so putting
    `reclaiming` over a `failed` entry costs a write, loses the fact that the
    last attempt was refused, and leaves the pass's own outcome write with a
    state to move BACK to. A remote that goes on refusing would otherwise
    alternate the durable state between the two forever, reporting a
    transition on every other visit that nothing actually transitioned.

    The decision still travels forward in memory either way: the entry this
    pass hands on says `reclaiming`, so a delete that lands and a child this
    pass cannot reach still leave the ref recorded as being taken.
    """
    try:
        decided = generation.with_resource(LateResource(
            kind=_SNAPSHOT,
            target=ref,
            resource_state=LateResourceState.RECLAIMING,
        ))
    except _formats.InvalidLateValue:
        log.exception("could not order the reclamation of %r", ref)
        return generation
    if not _already_ordered(generation, ref):
        walk.persist(decided)
    return decided


def _already_ordered(generation: LateGeneration, ref: str) -> bool:
    """Whether the record already holds a durable decision about this ref.

    Either of the two states a decision reaches counts, because the retry
    rule reads them alike: what both say is that a delete was authorized and
    the ledger has been standing behind it since.
    """
    return any(
        entry.resource_state in _ORDERED
        for entry in generation.resources
        if entry.kind == _SNAPSHOT and entry.target == ref
    )


def _observed_close(
    walk: _Pass, generation: LateGeneration,
) -> LateGeneration:
    """Mark a close a poll observed while this pass was reclaiming.

    The barrier every step of a reclamation is asked past, and it costs no
    request -- which is why it can be asked as often as there are steps. The
    write behind it happens once, on the pass that first reads one: a record
    that already carries the mark is handed straight back.

    The cancellation owner is resolved at call time because it imports this
    module for the reclamation rules a cancelled cycle reuses unchanged; a
    module-scope bind here would point that edge back at itself.
    """
    if generation.cancelled:
        return generation
    if not _observations.close_observed(walk.spec.slug, walk.issue.number):
        return generation
    late_cancellation = importlib.import_module(_CANCELLATION_OWNER)
    return late_cancellation._marked(
        walk.gh, walk.issue, walk.state, generation,
    )


def _release_consumers(
    walk: _Pass, generation: LateGeneration, ref: str, proven: _ChildScan,
) -> tuple[LateGeneration, bool]:
    """Let every child cut from this ref know it is gone, once each.

    Answers with the record this left and whether ALL of them were reached.
    Every consumer is attempted before that answer is given -- one child this
    pass could not reach is not a reason to leave the rest untold.

    A CANCELLED cycle tells none of them, and answers as though it had. Its
    children are issues a human's close stranded rather than work this
    orchestrator is still driving, and what that ending owes them is nothing
    at all: it does not close them, relabel them, write their pinned state, or
    put a word on their threads. Nothing about the ref is left unsaid by it --
    the transport drops this host's copy before it touches the remote and
    refuses the whole reclamation if that copy cannot be proved gone, so a
    child reopened afterwards finds no mirror, asks the remote once, and is
    stopped and told by its own guard on its own dispatch. The receipt is what
    a live split owes the children it is still responsible for, and this is
    the one pass that is responsible for none.

    Which is why the reading is taken between EVERY two of them rather than
    once for the walk. Each receipt is a comment on somebody else's issue, so
    a close observed after the first is one the second may not be written
    over: the children left are owed nothing, and the pass stops telling them
    where it stands. It answers "all told" for those, because a cycle that
    owes no receipt has left none undelivered.

    And once more INSIDE each of them, because proving a child untold is a
    request of its own: the thread walk stands between the reading this loop
    took and the comment it authorizes, and a close landing in there would
    otherwise be written over exactly as one landing between two children
    would.
    """
    if generation.cancelled:
        return generation, True
    marker = _lineage.release_marker(
        owner=walk.issue.number,
        cycle=generation.cycle_id,
        generation=generation.generation,
    )
    told = True
    for consumer in generation.consumers:
        generation = _observed_close(walk, generation)
        if generation.cancelled:
            break
        generation, delivered = _release(
            walk, proven, consumer, marker, generation,
        )
        told = delivered and told
    return generation, told


def _release(
    walk: _Pass,
    proven: _ChildScan,
    consumer: int,
    marker: str,
    generation: LateGeneration,
) -> tuple[LateGeneration, bool]:
    """Say on one child that the ref it was cut from is gone.

    A COMMENT, and nothing else. Everything this owner knows about a consumer
    it would rather write into that consumer's pinned comment -- drop the
    dangling pointer, park it -- and it may not: the pinned comment is written
    whole by whoever writes it, and a handler of the child's own that read it
    before this pass and wrote it after would put the reclaimed pointer back
    and take the park off, silently, with the owner already reconciled and
    nothing left to come back. A label is no proxy for "no writer" either: a
    finalize sets the terminal label BEFORE its last write, and the two
    pre-PR states a human can close an issue on are swept by nothing at all,
    so they never reach one.

    A comment has none of that. It is appended rather than rewritten, so no
    concurrent writer can lose it, and it reaches a consumer in every state a
    consumer can be in. What acts on it is the child's own guard
    (`late_reuse`), evaluated by the child's own handler, where there is
    nobody to race.

    Said once, proved from the thread rather than from state for the same
    reason: the receipt is a marker naming this issue, this cycle, and this
    generation, and a consumer already carrying one of ours has been told.

    Read off the scan the delete was proved on, not the one the pass opened
    with: that is the freshest reading of this child there is. A consumer that
    scan could not fetch, or whose thread could not be read or posted to,
    answers False -- the ref is gone either way, and a child that was never
    told is the one thing this step exists to prevent, so the obligation stays
    on the ledger until it can be.
    """
    child = proven.issues.get(int(consumer))
    if child is None:
        log.warning(
            "issue=#%d reclaimed a snapshot but could not reach consumer #%d "
            "to tell it; the obligation stays owed until it can",
            walk.issue.number, int(consumer),
        )
        return generation, False
    try:
        return _told(walk, child, marker, generation)
    except Exception:
        log.exception(
            "issue=#%d could not tell consumer #%d its snapshot is gone",
            walk.issue.number, int(consumer),
        )
        return generation, False


def _told(
    walk: _Pass,
    child: Issue,
    marker: str,
    generation: LateGeneration,
) -> tuple[LateGeneration, bool]:
    """Post this reclamation's receipt on one child unless it carries one.

    The thread walk that proves this child untold is a REQUEST, and the poll
    runs beside it: a close observed in there makes this a cancelled cycle,
    which owes its children nothing at all -- not a comment, and certainly not
    one addressed to a human. So the latch is asked between the reading and
    the write it authorizes, and the mark goes down where the walk stands
    rather than after the sentence it would have made unsayable.

    It answers "told" for that child all the same, because a cycle that owes
    no receipt has left none undelivered -- the same answer the loop above
    gives for every consumer it stops short of.
    """
    if _comments.carries_own_marker(
        child.get_comments(), marker,
        bot_login=getattr(walk.gh, "_bot_login", None),
    ):
        return generation, True
    generation = _observed_close(walk, generation)
    if generation.cancelled:
        log.warning(
            "issue=#%d was observed closed while consumer #%s was being "
            "read; writing nothing to it",
            walk.issue.number, child.number,
        )
        return generation, True
    walk.gh.comment(child, _RELEASED_NOTICE.format(
        mentions=config.HITL_MENTIONS,
        owner=walk.issue.number,
        marker=marker,
    ))
    return generation, True


def _our_snapshot(
    issue_number: int, generation: LateGeneration, ref: str,
) -> bool:
    """Whether the recorded ref is the one this generation's snapshot is at.

    Derived, not parsed: the namespace mints one ref per issue, cycle, and
    generation, so the question is only whether the ledger still names it. A
    record whose identity is too damaged to derive a ref from owns no ref
    either, and answering no leaves the entry owed and the umbrella open --
    which is where an obligation nobody can correlate belongs.
    """
    try:
        expected = _namespace.snapshot_ref(
            issue_number=issue_number,
            cycle_id=generation.cycle_id,
            generation=generation.generation,
        )
    except _namespace.InvalidSnapshotRef:
        log.exception(
            "issue=#%d cannot derive the snapshot ref its own record would "
            "be under", issue_number,
        )
        return False
    return ref == expected


def _recorded(
    generation: LateGeneration,
    kind: LateResourceKind,
    target: str,
    settled: LateResourceState,
) -> LateGeneration:
    """Move one obligation to the state this pass just established for it."""
    try:
        return generation.with_resource(LateResource(
            kind=kind, target=target, resource_state=settled,
        ))
    except _formats.InvalidLateValue:
        log.exception("could not record the %s obligation %r", kind, target)
        return generation


def _consumer_scan(
    gh: GitHubClient, issue: Issue, generation: LateGeneration,
) -> _ChildScan:
    """Read every recorded direct consumer as it stands right now.

    Fail-per-consumer rather than fail-per-pass. A read that raises leaves
    that consumer out of both maps, which the reclamation rule already reads
    as "not proved ended" and answers by keeping the ref -- while the branch
    half, which owes nothing to any consumer, is still settled on this visit.
    Abandoning the whole pass would instead let one unreadable child hold a
    superseded branch on the remote for as long as it stayed unreadable.

    Shaped as the parent scan the umbrella hands over, because the rule it
    feeds is the same rule and may not learn a second shape to ask it in.
    """
    consumer_issues: dict[int, Issue] = {}
    consumer_labels: dict[int, str | None] = {}
    for consumer in generation.consumers:
        number = int(consumer)
        consumer_issue = _consumer_issue(gh, issue, number)
        if consumer_issue is None:
            continue
        consumer_issues[number] = consumer_issue
        consumer_labels[number] = gh.workflow_label(consumer_issue)
    return _ChildScan(
        list(generation.consumers), consumer_issues, consumer_labels,
    )


def _consumer_issue(
    gh: GitHubClient, issue: Issue, consumer: int,
) -> Issue | None:
    """Fetch one recorded consumer, or None when it could not be asked for."""
    try:
        return gh.get_issue(consumer)
    except Exception:
        log.exception(
            "issue=#%s could not read snapshot consumer #%d; its snapshot "
            "stays retained", issue.number, consumer,
        )
        return None


def _record_branch_obligation(
    generation: LateGeneration, branch: str,
) -> LateGeneration:
    """Return this generation owing the remote one superseded branch.

    Written by the transaction before it attempts the delete, so a crash in
    between leaves the obligation for the umbrella above to retry rather than
    a branch nothing on the issue names.
    """
    return generation.with_resource(LateResource(
        kind=_BRANCH, target=branch, resource_state=LateResourceState.PENDING,
    ))


def _unwritable(generation: LateGeneration) -> bool:
    """Whether the RESOURCE ledger is one this binary may not update at all.

    Distinct from `has_opaque_ledger`, which folds in the consumer ledger
    beside it. The two are preserved and written independently, and they stop
    different things: an entry this binary cannot type on the RESOURCE ledger
    means no reclamation can be recorded, while one on the consumer ledger
    means no snapshot's proof can be taken. Reading them as one would leave a
    superseded branch on the remote because somebody hand-edited a list of
    issue numbers.
    """
    return generation.opaque_resources is not None


def _asked_of(
    walk: _Pass, generation: LateGeneration,
) -> tuple[tuple[LateResourceKind, str], ...]:
    """What this pass will ask the remote about, in the order it asks.

    A branch is asked about whenever it is owed. A snapshot is asked about
    once every recorded direct consumer is proved ended -- the rule that owns
    it -- or, past that proof, only for a ref the remote no longer has.

    Nothing at all while the RESOURCE ledger is opaque. The typed view is a
    projection of the entries this binary could read, and the write puts the
    verbatim copy back -- so a reclamation recorded against that view would be
    dropped at the next write and asked for again forever.

    An opaque CONSUMER ledger stops only what it is about. It is the thing a
    snapshot's proof is taken from, so no ref may be reclaimed while it cannot
    be read -- but a branch owes no consumer anything, and freezing the two
    together would leave a superseded branch on the remote for as long as a
    hand-edited consumer list stayed hand-edited. The two are preserved and
    written independently, and they are refused independently here.
    """
    if _unwritable(generation):
        return ()
    owed = tuple((_BRANCH, target) for target in _owed_branches(generation))
    return owed + tuple(
        (_SNAPSHOT, target) for target in _asked_snapshots(walk, generation)
    )


def _asked_snapshots(
    walk: _Pass, generation: LateGeneration,
) -> tuple[str, ...]:
    """The held refs this pass may act on, and what qualifies each of them.

    Every held ref qualifies once the consumers are proved ended, which is the
    rule that owns the snapshot.

    Past that proof there is exactly one more way in, and it is narrow on
    purpose. An entry reading `reclaiming` or `failed` records a decision that
    was taken against a proof, and half of what a retry has to finish is not
    repeatable: the ledger may be behind a delete that already landed, and a
    child told against it, while the consumers a fresh reading finds are
    whoever a human has reopened since. So the ref itself is asked about
    first, and the entry qualifies only if the remote no longer has it. A ref
    the remote still holds is a ref a reopened consumer may still be cutting
    from -- and the decision to take it, however durably recorded, does not
    outrank the reading in front of it.
    """
    if _reclaimable(walk.state, generation, walk.scan):
        return _held_snapshots(generation)
    return tuple(
        entry.target
        for entry in generation.resources
        if entry.kind == _SNAPSHOT
        and entry.resource_state in _ORDERED
        and _already_gone(walk, generation, entry.target)
    )


def _already_gone(
    walk: _Pass, generation: LateGeneration, ref: str,
) -> bool:
    """Whether an ordered ref the consumers no longer clear is gone anyway.

    One read, and it decides which of two wrongs to avoid. Assuming the ref
    is gone would delete one a reopened child came back for; assuming it is
    there would strand a ledger against a ref nothing can prove either way,
    holding a terminal open forever. Asking answers it, and only in the window
    where the two answers differ -- a decision recorded and the consumers no
    longer unanimous, which is a crash or a refusal followed by a reopen.

    Fails closed. Unreadable, mismatched, or raised all leave the ref held,
    which is the answer that destroys nothing.
    """
    try:
        observed = _snapshot_refs.observed_snapshot_ref(
            walk.spec, walk.spec.target_root,
            ref=ref, sha=generation.candidate_sha,
        )
    except Exception:
        log.exception("could not ask the remote about snapshot %r", ref)
        return False
    return observed == _snapshot_refs.SnapshotOutcome.ABSENT


def _reclaimed(walk: _Pass, generation: LateGeneration) -> _Reclamation:
    """Settle everything this issue owes that can be settled right now.

    The latch is asked between the obligations rather than once for the pass,
    because each of them is a request -- a branch delete, then a ref delete
    with a receipt on every child cut from it -- and a poll can observe the
    close between any two. What the mark changes is not WHETHER the rest is
    settled (a cancellation buys no shortcut through the reclamation rules)
    but what the settling owes anybody: a cancelled cycle tells its consumers
    nothing, and its owner takes no terminal until its own ending has run.
    """
    settled = generation
    acted = []
    for owed in _asked_of(walk, generation):
        settled = _observed_close(walk, settled)
        reclaimed = _reclaimed_one(walk, settled, *owed)
        if reclaimed is not None:
            settled = reclaimed
            acted.append(owed)
    entries = _settled_entries(settled, tuple(acted))
    return _Reclamation(
        generation=settled,
        entries=entries,
        moved=_moved_entries(generation, entries),
    )


def _reclaimed_one(
    walk: _Pass,
    generation: LateGeneration,
    kind: LateResourceKind,
    target: str,
) -> LateGeneration | None:
    """Settle one obligation, or None where this pass may not touch it.

    The branch is the one that can be refused here, and it is refused HERE
    rather than where the work list was assembled because of what stands
    between the two: the snapshot rule may spend a remote probe deciding
    whether an ordered ref is already gone, and a human can reopen the pull
    request inside it. An answer good enough to build a list with is not one
    good enough to delete on.

    What it protects is the one act on this pass nothing could undo. A split
    closed that pull request and this delete is what takes its branch away, so
    a human who reopened it has a change pointing at a ref this would remove
    out from under them. The record is what still names it: the retirement
    keeps the publication group for exactly this.

    Declined rather than recorded `failed`, and the difference matters.
    Nothing was attempted, so there is nothing to report and nothing to write;
    the entry stays owed, which holds the umbrella's terminal open, and the log
    line is what says why. A `failed` entry would claim a delete that never
    went out.
    """
    if kind != _BRANCH:
        return _reclaim_snapshot(walk, generation, target)
    undone = _late_publication._publication_undone(
        walk.gh, walk.issue, generation,
    )
    if undone:
        log.error(_HELD_BACK_BRANCH, walk.issue.number, undone, target)
        return None
    return _reclaim_branch(
        walk.gh, walk.spec, walk.issue.number, generation, target,
    )


def _settled_entries(
    generation: LateGeneration,
    asked: tuple[tuple[LateResourceKind, str], ...],
) -> tuple[LateResource, ...]:
    """What the record now says about each obligation this pass acted on.

    Read back off the record rather than inferred from what the remote said,
    because the two are not the same claim: a delete that landed while a
    child could not be told leaves a ref that is gone and an obligation
    that is not, and the entry is the only thing that carries both.
    """
    recorded = {
        (entry.kind, entry.target): entry for entry in generation.resources
    }
    return tuple(recorded[owed] for owed in asked if owed in recorded)


def _moved_entries(
    before: LateGeneration, entries: tuple[LateResource, ...],
) -> tuple[LateResource, ...]:
    """The acted-on obligations whose recorded state this visit changed.

    Asked against the record the pass OPENED with, so what counts as movement
    is what a reader of the ledger would see happen -- a first attempt, a
    refusal that became a reclamation, a reclamation a reopened consumer put
    back. A retry that reaches the same answer moves nothing, and there is
    nothing about it a second record could say that the first did not.
    """
    was = {
        (entry.kind, entry.target): entry.resource_state
        for entry in before.resources
    }
    return tuple(
        entry for entry in entries
        if was.get((entry.kind, entry.target)) != entry.resource_state
    )


def _blocking(generation: LateGeneration) -> tuple[str, ...]:
    """What may not be left behind when this umbrella closes.

    Every obligation that is not `reconciled`, branch and ref alike. There is
    no reading under which a ref still on the remote is settled: one kept
    because a consumer could not be proved ended is an object this repository
    is holding, and an umbrella closed over it is an object nothing would ever
    come back for -- the parent is `done` by then and no pass revisits it. The
    label staying put IS the retry, and it is also the only thing that makes
    an unreclaimable ref visible to a human.

    An opaque RESOURCE ledger blocks whatever the typed view says, and it has
    to: the entries this binary could not read are still obligations, and the
    typed entries beside them are not the whole of what is owed. Closing on
    the strength of a projection is exactly the reading the verbatim copy
    exists to prevent.

    An opaque CONSUMER ledger needs no clause of its own. It is what a
    snapshot's proof is taken from, so a ref it covers is never reclaimed and
    is therefore already here as an unreconciled entry -- while a branch,
    which owes no consumer anything, is settled and closes as it always did.
    """
    if _unwritable(generation):
        return (_OPAQUE,)
    return _owed_branches(generation) + _held_snapshots(generation)


def _settle(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _ChildScan,
) -> LateGeneration:
    """Settle what this issue owes right now, and answer the record it leaves.

    The write is behind what MOVED, not behind what was attempted. An entry
    already reconciled is not asked about at all, and one a retry left exactly
    as it found it has nothing to write down -- so a remote that goes on
    refusing one delete costs a request per visit rather than a request and a
    pinned write per visit, for as long as the refusal lasts.

    What is reported is behind the same reading, and the log line beside it is
    not: the sinks carry the transitions, and every visit that ends with
    something still owed says so where an operator reads it.

    The stage both sinks record is read off the issue rather than named by the
    caller, because it is a fact about where the reclamation happened and not
    about which owner drove it: the umbrella's terminal reaches here on
    `umbrella`, and the closed-owner sweep on whichever of the two cleanup
    states its issue was closed on.
    """
    walk = _Pass(gh=gh, spec=spec, issue=issue, state=state, scan=scan)
    settled = _reclaimed(walk, _late_state.read_late_generation(state))
    if settled.moved:
        walk.persist(settled.generation)
    if settled.attempted:
        _report(gh, issue, settled, stage=stage_name(gh.workflow_label(issue)))
    return settled.generation


def _settled_for_terminal(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _ChildScan,
) -> bool:
    """Whether this umbrella may complete, settling what it still owes.

    The caller is the umbrella's all-children-resolved branch, and the answer
    is a decision rather than a report: False keeps the parent open on
    `workflow:umbrella` for the next tick to ask again, which is what makes an
    unreclaimed remote loud instead of silent. An issue with no recorded
    generation owes nothing and answers without a write.

    The ledger is not the whole of what holds it. A split entered past
    publication owes the terminal one question as well as its obligations --
    whether the pull request it closed is still closed -- and that is asked
    HERE rather than left to the ledger, because the two can disagree: a
    reclamation that finished leaves nothing owed, so a human who restores the
    branch and reopens the change afterwards would find every entry settled
    and the terminal free to fire. What that terminal writes is `done` and a
    close, and the write ahead of it drops the publication group -- so nothing
    would ever ask again, and an open change carrying superseded work would be
    left under a parent this workflow had declared finished.

    Asked before anything is SAID, which is why it belongs to this owner and
    not to the completion behind it: the resolution comment is gated on a
    stamp the retirement write puts down, so a refusal taken past that comment
    would repeat it on every tick that holds.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        return _owes_nothing_uncorrelated(issue, generation)
    settled = _settle(gh, spec, issue, state, scan)
    held = _blocking(settled) + _unsettled_publication(gh, issue, settled)
    if not held:
        return True
    # Said on every tick that holds, because a hold with nothing attempted
    # writes nothing and emits nothing: an umbrella that will not close and
    # never says why is the one shape an operator cannot act on.
    log.info(
        "issue=#%d holds its terminal on: %s", issue.number, ", ".join(held),
    )
    return False


def _unsettled_publication(
    gh: GitHubClient, issue: Issue, generation: LateGeneration,
) -> tuple[str, ...]:
    """What holds a terminal when the change a split closed has come back.

    A reason rather than an obligation, and it is deliberately not written to
    the ledger. Nothing here is owed the remote: the branch really was
    reclaimed and the ref really was let go, and an entry claiming otherwise
    would send a later pass to delete a branch a human put back on purpose.
    What is unfinished is the pull request, and the only thing this workflow
    may do about that is decline to close over it and say so.

    Empty for everything that never had a publication, and no request is spent
    on any of them -- which is every umbrella the initial decomposer made and
    every split entered before the first push.
    """
    undone = _late_publication._publication_undone(gh, issue, generation)
    return (undone,) if undone else ()


def _owes_nothing_uncorrelated(
    issue: Issue, generation: LateGeneration,
) -> bool:
    """Whether an issue with no cycle identity may still close.

    An issue that never entered the late gate carries no ledger either, and
    answers True without a write -- which is every umbrella the initial
    decomposer made.

    A ledger with entries on a record whose identity is damaged is the other
    case, and it may not close. There is nothing to correlate a reclamation
    to, no issue number to prove a branch belongs to this generation, and no
    record either sink would accept -- so the only safe answer is to stay open
    and say so where an operator reads it. The write that damaged the identity
    kept the ledger on purpose; closing over it would finish the job.
    """
    if not generation.resources and not generation.has_opaque_ledger:
        return True

    log.error(
        "issue=#%d still records external obligations under a damaged late "
        "identity; holding the umbrella open rather than closing over them",
        issue.number,
    )
    return False


def _report(
    gh: GitHubClient,
    issue: Issue,
    settled: _Reclamation,
    *,
    stage: str | None,
) -> None:
    """Say on both sinks what each attempted reclamation changed.

    One `late_cleanup` per obligation whose recorded state MOVED, carrying the
    state the record now gives it. A typed failure rides with the one state
    that names a remote that REFUSED; an obligation still `reclaiming` is work
    in progress, not a failure, and says so by carrying that state rather than
    a second event. A retry that reached the same answer as the visit before
    it reports nothing at all: the record already carries that answer, and a
    stream of identical failures is one fact repeated per cadence rather than
    a second thing having gone wrong.

    The log is the other half and is deliberately not bounded that way. Every
    entry short of `reconciled` is warned about on every visit that attempted
    it, because a visit that keeps happening is happening for one of these,
    and an object nobody can reclaim has to stay visible for as long as it is
    held rather than only on the tick it first refused.
    """
    for moved in settled.moved:
        _emit_cleanup(gh, settled.generation, moved, stage)
    for entry in settled.entries:
        if entry.resource_state != LateResourceState.RECONCILED:
            log.warning(
                "issue=#%d still owes the remote %s %r (%s); it is retried "
                "on every visit until it is reclaimed",
                issue.number,
                entry.kind,
                entry.target,
                entry.resource_state,
            )


def _emit_cleanup(
    gh: GitHubClient,
    generation: LateGeneration,
    entry: LateResource,
    stage: str | None,
) -> None:
    """Report what happened to one external resource, on both sinks."""
    if entry.resource_state == LateResourceState.FAILED:
        _telemetry.emit_late_event(
            gh,
            _events.LateEvent(
                family=_events.LateEventFamily.FAILURE,
                failure=_FAILURES[entry.kind],
            ),
            generation,
            stage=stage,
        )
    _telemetry.emit_late_event(
        gh,
        _events.LateEvent(
            family=_events.LateEventFamily.CLEANUP,
            resource=entry,
        ),
        generation,
        stage=stage,
    )
