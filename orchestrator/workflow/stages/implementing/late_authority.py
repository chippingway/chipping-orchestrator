# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the human behind an adjudicated commit is one this issue can show.

The size gate lets a handful of commits publish without a reading, and one of
them is the commit an adjudication accepted. That is the exemption, and on its
own it is a claim about a DECISION rather than about a decider: it says this
change was ruled one coherent whole, and nothing in it says who agreed to put
an oversized change on a pull request. An adjudicator is an agent, and an
agent proposing to publish past the ceiling is the thing the ceiling is there
for -- so the exemption is only ever half of a bypass. The other half is an
operator's own authorization, recorded on the `overrides` owner from a comment
somebody wrote at an address anybody can go and read.

This owner is where the two are asked together, and the answer it gives is the
one the gate acts on: a commit both of them name publishes without a reading,
and a commit only the exemption names is measured like any other candidate.
Both halves are held to naming ONE commit, which is the invalidation rule the
exemption already had and the one this adds nothing to -- work committed on
top of an accepted commit is work nobody adjudicated and nobody authorized,
and it is measured as the fresh candidate it is.

The publication DEBT such a commit leaves is the same question one field over,
and it is asked off that debt's own recorded basis rather than inferred from
the records around it. The settlement writes the exemption and the approval in
one breath, so its approval is that adjudication wearing another field; every
other approval is this gate's own answer brought back by a crash, and no human
was ever owed a decision about one. An approval an older binary wrote says
nothing about its grounds, and there the exemption is the only evidence left.

What that leaves is the record an older binary wrote. Before an authorization
was required, a `single` verdict recorded an exemption by itself, so a live
issue can carry an exemption with no gesture behind it. Nothing here deletes
one, migrates one, or reads one as consent. A candidate an unauthorized
exemption names goes to the ordinary cumulative gate, and the reading decides:
at or below the ceiling it publishes exactly as any small candidate does --
the boundary is inclusive, so a change measuring exactly `MAX_ADDED_LINES`
goes out -- and past the ceiling it parks, which `late_consent` beside this
owns along with the command that ends one.

One thing is never held back by any of it. A commit the pull request this call
FROZE is already standing on publishes: a push of a commit the remote holds
moves nothing, so what is left is the bookkeeping behind it -- the relabel, the
receipt, the debt -- and holding that back would strand a published branch
under a stage nobody is going to advance. The seam before the initial
publication has no frozen entry and asks the same question of its receipt
instead, which `late_delivery` owns.

And nothing here rewrites work that is over: a merged or closed issue is
finalized before any handler reaches this gate, so the compatibility is asked
at publication time and never as a pass over records nobody is publishing
from.

The rewrite TRANSFER asks this owner's first question before it grants a
permit, since a transfer is the one road past the reading that no record names
in advance: moving an exemption nothing authorizes would hand the rewritten
commit a permission the accepted one never had. What DOES follow the exemption
is the authorization: the write that rotates one carries the other onto the
same pair, so a squash of an authorized candidate stays authorized and a
squash of a legacy one gains nothing it did not have.
"""
from __future__ import annotations

import logging

from orchestrator.git.measurement import fingerprint as _fingerprint
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    overrides as _overrides,
)
from orchestrator.workflow.stages.implementing import (
    late_parks as _parks,
    late_records as _records,
)

log = logging.getLogger("orchestrator.workflow")

# Why a commit an unauthorized exemption names still publishes, spelled as the
# gate's own log line reads it: the pull request is standing on it already, so
# there is nothing for a push to add and nothing for a hold to hold back.
_ON_ITS_PULL_REQUEST = "is the commit its pull request already stands on"


def _publishes_on_an_exemption(
    gate: _records._Gate, candidate_sha: str,
) -> bool:
    """Whether an adjudication AND an operator both vouch for this commit.

    The claim the gate skips the reading on, and it is deliberately two
    records rather than one. The exemption says the change was ruled one
    coherent whole, which is an agent's answer; the authorization says a human
    who read it agreed to publish past the ceiling, which is the only thing
    that may ever waive a guard against agents publishing past the ceiling.
    Either alone is half a bypass, and half a bypass is measured.

    Both are exact-SHA claims and neither is widened here. A commit made on
    top of an accepted one carries work nobody ruled on and nobody read, so it
    matches neither and is measured as the fresh candidate it is.

    And neither is BELIEVED on its own shape. Every term of an authorization
    but one is the pinned comment agreeing with itself, which a hand edit and
    a half-written crash can both arrange: a group naming this candidate over
    a base nobody froze, with a digest of nothing and a comment id somebody
    typed, reads back whole and licenses an unmeasured push of work no human
    ever saw. The digest is the one term the OBJECTS answer, so it is re-taken
    here between the pair the record names and held to what the record says --
    the same proof the settlement that wrote it took, asked again because this
    call happens on a later poll, on a later process, and on a host that never
    held the content between that pair.

    A reading this host cannot take refuses on the same footing as one that
    disagrees, and what that costs is the measurement the gate would have
    taken anyway.
    """
    if not _exemption_reading.is_exempt(gate.state, candidate_sha):
        return False
    if not _overrides.is_authorized(gate.state, candidate_sha):
        return False
    return _contributes_what_was_authorized(gate)


def _contributes_what_was_authorized(gate: _records._Gate) -> bool:
    """Whether the pair a human authorized still contributes what they read.

    Taken over the pair the RECORD names rather than over anything the
    checkout stands on or a base read now: the worktree is writable for the
    whole of an adjudication and for every tick after it, so its head says
    nothing about what was authorized, and a base read now names a change
    nobody decided about.

    Silent about every way it can fail, because they are one answer. A digest
    that disagrees is a record somebody edited or one taken under rules this
    build reads differently; a reading this host could not take is a store an
    operator repairs rather than a decision anybody made. Neither is grounds
    for a bypass, and both cost the candidate a measurement rather than the
    decision behind it -- the authorization stays exactly where it is, and a
    host that comes back publishes what it says without asking anyone twice.
    """
    authorized = _overrides.read_publication_override(gate.state).publication
    contribution = _fingerprint._fingerprint_contribution(
        gate.worktree, authorized.base_sha, authorized.candidate_sha,
    )
    if contribution.digest == authorized.fingerprint:
        return True
    log.warning(
        "issue=#%d authorizes candidate %s over a contribution this host "
        "does not read back as the one it was authorized on (%s); measuring "
        "it rather than publishing a bypass nothing vouches for",
        gate.issue.number, authorized.candidate_sha,
        contribution.failure or "the digest disagrees",
    )
    return False


def _unauthorized_exemption(
    gate: _records._Gate, candidate_sha: str,
) -> bool:
    """Whether this commit is exempt on a record no human stands behind.

    True for the record an older binary wrote, where a `single` verdict
    recorded an exemption on its own, and true for one whose authorization
    this build cannot read back whole -- a member missing, a field
    hand-edited, a digest taken under a scheme this build does not compute, a
    reading at or under its own ceiling, and a recorded pair that no longer
    contributes the change the digest was taken over. Those are one answer on
    purpose: a bypass nobody can show the terms of is worth exactly what a
    bypass nobody granted is worth, and the cost of both is the measurement
    the gate would have taken anyway.

    False for every candidate no exemption names, which is the ordinary one.
    Nothing here is a claim about a commit this issue never adjudicated.
    """
    if not _exemption_reading.is_exempt(gate.state, candidate_sha):
        return False
    return not _publishes_on_an_exemption(gate, candidate_sha)


def _already_on_its_pull_request(
    gate: _records._Gate, candidate_sha: str,
) -> str:
    """Why an adjudicated commit publishes untouched, or "" where it may not.

    The one thing an unauthorized exemption still buys, and it buys it from
    the REMOTE rather than from the record: a pull request this call itself
    froze, standing on this exact commit, has already received the work. A
    push of a commit the remote holds moves nothing, so what is being decided
    here is not whether unmeasured bulk may reach a pull request -- it is
    there -- but whether the bookkeeping behind it may finish. Held back, the
    receipt is never written, the debt is never paid, and the relabel never
    lands, which leaves published work under a stage no later tick will
    advance.

    Scoped to a commit an exemption names, and that is not decoration. A tip
    that merely happens to be the candidate in hand says nothing about how it
    got there, while an exemption is this workflow's own record that the
    change was adjudicated -- so what this recognizes is adjudicated work
    already delivered rather than any head a remote happens to agree with.

    Read off the entry and nothing else, because the entry IS the reading: the
    pull request the record names, the stage it was taken from, and the head
    it was standing on, each frozen before any effect and each refused unless
    it proved itself. An entry too damaged to name a publication is not
    evidence a pull request stands anywhere and answers nothing.

    Empty for the seam that froze none, which is the initial publication.
    There the push is what OPENS a pull request, so what says the work already
    went out is this stage's own receipt held to the remote -- the proof
    `late_delivery` takes, which reaches the same unmeasured road one answer
    further down.

    What the answer licenses is BOOKKEEPING and never a second publication:
    the push behind it is leased against this very commit and the relabel is
    handed the pull request the entry named.
    """
    if gate.entry is None:
        return ""
    if not _exemption_reading.is_exempt(gate.state, candidate_sha):
        return ""
    standing = (
        gate.entry.is_frozen and gate.entry.published_sha == candidate_sha
    )
    return _ON_ITS_PULL_REQUEST if standing else ""


def _unauthorized_debt(gate: _records._Gate, candidate_sha: str) -> bool:
    """Whether the push this commit is owed rests on an unauthorized exemption.

    Asked of the approval's own recorded basis rather than of the records
    standing around it, because provenance is a thing only the owner that
    granted an approval knows. The settlement writes the exemption and the
    debt in one breath, so its approval is that adjudication wearing another
    field and is worth exactly what the exemption is worth; every other
    approval on this issue is the gate's own answer brought back by a crash,
    and no human was ever owed a decision about one.

    Inferred from the exemption alone it is wrong in both directions, and both
    are reachable. A candidate the gate measured at or below the ceiling on an
    issue that still carries an older binary's exemption earns a genuine gate
    approval -- refusing it would re-judge a settled reading against a base
    that has moved since, which is the one thing the approval bypass exists to
    prevent. And a settlement's debt whose exemption somebody hand-edited
    would read as the gate's own and publish unmeasured, which is the one
    thing this rule exists to prevent.

    An authorization covering the commit ends the question whichever way the
    basis reads -- and it is the whole authorization that ends it, proved
    against the objects rather than read off the record, since a group naming
    this candidate over terms nobody froze is exactly the hand edit a bypass
    turns on.

    Two bases answer yes, and they are the two an operator's gesture is behind
    -- the settlement's own debt, and the debt a candidate past the ceiling
    earns when a human authorizes it at the gate. The second is the crash
    window this would otherwise leave open: the count behind such an approval
    really was this gate's, so recording it as an ordinary reading would let a
    record damaged between the approval and the push publish an oversized
    change nothing could show the grounds for.

    A record whose basis this build cannot READ is the sharpest of them, and
    it is the one shape a single hand edit reaches: the field the fallback
    turns on, touched, and the approval beside it reads as the gate's own. It
    is refused outright rather than handed to the exemption, because what it
    says is that the record claims grounds and cannot name them -- and grounds
    nobody can show are worth what grounds nobody granted are worth.

    A record with NO basis on it is the opposite record and earns the
    compatibility: an approval an older binary wrote, where the exemption is
    the only evidence there ever was -- so it is read, and read
    conservatively. A commit that exemption names is the adjudication's debt.
    So is a comment that CLAIMS an exemption and cannot say which commit it is
    about: a truncated or hand-edited field is not the same thing as an issue
    that never entered an adjudication, and reading the two alike is how a
    settlement's debt with a damaged exemption beside it publishes unmeasured
    -- the shape a hand edit reaches by touching the one field the bypass
    would otherwise have turned on. An issue carrying no exemption field at
    all is that other thing, and its approval is the gate's own.
    """
    basis = _parks._approved_basis(gate.state)
    if basis:
        return (
            basis in _parks.AUTHORIZED_BASES
            and not _publishes_on_an_exemption(gate, candidate_sha)
        )
    if _parks._unreadable_basis(gate.state):
        return not _publishes_on_an_exemption(gate, candidate_sha)
    if _exemption_reading.is_exempt(gate.state, candidate_sha):
        return not _publishes_on_an_exemption(gate, candidate_sha)
    # Presence and truth asked together, because the answer is the gap between
    # them. `read_exemption` is fail-closed, so a truncated or hand-edited
    # field comes back as no exemption -- right for a caller deciding whether
    # a commit may publish, and wrong for one deciding whose DECISION a debt
    # is. An issue that never entered an adjudication carries no field; one
    # whose field cannot be read carries the claim that an adjudication
    # happened and no way to say which commit it was about.
    if not gate.state.carries(_exemption_reading.LATE_EXEMPT_SHA):
        return False
    return _exemption_reading.read_exemption(gate.state) is None
