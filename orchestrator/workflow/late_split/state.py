# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The round trip one late generation takes through the pinned comment.

The durable operations over the `late_*` group and nothing else: what a record
reads back as, what a write leaves behind, and what a clear drops. Which keys
that group is comes off the `keys` owner, what each field is spelled as on the
way out comes off `encoding` and `ledger_encoding`, and what a raw value reads
back as on the way in comes off `payloads` and `ledgers` -- so what is decided
here is the ORDER those are applied in, which is the part a live issue's
comment depends on.

A record with no cycle identity is not a generation, so the write clears the
late fields rather than recording a half-record no later tick could correlate
to an audit line or a child's lineage. The two external ledgers are what it
does not clear: an obligation the remote is owed does not stop being owed
because the identity beside it was damaged, and dropping it would leave a
snapshot or a branch with nothing on the issue to reclaim it by. So an
uncorrelatable record still writes what it owes, and nothing else.

Keys outside this domain are not read or written: the pinned comment is shared
with every other stage, and a late write is only ever about its own fields.
The one key this owner touches that is not the generation's own is the
retirement correlation a write with an IDENTITY supersedes, spelled on the
`endings` owner beside this one. The `restart` owner moves the pending restart
marker rather than this one: the marker is a pinned field, but minting and
validating an identity is its own contract.
"""
from __future__ import annotations

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    encoding as _encoding,
    endings as _endings,
    formats as _formats,
    keys as _keys,
    ledgers as _ledgers,
    payloads as _payloads,
    restart as _restart,
    spends as _spends,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.late_split.publication import PublicationContext
from orchestrator.workflow.state import WorkflowLabel


def read_late_generation(state: PinnedState) -> LateGeneration:
    """Return the late generation a pinned comment records.

    An issue with no late fields reads back as the record's defaults, which
    `LateGeneration.is_present` answers False on -- the one reading that keeps
    a legacy issue out of every late decision without a migration.

    Which reader a field is read through is the field's contract, not its
    Python type: an identity has to be positive, a measurement non-negative, a
    frozen commit a whole object id and a fingerprint a whole digest, a flag
    literally `true`, a source stage one of this workflow's own labels, a
    measurement failure one of the steps the git domain names, and a restart
    target one of the two labels a restart may apply. Anything else
    reads back absent, so a hand-edited or older value never becomes live
    state -- a threshold of -1 does not make an unmeasured candidate oversized,
    and a `"false"` string does not arm a cancellation or a pending restart.

    The lineage depth is the one field with no safe substitute for an
    unreadable value, so it has none: a damaged or missing depth on a recorded
    cycle reads back as unknown rather than as the root's 0, and a lineage
    already at the bound therefore stays unsplittable while its field is
    damaged. The write leaves it unknown too, so nothing normalizes the gap
    away on the next pass.
    """
    return LateGeneration(
        cycle_id=_payloads.as_identity(state.get(_keys.CYCLE_ID)) or 0,
        generation=_payloads.as_count(state.get(_keys.GENERATION)) or 0,
        root_issue=_payloads.as_identity(state.get(_keys.ROOT_ISSUE)) or 0,
        current_issue=_payloads.as_identity(
            state.get(_keys.CURRENT_ISSUE),
        ) or 0,
        lineage_depth=_payloads.as_depth(state.get(_keys.LINEAGE_DEPTH)),
        scope=_payloads.as_text(state.get(_keys.SCOPE)) or "",
        candidate_sha=_payloads.as_hex(
            state.get(_keys.CANDIDATE_SHA), _formats.COMMIT_LENGTHS,
        ) or "",
        base_sha=_payloads.as_hex(
            state.get(_keys.BASE_SHA), _formats.COMMIT_LENGTHS,
        ) or "",
        threshold=_payloads.as_count(state.get(_keys.THRESHOLD)),
        additions=_payloads.as_count(state.get(_keys.ADDITIONS)),
        measurement_miss_count=_payloads.as_count(
            state.get(_keys.MEASUREMENT_MISS_COUNT),
        ) or 0,
        measurement_failure=_payloads.as_member(
            MeasurementFailure, state.get(_keys.MEASUREMENT_FAILURE),
        ),
        phase=_payloads.as_member(LatePhase, state.get(_keys.PHASE)),
        title_body_hash=_payloads.as_hex(
            state.get(_keys.TITLE_BODY_HASH), _formats.DIGEST_LENGTHS,
        ),
        comment_hash=_payloads.as_hex(
            state.get(_keys.COMMENT_HASH), _formats.DIGEST_LENGTHS,
        ),
        comment_watermark_id=_payloads.as_identity(
            state.get(_keys.COMMENT_WATERMARK_ID),
        ),
        plan_pr_number=_payloads.as_identity(state.get(_keys.PLAN_PR_NUMBER)),
        plan_pr_head=_payloads.as_hex(
            state.get(_keys.PLAN_PR_HEAD), _formats.COMMIT_LENGTHS,
        ) or "",
        plan_pr_body=_payloads.as_text(state.get(_keys.PLAN_PR_BODY)),
        publication=PublicationContext(
            post_publication=_payloads.as_flag(state.get(_keys.POST_PUBLICATION)),
            source_stage=_payloads.as_member(
                WorkflowLabel, state.get(_keys.SOURCE_STAGE),
            ),
            published_pr_number=_payloads.as_identity(
                state.get(_keys.PUBLISHED_PR_NUMBER),
            ),
            published_sha=_payloads.as_hex(
                state.get(_keys.PUBLISHED_SHA), _formats.COMMIT_LENGTHS,
            ) or "",
        ),
        obligations=_ledgers.read_obligations(
            state.get(_keys.RESOURCES), state.get(_keys.CONSUMERS),
        ),
        split_children=_ledgers.read_register(state.get(_keys.SPLIT_CHILDREN)),
        links_announced=_payloads.as_flag(state.get(_keys.LINKS_ANNOUNCED)),
        owner_check_pending=_payloads.as_flag(
            state.get(_keys.OWNER_CHECK_PENDING),
        ),
        cancelled=_payloads.as_flag(state.get(_keys.CANCELLED)),
        cancelled_at=_payloads.as_text(state.get(_keys.CANCELLED_AT)),
        cancelled_phase=_payloads.as_member(
            LatePhase, state.get(_keys.CANCELLED_PHASE),
        ),
        restart_pending=_payloads.as_flag(state.get(_keys.RESTART_PENDING)),
        restart_target=_restart.restart_target(
            state.get(_keys.RESTART_TARGET),
        ),
        restart_cycle_id=_payloads.as_identity(
            state.get(_keys.RESTART_CYCLE_ID),
        ),
        restart_predecessor=_payloads.as_identity(
            state.get(_keys.RESTART_PREDECESSOR),
        ),
    )


def write_late_generation(
    state: PinnedState,
    generation: LateGeneration,
) -> None:
    """Record one late generation, replacing whatever late fields were there.

    Every late key is dropped first, so a field a caller cleared leaves no
    stale value behind for the next tick to reconcile against.

    With one exception, and it is the retirement correlation's own rule: a
    generation with an IDENTITY supersedes it. That correlation names the
    cycle a retirement dropped so a close observed inside that write can
    still be adopted, and a record carrying a live cycle is one where that
    window is over -- either the adoption itself put the cycle back, or an
    operator authorized a fresh one. Leaving it would let a later reader
    correlate an append-only receipt to a cycle the record has long moved
    past. A write with no identity leaves it exactly as the caller set it,
    which is what makes recording it and clearing late mode one write.
    """
    clear_late_generation(state)
    if generation.is_present:
        _endings.clear_retired_cycle(state)
    for key, written in _encoding.written_fields(generation).items():
        state.set(key, written)


def clear_late_generation(state: PinnedState) -> None:
    """Drop every late field, leaving the rest of the pinned state alone."""
    for key in _keys.LATE_STATE_KEYS:
        state.data.pop(key, None)


def read_late_spends(state: PinnedState) -> tuple:
    """The route bookkeeping a hold on this frozen pair still owes.

    All of it or none of it. What a hold owed is ONE claim -- the round a fix
    spends together with the feedback bookmarks that round consumed -- and the
    caller that restores it cannot tell which half it got. Dropping members
    individually is what turns a damaged record into a half-applied one: the
    round advances, the bookmark it was spent for stays pending, the spend
    record is discarded as paid, and the next in_review re-entry correlates
    the same comments again and reruns a developer over feedback that was
    already answered. So a single member the comment cannot vouch for refuses
    the whole group, and `late_claims` parks on the raw key still being there.

    What a member may be is bounded on both ends by the `spends` owner beside
    this one: the key has to name a field this domain knows a route closes,
    and the value has to be one that FIELD may take.

    Empty for every generation frozen by a seam with no bookkeeping behind it,
    which is the whole implementing side: there is no reviewer to have spent a
    round and no stage tail to have been interrupted.
    """
    recorded = state.get(_keys.SPENDS)
    if not isinstance(recorded, list) or not recorded:
        return ()
    if not all(_spends.spendable(pair) for pair in recorded):
        return ()
    return tuple(tuple(pair) for pair in recorded)


def write_late_spends(state: PinnedState, fields: tuple) -> None:
    """Record what a hold on this pair owes, or drop the key where nothing is.

    Written beside the generation and inside `LATE_STATE_KEYS`, so it lives
    and dies with the pair it is about: the retirement that ends a generation
    drops it in the same write, and no later cycle can be handed a round an
    earlier one was owed.
    """
    if not fields:
        state.data.pop(_keys.SPENDS, None)
        return
    state.set(_keys.SPENDS, [[key, spent] for key, spent in fields])
