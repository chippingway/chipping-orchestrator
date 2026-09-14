# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a child born of a split proves before it starts on what it was cut from.

A late split hands each child a pointer to an immutable ref and tells it to
reuse the candidate under it. That ref does not live forever: it is reclaimed
once every child cut from it has ended, and a human is free to reopen one
afterwards. So the pointer a child carries is a claim about the past, and the
one moment it matters is the moment the child is about to act on it.

This is the guard at that moment, and it is deliberately the CHILD's own. The
owner that reclaimed the ref cannot make this safe from its side: it would be
writing another live issue's pinned comment from a worker of its own, and that
comment is written whole -- a terminal finalize that read it first and wrote it
after would put the reclaimed pointer back and take any park off, with nothing
left to notice. Evaluated here instead, on the issue's own dispatch, there is
nobody to race: whatever a concurrent writer did to the record, the child reads
it again and decides again.

The dispatcher is where it runs, ahead of every handler and ahead of the
terminal no-op. That last one is the point: a consumer that ended is `done` or
`rejected`, and reopening one leaves the label exactly where it was -- so the
issue a human brings back is precisely the issue the dispatcher would otherwise
have nothing to do with. Running here also means no route around it: a relabel
straight to another stage is dispatched through the same seam.

Two things can answer it, and the first outranks the second.

**The receipt the reclamation left.** As a ref goes, its owner posts one
comment on each child cut from it, marked with that owner, cycle, and
generation. That marker is the authoritative answer, because it says what
HAPPENED rather than what a later reading of the world suggests: a mirror this
host never got round to dropping, or a ref somebody pushed again at the same
commit, would both make the world look untouched while the candidate the child
was promised is no longer one anybody vouches for. Read off the thread and only
from a comment of ours, so neither a stale local ref nor a third party's forged
marker can speak for a reclamation. A child that has never been split into
carries no ancestry and never asks; one whose pointer this guard has already
dropped never asks again.

A thread that could not be READ is not a thread with no receipt on it, and the
difference decides the tick. Everything behind this reading can look untouched
while the answer that outranks it sits unseen -- a mirror nobody dropped, a ref
pushed again at the same commit -- so an unreadable thread holds the dispatch
rather than falling through to readings it would have overruled.

**What the world says, when no receipt does.** A reclamation whose receipt
never landed -- a crash, a thread that could not be posted to -- still has to
stop the child, so the ref is asked about. This host first, and that shortcut
is bought by the ORDER the reclamation runs in rather than assumed of it: the
local mirror is taken down before the remote ref is touched at all, and a
mirror that cannot be proved gone stops the reclamation instead of being
logged past. So a mirror still here says nothing has been reclaimed, and only
a mirror that is gone is worth one `ls-remote`.

"Still here" is an identity, not an existence. The mirror is a ref in the
object store every agent's worktree shares, so what the name resolves to is
the whole of what it proves: a copy at the exact commit this child was
promised is the reclamation-has-not-happened reading, and a copy at anything
else is somebody's write, which says nothing about the ref on the remote and
is not a candidate this child may work from either. Both of those go to the
ask.

That shortcut is taken only where the pointer itself says it may be. An
ancestry written before the reclamation put this host's copy first is a
pointer into a world where the remote went first and the mirror came down
best-effort -- so a surviving mirror there is as likely to be the residue of a
reclamation that finished as proof one never started, and the child pays a
read-only ask rather than trusting it. Nothing migrates: the stamp is written
by the binary that would do the reclaiming, and its absence is the whole
question answered.

Three answers come back and each is a different verdict. A proved absence is
the reclamation this child was not told about. A `MISMATCH` is the ref
carrying somebody else's commit, which is not the candidate this child was
promised and is not a thing to start work against either -- the reclamation
refuses one for a human, and so does this. `UNREADABLE` is neither: it is an
outage, and an outage is not evidence about anything, so the dispatch is HELD
rather than parked or waved through. Held is the cheap direction -- the child
is looked at again on the next tick and no comment, label, or park is written
-- while waving it through spawns an agent against instructions naming a ref
nobody could vouch for.

One shape has neither pointer nor pinned lineage, and it still has to stop.
The split records a child on the parent's ledger before it seeds that child's
ancestry -- a child on GitHub the parent does not record is a child nothing
would come back to -- so a seed that failed leaves an issue whose BODY tells it
to reuse a snapshot and whose pinned comment says nothing. The reclamation
counts it as a consumer all the same, and leaves its receipt on it all the
same. The body's own marker is what says this is a child of a split, and it
costs nothing to read.

It is also the one lineage claim here that comes out of a field the world can
write, and every claim it competes with is authenticated: a pinned comment
only this orchestrator writes, a receipt checked against its author. So it is
CORROBORATED rather than believed. The marker names an owner, a cycle, and a
generation; the owner's own record is read fresh and has to name the same
cycle and generation and carry this issue's number among the consumers it cut
from that ref. A claim it does not vouch for is a claim about nothing, and the
guard steps aside -- parking an issue on the strength of a sentence somebody
typed into its body is exactly the denial of service that reading a body as
authority buys.

A vouched claim yields the whole pointer the failed seed never wrote: the ref
the identity mints, and the commit the owner recorded preserving. That is what
makes the ask the same ask the recorded shape makes -- whether THIS candidate
is still obtainable -- rather than whether some name is occupied. And the ask
has to happen, because the receipt cannot cover the window it is posted after:
a ref is deleted first, so a silent thread is what that window looks like, and
so is a thread this tick could not read. A record nobody could read holds the
dispatch instead; it may well be true and this tick cannot tell.

The park is the whole point rather than a formality: it is what stops an
implementation from running against instructions naming a ref that no longer
exists, and it says what continuing takes -- an ordinary change, or an explicit
new split cycle on the owner, which preserves a candidate of its own.
"""
from __future__ import annotations

import logging
from enum import Enum
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.git.snapshots import mirrors as _snapshot_mirrors, refs as _snapshot_refs
from orchestrator.github import client as _client, comments as _comments, pinned_state as _pinned_state
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.late_split import ancestry as _ancestry, lineage as _lineage, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration

log = logging.getLogger("orchestrator.workflow")

# The reason the `park_awaiting_human` audit record carries for a child whose
# snapshot was reclaimed before it came back to it.
PARK_SNAPSHOT_RECLAIMED = "late_snapshot_reclaimed"

# And for the other way the promise can be broken: the ref is still there and
# carries a commit nobody preserved. Kept apart from the reclamation because
# an operator reading a park has to know which world they are in -- one is
# this orchestrator finishing its own work, and the other is a ref in its
# namespace that somebody else wrote.
PARK_SNAPSHOT_REPOINTED = "late_snapshot_repointed"


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

_RECLAIMED_PARK = (
    "{mentions} the immutable snapshot this issue was created to reuse "
    "(`{ref}`, from the split on #{owner}) has been reclaimed -- it is "
    "deleted once every issue cut from it has ended. That ref is never "
    "recreated: what made it worth reusing was that it provably carried one "
    "exact commit, and a ref pushed again from whatever is reachable now "
    "proves nothing. Implement this issue as an ordinary change, or start an "
    "explicit new split cycle on #{owner}, which preserves a candidate of its "
    "own. The reuse instructions in the issue body no longer apply."
)

# And what it is told when the ref is still there under another commit. It
# says what is true rather than that the snapshot is gone: the name survived
# and what it stands for did not, which is a state this orchestrator never
# produces -- a reclamation refuses a re-pointed ref exactly as this does --
# so the ref is left where it is and the sentence is about the promise.
_REPOINTED_PARK = (
    "{mentions} the immutable snapshot this issue was created to reuse "
    "(`{ref}`, from the split on #{owner}) no longer carries the commit it "
    "was preserved at, so the candidate this issue was cut from cannot be "
    "obtained from it. Nothing here re-points or deletes that ref: a ref in "
    "this namespace carrying somebody else's commit is a question for a "
    "human. Implement this issue as an ordinary change, or start an explicit "
    "new split cycle on #{owner}, which preserves a candidate of its own. The "
    "reuse instructions in the issue body no longer apply."
)

# What the same child is told when its own record of WHICH snapshot never
# landed. It names no ref because none was ever written down: the evidence is
# either the reclamation's own receipt on the thread above or the remote no
# longer carrying the ref that split's identity names, and the sentence has
# to be true whichever of the two this tick read.
_UNRECORDED_PARK = (
    "{mentions} this issue was created by the split on #{owner} to reuse an "
    "immutable snapshot of that issue's committed candidate, and that "
    "snapshot has been reclaimed -- it is deleted once every issue cut from "
    "it has ended. This issue never recorded which snapshot it was; what says "
    "the ref is gone is the reclamation's receipt above, or the remote "
    "itself where no receipt reached this issue. That ref is never "
    "recreated: what made it worth reusing was that it provably carried one "
    "exact commit. Implement this issue as an ordinary change, or start an "
    "explicit new split cycle on #{owner}, which preserves a candidate of "
    "its own. The reuse instructions in the issue body no longer apply."
)

# How each verdict that stops a child for a human says so: what the thread is
# told, and what the audit record is filed under. Paired here because they are
# one decision -- a park an operator filters as a reclamation has to be the
# park whose comment says the ref was reclaimed.
_VERDICT_PARKS = MappingProxyType({
    _Reuse.RECLAIMED: (_RECLAIMED_PARK, PARK_SNAPSHOT_RECLAIMED),
    _Reuse.REPOINTED: (_REPOINTED_PARK, PARK_SNAPSHOT_REPOINTED),
})


def _refuses_reuse(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether this child must be answered for before it may start.

    True tells the caller to return, and covers two different states. One is
    a verdict: the ref is gone, or carries a commit nobody preserved, and the
    issue is parked for a human with its pointer dropped -- dropping it is
    what makes this cost nothing on every tick after, since an ancestry that
    goes on naming a ref the child may not use is one every later reader would
    follow. The other is the absence of a verdict, where nothing at all is
    written and the same question is asked again next tick.

    An issue with no recorded ancestry at all is not automatically an issue of
    no lineage -- see `_refuses_unrecorded`, which is what the crash window
    between recording a child and seeding it leaves behind.

    The write is this handler's own, on its own issue, so there is no second
    writer to lose it to -- which is the whole reason the guard lives here
    rather than on the owner that did the reclaiming.
    """
    ancestry = _lineage.read_late_ancestry(state)
    if not ancestry.is_present:
        return _refuses_unrecorded(gh, spec, issue, state)
    if not ancestry.has_snapshot:
        return False
    verdict = _verdict(gh, spec, issue, ancestry)
    if verdict is _Reuse.ALLOWED:
        return False
    if verdict is _Reuse.DEFERRED:
        log.warning(
            "issue=#%s was cut from %s and nobody could say whether that ref "
            "is still there; holding this dispatch rather than starting work "
            "against a promise nothing vouched for",
            issue.number, ancestry.snapshot_ref,
        )
        return True
    log.warning(
        "issue=#%s was cut from %s, which it may not reuse (%s); parking it "
        "rather than starting work against it",
        issue.number, ancestry.snapshot_ref, verdict.value,
    )
    notice, reason = _VERDICT_PARKS[verdict]
    return _parked(
        gh, issue, state, ancestry.without_snapshot(), (
            notice.format(
                mentions=config.HITL_MENTIONS,
                ref=ancestry.snapshot_ref,
                owner=ancestry.parent_issue,
            ),
            reason,
        ),
    )


def _refuses_unrecorded(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether an issue with no recorded ancestry is a child of a split anyway.

    The split records a child on the parent's ledger BEFORE it seeds that
    child's ancestry, because a child on GitHub the parent does not record is
    a child nothing would ever come back to. The window between the two is
    durable: a seed that failed leaves an issue whose BODY tells it to reuse a
    snapshot and whose pinned comment says nothing at all -- and the
    reclamation that later takes that ref still counts it as a consumer, and
    still leaves its receipt.

    So the body decides whether to look, and it costs nothing: the dispatcher
    already has the issue, and the marker the transaction stamped into it
    names the owner, the cycle, and the generation. Every issue no split
    created stops right there, without a request.

    A body is a field the world can write, so nothing here acts on what it
    claims until the SPLIT's own record says the same thing -- see
    `_unrecorded_verdict`. What the marker buys is the right to ask, and the
    asking is what decides.

    The park writes back the lineage the body claims, and only the lineage:
    the pointer this tick worked from was assembled out of the owner's record
    rather than out of anything this issue holds, and leaving half of it in
    the pinned comment is leaving a ref every later reader would follow. It is
    both the repair the failed seed owes -- an issue that now says which split
    made it -- and what stops the question being asked again, since a lineage
    with no snapshot on it returns above at once.
    """
    claimed = _ancestry.child_lineage(getattr(issue, "body", None))
    if claimed is None:
        return False
    verdict, vouched = _unrecorded_verdict(gh, spec, issue, claimed)
    if verdict is _Reuse.ALLOWED:
        return False
    if verdict is _Reuse.DEFERRED:
        log.warning(
            "issue=#%s claims the split on #%s made it, and nobody could say "
            "what that split still holds; holding this dispatch",
            issue.number, claimed.parent_issue,
        )
        return True
    log.warning(
        "issue=#%s was created by the split on #%s and never recorded which "
        "snapshot; the ref that split preserved is one it may not reuse (%s), "
        "so it is parked rather than started",
        issue.number, claimed.parent_issue, verdict.value,
    )
    return _parked(
        gh, issue, state, claimed,
        _unrecorded_park(verdict, vouched, claimed.parent_issue),
    )


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


def _unrecorded_park(
    verdict: _Reuse,
    vouched: _ancestry.LateAncestry | None,
    owner: int,
) -> tuple[str, str]:
    """What this child is told, and what the park is filed under.

    The reclaimed sentence is its own, because what this issue is missing is
    its own record of WHICH snapshot -- so the notice names none, and what
    says the ref is gone is the receipt above it or the remote. A ref that is
    still there under somebody else's commit is the recorded shape's sentence
    exactly: the ref can be named, because the owner's ledger is what named
    it.
    """
    if verdict is _Reuse.REPOINTED and vouched is not None:
        return (
            _REPOINTED_PARK.format(
                mentions=config.HITL_MENTIONS,
                ref=vouched.snapshot_ref,
                owner=owner,
            ),
            PARK_SNAPSHOT_REPOINTED,
        )
    return (
        _UNRECORDED_PARK.format(mentions=config.HITL_MENTIONS, owner=owner),
        PARK_SNAPSHOT_RECLAIMED,
    )


def _parked(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    ancestry: _ancestry.LateAncestry,
    park: tuple[str, str],
) -> bool:
    """Record what is left of the lineage, park the issue, and say why.

    `park` is what the thread is told and what the audit record is filed
    under, handed over as one value because they are one decision: a park an
    operator filters as a reclamation has to be the park whose comment says
    the ref was reclaimed, and a call site free to pair either message with
    either reason is free to file one as the other.

    Always True: the caller has already decided, and returning the decision
    keeps every refusal one statement at its call site.
    """
    notice, reason = park
    _lineage.write_late_ancestry(state, ancestry)
    _guards._park_awaiting_human(gh, issue, state, notice, reason=reason)
    gh.write_pinned_state(issue, state)
    return True


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
