# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Durable writes for exact-commit exemptions and their semantic identities.

The exemption and identity outlive the generation that earned them. Moving
the exempt commit drops the prior identity; recording an identity requires
the same commit and validates every frozen term. The read owner supplies
the key groups and the exact-commit check used by these writes.
"""
from __future__ import annotations

from orchestrator.git.measurement.models import FINGERPRINT_FORMAT
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    formats as _formats,
)


def record_exemption(state: PinnedState, candidate_sha: str) -> None:
    """Exempt exactly this commit from the size gate.

    Refuses anything that is not a whole git object id. The field is read by
    the gate that decides whether a candidate may publish, so a value that
    cannot name one commit is a bypass rather than a record -- and recording
    it here would move the failure onto the reader, which has a candidate in
    hand and nowhere to put it.

    Moving the field to ANOTHER commit drops the identity standing beside it,
    and that is what keeps a stale one from becoming believable again. An
    identity describes the commit the field named when it was written, and a
    verdict that records only the commit -- every one whose fingerprint could
    not be read -- writes nothing over it. Left there, it would go on matching
    by name alone: an issue that accepts commit A with an identity, then B
    with none, then A again with none would hand A's first digest back as what
    the last adjudication decided, over a base that generation never measured.

    Re-recording the SAME commit keeps it, which is what a retry needs. A
    settlement that crashed between this write and its handoff comes back and
    writes the exemption again, over an identity its own earlier pass derived
    from the very pair this one is still frozen on.
    """
    if not _formats.is_hex_of(candidate_sha, _formats.COMMIT_LENGTHS):
        raise _formats.InvalidLateValue(
            f"an exemption is not a commit ({type(candidate_sha).__name__})",
        )
    if _exemption_reading.read_exemption(state) != candidate_sha:
        for key in _exemption_reading._IDENTITY_KEYS:
            state.data.pop(key, None)
    state.set(_exemption_reading.LATE_EXEMPT_SHA, candidate_sha)


def record_semantic_identity(
    state: PinnedState,
    base_sha: str,
    candidate_sha: str,
    fingerprint: str,
) -> None:
    """Record what the exempt commit contributes, over the pair it was read on.

    Written beside an exemption that is already down and validated against it:
    an identity naming any other commit would describe a change this issue
    never adjudicated, and would describe it under the authority of a verdict
    about something else, so it refuses rather than recording one.

    Every field is held to the shape it claims for the reason the exemption
    itself is -- a value that cannot name a commit or a digest is not one, and
    writing it would move the failure onto a reader that has a comparison to
    make and nothing sound to make it against.

    The version is this build's own rather than the caller's. What it says is
    which scheme the digest beside it was taken under, and only the owner that
    takes one can answer that.
    """
    for given, lengths in (
        (base_sha, _formats.COMMIT_LENGTHS),
        (candidate_sha, _formats.COMMIT_LENGTHS),
        (fingerprint, _formats.DIGEST_LENGTHS),
    ):
        if not _formats.is_hex_of(given, lengths):
            raise _formats.InvalidLateValue(
                f"a semantic identity is not one ({type(given).__name__})",
            )
    if _exemption_reading.read_exemption(state) != candidate_sha:
        raise _formats.InvalidLateValue(
            "a semantic identity is not the exempt commit's",
        )
    state.set(_exemption_reading.LATE_EXEMPT_BASE_SHA, base_sha)
    state.set(_exemption_reading.LATE_EXEMPT_CANDIDATE_SHA, candidate_sha)
    state.set(_exemption_reading.LATE_EXEMPT_FINGERPRINT, fingerprint)
    state.set(_exemption_reading.LATE_EXEMPT_FINGERPRINT_FORMAT, FINGERPRINT_FORMAT)


def clear_exemption(state: PinnedState) -> None:
    """Drop the exemption and its identity, leaving every other field alone."""
    for key in _exemption_reading._EXEMPTION_KEYS:
        state.data.pop(key, None)
