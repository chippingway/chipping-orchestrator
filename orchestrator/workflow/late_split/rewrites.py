# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Durable rewrite grants, publication rotation, and transfer-proof retirement.

A grant records evidence before a push and moves no exemption. Publication
spends a readable outstanding grant, rotates the exemption and its identity,
carries the operator authorization, and records the proof together. Callers
persist that staged group with their account of what the remote holds.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    exemption_reading as _exemption_reading,
    formats as _formats,
    overrides as _overrides,
    rewrite_fields as _rewrite_fields,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)


def record_rewrite_authorization(
    state: PinnedState, rewrite: _rewrite_values.LateRewrite, fingerprint: str,
) -> None:
    """Record what authorizes this issue's exemption to move, before any push.

    Nothing moves here. The exemption stays exactly on the commit a human
    ruled on, and what goes down beside it is the permission for a later write
    to move it -- so a transfer whose push never lands leaves the verdict
    where the adjudication put it rather than on an object no branch carries.
    The rotation belongs to `record_rewrite_publication`, which the write that
    receipts the push stages it into, so the move lands with that receipt or
    not at all.

    Written beside that exemption and validated against it: the accepted end
    of the rewrite has to BE the commit this issue exempts, because the whole
    of what this record licenses is moving that one verdict, and one naming
    any other commit would describe a move this issue never earned.

    Every field is held to the shape it claims for the reason the exemption
    itself is -- a value that cannot name a commit, a digest, a bounded kind,
    a pull request, or a stage a publication is entered from is not one, and
    writing it would move the failure onto a reader whose only move is to
    reverse a transfer it could not check.

    The phase and the digest scheme are this build's own rather than the
    caller's. The first says the push this authorizes has not been receipted
    yet, which is what tells a reader the exemption has not moved and a
    rollback may still drop the permission; the second says which scheme the
    digest beside it was taken under, and only the owner that takes one can
    answer that.
    """
    refusal = _rewrite_fields._unusable_terms(rewrite, fingerprint)
    if refusal:
        raise _formats.InvalidLateValue(refusal)
    if _exemption_reading.read_exemption(state) != rewrite.from_sha:
        raise _formats.InvalidLateValue(
            "a rewrite authorization is not the exempt commit's",
        )
    for key, recorded in _rewrite_fields._written_terms(rewrite, fingerprint).items():
        state.set(key, recorded)
    # The proof belongs to the transfer this grant REPLACES, and the phase
    # going back to `authorized` is what makes it unreadable beside the new
    # one. A report whose own drop-write GitHub refused is the only way one
    # survives this far, and its record has already been made -- so it is
    # dropped with the group it described rather than left to park the issue
    # a settlement later.
    forget_transfer_proof(state)


def forget_transfer_proof(state: PinnedState) -> None:
    """Drop the proof a report has just been made from."""
    state.data.pop(_rewrite_fields.LATE_REWRITE_PROOF, None)


def record_rewrite_publication(
    state: PinnedState, proof: _rewrite_values.LateRewriteProof,
) -> _rewrite_values.LateRewrite:
    """Spend the permission standing here, carrying the exemption with it.

    The one write in this domain that MOVES a verdict, and every field it
    moves goes down in one statement because a reader is entitled to find them
    agreeing: the exemption becomes the commit the rewrite produced, the
    identity beside it becomes what that commit contributes over its own base,
    the authorization an operator granted for the accepted commit follows the
    exemption onto the same pair, and the phase says the transfer is over.
    Split across writes, a crash between any two leaves a comment whose phase
    and whose commit disagree -- which every reader here refuses, and rightly,
    since it cannot be told from a hand edit.

    The authorization travels because the exemption is not on its own what
    lets a candidate past the gate: a commit an exemption names and no
    authorization stands behind is one the gate measures. Left on the accepted
    commit, an operator's decision would stop covering the object the workflow
    replaced it with, and a rewrite nobody has to decide about again would be
    held for a decision that was already made. What moves with it is the pair
    alone -- the size, the ceiling, and the comment are what a human decided
    rather than facts about an object -- and a comment carrying no
    authorization moves nothing, which is the legacy record's answer and the
    right one: an exemption no gesture stands behind gains none by being
    carried.

    Held to the RECORD rather than to the caller. The permission is read back
    whole and has to still be outstanding, so what is spent is a transfer this
    build granted and can still account for: a group missing a member, one
    bound to a commit this issue does not exempt, one whose kind or phase came
    from somewhere else, and one already `published` are each a record nothing
    may move a human's verdict on, and each refuses rather than being
    repaired. The digest is the record's own for the same reason -- it is what
    the permit was granted over, re-derived and compared before the grant, and
    a reading taken here would fingerprint a checkout that has been writable
    since.

    The PROOF rides the same statement, and it is the one field here that is
    not about the move: it says which reading showed the push had landed, and
    nothing later can re-derive it. Kept on the comment until the record it
    belongs to reaches the sinks, so a process lost between this write and
    that record leaves the next reader something to report from rather than a
    settled transfer nobody ever announced.

    Staged rather than persisted, like every other writer in this domain: what
    makes the move durable is the caller's own write, which is what lets the
    exemption, the identity, and the account of what the remote now holds land
    together or not at all.

    Answers with the rewrite it spent, since the caller that has just moved a
    verdict is the one that owes a record of the move and holds nothing else
    to describe it from.
    """
    authorization = _rewrite_reading.read_rewrite_authorization(state)
    if authorization is None:
        raise _formats.InvalidLateValue(
            "a rewrite publication has no authorization to spend",
        )
    if authorization.phase != _rewrite_values.LateRewritePhase.AUTHORIZED:
        raise _formats.InvalidLateValue(
            "a rewrite publication is not one still outstanding",
        )
    rewrite = authorization.rewrite
    _exemption.record_exemption(state, rewrite.to_sha)
    _exemption.record_semantic_identity(
        state,
        base_sha=rewrite.to_base_sha,
        candidate_sha=rewrite.to_sha,
        fingerprint=authorization.fingerprint,
    )
    _overrides.carry_publication_override(
        state, rewrite.from_sha, rewrite.to_sha, rewrite.to_base_sha,
    )
    state.set(_rewrite_fields.LATE_REWRITE_PHASE, str(_rewrite_values.LateRewritePhase.PUBLISHED))
    state.set(_rewrite_fields.LATE_REWRITE_PROOF, str(proof))
    return rewrite


def clear_rewrite_authorization(state: PinnedState) -> None:
    """Drop the whole authorization and the proof it would have reported.

    Every other field is left alone. The proof goes because it describes the
    transfer being dropped: kept, it would stand over no authorization at all,
    which every reader here refuses as damage.
    """
    for key in _rewrite_fields._AUTHORIZATION_KEYS:
        state.data.pop(key, None)
    forget_transfer_proof(state)
