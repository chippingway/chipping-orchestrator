# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settle a published verification artifact in the one write that makes it current.

The settlement proves the whole binding once more before it declares anything
current, because a post is long enough for any of it to move: another road can
settle a later report or record another review subject on the pinned comment
meanwhile. So the issue and the pinned comment are read afresh, the comment has
to carry every bound record exactly as the state in hand does
(`verification_durable`), and the whole proof -- pull request, checkout and
trees, context, recorded review subject, settled report at its location,
requirements -- is taken again over them. The settling label is read off that
same issue. Then ONE write, composed over the comment as it stands rather than
over the state in hand, installs it: the evidence that was current goes into
history as superseded, this one becomes current, the handoff names its
receipt, and the pending record is dropped. A settlement replayed after a
crash in front of that write finds the artifact by its receipt and makes the
same write again.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import labels as _labels
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_evidence_models as _evidence_models,
    report_publication_evidence as _publication,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def settles(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    comment_id: int,
) -> bool:
    """Declare one published transaction current, in one write, or leave it owed.

    Composed over the pinned comment as it stands NOW rather than the state in
    hand, and only once the whole binding is proved over it again.
    """
    durable, fresh, refused = _fresh_world(reading, pending, comment_id)
    if refused is not None:
        log.info(
            "issue=#%d is not settling verification evidence revision %d: %s; "
            "leaving it owed", reading.issue.number, pending.revision, refused.refusal,
        )
        if durable is not None:
            # The artifact is on the thread and its comment id is tracked on
            # the comment as it stands; persisted now, over whatever moved,
            # since the tick that next proves the world may defer before it
            # ever reads the thread again.
            _writes(reading, durable)
        return refused.holds
    composed = _settlement.settled_state(durable, pending, comment_id, _label_of(fresh))
    if composed is None:
        log.error(
            "issue=#%d published verification evidence revision %d and settles "
            "into a record this build will not store; holding the tick",
            reading.issue.number, pending.revision,
        )
        return True
    _writes(reading, composed)
    log.info(
        "issue=#%d settled verification evidence revision %d on PR #%d",
        reading.issue.number, pending.revision,
        pending.binding.target.publication.pr_number,
    )
    return False


def _fresh_world(
    reading: _proof.ProofReading,
    pending: _records.PendingEvidence,
    comment_id: int,
) -> tuple[PinnedState | None, Issue | None, _evidence_models.ReportEvidence | None]:
    """The comment and issue read afresh, and the refusal the binding earns over them.

    The comment has to carry every bound record as the state in hand does
    (`verification_durable`); the artifact's comment id is tracked on it, and
    then the whole proof is taken again over it and the fresh issue -- the pull
    request, the checkout and trees, the context, the recorded review subject,
    the settled report re-read at its location, and the requirements.
    """
    try:
        fresh = reading.gh.get_issue(reading.issue.number)
    except Exception:
        log.exception(
            "issue=#%d could not be re-read before settling its verification "
            "evidence", reading.issue.number,
        )
        return None, None, _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the issue could not be re-read before the settlement",
        )
    durable, moved = _durable.durable_comment(reading.gh, fresh, reading.state)
    if durable is not None:
        _comments._track_orchestrator_comment(durable, comment_id)
    if moved is not None:
        return durable, fresh, moved
    publication = pending.binding.target.publication
    proved = _proof.rest_verdict(
        _proof.ProofReading(reading.gh, reading.spec, fresh, durable),
        pending.binding,
        _publication.subject_verdict(reading.gh, publication),
    )
    return durable, fresh, None if proved.proved else proved


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


def _writes(reading: _proof.ProofReading, composed: PinnedState) -> None:
    """Install `composed` as the state in hand and write it to the pinned comment."""
    reading.state.data = composed.data
    reading.gh.write_pinned_state(reading.issue, reading.state)
