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
(`verification_carries`). Nothing is posted a second time either way.

The settlement that follows a landed post is `verification_settling`'s.

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
from orchestrator.workflow.engine.verification_carries import abandons_afresh, is_carry

log = logging.getLogger("orchestrator.workflow")

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
    unsettled = _settlement_room(reading, pending)
    if unsettled is not None:
        log.warning(
            "issue=#%d cannot settle verification evidence revision %d over its "
            "pinned comment as it stands (%s); leaving the artifact unpublished "
            "and still owed", issue.number, pending.revision, unsettled.refusal,
        )
        return unsettled.holds
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
    as the state in hand spells it, and every other field as the comment
    carries it now. The artifact's ledger entry is reserved against the ledger
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
        reading.gh, reading.issue, _durable.guarded(reading.state, _settling.SETTLES), widest,
        _verification_comments.RESERVED_LEDGER,
    )
    refused = _durable.refusal_of(prepared)
    if refused is not None:
        return refused
    invalidated = PinnedState(state_data=prepared.reading.data)
    return None if _settlement.retire_current_evidence(invalidated) else _NO_ROOM


def _refuses_the_reading(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    presence: _pr_reports.ReportPresence,
) -> bool:
    """Whether one reading short of PRESENT stops the tick, logged either way.

    A carry is abandoned on a definite answer with the approval it was
    recorded for (`verification_carries`), since nothing a later route does
    makes it answer again.
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
    if is_carry(pending):
        return abandons_afresh(reading.gh, issue, reading.state, pending)
    return False
