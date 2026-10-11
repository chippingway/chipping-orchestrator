# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Post a proved transaction's artifact, and settle it in the one commit that makes it current.

The post is idempotent by construction: it is scoped by the transaction's
receipt, so a retry finds whatever an earlier attempt landed -- including the
attempt whose response never came back, which GitHub may well have accepted --
and only a reading that says the artifact is PRESENT settles anything. The
comment it landed as is recorded as this orchestrator's own on the way, so a
generated artifact is never read back as a human's feedback.

What a reading short of PRESENT is owed is the report transaction's split. A
reading nobody could take HOLDS, since the artifact may well be there. Every
other one -- our comment under this receipt edited out of shape -- is a
definite answer about content a human owns, and STANDS DOWN onto the routes
behind the reconciliation with the transaction still owed -- save a carry,
which is abandoned with the approval it was recorded for
(`verification_carries`), and a transaction published under a standing
auto-rebase anchor, which is abandoned the same way since no route behind the
anchor answers it (`verification_carries.abandons_on_refusal`). Nothing is
posted a second time either way.

The settlement that follows a landed post is `verification_settling`'s.

Behind that room, right before the post, the readings no guarded commit
holds are taken again (`verification_unguarded`): the anchor's landing and
base, the issue fetched afresh -- still live work, its requirements hashed over
that reading -- and the configuration last, so an issue edited, a base
advanced, or a command configured otherwise while the proof's requests were
answered posts nothing; a carry, or a transaction published under a standing
anchor, is abandoned on such a refusal as on the proof's own.

The room for that commit is proved ahead of the post, where nothing has
happened yet: the settlement's own guarded commit, staged at its widest and
PREPARED over the pinned comment read afresh (`pinned_commit.prepare`), so a
comment another road filled since this tick read it, or one whose bound records
moved, posts nothing. The settlement measures it again over the comment as it
stands, since the post is long enough for another road to fill it.
"""
from __future__ import annotations

import logging
from typing import Any

from orchestrator.github import pull_request_reports as _pr_reports, verification_evidence as _evidence
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    verification_comments as _verification_comments,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_settling as _settling,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.verification_carries import abandons_afresh, abandons_on_refusal
from orchestrator.workflow.engine.verification_unguarded import unguarded_refusal

log = logging.getLogger("orchestrator.workflow")

_EDITED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "our comment under this transaction's receipt no longer reads as its artifact",
)

_NO_ROOM = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the pinned comment has no room to settle the evidence and later invalidate it",
)


def publishes(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    pull_request: Any,
) -> bool:
    """Post `pending`'s artifact onto the proved pull request and settle it if it lands.

    True holds the tick; False lets it carry on, over a transaction either
    settled or still owed.
    """
    issue = reading.issue
    held = _stops_before_the_post(reading, pending)
    if held is not None:
        return held
    try:
        lookup = _verification_comments._publish_verification_artifact(
            reading.gh, pull_request, reading.state, pending.artifact,
        )
    except _evidence.ArtifactRefusedError:
        log.exception(
            "issue=#%d records verification evidence the artifact format will "
            "not publish; holding the tick", issue.number,
        )
        return True
    if lookup.presence is not _pr_reports.ReportPresence.PRESENT:
        return _refuses_the_reading(reading, pending, lookup.presence)
    if lookup.landed_id is None:
        log.warning(
            "issue=#%d published verification evidence revision %d and could "
            "not read the comment it landed as; holding the tick",
            issue.number, pending.revision,
        )
        return True
    return _settling.settles(reading, pending, lookup.landed_id)


def _settlement_room(
    reading: _proof.ProofReading, pending: _records.PendingEvidence,
) -> ReportEvidence | None:
    """Refuse a post whose settlement the pinned comment as it stands could not record, or None.

    The settlement is staged at its widest -- the widest comment id and label,
    and refused where the evidence it installs could not later be invalidated
    within the comment (`verification_record_state.settled_payload`) -- and
    prepared under the guard the settlement's own commit is taken under
    (`verification_settling`): the comment this tick read, every bound record
    -- and every record the reading rests on (`ProofReading.rests_on`) -- as
    the state in hand spells it, and every other field as the comment carries
    it now. The artifact's ledger entry is reserved against the ledger
    as it stands (`verification_comments.RESERVED_LEDGER`), since a slot
    reserved against the tick's reading may be one another road has recorded
    since, which would reserve nothing. That invalidation is measured again
    over the prepared candidate, since the comment it is laid over may have
    grown. A comment that will not read holds; a bound record that moved, and
    a comment with no room, stand down with nothing posted.
    """
    widest = _record_state.settled_payload(reading.state, pending)
    if widest is None:
        return _NO_ROOM
    prepared = _commit.prepare(
        reading.gh, reading.issue, _durable.guarded(reading.state, _settling.SETTLES, reading.rests_on), widest,
        _verification_comments.RESERVED_LEDGER,
    )
    refused = _durable.refusal_of(prepared)
    if refused is not None:
        if prepared.fields:
            reading.observes(refused)
        return refused
    invalidated = PinnedState(state_data=prepared.reading.data)
    return None if _settlement.retire_current_evidence(invalidated) else _NO_ROOM


def _stops_before_the_post(reading: _proof.ProofReading, pending: _records.PendingEvidence) -> bool | None:
    """Whether the tick stops short of the post, logged; None where the artifact may go out.

    The settlement's room first (`_settlement_room`): a comment that will not
    read holds, and one with no room or whose bound records moved posts
    nothing. Then, behind that and every request of the proof, the readings
    no guarded commit holds (`verification_unguarded.unguarded_refusal`): the
    anchor's landing and base, the issue fetched afresh -- still live work,
    its requirements hashed over that reading -- and the configuration, so
    one that moved while those requests were answered posts nothing. An issue
    that would not read again or stopped being live work writes nothing
    either; any other refusal short of a reading nobody could take abandons
    a carry, or a transaction published under a standing anchor, as the
    proof's own refusal does (`verification_carries.abandons_on_refusal`),
    and leaves the rest owed.
    """
    unsettled = _settlement_room(reading, pending)
    if unsettled is not None:
        log.warning(
            "issue=#%d cannot settle verification evidence revision %d over its "
            "pinned comment as it stands (%s); leaving the artifact unpublished "
            "and still owed", reading.issue.number, pending.revision, unsettled.refusal,
        )
        return unsettled.holds
    behind, refused = unguarded_refusal(reading, reading.state, pending)
    if refused is None:
        return None
    log.info(
        "issue=#%d is not publishing verification evidence revision %d: %s; leaving it owed",
        reading.issue.number, pending.revision, refused.refusal,
    )
    abandoned = abandons_on_refusal(pending, anchored=reading.anchored is not None)
    if behind is None or refused.holds or not abandoned:
        return refused.holds
    return abandons_afresh(reading.gh, reading.issue, reading.state, pending, reading.rests_on)


def _refuses_the_reading(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    presence: _pr_reports.ReportPresence,
) -> bool:
    """Whether one reading short of PRESENT stops the tick, logged either way.

    A carry is abandoned on a definite answer with the approval it was
    recorded for (`verification_carries`), since nothing a later route does
    makes it answer again, and so is a transaction published under a standing
    auto-rebase anchor (`verification_proof.ProofReading.anchored`). The
    answer is kept as the refusal it is before the abandonment is tried
    (`ProofReading.observes`), so a caller collecting them still has it where
    the abandonment's own reading goes unanswered.
    """
    issue = reading.issue
    if presence is _pr_reports.ReportPresence.UNCONFIRMED:
        log.warning(
            "issue=#%d could not confirm verification evidence revision %d on "
            "its pull request; holding the tick", issue.number, pending.revision,
        )
        return True
    log.info(
        "issue=#%d cannot settle verification evidence revision %d (%s); "
        "standing down", issue.number, pending.revision, presence.value,
    )
    reading.observes(_EDITED)
    if abandons_on_refusal(pending, anchored=reading.anchored is not None):
        return abandons_afresh(reading.gh, issue, reading.state, pending, reading.rests_on)
    return False
