# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one late generation is spelled as in the pinned comment.

The write side of the round trip, apart from the operations that apply it: the
question here is what each field BECOMES, and the answer has to be the same
spelling the readers on the other side already know -- a vocabulary member as
its wire string, an unset field as nothing at all.

A record with no cycle identity records only what it owes: the two ledgers, if
either holds anything. Everything else on such a record is a half-record
nothing could correlate to an audit line or a child's lineage, while an
obligation stays an obligation whatever happened to the identity that was
written beside it.

Past that gate each field says for itself what "unset" means. A field at its
own empty value -- an absent identity, an empty SHA, a flag that is not set --
names itself None here and is dropped, so the pinned comment carries what this
generation actually knows. A lineage depth of 0 is not one of them: it is the
root of a lineage, and it is written as itself. What is dropped there is an
unknown depth, which is not the same thing and must not be recorded as if it
were.

The publication provenance is additive twice over, and this encoding is what
makes the second half of that true: a generation entered before the work was
published records none of the group, which is the same pinned comment a binary
that never had the group writes. One state, one spelling -- so reading an
absent flag as a pre-publication entry is right about a live issue without a
migration having reached it.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from orchestrator.workflow.late_split import (
    keys as _keys,
    ledger_encoding as _ledger_encoding,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.publication import PublicationContext


def written_fields(generation: LateGeneration) -> dict[str, Any]:
    """Return the pinned fields this generation records, unset ones out."""
    ledgers = _ledger_encoding.ledger_fields(generation.obligations)
    if not generation.is_present:
        return ledgers
    fields = {
        **_evidence_fields(generation),
        **_publication_fields(generation.publication),
        **ledgers,
        _keys.SPLIT_CHILDREN: list(generation.split_children) or None,
        _keys.LINKS_ANNOUNCED: generation.links_announced or None,
        _keys.OWNER_CHECK_PENDING: generation.owner_check_pending or None,
        _keys.CANCELLED: generation.cancelled or None,
        _keys.CANCELLED_AT: generation.cancelled_at,
        _keys.CANCELLED_PHASE: _wire(generation.cancelled_phase),
        _keys.RESTART_PENDING: generation.restart_pending or None,
        _keys.RESTART_TARGET: generation.restart_target,
        _keys.RESTART_CYCLE_ID: generation.restart_cycle_id,
        _keys.RESTART_PREDECESSOR: generation.restart_predecessor,
    }
    return {
        key: written
        for key, written in fields.items()
        if written is not None
    }


def _wire(member: StrEnum | None) -> str | None:
    """Return the wire string one vocabulary field is recorded under, or None.

    Every field holding a member goes through it -- the boundary a generation
    reached, the one it was cancelled from, the stage it was entered at, and
    the step a reading that did not happen stopped at -- so each is written
    exactly as the vocabulary that reads it back spells it.
    """
    return None if member is None else str(member)


def _evidence_fields(generation: LateGeneration) -> dict[str, Any]:
    """Return the identity, the frozen commits, and what they measured.

    A lineage depth of 0 is written as itself: it is the root of a lineage,
    and what is dropped instead is an unknown depth, which is not the same
    thing and must not be recorded as if it were.

    The record of a reading that did not happen is here too, beside the
    measurement it is the absence of, and it is written only while there is
    one: no misses and no failure is what every pinned comment written before
    the pair says, so a generation that measured first time is the same
    comment rather than a second spelling of one.
    """
    return {
        _keys.CYCLE_ID: generation.cycle_id or None,
        _keys.GENERATION: generation.generation or None,
        _keys.ROOT_ISSUE: generation.root_issue or None,
        _keys.CURRENT_ISSUE: generation.current_issue or None,
        _keys.LINEAGE_DEPTH: generation.lineage_depth,
        _keys.SCOPE: generation.scope or None,
        _keys.CANDIDATE_SHA: generation.candidate_sha or None,
        _keys.BASE_SHA: generation.base_sha or None,
        _keys.THRESHOLD: generation.threshold,
        _keys.ADDITIONS: generation.additions,
        _keys.MEASUREMENT_MISS_COUNT: (
            generation.measurement_miss_count or None
        ),
        _keys.MEASUREMENT_FAILURE: _wire(generation.measurement_failure),
        _keys.PHASE: _wire(generation.phase),
        _keys.TITLE_BODY_HASH: generation.title_body_hash,
        _keys.COMMENT_HASH: generation.comment_hash,
        _keys.COMMENT_WATERMARK_ID: generation.comment_watermark_id,
        _keys.PLAN_PR_NUMBER: generation.plan_pr_number,
        _keys.PLAN_PR_HEAD: generation.plan_pr_head or None,
        _keys.PLAN_PR_BODY: generation.plan_pr_body,
    }


def _publication_fields(publication: PublicationContext) -> dict[str, Any]:
    """Return how this generation was entered, absent context dropped.

    A generation entered before anything was published records none of it, so
    the flag goes down only while it is set and the three fields beside it
    only while they hold something. That is what keeps a pre-publication entry
    and a record written without this group the same pinned comment, rather
    than two spellings a later reader would have to tell apart.
    """
    return {
        _keys.POST_PUBLICATION: publication.post_publication or None,
        _keys.SOURCE_STAGE: _wire(publication.source_stage),
        _keys.PUBLISHED_PR_NUMBER: publication.published_pr_number,
        _keys.PUBLISHED_SHA: publication.published_sha or None,
    }
