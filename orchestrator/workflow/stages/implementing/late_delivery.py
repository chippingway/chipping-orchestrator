# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the pull request this issue records is already standing on the commit.

The window between a push that opened a pull request and a relabel that never
landed, read from the far end. `implementing_published_sha` is the note this
stage leaves naming the commit it pushed, and the tick after a crash reads it
to recognize a branch the remote already carries: past the push a pull request
carries the work and only the relabel is owed, so measuring that commit again
and finding it oversized would route a PUBLISHED branch into an adjudication
with nothing left to hold back.

That is what the note is FOR, and it is all the note can say. It records what
this stage last pushed and nothing about where it went or whether it is still
there, and it is never cleared -- so a branch this issue published rounds ago
carries one for the rest of its life. Answered on the note alone, a candidate
skips the reading, is pushed unmeasured and unleased onto a pull request that
may have moved, merged, closed, or never have been the one this issue records,
a SECOND pull request is opened over the same work, and the issue is handed on
as though the whole thing had been published all along.

So the note is proof of nothing by itself, and what makes it proof is asked of
the REMOTE: the pull request the receipt itself names, open, with its head in
this repository, standing on this exact commit, and open on the branch the seam
behind the answer would push. Every one of those is required and none of them
is widened. Without the receipt, any head a remote happened to agree with would
do. Without the remote reading, a local note over a pull request the branch has
moved off would do. Without the repository, a fork carrying the same ref name
over the same commit would answer for a publication this issue never made. And
without the branch, a record naming a pull request on some other ref would
license a push to a branch nothing has published.

The NUMBER is the receipt's OWN, written with it, and it is never searched for.
`pr_number` is what the relabel writes, which is exactly the write this window
is missing -- a push that landed and a process that died before it -- and the
only other way to name a pull request is a lookup by branch, which answers with
whatever is open on that ref: a REPLACEMENT somebody opened after closing the
original satisfies it, and the relabel, the debt and the receipt behind the
answer are all spent against a publication this stage never made. Absent or
unreadable, the proof refuses.

A call taken PAST a publication asks none of it. That seam freezes an entry of
its own -- the pull request, the stage, and the head it is standing on, each
refused unless it proves itself -- and the entry IS the reading this owner
would take. The implementing seam freezes none, because its push is what opens
a pull request in the first place.

What the answer licenses is BOOKKEEPING and never a second publication, which
is why it is a NUMBER rather than a bare permission. A reading is a moment: the
push behind it is leased against the very commit the proof was about, so a
branch somebody moved in the window rejects it instead of being force-
overwritten, and the relabel is handed that pull request by number, so one
somebody closed in the window holds the tick instead of earning another one
over work the first already carries.

A receipt this build cannot READ at all is the same answer one step earlier.
Every late commit field is read fail-closed, so a hand edit or a half-written
crash comes back as no receipt -- right for a reader asking whether a commit
may publish, and exactly wrong for one asking whether the record is sound. Read
as an absence it publishes, and the push writes a receipt over the damaged
field, destroying what an operator would have repaired it from.

A proof that FAILS is a hold rather than a fall-through, and that is the whole
of what the reading is worth. The commit under it is one this stage's own
record says already went to a remote, so there is no reading of it that makes
republishing safe: measured and found small it would be force-pushed onto a
branch nothing here could confirm and a second pull request opened over it,
which is the exact outcome on every road this proof exists to close. So the
tick parks with the receipt, the pull request number and whatever debt stands
beside them left untouched -- there for the terminal that drains finished work,
and there for the retry once a human has reconciled the record with the remote.

Nothing is outside that hold, and an exemption or an approval naming the same
commit least of all. Each answers whether the candidate needs a fresh READING
and says nothing about where the work went, which is the question that failed
-- and the road that admits a delivered candidate records the commit as a debt
BEFORE it pushes, so a tick dying there leaves an approval with no lease beside
it. Waved past on one, the retry publishes with nothing to lease against and
reuses whatever pull request a branch lookup finds, which is the pair of
outcomes this proof exists to close.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from orchestrator.config import settings as config
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_overflow as _overflow,
    late_park_notices as _late_park_notices,
    late_publication_state as _late_publication_state,
    late_receipt_damage as _late_receipt_damage,
    late_records as _records,
)

log = logging.getLogger("orchestrator.workflow")


# Why the publication a receipt names could not be shown, spelled as the park
# comment reads it. Each is a different thing for an operator to reconcile.
_DAMAGED_RECEIPT = (
    "`{field}` is missing or is not a value this build can read"
)

_UNSCOPED_LEASE = (
    "the receipt names `{lease}` as the head its push replaced, and the call "
    "this candidate reached froze no publication for that to be about"
)

_UNREADABLE_PULL_REQUEST = (
    "pull request #{number} could not be read from this host"
)

_SETTLED_PULL_REQUEST = (
    "pull request #{number} is {state} rather than open"
)

_FOREIGN_REPOSITORY = (
    "pull request #{number} has its head in `{read}` rather than in "
    "`{expected}`, so it is not a publication this issue could have made"
)

_FOREIGN_BRANCH = (
    "pull request #{number} is open on `{read}` rather than on `{expected}`, "
    "which is the branch this publication would push"
)

_MOVED_HEAD = (
    "pull request #{number} stands at `{read}` rather than on that commit"
)


# What each refusal is logged and reported as. They are two different things
# for an operator to hold: one is a record the remote disagrees with, and the
# other is a record this build cannot read at all.
_UNPROVABLE_RECEIPT = "the publication its own receipt names cannot be shown"

_DAMAGED_GROUP = "the publication receipt group does not read back whole"


_UNPROVABLE_RECEIPT_PARK = (
    "{mentions} this issue's pinned comment records that this stage has "
    "already pushed, and this tick cannot show the publication that receipt "
    "is about: {refusal}. The candidate in the worktree is `{candidate}`. "
    "That note is never cleared, so measuring "
    "the commit again and publishing it would force-push a branch nothing "
    "here could confirm and open a second pull request over work the first "
    "may already carry. Nothing was pushed and nothing was discarded, and the "
    "receipt, the recorded pull request and whatever push is still owed are "
    "all left exactly as they stand. {remedy}"
)


_DAMAGED_RECEIPT_PARK = (
    "{mentions} this issue's pinned comment records that this stage has "
    "already pushed, and the receipt group that says so does not read back "
    "whole: {refusal}. The three members are one write -- the commit that "
    "reached the remote, the head it replaced, and the pull request it went "
    "onto -- so a group missing one of them, or carrying a value this build "
    "cannot read, is a record no tick here produced and nothing may act on. "
    "Nothing was measured, pushed or discarded, and the receipt, the recorded "
    "pull request and whatever push is still owed are all left exactly as "
    "they stand. {remedy}"
)


# What an operator does about it, which is not the same sentence for every
# refusal above. A publication nothing could SHOW is a disagreement between
# the record and the remote, and a fresh commit is a fresh question that this
# hold has nothing to say about -- the receipt names some other object id by
# then, so the road is not taken at all.
_MEASURED_AFRESH = (
    "Reconcile the pinned comment with what is on the remote, or commit again "
    "so the candidate is measured afresh."
)


# A receipt this build cannot READ is the opposite, and telling an operator to
# commit again would be advice that cannot work: the field is refused before
# any candidate is compared to it, so every later commit earns this same hold.
# The field itself is the only thing that ends it.
_REPAIR_THE_RECEIPT = (
    "Committing again will not clear this one: the group is read before any "
    "candidate is compared against it, so a fresh commit earns the same hold. "
    "Repair all three members in the pinned comment -- "
    "`implementing_published_sha`, the commit this stage last pushed, "
    "`implementing_published_lease`, the head that push replaced, and "
    "`implementing_published_pr`, the pull request it went onto -- or remove "
    "all three, if nothing was ever published from this branch, and the next "
    "tick reads the record again."
)


@dataclass(frozen=True)
class _Delivered:
    """The publication a receipt names, or the reason none could be shown.

    Both together because a caller needs both: the NUMBER is what the
    bookkeeping behind a proved publication is bound to, and the REFUSAL is
    what the park over an unprovable one has to tell a human -- a pull request
    somebody closed, one the branch moved off, and one open on another ref are
    three different things to reconcile.

    Empty on both counts for a call this question is not about at all: one
    that froze a publication of its own, and one whose receipt names some
    other commit.
    """

    number: int = 0
    refusal: str = ""

    @property
    def is_proved(self) -> bool:
        """Whether a pull request was shown standing on the commit."""
        return bool(self.number)


def _delivered_before_the_relabel(
    gate: _late_gate_models._Gate, candidate_sha: str,
) -> _Delivered:
    """The pull request already standing on this commit, or why none is.

    Nothing froze a publication here, so every half of the proof is taken
    together: the RECEIPT says this stage pushed the commit, which is what
    tells work this issue delivered from a tip somebody else moved the branch
    to; the REMOTE says the pull request is standing on it still; and the
    BRANCH that pull request is open on is the one the seam behind this would
    push.

    That last one is what makes "the push moves nothing" true rather than
    merely likely. The seam resolves its own branch from the record and pushes
    THAT, then reuses whatever open pull request is on it -- so a record naming
    a pull request on some other branch would have this answer license a push
    to a branch nobody has published and a second pull request opened over the
    same work. Verified equal, the push has nothing to send and the lookup
    behind it finds the very pull request this reading proved, which is the
    difference between finishing bookkeeping and publishing again.

    Taken ONCE per gate call and handed to each road that rests on it, rather
    than re-asked: a second reading is a second answer, and the roads it feeds
    have already decided to publish by the time one could disagree. It costs no
    request unless the receipt names the candidate in hand.

    Empty for a call that froze a publication, which has its own proof and
    spends no request on this one, and for a receipt naming some other commit
    -- neither is a question about the candidate in hand.

    The LEASE is the last half and is asked of the RECORD rather than of the
    remote, because at this seam there is nothing to ask. A lease names the
    head a push REPLACED, and it is written only where the call that made that
    push froze one -- this call froze none, so the only receipt this window is
    about is the one an initial publication left, and that one records no
    lease at all. A receipt carrying one was written by some other call
    entirely, and its commit matching the candidate is a coincidence this
    proof may not spend: waved through, the candidate skips the reading and
    the fresh receipt behind it CLEARS the lease, which is the one field
    saying which attempt the record was really about.

    A REFUSAL is the answer everywhere else the proof does not hold: a receipt
    scoped to a publication this call never froze, a pull request this host
    could not read, one that has merged or been closed, one in another
    repository, one standing on another commit, and one open on another
    branch. Each names itself, because what the caller does with one is park a
    human over it and they are different things to reconcile.

    Which pull request is read off the RECEIPT GROUP rather than off
    `pr_number`, and never searched for. `pr_number` is the relabel's write,
    which is the very one the window this proof exists for is missing -- a
    push that landed and a process that died before it -- so the identity goes
    down with the receipt instead, where it covers exactly that window. The
    only other way to name one is a lookup by branch, and that answers with
    whatever is open on the ref, so a REPLACEMENT somebody opened after
    closing the original would be taken for the publication this stage made.

    A group this build cannot read WHOLE never reaches here, a receipt naming
    no pull request among them: `_holds_a_damaged_receipt` refuses both at the
    gate's own door, ahead of every road that could write over them, because
    the comparisons here cannot see one -- every late field is read
    fail-closed, so a hand edit comes back as no receipt at all.
    """
    if gate.entry is not None:
        return _Delivered()
    if _late_publication_state._published_commit(gate.state) != candidate_sha:
        return _Delivered()
    lease = _late_publication_state._published_lease(gate.state)
    if lease:
        return _Delivered(refusal=_UNSCOPED_LEASE.format(lease=lease))
    return _proved_against(
        gate, _late_publication_state._published_pull_request(gate.state), candidate_sha,
    )


def _proved_against(
    gate: _late_gate_models._Gate, number: int, candidate_sha: str,
) -> _Delivered:
    """Hold one numbered pull request to what the push behind it would do.

    Every term is compared against what the SEAM resolves rather than against
    anything the reading supplies for itself, since the question is whether its
    push would move anything: the repository it pushes to is this issue's own,
    the branch it would push is the one the record names, and the commit it
    would send is the candidate in hand.

    The REPOSITORY is asked first, because it is what makes the two below
    identify anything. A fork carries this repository's ref names over this
    repository's commits, so a pull request from one agrees on both while
    pointing at a branch no push of this issue's has ever touched -- and
    admitted, the seam would call the work delivered, skip the reading, and
    hand a reviewer somebody else's publication.
    """
    reading = _overflow._PublicationReading.taken(gate.gh, number)
    if reading.refusal is not None:
        return _Delivered(
            refusal=_UNREADABLE_PULL_REQUEST.format(number=number),
        )
    if reading.state != _overflow._OPEN:
        return _Delivered(refusal=_SETTLED_PULL_REQUEST.format(
            number=number, state=reading.state,
        ))
    if not gate.gh.is_own_repository(reading.head_repo):
        return _Delivered(refusal=_FOREIGN_REPOSITORY.format(
            number=number, read=reading.head_repo, expected=gate.gh.repo_slug,
        ))
    return _standing_where_the_push_lands(
        gate, reading, number, candidate_sha,
    )


def _standing_where_the_push_lands(
    gate: _late_gate_models._Gate,
    reading: _overflow._PublicationReading,
    number: int,
    candidate_sha: str,
) -> _Delivered:
    """Hold a live pull request of this repository's to the push's own terms.

    The two facts the SEAM decides rather than the remote: the branch it
    resolves from the record and pushes, and the commit it would send. Equal on
    both, the push has nothing left to do and the lookup behind it finds this
    very pull request; different on either, it would publish somewhere the
    proof was never taken.
    """
    branch = _naming._resolve_branch_name(
        gate.state, gate.spec, gate.issue.number,
    )
    if reading.head_branch != branch:
        return _Delivered(refusal=_FOREIGN_BRANCH.format(
            number=number, read=reading.head_branch, expected=branch,
        ))
    observed = _payloads.as_hex(reading.head, _formats.COMMIT_LENGTHS)
    if observed != candidate_sha:
        return _Delivered(refusal=_MOVED_HEAD.format(
            number=number, read=observed or reading.head,
        ))
    log.info(
        "issue=#%d records pull request #%d already standing on %s; what is "
        "left for it is the bookkeeping behind a publication that happened",
        gate.issue.number, number, candidate_sha,
    )
    return _Delivered(number=number)


def _receipt_answers_alone(
    gate: _late_gate_models._Gate, delivered: _Delivered, candidate_sha: str,
) -> bool:
    """Whether a local receipt may vouch for this commit with nothing beside it.

    It never may, whatever the record beside it says. The receipt is a local
    note and it is never cleared, so a branch pushed rounds ago carries one
    still -- and answering on the note alone republishes, unmeasured and with
    no frozen head to lease against, onto a pull request that may have moved,
    merged, closed, or never have been the one this issue records.

    A call that DID freeze a publication asks the same question of what it
    FROZE rather than of the remote: the entry is a reading of the very pull
    request the record names, so a second one would only be a second chance to
    disagree with it. Both of its terms are required, because the frozen head
    alone is the same hole the remote reading exists to close one seam over. A
    pull request standing on the candidate says the work is THERE; it says
    nothing about how it got there or which publication this issue's own push
    went onto. So the number the receipt names has to be the number this call
    froze -- and a receipt naming another one is an earlier publication of
    this issue's, a replacement somebody opened after closing the original, or
    a record a hand edit pointed somewhere else. Each of those would have the
    relabel, the debt and the receipt spent against a publication this stage
    never made.

    A receipt naming NO pull request answers False there as it does at the
    other seam. There is no second place to look that is not a search, and a
    search by branch answers with whatever is open on the ref -- so the
    candidate goes back through the ordinary reading, which is the safe road:
    measured, then pushed leased against the head this call froze.

    The frozen HEAD is required with the number and is the half it cannot
    supply: a pull request the record names and this issue has published onto
    before, standing on some commit that is not the candidate, is a
    publication that is over. Read as one still standing, the tick would hand
    a reviewer a head the pull request does not have.
    """
    if gate.entry is None:
        return delivered.is_proved
    entry = gate.entry
    if entry.published_sha != candidate_sha:
        return False
    return bool(entry.pr_number) and (
        _late_publication_state._published_pull_request(gate.state) == entry.pr_number
    )


def _holds_a_damaged_receipt(gate: _late_gate_models._Gate) -> bool:
    """Park a record whose publication receipt group cannot be read whole.

    Asked at the gate's DOOR rather than beside the candidate question,
    because the roads that would write over the damage do not all reach that
    question. An install with `DECOMPOSE=off` and no caller-named candidate
    answers before it; the accepted settlement reaches the transport by
    another door entirely and is refused by its own reconciliation. What every
    one of them ends in is the write that puts a fresh group down -- and a
    fresh group over a damaged one destroys the only evidence an operator had.

    Asked of the RECORD and of no candidate, which is why it stands here at
    all: the group is what claims a publication, and a group that cannot say
    which publication that was is unusable whatever commit is in the worktree.
    So a fresh commit is no road out either, and the park says so rather than
    offering an escape that would loop.

    The park writes nothing else. The receipt, the recorded pull request, the
    approval and any debt beside them stand exactly as they were -- there for
    the terminal that drains finished work, and there for the retry once a
    human has repaired the group.

    Silent for every record that reads back whole, which is every ordinary
    tick, and for an issue that never published at all.
    """
    damaged = _late_receipt_damage._damaged_receipt(gate.state)
    if not damaged:
        return False
    refusal = _DAMAGED_RECEIPT.format(field=damaged)
    log.error(
        "issue=#%d carries a publication receipt group this build cannot "
        "read whole (%s); refusing to act on a record that claims a "
        "publication it cannot name",
        gate.issue.number, refusal,
    )
    return _late_park_notices._parked(
        gate,
        _records._reportable(
            gate, _late_state.read_late_generation(gate.state),
        ),
        _DAMAGED_GROUP,
        _DAMAGED_RECEIPT_PARK.format(
            mentions=config.HITL_MENTIONS,
            refusal=refusal,
            remedy=_REPAIR_THE_RECEIPT,
        ),
    )


def _holds_an_unprovable_receipt(
    gate: _late_gate_models._Gate, candidate_sha: str, delivered: _Delivered,
) -> bool:
    """Park a candidate whose own receipt names a publication nothing can show.

    Fail-CLOSED, and the alternative is what makes it so. This commit is one
    the record says this stage already pushed, so measuring it is not a
    neutral fallback: a count under the ceiling publishes it, which force-
    pushes a branch nothing here could confirm and opens a second pull request
    over work the first may already carry. There is no reading of an
    unprovable publication that makes republishing onto it safe.

    Parked rather than held silently, because none of the refusals clears
    itself: a number the record never had, one this host cannot read, a pull
    request somebody settled, one in another repository, and one open
    somewhere else are each a disagreement between the pinned comment and the
    remote that a person resolves. The park writes nothing else -- the
    receipt, the recorded pull request, and any debt beside them stand exactly
    as they were, for the terminal that drains finished work or for the retry
    behind a repair.

    What it TELLS that person differs by which refusal it was, and the answer
    travels with the refusal for that reason. Every publication nothing could
    show is one a fresh commit moves past: the receipt names some other object
    id by then, so this road is not taken at all and the candidate is measured
    like any other. A receipt nothing could READ is the one that does not
    move, since it is refused before any candidate is compared against it --
    so the park says to repair the field rather than offering an escape that
    would loop.

    NOTHING is outside it, and an exemption or an approval naming the same
    commit least of all. Each says the candidate needs no fresh READING --
    that a human adjudicated the change, or that this gate already counted it
    -- and neither says a word about where the work went. The publication
    proof is the other question, and it is the one that has failed.

    Carving those two out is what a proven-delivery attempt that CRASHES
    turns into an unleased republication. The road that admits a delivered
    candidate makes the commit durable as a debt before it pushes, so a tick
    dying in that window leaves an approval naming it with no lease beside it
    -- the head it would have been pinned to was the pull request the proof
    named, and that proof is exactly what the retry can no longer take. Waved
    past on the approval, the next poll publishes with nothing to lease
    against and reuses whatever pull request a branch lookup finds: a blind
    force-push over a tip somebody moved, and a second pull request opened
    over work the first may already carry. An exemption is the same hole one
    field over, and the commonest one on the road this proof exists for.

    So the park holds every one of them, and holds exactly what each needs to
    be paid once a human has reconciled the record: the exemption, the
    approval, the receipt and the recorded number all stand untouched, and the
    publication those decisions are owed happens on the poll after the repair
    rather than blind on this one.

    Silent for every candidate no receipt names, which is every ordinary tick,
    and for a call that froze a publication of its own.
    """
    if not delivered.refusal:
        return False
    log.error(
        "issue=#%d records a receipt for %s and cannot show the publication "
        "it names (%s); refusing to measure and republish a commit this "
        "stage has already pushed",
        gate.issue.number, candidate_sha, delivered.refusal,
    )
    return _late_park_notices._parked(
        gate,
        _records._reportable(
            gate, _late_state.read_late_generation(gate.state),
        ),
        _UNPROVABLE_RECEIPT,
        _UNPROVABLE_RECEIPT_PARK.format(
            mentions=config.HITL_MENTIONS,
            candidate=candidate_sha,
            refusal=delivered.refusal,
            remedy=_MEASURED_AFRESH,
        ),
    )
