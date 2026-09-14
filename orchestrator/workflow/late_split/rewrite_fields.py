# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Rewrite pinned keys, bounded field reads, and validated wire encodings.

The phase chooses which commit binds the record to the exemption. Field
readers preserve unknown data as a refusal, and writers validate the full
kind/stage, publication, commit, base, lease, and digest group.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.git.measurement.models import FINGERPRINT_FORMAT
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.state import (
    WorkflowLabel,
)

# Which rewrite the transfer was granted for, and how far it got. Spelled here
# because this is the record's owner, and deliberately outside the keys
# `clear_late_generation` drops.
LATE_REWRITE_KIND = "late_rewrite_kind"

LATE_REWRITE_PHASE = "late_rewrite_phase"

# The pair the contribution came FROM -- the exempt commit a human ruled on,
# and the base it is read over -- and the pair it went TO. Both are recorded
# because the equality between them is re-derived rather than believed: a
# reader with the four ends can fingerprint each pair again and compare, and
# one holding a digest alone could only take this record's word for it.
LATE_REWRITE_FROM_SHA = "late_rewrite_from_sha"

LATE_REWRITE_FROM_BASE_SHA = "late_rewrite_from_base_sha"

LATE_REWRITE_TO_SHA = "late_rewrite_to_sha"

LATE_REWRITE_TO_BASE_SHA = "late_rewrite_to_base_sha"

# The digest both pairs fingerprinted to, and the scheme it was taken under.
# The version travels with it for the reason it travels beside the exemption's
# own: two digests taken under different rules are not comparable, and nothing
# about the ids themselves would say so.
LATE_REWRITE_FINGERPRINT = "late_rewrite_fingerprint"

LATE_REWRITE_FINGERPRINT_FORMAT = "late_rewrite_fingerprint_format"

# The publication the rewrite was made against, which is what scopes this
# authorization to one push: the pull request the work is on, the stage the
# rewrite was entered from, and the head that pull request was standing on
# when the force-push behind it was leased.
LATE_REWRITE_PR_NUMBER = "late_rewrite_pr_number"

LATE_REWRITE_SOURCE_STAGE = "late_rewrite_source_stage"

LATE_REWRITE_LEASE = "late_rewrite_lease"

# Which reading proved the push a settled transfer was spent on, kept beside
# the record until the sinks have been told. The proof is a fact about the
# remote at the moment of the push and nothing later can re-derive it, so a
# process lost between the write that settles the transfer and the record it
# owes would lose it for good. Written with the settlement and dropped by the
# report, so a comment still carrying one is a report somebody still owes.
#
# Deliberately outside the group a reader is held to whole: the transfer is
# settled whether or not it has been reported, and a record short of this
# member is not one to refuse. Being PRESENT is another matter -- the key
# stands only between a settlement and the record it owes -- so one standing
# over a phase or a reading nothing here can account for is damage.
LATE_REWRITE_PROOF = "late_rewrite_proof"

# What each recorded hex field has to be, at its exact length: every end of
# either contribution is a whole git object id, the lease is the whole head a
# push was pinned against, and the fingerprint is a whole digest. An
# abbreviation is not a commit this domain froze, and a truncated digest is
# not a hash of anything.
_HEX_SHAPES = MappingProxyType({
    LATE_REWRITE_FROM_SHA: _formats.COMMIT_LENGTHS,
    LATE_REWRITE_FROM_BASE_SHA: _formats.COMMIT_LENGTHS,
    LATE_REWRITE_TO_SHA: _formats.COMMIT_LENGTHS,
    LATE_REWRITE_TO_BASE_SHA: _formats.COMMIT_LENGTHS,
    LATE_REWRITE_LEASE: _formats.COMMIT_LENGTHS,
    LATE_REWRITE_FINGERPRINT: _formats.DIGEST_LENGTHS,
})

# Everything one authorized transfer leaves on the pinned comment, taken as
# one group: it describes the commit the exemption names, so a record short of
# any member describes a transfer this issue cannot show the evidence for.
_AUTHORIZATION_KEYS = (
    *_HEX_SHAPES,
    LATE_REWRITE_KIND,
    LATE_REWRITE_PHASE,
    LATE_REWRITE_FINGERPRINT_FORMAT,
    LATE_REWRITE_PR_NUMBER,
    LATE_REWRITE_SOURCE_STAGE,
)


def rewritten_commit(state: PinnedState) -> str | None:
    """The commit a group standing here says a rewrite produced, or None.

    The raw end rather than the bound one, because what asks is a caller
    deciding whether a group is ABOUT a commit at all -- before any question
    of whether the move has happened. Read fail-closed like every other
    recorded id, so a field that is missing or is not a whole object id
    answers None, which a caller has to read as "cannot say" rather than as
    "some other commit".
    """
    return _payloads.as_hex(
        state.get(LATE_REWRITE_TO_SHA), _formats.COMMIT_LENGTHS,
    )


def _bound_end(state: PinnedState) -> str | None:
    """Which end of the rewrite this record says the exemption is on, or None.

    The one thing the phase decides for a reader, and the reason it is on the
    record at all. A transfer is granted BEFORE the push and rotates nothing:
    while it stands at `authorized` the exemption is still the commit a human
    ruled on, so the accepted end is what binds the record to it. The write
    that receipts the landed push is what moves the exemption onto the object
    the rewrite produced, and past that boundary the rewritten end is what
    binds -- which is why that write moves the two in one statement rather
    than one after the other.

    None where the phase or the end it names is not one this build can read,
    which is not the same claim as "bound to some other commit": a record that
    cannot say which end it is on has not been shown to be about anything
    else, and every caller here treats that as a claim rather than as a gap.
    """
    phase = _payloads.as_member(
        _rewrite_values.LateRewritePhase, state.get(LATE_REWRITE_PHASE),
    )
    if phase is None:
        return None
    bound = (
        LATE_REWRITE_TO_SHA if phase == _rewrite_values.LateRewritePhase.PUBLISHED
        else LATE_REWRITE_FROM_SHA
    )
    return _payloads.as_hex(state.get(bound), _formats.COMMIT_LENGTHS)


def _bounded_terms(state: PinnedState) -> dict | None:
    """The five bounded fields of one record, or None if any is not one.

    Together because they fail together: a kind, a phase, a digest scheme, a
    pull request, and a stage are each a value this build either accounts for
    or does not, and a record short of any of them is not one to act on.

    The stage is asked what it IS rather than merely whether it is a label,
    and asked AGAINST THE KIND beside it: the two are one claim about which
    rewrite this workflow made and where, so a record whose stage does not
    make its kind is one nothing here produced however well each field types
    on its own. That is narrower than the predicate the entry was frozen
    against and admits nothing it would not, so a record this reads whole
    still describes a publication the remote already carries.
    """
    kind = _payloads.as_member(_rewrite_values.LateRewriteKind, state.get(LATE_REWRITE_KIND))
    phase = _payloads.as_member(
        _rewrite_values.LateRewritePhase, state.get(LATE_REWRITE_PHASE),
    )
    written = _payloads.as_identity(state.get(LATE_REWRITE_FINGERPRINT_FORMAT))
    pr_number = _payloads.as_identity(state.get(LATE_REWRITE_PR_NUMBER))
    stage = _payloads.as_member(
        WorkflowLabel, state.get(LATE_REWRITE_SOURCE_STAGE),
    )
    if kind is None or phase is None or pr_number is None:
        return None
    if written != FINGERPRINT_FORMAT:
        return None
    if not _rewrite_values.entered_from(kind, stage):
        return None
    return {
        "kind": kind,
        "phase": phase,
        "fingerprint_format": written,
        "pr_number": pr_number,
        "source_stage": stage,
    }


def _written_terms(rewrite: _rewrite_values.LateRewrite, fingerprint: str) -> dict:
    """Every key one authorization goes down as, with what it carries.

    Assembled as one mapping rather than written a field at a time, because
    the record is believed as one: a reader holds it whole or not at all, so
    the write that produces it is one statement of what the whole is.
    """
    return {
        LATE_REWRITE_KIND: str(rewrite.kind),
        LATE_REWRITE_PHASE: str(_rewrite_values.LateRewritePhase.AUTHORIZED),
        LATE_REWRITE_FROM_SHA: rewrite.from_sha,
        LATE_REWRITE_FROM_BASE_SHA: rewrite.from_base_sha,
        LATE_REWRITE_TO_SHA: rewrite.to_sha,
        LATE_REWRITE_TO_BASE_SHA: rewrite.to_base_sha,
        LATE_REWRITE_FINGERPRINT: fingerprint,
        LATE_REWRITE_FINGERPRINT_FORMAT: FINGERPRINT_FORMAT,
        LATE_REWRITE_PR_NUMBER: rewrite.pr_number,
        LATE_REWRITE_SOURCE_STAGE: str(rewrite.source_stage),
        LATE_REWRITE_LEASE: rewrite.lease,
    }


def _unusable_terms(rewrite: _rewrite_values.LateRewrite, fingerprint: str) -> str:
    """Why this rewrite is not one an authorization may be written for, or "".

    One answer for every term, because a caller that cannot name any of them
    has the same problem: it is asking this domain to record evidence a later
    reader could not check, and the reader's only move is to undo a human's
    verdict on the strength of it.
    """
    if rewrite.kind not in _rewrite_values.LateRewriteKind:
        return f"a rewrite kind is not one this build authorizes ({rewrite.kind!r})"
    if not _formats.whole_number(rewrite.pr_number) or rewrite.pr_number <= 0:
        return (
            "a rewritten publication is not an identity "
            f"({type(rewrite.pr_number).__name__})"
        )
    if not _rewrite_values.entered_from(rewrite.kind, rewrite.source_stage):
        return (
            f"a {rewrite.kind} rewrite is not one "
            f"`{rewrite.source_stage}` makes"
        )
    named = (
        (rewrite.from_sha, _formats.COMMIT_LENGTHS),
        (rewrite.from_base_sha, _formats.COMMIT_LENGTHS),
        (rewrite.to_sha, _formats.COMMIT_LENGTHS),
        (rewrite.to_base_sha, _formats.COMMIT_LENGTHS),
        (rewrite.lease, _formats.COMMIT_LENGTHS),
        (fingerprint, _formats.DIGEST_LENGTHS),
    )
    for given, lengths in named:
        if not _formats.is_hex_of(given, lengths):
            return f"a rewrite authorization is not one ({type(given).__name__})"
    return ""
