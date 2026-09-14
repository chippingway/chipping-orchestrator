# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fingerprint accepted, claimed, and rewritten contributions before granting transfer.

The recorded adjudication must reproduce on this host. A different
claimed base must preserve that contribution too, and the rewritten pair
receives a permit only when its fingerprint is equal.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.git.measurement import (
    fingerprint as _measurement_fingerprint,
)
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
)

# Which end of the rewrite a reading that could not be taken was about, so an
# operator told a contribution has no fingerprint knows which one.
_ACCEPTED = "accepted"

_CLAIMED = "the rewrite claims it replaced"

_REWRITTEN = "rewritten"

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


def _equal_contributions(
    gate: _late_gate_models._Gate,
    rewrite: _rewrite_values.LateRewrite,
    identity: _exemption_reading.LateSemanticIdentity,
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
    gate: _late_gate_models._Gate,
    rewrite: _rewrite_values.LateRewrite,
    identity: _exemption_reading.LateSemanticIdentity,
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
    gate: _late_gate_models._Gate,
    rewrite: _rewrite_values.LateRewrite,
    identity: _exemption_reading.LateSemanticIdentity,
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
    gate: _late_gate_models._Gate, side: str, base_sha: str, candidate_sha: str,
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
