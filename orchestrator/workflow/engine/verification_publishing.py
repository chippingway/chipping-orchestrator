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

The settlement proves the world once more before it declares anything current,
because a post is long enough for it to move: the pull request, read afresh,
has to be standing on the head the artifact was written for, and the issue,
read afresh, has to carry the requirements the evidence was bound to. The
settling label is read off that same issue. Then ONE write installs it:
the evidence that was current goes into history as superseded, this one
becomes current, the handoff names its receipt, and the pending record is
dropped. A settlement replayed after a crash in front of that write finds the
artifact by its receipt and makes the same write again.

The room for that write is proved ahead of the post, not at it: here nothing
has happened yet, while at the write the artifact is already on the thread.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github import (
    labels as _labels,
    pull_request_reports as _pr_reports,
    verification_evidence as _evidence,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_publication_evidence as _publication,
    report_record_state as _report_record_state,
    verification_comments as _verification_comments,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_subject as _subject,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def publishes(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingEvidence,
    pull_request: Any,
) -> bool:
    """Post `pending`'s artifact onto the proved pull request and settle it if it lands.

    True holds the tick; False lets it carry on, over a transaction either
    settled or still owed.
    """
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
            gh, pull_request, state, pending.artifact,
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
    return settles(gh, issue, state, pending, lookup.landed_id)


def settles(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingEvidence,
    comment_id: int,
) -> bool:
    """Declare one published transaction current, in one write, or leave it owed."""
    fresh, refused = _fresh_world(gh, issue, state, pending)
    if refused is not None:
        log.info(
            "issue=#%d is not settling verification evidence revision %d: %s; "
            "leaving it owed", issue.number, pending.revision, refused.refusal,
        )
        # The artifact is on the thread and its comment id is in the ledger
        # held here; persisted now, since the tick that next proves the world
        # may defer before it ever reads the thread again.
        gh.write_pinned_state(issue, state)
        return refused.holds
    composed = _settlement.settled_state(state, pending, comment_id, _label_of(fresh))
    if composed is None:
        log.error(
            "issue=#%d published verification evidence revision %d and settles "
            "into a record this build will not store; holding the tick",
            issue.number, pending.revision,
        )
        return True
    state.data = composed.data
    gh.write_pinned_state(issue, state)
    log.info(
        "issue=#%d settled verification evidence revision %d on PR #%d",
        issue.number, pending.revision,
        pending.binding.target.publication.pr_number,
    )
    return False


def _fresh_world(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pending: _records.PendingEvidence,
) -> tuple[Issue | None, _evidence_models.ReportEvidence | None]:
    """The issue read afresh, or the refusal the pull request or requirements earn."""
    standing = _publication.subject_verdict(gh, pending.binding.target.publication)
    if not standing.proved:
        return None, standing
    try:
        fresh = gh.get_issue(issue.number)
    except Exception:
        log.exception(
            "issue=#%d could not be re-read before settling its verification "
            "evidence", issue.number,
        )
        return None, _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the issue could not be re-read for its requirements",
        )
    requirements = pending.binding.target.publication.requirements_revision
    return fresh, _subject.requirements_verdict(fresh, state, requirements)


def _label_of(fresh: Issue) -> WorkflowLabel | None:
    """The workflow label `fresh` carries, or None where it will not read.

    Fail-closed: a settlement raising out of a lazy label read would leave the
    artifact published and the transaction still owed.
    """
    try:
        return _labels.workflow_label(fresh)
    except Exception:
        log.exception(
            "issue=#%d could not read the label its verification evidence "
            "settled under; recording the settlement without one", fresh.number,
        )
        return None


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
