# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Post a proved transaction's artifact, and settle it in the one write that makes it current.

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
behind the reconciliation with the transaction still owed. Nothing is posted a
second time either way.

The settlement that follows a landed post is `verification_settling`'s.

The room for that write is proved ahead of the post, not at it: here nothing
has happened yet, while at the write the artifact is already on the thread.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github import pull_request_reports as _pr_reports, verification_evidence as _evidence
from orchestrator.workflow.engine import (
    report_record_state as _report_record_state,
    verification_comments as _verification_comments,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settling as _settling,
)

log = logging.getLogger("orchestrator.workflow")


def publishes(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    pull_request: Any,
) -> bool:
    """Post `pending`'s artifact onto the proved pull request and settle it if it lands.

    True holds the tick; False lets it carry on, over a transaction either
    settled or still owed.
    """
    issue, state = reading.issue, reading.state
    settled = _record_state.settled_payload(state, pending)
    if settled is None or not _report_record_state.fits_the_comment(settled):
        log.error(
            "issue=#%d cannot settle verification evidence revision %d without "
            "writing a pinned comment past what GitHub accepts; standing down "
            "with the artifact unpublished and still owed",
            issue.number, pending.revision,
        )
        return False
    try:
        lookup = _verification_comments._publish_verification_artifact(
            reading.gh, pull_request, state, pending.artifact,
        )
    except _evidence.ArtifactRefusedError:
        log.exception(
            "issue=#%d records verification evidence the artifact format will "
            "not publish; holding the tick", issue.number,
        )
        return True
    if lookup.presence is not _pr_reports.ReportPresence.PRESENT:
        return _refuses_the_reading(issue, pending, lookup.presence)
    if lookup.landed_id is None:
        log.warning(
            "issue=#%d published verification evidence revision %d and could "
            "not read the comment it landed as; holding the tick",
            issue.number, pending.revision,
        )
        return True
    return _settling.settles(reading, pending, lookup.landed_id)


def _refuses_the_reading(
    issue: Issue,
    pending: _records.PendingEvidence,
    presence: _pr_reports.ReportPresence,
) -> bool:
    """Whether one reading short of PRESENT stops the tick, logged either way."""
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
    return False
