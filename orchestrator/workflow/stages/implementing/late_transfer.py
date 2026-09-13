# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a rewrite may carry an adjudicated change onto the commit replacing it.

The gate recognizes a decided candidate by one commit and only it, which is
what keeps work committed on top of an accepted one from riding through on
somebody else's verdict. A workflow REWRITE is the one thing that turns that
rule against itself. The squash a reviewer's approval earns collapses the
accepted commit into a new object, and the clean base rebase the per-tick
refresh publishes replays it onto a base that moved; either way what comes out
carries the identical contribution and the exemption -- which names the old
object -- stops answering for it. Measured afresh, the very change a human
ruled on goes past the same ceiling and into a second adjudication, with a
pull request already open over the work.

So the exemption may MOVE, and this owner is the whole of what it may move on.
A permit is granted only when every one of these holds, and the answer is a
refusal the moment one does not:

* the commit the rewrite came from is the exact commit this issue exempts, an
  operator authorization stands behind that exemption -- it is half a bypass
  without one, and a move would hand the rewrite a permission the accepted
  commit never had -- and the semantic record beside it is whole: the frozen
  pair the adjudication was taken between, the digest of what lay between
  them, and the scheme it was taken under;
* the evidence names a rewrite kind this build authorizes, from a stage that
  really makes that kind, and names every end of both contributions, the pull
  request, and the lease at the shape each of those takes;
* that publication is the one this call was entered on and the one this issue
  still records -- same pull request, same stage, and a remote standing on a
  head this permit accounts for: the lease it was granted against, or, while
  the permission is still outstanding, the rewritten commit itself, which is
  this permit's own push having landed and only its receipt being lost;
* the checkout is provably clean and standing exactly on the rewritten
  commit, and the head the push is leased against peels to a commit this host
  really holds -- it is allowed to differ from the accepted one, so nothing
  else here would ever read that object;
* the issue itself is confirmed by a read taken now, not by the snapshot the
  tick opened with, and confirmed UNCHANGED rather than merely open: no
  `paused` or `backlog` control label, and still on the workflow stage the
  rewrite recorded;
* no authorization this build cannot read is already standing for the commit
  the issue exempts, since a grant replaces that record rather than adding to
  it;
* and both contributions fingerprint, from objects this host can really hand
  back, to the same digest. The accepted one is taken over the pair the RECORD
  names rather than the pair the caller claims -- so a hand-edited base is the
  record failing to prove itself rather than a field nothing ever read -- and
  the caller's claim about what it replaced is held to that same digest, as is
  the digest any permission already standing here recorded: carried forward
  unchecked, a grant would write this reading's answer over it and call
  evidence nobody checked repaired.

Every one is asked here rather than inherited from the reading that happened
to establish it, because what a permit licenses is a push that skips the
measurement entirely. The two exceptions are the ones this call has already
taken for itself, this tick and before any effect: the entry froze the pull
request from a fresh read that refuses anything but an open one standing on
the caller's lease, and the gate proved the candidate is the commit its caller
named.

A refusal is not a park and not a failure. It leaves the exemption exactly
where it is and lets the ordinary cumulative size gate measure the rewritten
commit like any other candidate for a pull request the remote already carries
-- which is the behavior every install had before an exemption could move at
all. That measurement may well PUBLISH the same commit, since a rewrite under
the ceiling is the ordinary case, so the answer this owner gives is carried
down the push tail beside the commit it was given for: a publication the
settlement behind it rotates is one this owner vouched for on this tick, and
a permission left readable on the comment vouches for nothing.

A grant is durable BEFORE the push, and what it makes durable is the
PERMISSION rather than the move. The exemption stays exactly on the commit a
human ruled on: the rewritten object is on no remote yet, so a verdict rotated
onto it here would sit on something only this host has the moment a push fails
or a process dies. The rotation belongs to the write that receipts the landed
push, where the exemption, the identity it carries, and the account of what the
remote holds go down together or not at all -- `late_rotation` inside the push
tail is the owner of that write. What licenses
THIS tick's publication is the permit handed back to the gate, so nothing has
to move early for the push to be allowed.

That one write carries the debt as well, because the account of what the branch
carries and the account of where it has still to go may not be split: a rewrite
has already replaced the branch's commits with one by the time it runs, so a
crash between them comes back to a one-commit branch nothing says a push is
owed for -- and the next squash finds a single commit, takes the
nothing-to-squash road, and reports success without measuring or pushing
anything.

A write GitHub REFUSES is a permission that was never granted, and it is
handled here rather than allowed out: the staged payload is put back exactly as
it was found and the permit is refused, so the rewritten commit falls through
to the ordinary gate and the caller still gets an answer it can roll its rewrite
back for. Left to escape, the exception would carry past every failure path the
squash has, stranding a collapsed branch nothing recorded and nothing pushed.

The other side is the rollback: a force-push the remote refuses puts the branch
back on the head the rewrite found it on -- the accepted end where a squash
collapsed that commit, the lease where a rebase read the anchor for itself --
so what the reset owes is dropping the permission it will never spend, and
nothing else. The exemption needs nothing either way, since the grant never
moved it.

An OUTSTANDING permission is a claim on the tick after a crash as well, and it
is read two ways there. It says a push is owed for the commit it names, so the
approval standing beside it may not be spent on the object id alone -- the gate
defers, and the permit is re-asked in full over both pairs, the publication and
the lease the record itself carries. And it says the receipt behind that push
has not landed, which is why a remote already standing on the rewritten commit
is this permit's own work rather than somebody else's move. A permission this
build cannot read, or one whose commit disagrees with the debt beside it, is
neither: the ordinary cumulative gate measures the rewrite like any other
candidate, and the publication that follows spends no permit it did not earn.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.git.measurement import (
    commits as _measurement_commits,
    fingerprint as _measurement_fingerprint,
)
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github import labels as _labels
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    formats as _formats,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_authority as _authority,
    late_records as _records,
    late_verdict as _verdict_owner,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The revision a checkout's own head is named by.
_HEAD = "HEAD"

# What the gate reports a carried-over candidate as, spelled the way the log
# line it joins reads.
_CARRIED_OVER = "carries an adjudicated change through a workflow rewrite"

# The state a GitHub issue has to report for a transfer to be granted.
_OPEN = "open"

# Which end of the rewrite a reading that could not be taken was about, so an
# operator told a contribution has no fingerprint knows which one.
_ACCEPTED = "accepted"

_CLAIMED = "the rewrite claims it replaced"

_REWRITTEN = "rewritten"

# Why a rewrite may not carry the exemption over. Each is worded for the log
# line an operator reads when a change a human already ruled on is about to be
# measured again, because what they have to reconcile differs by which of them
# failed.
_UNKNOWN_KIND = "`{kind}` is not a rewrite kind this build authorizes"

_FOREIGN_STAGE = "a `{kind}` rewrite is not one `{stage}` makes"

_UNNAMEABLE_REWRITE = "it cannot name both ends of both contributions"

_UNNAMEABLE_PUBLICATION = (
    "it names no pull request or no head to lease a push against"
)

_UNENTERED_PUBLICATION = (
    "this call was not entered on a publication, so nothing read the pull "
    "request the rewrite claims to be against"
)

_FOREIGN_PUBLICATION = (
    "the rewrite was made against pull request #{claimed} from `{stage}` and "
    "this call was entered on #{entered} from `{frozen}`"
)

_REPLACED_PUBLICATION = (
    "the rewrite was made against pull request #{claimed} and this issue now "
    "records {recorded}"
)

_MOVED_REMOTE = (
    "the force-push is leased against `{lease}` and pull request #{number} "
    "stands at `{standing}`"
)

_UNAUTHORIZED_EXEMPTION = (
    "no operator authorization stands behind the exemption for `{accepted}`"
)

_UNREADABLE_AUTHORIZATION = (
    "this issue already claims a transfer onto the commit it exempts and the "
    "record of it is not one this build can read"
)

_UNPROVABLE_TREE = (
    "the worktree is not provably clean, so the contribution it would be "
    "fingerprinted over is not the one a push would publish"
)

_MOVED_CHECKOUT = (
    "the rewrite produced `{rewritten}` and the checkout stands on `{head}`"
)

_UNPROVABLE_LEASE = (
    "the head this push is leased against (`{lease}`) is not a commit this "
    "host holds"
)

_UNREADABLE_OWNER = "this issue could not be read again"

_CLOSED_OWNER = "this issue is {state} rather than open"

_CONTROLLED_OWNER = "this issue carries `{control}`"

_RELABELLED_OWNER = (
    "the rewrite was entered from `{frozen}` and this issue is on `{read}` now"
)

_LATCHED_CLOSE = (
    "a poll observed this issue closed and nothing has settled the reading"
)

_UNFINGERPRINTABLE = (
    "the contribution {side} `{base}...{candidate}` could not be "
    "fingerprinted ({failure})"
)

_UNRECORDED_CONTRIBUTION = (
    "the accepted pair `{base}...{candidate}` fingerprints to `{recomputed}` "
    "here and the adjudication recorded `{recorded}`"
)

_UNCLAIMED_CONTRIBUTION = (
    "the rewrite says it replaced the contribution over `{base}`, which "
    "fingerprints to `{claimed}`, and the adjudication was taken over "
    "`{recorded}`, which fingerprints to `{accepted}`"
)

_DIFFERENT_CONTRIBUTION = (
    "the accepted contribution fingerprints to `{accepted}` and the rewritten "
    "one to `{rewritten}`"
)

_DISAGREEING_AUTHORIZATION = (
    "the permission standing here records `{recorded}` as the contribution it "
    "was granted over and this reading takes `{recomputed}`"
)


@dataclass(frozen=True)
class _Permit:
    """Whether the rewrite may carry the exemption, and what it carries.

    The digest travels with the grant because the write behind it records what
    the rewritten commit contributes, and re-taking the reading to find out
    would fingerprint a checkout that has been writable in between. A refusal
    carries no digest for the same reason a failed measurement carries no
    count: nothing was established, and an empty value is not an answer.
    """

    refusal: str = ""
    fingerprint: str = ""

    @property
    def is_granted(self) -> bool:
        """Whether a transfer may be persisted on this reading."""
        return not self.refusal


def _carried_over(gate: _records._Gate, candidate_sha: str) -> str:
    """Carry the exemption onto this rewritten commit, or "" if it may not.

    Answered before anything is measured and before anything is pushed, and
    answered in silence for every candidate that is not a rewrite of an
    accepted one: a squash of work nobody adjudicated is the ordinary case,
    and a line about it on every approval would say nothing.

    Past that, a refusal IS worth a line. What it means is that a change a
    human already ruled on is about to be measured again and may be routed
    back into adjudication with the branch already approved, so the reason is
    said out loud even though nothing is parked over it.

    A caller with no evidence of its own is answered from the RECORD, which is
    what makes the crash between a grant and the push it licensed recoverable
    on the same terms it was granted on. The recovery that republishes an
    approved commit has no plan behind it and no rewrite to describe, so the
    permission already on the comment supplies both ends of both pairs, the
    publication, and the lease -- and every question is asked again over them.
    Believed instead of re-asked, a hand-edited record, a repointed pull
    request, or a relabelled issue would each push an oversized rewrite that
    nothing revalidated.
    """
    rewrite = gate.rewrite or _outstanding_rewrite(gate.state, candidate_sha)
    if rewrite is None or rewrite.to_sha != candidate_sha:
        return ""
    identity = _exemption.read_semantic_identity(gate.state)
    if identity is None or identity.exempt_sha != rewrite.from_sha:
        return ""
    permit = _permit(gate, rewrite, identity)
    if not permit.is_granted:
        log.info(
            "issue=#%d may not carry the exemption for %s onto the rewritten "
            "%s (%s); measuring it as a fresh candidate",
            gate.issue.number, rewrite.from_sha, rewrite.to_sha,
            permit.refusal,
        )
        return ""
    granted = _authorized(
        gate, rewrite, permit.fingerprint, identity.fingerprint,
    )
    return _CARRIED_OVER if granted else ""


def _outstanding_rewrite(
    state: PinnedState, candidate_sha: str,
) -> _rewrites.LateRewrite | None:
    """The rewrite a standing permission still licenses for this commit.

    What a tick with no evidence of its own is answered from. A permission is
    written before the push and spent by the receipt behind it, so one left at
    `authorized` names a rewrite whose push has not been accounted for -- and
    the commit it names is exactly the one an approval is owed a push for.
    Handed back, the permit is re-asked over the terms it was granted on
    rather than assumed from the approval's bare object id.

    None for anything else: a comment carrying no permission, one this build
    cannot read whole, one already spent, and one naming some other commit.
    Each of those leaves the candidate to the ordinary cumulative gate, which
    is the answer a rewrite nobody can revalidate has to get.
    """
    authorization = _rewrites.read_rewrite_authorization(state)
    if authorization is None or authorization.rewrite.to_sha != candidate_sha:
        return None
    if authorization.phase != _rewrites.LateRewritePhase.AUTHORIZED:
        return None
    return authorization.rewrite


def _licensed_by_a_permit(state: PinnedState) -> bool:
    """Whether this commit's debt rests on a permit rather than a reading.

    The gate skips the measurement for a commit an approval is owed a push
    for, because the approval is its own earlier decision brought back by a
    crash. That holds for every approval but one: a commit an approval names
    only because a TRANSFER let it past has never been measured and never been
    adjudicated -- what licensed it was a permit, and a permit is granted on
    terms that can stop being true between the grant and the recovery. A
    pull request repointed, an issue relabelled, a record hand-edited, or a
    contribution that no longer fingerprints alike each leave an approval
    standing over a rewrite nothing may publish unmeasured.

    So the bypass defers to the permit, which is re-asked in full over the
    record the grant left -- and where it refuses, the ordinary cumulative
    gate measures the rewrite like any other candidate.

    Asked of the PERMISSION rather than of the commit the record names, and
    that is what cross-binds it to the debt. An outstanding permission says a
    push is owed for the commit it produced, and the grant writes that
    permission and that debt in one write for one commit -- so an approval
    standing beside an outstanding permission is either the one it licensed or
    evidence that the two disagree, and neither may be spent on an object id.
    Compared against the commit the record names instead, a hand-edited target
    would make the permit invisible: the approval would look like any other
    and the rewrite nothing could revalidate would be pushed unmeasured.

    Only a record this build can vouch for ENTIRELY is recognized as spent,
    which is the record owner's own rule: a group announcing `published` over
    fields nothing else here understands, or bound to a commit this issue does
    not exempt, has not been shown to be over. A spent one licenses nothing
    outstanding, and that is what keeps the ordinary bypass intact -- a
    transfer that settled leaves its record behind for good, and reading that
    as a standing claim would send every later approval this issue earns back
    through a measurement.

    What ends the deferral is the receipt of the push the permission was
    granted for: that write carries the exemption over and moves the phase, so
    the record standing afterwards is spent and every later approval this
    issue earns is the ordinary one again. Until it lands the deferral holds,
    which costs a reading rather than a decision -- and where the permit
    refuses on the re-ask, the ordinary cumulative gate measures the rewrite
    like any other candidate.
    """
    return _rewrites.outstanding_permission(state)


def _permit(
    gate: _records._Gate,
    rewrite: _rewrites.LateRewrite,
    identity: _exemption.LateSemanticIdentity,
) -> _Permit:
    """Everything a transfer is granted on, asked in the order it costs.

    The evidence's own shape first, because it costs nothing and no later
    question means anything without it. Then the authorization already on the
    comment, which is the one thing a grant would DESTROY rather than merely
    read. Then the publication, which this call has already read. Then the two
    local git reads -- the checkout, and the lease as an object this host has
    to hold. Then the issue, which is a request. And the fingerprints last,
    because they are the heaviest reading in the domain -- every object either
    contribution names is read back in full -- and there is no point taking
    them for a transfer something cheaper has already refused.

    The operator authorization behind the exemption is asked with them rather
    than at the door for that same reason: proving one is a fingerprint, since
    every other term of an authorization is the pinned comment agreeing with
    itself. Its own reading is the first of the three, because a transfer that
    may not happen at all should not pay for the two that compare
    contributions.
    """
    for question in (
        _unusable_evidence,
        _unreadable_authorization,
        _disagreeing_publication,
        _unproven_checkout,
        _unproven_lease,
        _unconfirmed_owner,
        _unauthorized_exemption,
    ):
        refusal = question(gate, rewrite)
        if refusal:
            return _Permit(refusal=refusal)
    permit = _equal_contributions(gate, rewrite, identity)
    if permit.refusal:
        return permit
    disagreeing = _disagreeing_authorization(gate, permit.fingerprint)
    return _Permit(refusal=disagreeing) if disagreeing else permit


def _unauthorized_exemption(
    gate: _records._Gate, rewrite: _rewrites.LateRewrite,
) -> str:
    """Why the exemption this would move licenses nothing, or "".

    An exemption is half a bypass: it says an ADJUDICATOR ruled the change one
    coherent whole, and the operator authorization beside it is what says a
    human agreed to publish past the ceiling. A commit only the exemption
    names is one the ordinary gate measures, so moving that exemption onto a
    rewrite would hand the rewritten commit a permission the accepted one
    never had -- and this owner's grant is the one road that skips the reading
    without any record naming the commit in advance.

    PROVED rather than parsed, which is why this is asked among the
    fingerprints rather than at the door. Every term of an authorization but
    the digest is the pinned comment agreeing with itself, and a hand edit
    arranges that as easily as a crash: a group naming the accepted commit
    over a base nobody froze, with a digest of nothing, reads back whole and
    would license this grant -- and past the grant an oversized change no
    human ever saw publishes on a rewrite the gate never measured. The digest
    is the one term the objects answer, so it is re-taken between the pair the
    record names and held to what the record says. Asked through the owner the
    GATE asks it through, so an authorization means the same thing on both
    roads past the measurement.

    The record an older binary left reaches it too: a `single` verdict wrote
    the exemption alone before a human's own decision was required at
    publication, and so does any comment whose authorization this build cannot
    read back whole.

    Refused, nothing moves and the rewritten commit is measured by the
    ordinary cumulative gate exactly as every other refusal here leaves it.
    """
    if _authority._publishes_on_an_exemption(gate, rewrite.from_sha):
        return ""
    return _UNAUTHORIZED_EXEMPTION.format(accepted=rewrite.from_sha)


def _unreadable_authorization(
    gate: _records._Gate, rewrite: _rewrites.LateRewrite,
) -> str:
    """Why a claim already standing here forbids replacing it, or "".

    A grant writes the whole authorization group, so it does not add a record
    beside one -- it destroys whatever was there. Where that was a claim about
    the very commit this issue exempts and this build cannot read it back --
    a member missing, a field hand-edited, a kind or a phase from somewhere
    else -- overwriting it would repair evidence nobody checked, under the
    authority of a transfer this owner is in the middle of deciding.

    So it refuses, which costs the exemption nothing: the record stays exactly
    as it stands and the rewritten commit is measured by the ordinary gate
    until a human settles what is on the comment.

    A group describing some OTHER commit is not that claim and is replaced
    without ceremony: the exemption moved on since, so what is left names a
    commit nothing exempts and is not evidence for anything this issue still
    holds.
    """
    if not _rewrites.claims_the_exemption(gate.state):
        return ""
    if _rewrites.read_rewrite_authorization(gate.state) is None:
        return _UNREADABLE_AUTHORIZATION
    return ""


def _disagreeing_authorization(gate: _records._Gate, fingerprint: str) -> str:
    """Why the digest a standing permission recorded is not this one, or "".

    The one field of an authorization that says what it was GRANTED over
    rather than what it is about, and the only one no other question here
    reaches: the ends are checked against the evidence, the publication
    against the entry, and the exemption against the record -- while the
    digest between them would otherwise be carried forward untested and
    written back as whatever this reading happened to take.

    That is a repair, and this owner may not make one. A permission whose
    digest disagrees with the contribution actually in front of it is either a
    record somebody edited or one taken under rules this build no longer
    reads the same way, and in both the honest answer is that nothing here
    knows which of the two digests the human ruled on. So the permit is
    refused, the record is left exactly as it stands, and the rewritten commit
    is measured by the ordinary cumulative gate.

    Asked only of a group claiming the commit this issue exempts, because that
    is the only one a grant would overwrite. One describing some other commit
    is replaced without ceremony and is evidence for nothing this issue still
    holds, so its digest is not a claim about this contribution either.

    A group that cannot be read whole is somebody else's refusal -- it comes
    first, and reaching here means the record proved out in every other field.
    """
    if not _rewrites.claims_the_exemption(gate.state):
        return ""
    authorization = _rewrites.read_rewrite_authorization(gate.state)
    if authorization is None or authorization.fingerprint == fingerprint:
        return ""
    return _DISAGREEING_AUTHORIZATION.format(
        recorded=authorization.fingerprint, recomputed=fingerprint,
    )


def _unusable_evidence(
    gate: _records._Gate, rewrite: _rewrites.LateRewrite,
) -> str:
    """Why this evidence names no rewrite at all, or "".

    The kind is bounded because what a member licenses is a commit the
    orchestrator produced itself, out of commits it can name both ends of; a
    spelling this build does not authorize describes a rewrite nothing here
    made. The STAGE beside it is held to that kind rather than merely to being
    a stage a publication is entered from: the two are one claim about which
    rewrite this workflow made and where, so a `conflict_rebase` offered from
    `validating` or a `squash` from `resolving_conflict` describes a rewrite
    that stage does not make -- and checked a field at a time each half passes
    while the pair is evidence nothing here produced. Every other field is
    held to the shape it claims for the reason each pinned end is: an
    abbreviation is not a commit and a value that cannot name a pull request
    is not one, so a permit granted over either would rest on evidence no
    later reader could check.
    """
    if rewrite.kind not in _rewrites.LateRewriteKind:
        return _UNKNOWN_KIND.format(kind=rewrite.kind)
    if not _rewrites.entered_from(rewrite.kind, rewrite.source_stage):
        return _FOREIGN_STAGE.format(
            kind=rewrite.kind, stage=rewrite.source_stage,
        )
    named = (
        rewrite.from_sha, rewrite.from_base_sha,
        rewrite.to_sha, rewrite.to_base_sha,
    )
    if not all(
        _formats.is_hex_of(end, _formats.COMMIT_LENGTHS) for end in named
    ):
        return _UNNAMEABLE_REWRITE
    pinned = (
        _formats.whole_number(rewrite.pr_number) and rewrite.pr_number > 0
        and _formats.is_hex_of(rewrite.lease, _formats.COMMIT_LENGTHS)
    )
    return "" if pinned else _UNNAMEABLE_PUBLICATION


def _disagreeing_publication(
    gate: _records._Gate, rewrite: _rewrites.LateRewrite,
) -> str:
    """Why the rewrite is not against the publication this call froze, or "".

    The entry is this call's own fresh reading of that pull request, taken
    before any effect and refused unless it came back open and standing on the
    head the caller established -- so a rewrite whose every term matches it is
    one made against a pull request confirmed open and unmoved this tick. Read
    a second time here, the answer could only be a later one than the head the
    force-push is already leased against.

    The pull request the ISSUE records is asked beside it, because the entry
    proves the pull request was read and not that it is still the one this
    issue's work belongs to: a repointed `pr_number` describes a publication
    the rewrite was never made against.
    """
    entry = gate.entry
    if entry is None or not entry.is_frozen:
        return _UNENTERED_PUBLICATION
    claimed = (rewrite.pr_number, rewrite.source_stage)
    if claimed != (entry.pr_number, entry.stage):
        return _FOREIGN_PUBLICATION.format(
            claimed=rewrite.pr_number, stage=rewrite.source_stage,
            entered=entry.pr_number, frozen=entry.stage,
        )
    if not _standing_where_the_permit_left_it(gate, rewrite):
        return _MOVED_REMOTE.format(
            lease=rewrite.lease, number=entry.pr_number,
            standing=entry.published_sha,
        )
    recorded = gate.state.get(_state._PR_NUMBER)
    if recorded != rewrite.pr_number:
        return _REPLACED_PUBLICATION.format(
            claimed=rewrite.pr_number, recorded=recorded,
        )
    return ""


def _standing_where_the_permit_left_it(
    gate: _records._Gate, rewrite: _rewrites.LateRewrite,
) -> bool:
    """Whether the remote is a head this permit accounts for.

    Two heads do, and the second is what makes a lost receipt recoverable.
    The LEASE is the ordinary one: the pull request is where the rewrite was
    made against it and the push has not gone out.

    The REWRITTEN commit is the other, and only while the permission is still
    outstanding. A pull request standing there is this permit's own push
    having landed -- nothing else force-pushes that object under that lease --
    and what is missing is the receipt behind it. Refused as a moved remote,
    the recovery would remeasure a squash the pull request already carries and
    route an oversized one straight back into adjudication with the work
    already published. Admitted, the permit re-proves everything else and the
    republication is the leased no-op it should be, which is what lets the
    receipt behind it settle the debt the grant made durable.

    Phase-aware, because that is the whole of what makes it safe: a spent
    permission accounts for no outstanding push, so past the receipt this head
    is an ordinary moved remote again.
    """
    entry = gate.entry
    if entry.published_sha == rewrite.lease:
        return True
    if entry.published_sha != rewrite.to_sha:
        return False
    return _outstanding_rewrite(gate.state, rewrite.to_sha) is not None


def _unproven_checkout(
    gate: _records._Gate, rewrite: _rewrites.LateRewrite,
) -> str:
    """Why the checkout is not provably the rewritten commit, or "".

    Both halves, because a transfer is a claim about what the checkout will
    publish. A tree carrying anything loose is one whose contribution is not
    the contribution a push would send, and a `git status` that established
    nothing names no paths -- which is what a clean tree names too. And a head
    that is not the rewritten commit, or one this host cannot peel, is a
    checkout the rewrite's own before-and-after says nothing about.
    """
    if not _verification_probes._worktree_status(gate.worktree).is_clean:
        return _UNPROVABLE_TREE
    proved = _measurement_commits._prove_candidate_commit(
        gate.worktree, _HEAD,
    )
    if proved.is_frozen and proved.sha == rewrite.to_sha:
        return ""
    return _MOVED_CHECKOUT.format(
        rewritten=rewrite.to_sha, head=proved.sha or "an unreadable head",
    )


def _unproven_lease(
    gate: _records._Gate, rewrite: _rewrites.LateRewrite,
) -> str:
    """Why the head this push is leased against is not one to lease on, or "".

    The one end of the evidence nothing else here reads as an OBJECT. The
    checkout proves the rewritten commit, and the two fingerprints prove both
    ends of both contributions by reading every byte they name -- but the
    lease is compared as an id and never asked for, and it is deliberately
    allowed to differ from the accepted commit, so nothing else would catch a
    whole-looking object id this repository does not hold.

    That gap matters because of what the lease IS: the head the pull request
    was standing on, which this branch was on before the rewrite collapsed it.
    An id the remote reports and this host cannot peel is a fetch that brought
    nothing back or work made somewhere else -- so the agreement between the
    entry and the record is two readings of a commit neither of them can
    produce, and a permit resting on it would skip the measurement on evidence
    nobody can check.

    Proved rather than looked up, for the reason every other commit in this
    domain is: git resolves a full object id to itself whether or not the
    store has ever seen it, so only peeling tells the two apart.
    """
    proved = _measurement_commits._prove_candidate_commit(
        gate.worktree, rewrite.lease,
    )
    if proved.is_frozen:
        return ""
    return _UNPROVABLE_LEASE.format(lease=rewrite.lease)


def _unconfirmed_owner(
    gate: _records._Gate, rewrite: _rewrites.LateRewrite,
) -> str:
    """Why this issue is not the one the rewrite was made on, or "".

    The issue in hand was fetched when the tick began and a squash-on-approval
    runs minutes later, so the snapshot says nothing about whether anybody
    still wants this work or has taken it somewhere else. A transfer is the
    one answer here that carries a human's verdict forward without re-asking a
    human anything, so the issue is re-read for it rather than assumed -- and
    the latch is asked first, because a close a poll observed while this
    worker holds the issue is one no request of this tick's would ever show.

    The three things asked of that read are one question: is this still the
    issue the rewrite was entered on. Its STATE, since a closed one wants none
    of it. Its CONTROL labels, since `paused` and `backlog` are how an
    operator says stop and a transfer that pushed past one would be the
    orchestrator carrying on where it was told not to. And its WORKFLOW label,
    against the stage the rewrite recorded -- the entry read that stage off
    the issue the tick opened with, so a relabel during the rewrite is
    invisible to every reading but this one, and a permit granted under it
    would publish onto a pull request whose stage no longer owns the branch.

    Fails closed twice over, like every other owner read in this domain: an
    exception is unreadable -- the fetch and every attribute behind it, since
    a fetched issue is lazy -- and so is a state that is neither of the two
    GitHub reports, which would otherwise default to open and grant a permit
    on a read that established nothing.
    """
    if _observations.close_observed(gate.spec.slug, gate.issue.number):
        return _LATCHED_CLOSE
    try:
        return _moved_issue(
            gate.gh.get_issue(gate.issue.number), rewrite.source_stage,
        )
    except Exception:
        log.warning(
            "issue=#%d could not be re-read before carrying its exemption "
            "onto a rewritten commit", gate.issue.number, exc_info=True,
        )
    return _UNREADABLE_OWNER


def _moved_issue(fetched: Issue, source_stage: WorkflowLabel | None) -> str:
    """Why this reading is not the open, unpaused issue that stage owns.

    Read off the FETCHED issue rather than the one the tick opened with, which
    is the whole point of taking it: the state, the control labels, and the
    workflow label are three things a human moves while an agent runs, and the
    snapshot in hand is as old as the run that has just finished.
    """
    owner_state = getattr(fetched, "state", "")
    if owner_state != _OPEN:
        return _CLOSED_OWNER.format(state=owner_state or "unreadable")
    controlled = _labels.hard_skip_control_label(fetched)
    if controlled:
        return _CONTROLLED_OWNER.format(control=controlled)
    stage = _labels.workflow_label(fetched)
    if stage != source_stage:
        return _RELABELLED_OWNER.format(frozen=source_stage, read=stage)
    return ""


def _equal_contributions(
    gate: _records._Gate,
    rewrite: _rewrites.LateRewrite,
    identity: _exemption.LateSemanticIdentity,
) -> _Permit:
    """Whether both ends of the rewrite are one contribution, as a permit.

    Fingerprinting the REWRITTEN pair is the question itself, taken once the
    accepted side beside it has proved itself, and equality is what the whole
    permit turns on. It is equality of the contribution rather than of the
    trees: the digest is taken over the diff a reviewer would be handed, so
    the same work over an equivalent base fingerprints alike no matter which
    commit carries it, and anything the rewrite picked up along the way is a
    different contribution that has never been adjudicated.
    """
    accepted = _accepted_contribution(gate, rewrite, identity)
    if accepted.refusal:
        return accepted
    rewritten = _fingerprinted(
        gate, _REWRITTEN, rewrite.to_base_sha, rewrite.to_sha,
    )
    if rewritten.refusal:
        return rewritten
    if accepted.fingerprint != rewritten.fingerprint:
        return _Permit(refusal=_DIFFERENT_CONTRIBUTION.format(
            accepted=accepted.fingerprint, rewritten=rewritten.fingerprint,
        ))
    return rewritten


def _accepted_contribution(
    gate: _records._Gate,
    rewrite: _rewrites.LateRewrite,
    identity: _exemption.LateSemanticIdentity,
) -> _Permit:
    """What the adjudication accepted, as the digest a transfer is held to.

    Fingerprinted over the pair the RECORD names, never over the one the
    caller hands in. The record is the whole account of what a human ruled on
    -- the base the adjudication was measured from, the commit it accepted,
    and the digest between them -- and reading that digest back against some
    other base would leave the base itself unchecked: a hand-edited
    `late_exempt_base_sha` would sit there naming a pair nothing ever compared
    anything to, while a permit was granted on the strength of the record it
    belongs to. Taken over its own pair, the record either proves itself or
    refuses -- and proves along the way that the objects the adjudication
    named are still ones this host can hand back in full, which no comparison
    of stored values could.

    The pair the CALLER claims it rewrote is then held to the same digest,
    because a rewrite is a claim about what it replaced and this owner may not
    take that on trust either.
    """
    accepted = _fingerprinted(
        gate, _ACCEPTED, identity.base_sha, identity.candidate_sha,
    )
    if accepted.refusal:
        return accepted
    if accepted.fingerprint != identity.fingerprint:
        return _Permit(refusal=_UNRECORDED_CONTRIBUTION.format(
            base=identity.base_sha, candidate=identity.candidate_sha,
            recomputed=accepted.fingerprint, recorded=identity.fingerprint,
        ))
    unclaimed = _unclaimed_contribution(gate, rewrite, identity, accepted)
    return _Permit(refusal=unclaimed) if unclaimed else accepted


def _unclaimed_contribution(
    gate: _records._Gate,
    rewrite: _rewrites.LateRewrite,
    identity: _exemption.LateSemanticIdentity,
    accepted: _Permit,
) -> str:
    """Why the pair the caller says it rewrote is not the accepted one, or "".

    The caller names the base it read the pre-rewrite commit over, and that is
    a second, independent reading of the same contribution: the record's base
    is the tip the adjudication froze, the caller's is the fork point the
    rewrite was collapsed onto, and a three-dot range over either resolves to
    the same merge base while the branch has not moved. So the two are checked
    against each other by DIGEST rather than by spelling -- required equal as
    object ids they would disagree the moment the base branch advanced, which
    is every ordinary week.

    Silent where the caller named the record's own base, since re-reading the
    same pair could only answer what it just answered.
    """
    if rewrite.from_base_sha == identity.base_sha:
        return ""
    claimed = _fingerprinted(
        gate, _CLAIMED, rewrite.from_base_sha, rewrite.from_sha,
    )
    if claimed.refusal:
        return claimed.refusal
    if claimed.fingerprint == accepted.fingerprint:
        return ""
    return _UNCLAIMED_CONTRIBUTION.format(
        base=rewrite.from_base_sha, claimed=claimed.fingerprint,
        recorded=identity.base_sha, accepted=accepted.fingerprint,
    )


def _fingerprinted(
    gate: _records._Gate, side: str, base_sha: str, candidate_sha: str,
) -> _Permit:
    """One end of the rewrite as a comparable digest, or why there is none."""
    contribution = _measurement_fingerprint._fingerprint_contribution(
        gate.worktree, base_sha, candidate_sha,
    )
    if not contribution.is_fingerprinted:
        return _Permit(refusal=_UNFINGERPRINTABLE.format(
            side=side, base=base_sha, candidate=candidate_sha,
            failure=contribution.failure,
        ))
    return _Permit(fingerprint=contribution.digest)


def _authorized(
    gate: _records._Gate,
    rewrite: _rewrites.LateRewrite,
    fingerprint: str,
    recorded: str,
) -> bool:
    """Record what licenses this rewrite to publish, durably, before any push.

    The PERMISSION rather than the move. The exemption stays exactly on the
    commit a human ruled on and the identity beside it stays with it, because
    the commit this permission is about is on no remote yet: rotated here, a
    push that never lands would leave a verdict on an object only this host
    has, and every later tick would read the accepted work at HEAD as carrying
    none. The rotation belongs to the write that receipts the landed push,
    where it goes down with the account of what the remote carries or not at
    all -- so what this records is a permission that stands until that write
    spends it.

    What licenses THIS tick's publication is the permit itself, handed back to
    the gate -- so nothing has to be rotated early for the push to be allowed.

    Two things go down together. The authorization is what says the move was
    earned rather than assumed: it names both pairs, the rewrite that produced
    the second, and the publication it was made against, which is what lets
    the receipt spend exactly this permission and a rollback drop exactly it.

    And the DEBT is the second, because the account of what the branch carries
    and the account of where it has still to go may not be split across two
    writes. A rewrite has already replaced the branch's commits with one by
    the time this runs, so a process dying between a record that explains that
    commit and a debt naming the push it is owed comes back to a one-commit
    branch, a remote still on the head it replaced, and nothing saying a push
    is outstanding -- and the next squash finds a single commit, takes the
    nothing-to-squash road, and reports success without measuring or pushing
    anything, so reviewer-approved work reaches the merge button neither
    counted nor on the remote. Carried on this write instead, the
    reconciliation ahead of the next handler finds the debt, republishes the
    commit under the lease the rewrite froze, and settles the transfer with
    it. The verdict that follows this call finds the debt already down for the
    same commit and leaves it exactly as it is.

    Ahead of the push rather than behind it, for the reason every other record
    this gate writes goes down before the effect it is about: a process dying
    in between comes back to an issue that says a push is owed for the commit
    on its branch and what that push is allowed to carry over.

    Answers whether that write landed. A comment GitHub refused records no
    permission, so the caller may not report one either.
    """
    before = dict(gate.state.data)
    log.info(
        "issue=#%d carries the exemption for %s onto %s: the %s rewrite left "
        "the contribution the adjudication accepted (%s) unchanged",
        gate.issue.number, rewrite.from_sha, rewrite.to_sha,
        rewrite.kind, recorded,
    )
    _rewrites.record_rewrite_authorization(gate.state, rewrite, fingerprint)
    _verdict_owner._stages_unmeasured_debt(
        gate, rewrite.to_sha, rewrite.lease,
    )
    return _persisted(gate, before)


def _persisted(gate: _records._Gate, before: dict) -> bool:
    """Make the staged transfer durable, or put the comment back as it was.

    A write GitHub refuses is a transfer that did not happen, and the one
    thing that must not survive it is the belief that it did. Everything above
    is staged in memory on the pinned state the whole tick shares, so a
    refusal left as it stands would hand every owner behind this one an
    exemption on a commit no comment names -- and the first of them to write
    for its own reasons would make that until-then-imaginary move durable.

    So the payload is put back exactly as it was found and the permit is
    refused: the rewritten commit falls through to the ordinary cumulative
    size gate, which is the same answer every other refusal here gives, and
    the tick carries on rather than ending in an exception the gate never
    returned from and the caller could not roll its rewrite back for.

    Restored by content rather than by re-reading GitHub, because the read
    that would supply one is the request that just failed -- and because what
    this owes is exactly the payload the call started from, which it holds.

    A payload the staging did not change is already durable and spends no
    request: that is what a recovery re-asking the permit over the record the
    grant left arrives at, and a write there would cost a request to say what
    the comment already says.
    """
    if gate.state.data == before:
        return True
    try:
        gate.gh.write_pinned_state(gate.issue, gate.state)
    except Exception:
        log.warning(
            "issue=#%d could not record the transfer it granted onto %s; "
            "leaving the exemption where the adjudication put it and "
            "measuring the rewrite as a fresh candidate",
            gate.issue.number, gate.state.get(_exemption.LATE_EXEMPT_SHA),
            exc_info=True,
        )
        gate.state.data.clear()
        gate.state.data.update(before)
        return False
    return True


def _abandoned_authorization(gate: _records._Gate, restored: str) -> bool:
    """Drop the permission a rolled-back rewrite will never spend.

    A force-push the remote refuses is followed by a reset onto the head the
    rewrite found the branch on, so the object the permission was granted FOR
    is on no branch any more -- only the reflog still has it. The exemption
    itself needs no repair, because the grant never moved it: it is the commit
    a human ruled on and has been the whole time. What is left over is the
    permission, and it names a rewritten commit nothing will ever push.

    Left standing it is a claim about this issue's exemption that no later
    write spends and no reader can act on -- and the next rewrite would be
    deciding whether to replace a record describing a push that never
    happened. So it goes with the commit it was about.

    Only an `authorized` record is dropped, and only one this reader can vouch
    for entirely. A `published` one describes a transfer the pull request
    already carries and the exemption has already moved for; a record missing
    or damaged in any field describes a permission nobody can check, and
    dropping it would throw away the only account of how the exemption came to
    name what it names.

    Answers whether it changed anything, so the caller writes the pinned
    comment exactly when there is something in it to make durable.
    """
    authorization = _rewrites.read_rewrite_authorization(gate.state)
    if authorization is None or not _put_back(authorization.rewrite, restored):
        return False
    if authorization.phase != _rewrites.LateRewritePhase.AUTHORIZED:
        return False
    _rewrites.clear_rewrite_authorization(gate.state)
    log.info(
        "issue=#%d dropped the permission a refused rewrite held to carry its "
        "exemption onto %s, which its branch was reset off",
        gate.issue.number, authorization.rewrite.to_sha,
    )
    return True


def _put_back(rewrite: _rewrites.LateRewrite, restored: str) -> bool:
    """Whether this reset landed where the rewrite found the branch.

    Two ends of the record answer it, because which of them the branch was
    standing on beforehand is a fact about the REWRITE rather than about the
    exemption. A squash collapses the accepted commit itself, so the head it
    replaced is the commit the contribution came from. A refresh-time base
    rebase replays whatever the branch had and reads the pre-rebase anchor for
    itself, so what a reset goes back to there is the head the force-push was
    leased against -- which is the accepted commit only while the branch was
    standing exactly on it, and the equality of the two contributions never
    claimed that it was.

    Held to the record's own ends rather than to "anywhere but the rewritten
    commit", which is the fail-closed rule every other reader of this group
    follows: a reset nothing here can tie to the permission in front of it is
    not this rewrite's rollback, and the group is the only account there is of
    how the exemption came to name what it names.
    """
    return restored in (rewrite.from_sha, rewrite.lease)
