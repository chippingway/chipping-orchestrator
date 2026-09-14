# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Exact-commit exemptions and their fail-closed semantic identity reads.

The exact SHA stands on its own. A transferable identity additionally needs
every frozen term, a candidate matching that SHA, and this build's digest
format. A claimed but unreadable record stays distinct from no record.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from orchestrator.git.measurement.models import FINGERPRINT_FORMAT
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

# The commit an authorized settlement published under. Spelled here because
# this is the field's owner, and it is deliberately not one of the keys
# `clear_late_generation` drops.
LATE_EXEMPT_SHA = "late_exempt_sha"

# What that commit carries, spelled beside it because the identity is the
# exemption's own record and shares its whole lifetime. The two ends are the
# generation's frozen base and the candidate the verdict accepted -- the
# candidate is recorded rather than inferred from the exemption so a reader
# can PROVE the digest belongs to the exempt commit instead of assuming it.
LATE_EXEMPT_BASE_SHA = "late_exempt_base_sha"

LATE_EXEMPT_CANDIDATE_SHA = "late_exempt_candidate_sha"

LATE_EXEMPT_FINGERPRINT = "late_exempt_fingerprint"

LATE_EXEMPT_FINGERPRINT_FORMAT = "late_exempt_fingerprint_format"

# What each recorded hex field has to be, at its exact length: an end of the
# diff is a whole git object id, and the fingerprint is a whole digest. An
# abbreviation is not a commit this domain froze and a truncated digest is not
# a hash of anything, so neither is a value a comparison could be made on.
_IDENTITY_SHAPES = MappingProxyType({
    LATE_EXEMPT_BASE_SHA: _formats.COMMIT_LENGTHS,
    LATE_EXEMPT_CANDIDATE_SHA: _formats.COMMIT_LENGTHS,
    LATE_EXEMPT_FINGERPRINT: _formats.DIGEST_LENGTHS,
})

# The identity as one group, because it is written, dropped, and believed as
# one: it describes the commit on the field beside it and nothing else, so a
# write that moves that field takes the whole group with it rather than
# leaving members a later exemption could be read against.
_IDENTITY_KEYS = (
    *_IDENTITY_SHAPES,
    LATE_EXEMPT_FINGERPRINT_FORMAT,
)

# Everything one accepted candidate leaves on the pinned comment. The clear
# takes the group rather than the commit alone: an identity for a commit
# nothing exempts describes a decision this issue does not record.
_EXEMPTION_KEYS = (LATE_EXEMPT_SHA, *_IDENTITY_KEYS)


@dataclass(frozen=True)
class LateSemanticIdentity:
    """What an exempt commit contributes, once every field of it proved out.

    Handed out whole or not at all, so nothing downstream has to decide what
    half of one means. `exempt_sha` and `candidate_sha` are the same commit by
    construction and are both carried because the reader PROVES that rather
    than assuming it: they are separate pinned fields, and a comment where
    they disagree is one this domain did not write.

    `fingerprint_format` travels with the digest because a digest is only ever
    spent compared, and two taken under different rules are not comparable.
    """

    exempt_sha: str
    base_sha: str
    candidate_sha: str
    fingerprint: str
    fingerprint_format: int


def read_exemption(state: PinnedState) -> str | None:
    """Return the commit this issue currently exempts, or None.

    Read through the domain's own object-id reader, so an abbreviation, prose,
    or a value an older binary wrote in some other shape reads back as no
    exemption at all rather than as one nothing can be compared against.
    """
    return _payloads.as_hex(
        state.get(LATE_EXEMPT_SHA), _formats.COMMIT_LENGTHS,
    )


def read_semantic_identity(state: PinnedState) -> LateSemanticIdentity | None:
    """Return what this issue's exempt commit contributes, or None.

    None wherever the record cannot vouch for itself, which is every way it
    can fail to: a field that is missing, a group where only some of them are
    there, a value that is not the shape its field takes, a candidate that is
    not the commit the exemption names, a pinned comment written before this
    field existed, and a digest taken under a scheme this build does not
    compute. Each of those is an id nothing may act on, and answering with a
    partial one would hand a caller a comparison it has no grounds to make.

    What none of them touches is the exemption. The exact commit is exempt on
    its own field and stays exempt here, so a damaged identity costs a later
    tick the transfer and never the decision a human already made.
    """
    exempt = read_exemption(state)
    recorded = {
        key: _payloads.as_hex(state.get(key), lengths)
        for key, lengths in _IDENTITY_SHAPES.items()
    }
    if exempt is None or not all(recorded.values()):
        return None
    if recorded[LATE_EXEMPT_CANDIDATE_SHA] != exempt:
        return None
    written = _payloads.as_identity(state.get(LATE_EXEMPT_FINGERPRINT_FORMAT))
    if written != FINGERPRINT_FORMAT:
        return None
    return LateSemanticIdentity(
        exempt_sha=exempt,
        base_sha=recorded[LATE_EXEMPT_BASE_SHA],
        candidate_sha=recorded[LATE_EXEMPT_CANDIDATE_SHA],
        fingerprint=recorded[LATE_EXEMPT_FINGERPRINT],
        fingerprint_format=written,
    )


def unreadable_exemption(state: PinnedState) -> bool:
    """Whether this comment CLAIMS an exemption it cannot show whole.

    Presence rather than truth, and the question a caller asks before it acts
    on the ABSENCE of one. The fail-closed readers beside this answer "no
    exemption" and "no identity" for a record something damaged just as
    readily as for a comment that never had one -- which is the right answer
    for the gate, whose only move is to measure a candidate afresh, and the
    wrong one for a caller whose move is to walk past an issue as though no
    verdict were in flight. A half-written group, a hand-edited digest, and a
    field carrying `null` all read as nothing there, and an adjudicated commit
    would be left behind on the strength of it.

    Two shapes count. A comment carrying any member of the group whose
    exemption field cannot be read back as a commit is claiming one it cannot
    show. And an identity group with a member present that does not read back
    whole is a claim about what that commit contributes which nothing can
    check.

    The LEGACY shape is neither, and it is why the identity is asked by
    presence rather than by truth: a comment written before this group existed
    carries the exempt commit and nothing beside it, which is complete for
    what it says. It reads as sound here, and what it costs a later tick is
    the transfer rather than the verdict.
    """
    if not any(key in state.data for key in _EXEMPTION_KEYS):
        return False
    if read_exemption(state) is None:
        return True
    if not any(key in state.data for key in _IDENTITY_KEYS):
        return False
    return read_semantic_identity(state) is None


def is_exempt(state: PinnedState, candidate_sha: str) -> bool:
    """Whether THIS commit is the one an adjudication let through.

    Both sides have to be a whole object id and they have to be the same one.
    A candidate the caller could not name, and a recorded exemption that is
    not a commit, each answer False -- the gate's job is to measure what it
    cannot prove was already decided.

    The identity recorded beside the field is deliberately not consulted here.
    This is the claim the gate reads before anything publishes, and it is the
    exact one either way: a commit made on top of the accepted one is a
    different commit carrying different work, and it is measured as the fresh
    candidate it is whatever else the record remembers beside it.
    """
    exempt = read_exemption(state)
    if exempt is None:
        return False
    return exempt == _payloads.as_hex(candidate_sha, _formats.COMMIT_LENGTHS)
