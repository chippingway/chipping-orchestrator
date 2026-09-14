# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Rewrite authorization claims, whole-record reads, and pending transfer proofs.

An unreadable claim cannot be overwritten as though nothing was recorded.
An authorized transfer remains outstanding until publication rotates its
exemption; a published transfer keeps its reporting proof until the caller
receipts it. Every read checks the phase-dependent exempt end.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    payloads as _payloads,
    rewrite_fields as _rewrite_fields,
    rewrite_values as _rewrite_values,
)


def carries_rewrite_authorization(state: PinnedState) -> bool:
    """Whether this comment carries any part of an authorization at all.

    Presence rather than truth, and presence of ANY member rather than of all
    of them, because what this answers is whether the comment is CLAIMING a
    transfer -- which a record a crash left half written, or one a hand edit
    damaged, claims just as loudly as a whole one. A reader that asked the
    fail-closed reader instead would read a damaged claim as no claim, which
    is the one reading that lets a repair overwrite evidence nobody checked.

    The key being THERE is the whole test, rather than the value under it
    being something. A pinned comment is JSON, so a field can be present and
    `null` -- a hand edit, or an older binary writing a value this one reads
    as nothing -- and a group carrying one member spelled that way is exactly
    the minimal damaged claim this exists to catch. Asked for a value instead,
    it would answer "no group at all" and let the write past.
    """
    return any(key in state.data for key in _rewrite_fields._AUTHORIZATION_KEYS)


def claims_the_exemption(state: PinnedState) -> bool:
    """Whether a group standing here claims the commit currently exempt.

    What a WRITER has to ask before it replaces one. An authorization is
    evidence for the exemption beside it, so overwriting a group this build
    could not read would throw away the only account of how the exemption came
    to name what it names -- and a transfer that did so would be granting
    itself the right to repair a record nobody checked.

    A group whose new commit is readable and is NOT the exempt one is the
    exception, and it is not a claim about anything a transfer is doing: the
    exemption has moved on since, which drops the identity and leaves this
    group describing a commit nothing exempts. Left as a claim it would refuse
    every transfer this issue could ever earn again.

    Anything else counts, the missing and the damaged `to_sha` included. A
    record that cannot name its own new commit has not been shown to be about
    some other one, and "not shown to be stale" is the only reading a writer
    may act on here.
    """
    if not carries_rewrite_authorization(state):
        return False
    bound = _rewrite_fields._bound_end(state)
    if bound is None:
        return True
    return bound == _exemption_reading.read_exemption(state)


def outstanding_permission(state: PinnedState) -> bool:
    """Whether a group standing here says a push is still owed.

    The one question a caller may ask of a record it is not going to act on,
    and the answer is deliberately asymmetric. A permission is recognized as
    SPENT only from a record this build can vouch for entirely -- every field
    at its shape, the phase-bound end the commit the exemption names, and that
    phase `published` -- which is exactly what the write that spends one
    leaves, since it moves the exemption and the phase together. Read off the
    raw phase instead, a group carrying
    nothing else this build understands would announce itself as finished, and
    the approval standing beside it would be spent on an object id with
    neither the permit nor a reading behind it.

    Everything else that carries a group is a claim: a record missing a
    member, one bound to a commit this issue does not exempt, and one still at
    `authorized`. None of those has been shown to be over, and "not shown to
    be over" is the only reading a caller deciding whether to skip a
    measurement may act on.
    """
    if not carries_rewrite_authorization(state):
        return False
    authorization = read_rewrite_authorization(state)
    if authorization is None:
        return True
    return authorization.phase == _rewrite_values.LateRewritePhase.AUTHORIZED


def read_rewrite_authorization(
    state: PinnedState,
) -> _rewrite_values.LateRewriteAuthorization | None:
    """Return the transfer this issue's exemption was granted by, or None.

    None wherever the record cannot vouch for itself, which is every way it
    can fail to: a field that is missing, a group where only some of them are
    there, a value that is not the shape its field takes, a kind or a phase
    this build cannot account for, a digest taken under a scheme it does not
    compute, a stage no publication is entered from, and an end the phase
    binds to that is not the commit the exemption currently names -- the
    accepted one while the transfer stands at `authorized`, the rewritten one
    once the receipt has moved it.

    Each of those is a record nothing may act on, and what acting on it would
    do is MOVE a human's verdict: onto the rewritten commit where the push it
    licensed has landed, and back off it where a rollback abandoned one.
    Either way, a record whose ends nobody can name would move that verdict
    onto whatever the damaged field happened to say.
    """
    recorded = {
        key: _payloads.as_hex(state.get(key), lengths)
        for key, lengths in _rewrite_fields._HEX_SHAPES.items()
    }
    if not all(recorded.values()):
        return None
    if _rewrite_fields._bound_end(state) != _exemption_reading.read_exemption(state):
        return None
    bounded = _rewrite_fields._bounded_terms(state)
    if bounded is None:
        return None
    return _rewrite_values.LateRewriteAuthorization(
        rewrite=_rewrite_values.LateRewrite(
            kind=bounded["kind"],
            from_sha=recorded[_rewrite_fields.LATE_REWRITE_FROM_SHA],
            from_base_sha=recorded[_rewrite_fields.LATE_REWRITE_FROM_BASE_SHA],
            to_sha=recorded[_rewrite_fields.LATE_REWRITE_TO_SHA],
            to_base_sha=recorded[_rewrite_fields.LATE_REWRITE_TO_BASE_SHA],
            pr_number=bounded["pr_number"],
            source_stage=bounded["source_stage"],
            lease=recorded[_rewrite_fields.LATE_REWRITE_LEASE],
        ),
        phase=bounded["phase"],
        fingerprint=recorded[_rewrite_fields.LATE_REWRITE_FINGERPRINT],
        fingerprint_format=bounded["fingerprint_format"],
    )


def unreported_transfer(state: PinnedState) -> _rewrite_values.LateRewriteProof | None:
    """The proof a settled transfer still owes the sinks a record of, or None.

    A transfer is settled by the write that receipts its push, and the record
    of it goes to the sinks behind that write -- so a process lost in between
    leaves a verdict that moved and nothing anywhere saying so. What cannot be
    re-derived later is which reading PROVED the push landed, since the
    receipt looks identical either way, so the proof is kept on the comment
    until the record is out and dropped by the write that follows it.

    None wherever there is nothing owed: a comment carrying no proof, one
    whose transfer this build cannot read back whole, one still outstanding,
    and one whose proof is not a reading this build knows. Each of those is a
    record nothing may be reported from, which is the same answer every other
    reader in this domain gives evidence it cannot check.

    Answering None is not the same as saying the comment is sound, and the
    caller that has to know the difference asks `stranded_transfer_proof`
    beside this.
    """
    proof = _payloads.as_member(_rewrite_values.LateRewriteProof, state.get(_rewrite_fields.LATE_REWRITE_PROOF))
    if proof is None:
        return None
    authorization = read_rewrite_authorization(state)
    if authorization is None:
        return None
    if authorization.phase != _rewrite_values.LateRewritePhase.PUBLISHED:
        return None
    return proof


def stranded_transfer_proof(state: PinnedState) -> bool:
    """Whether a proof stands here that nothing can be reported from.

    Presence rather than truth, which is the difference the reader above
    cannot express. A proof is written by the one statement that settles a
    transfer and dropped by the write behind the record it feeds, so the key
    being there at all says a settlement happened and its record may still be
    owed. Where that key is present and no proof comes back, the comment is
    saying two things that cannot both be true: a settled transfer, and a
    record naming a reading, a phase, or an authorization this build cannot
    account for.

    Read as simply "nothing owed", such a comment lets a road finish over a
    settled transfer no sink ever heard about, with the one fact that would
    have reported it left for nobody. So it is answered as the damage it is,
    and every road that asks fails closed on it.

    False for the ordinary comment, which carries no proof at all: the key is
    dropped by the report, by a rollback, and by the grant that replaces the
    transfer it belonged to.
    """
    if _rewrite_fields.LATE_REWRITE_PROOF not in state.data:
        return False
    return unreported_transfer(state) is None
