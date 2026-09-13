# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned fields a settlement an operator authorized leaves behind.

An oversized candidate publishes without a reading only where two records
name it: the exemption an adjudication's settlement wrote, and the terms an
operator authorized that publication on. Every stage whose tests put an
accepted commit in front of the size gate needs both, so they are spelled once
here rather than once per stage -- a seed carrying the exemption alone is the
LEGACY shape, and cases about that ask for it by name.

The terms one is granted on are the writer's under `tests/support/`, since the
stage fixtures here and the git-side ones have to agree about them.
"""
from __future__ import annotations

from orchestrator.github import PinnedState
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    overrides as _overrides,
)
from tests.support.authorization import _authorize
from tests.workflow.repo_values import (
    CONTRIBUTION_DIGEST,
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
)

# What the accepted contribution fingerprints to, which is the digest the
# hermetic world answers with: a seed and a reading taken over the same pair
# have to agree, or a case about a record that MATCHES would be seeded with
# one that does not.
ACCEPTED_DIGEST = CONTRIBUTION_DIGEST

# A digest of the same shape that no reading of this world ever takes: what a
# hand edit leaves behind when it writes a term that has to LOOK like one.
FABRICATED_DIGEST = "f" * len(CONTRIBUTION_DIGEST)

# A commit that types as one and that no record on these seeds names.
STRANGER_SHA = "d" * SHA_LENGTH


def _authorized_exemption(
    candidate_sha: str = MEASURED_CANDIDATE_SHA,
    base_sha: str = MEASURED_BASE_SHA,
    *,
    identity: bool = False,
) -> dict:
    """The pinned fields an authorized settlement of `candidate_sha` leaves.

    Written through the two owners rather than spelled as literals, so a seed
    is exactly what the settlement would have produced and a field this domain
    would refuse never reaches a test as though it had been recorded.

    The reading and the comment are the module's own constants rather than
    parameters: what a case varies is which commit the two records name, and
    nothing the gate asks turns on how large the authorized change was.

    `identity` adds the semantic record beside the exemption, which only the
    cases about a transfer need: the exact-SHA claim is what the gate reads,
    and every other case is about that.
    """
    seeded = PinnedState(data={})
    _exemption.record_exemption(seeded, candidate_sha)
    if identity:
        _exemption.record_semantic_identity(
            seeded,
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            fingerprint=ACCEPTED_DIGEST,
        )
    _authorize(seeded, candidate_sha, base_sha, ACCEPTED_DIGEST)
    return seeded.data


def _legacy_exemption(candidate_sha: str = MEASURED_CANDIDATE_SHA) -> dict:
    """The exemption an older binary wrote, with no gesture behind it.

    A `single` verdict used to record this on its own, so a live issue can
    carry it. The candidate it names goes to the ordinary cumulative gate.
    """
    seeded = PinnedState(data={})
    _exemption.record_exemption(seeded, candidate_sha)
    return seeded.data


def _fabricated_authorization(
    candidate_sha: str = MEASURED_CANDIDATE_SHA,
) -> dict:
    """An authorization whose every term reads back and none of it is true.

    The hand edit a shape check cannot catch: the candidate is the commit in
    hand, the base and the digest are whole values of the right length, the
    comment id is an identity, and the count is past its ceiling -- so the
    group parses, names this candidate, and describes a decision nobody made
    over a pair nobody froze. The digest is the one term the objects answer,
    and it is the one this seeds wrong.
    """
    seeded = _authorized_exemption(candidate_sha)
    seeded[_overrides.LATE_OVERRIDE_FINGERPRINT] = FABRICATED_DIGEST
    return seeded


def _damaged_authorization(
    candidate_sha: str = MEASURED_CANDIDATE_SHA,
) -> dict:
    """The same exemption beside an authorization nothing can read whole.

    A hand edit, a half-written crash, and an older scheme all reach the same
    place: a group short of a member it needs is no authorization, and the
    candidate is measured exactly as the legacy record's is.
    """
    seeded = _authorized_exemption(candidate_sha)
    seeded.pop(_overrides.LATE_OVERRIDE_FINGERPRINT, None)
    return seeded


def _authorize_command(candidate_sha: str = MEASURED_CANDIDATE_SHA) -> str:
    """The whole comment an operator publishes a parked candidate with."""
    return f"/orchestrator authorize-oversized {candidate_sha}"
