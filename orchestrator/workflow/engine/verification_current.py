# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the current evidence record is still the evidence the pull request carries.

The record says what a settlement put on the pull request once; only a fresh
reading of the exact comment it recorded says the pull request still carries
it. So a reader about to rely on current evidence -- a reviewer handed it, a
readiness decision -- asks two things beside the world the evidence is about.

The HANDOFF has to describe the current record: the same receipt, pull
request, revision, and head. A settlement writes the two in one write, so a
current record the handoff does not describe is one of them replaced by
something other than a settlement, and neither says which evidence is the
latest.

The ARTIFACT has to be there: the comment the settlement recorded, read again
off the pull request's thread, has to be ours and re-render byte for byte as
an artifact, and that artifact has to be the one the record describes -- the
receipt and revision, every identity member the binding supplies, and the
digest of the evidence it carries. A comment deleted, edited out of shape, or
standing there as some other artifact is evidence nobody can be shown.

Both refusals DEFER, since what answers them is fresh evidence rather than a
retry; a thread nobody could read HOLDS.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_records as _records,
    verification_settlement_state as _settlement,
)


def publication_verdict(
    gh: GitHubClient,
    state: PinnedState,
    current: _records.CurrentEvidence,
    pull_request: Any,
) -> _evidence_models.ReportEvidence | None:
    """Refuse current evidence its handoff or its artifact no longer vouches for, or None.

    `pull_request` is the one the caller proved open and standing on the
    evidence's target head, so the thread read is that pull request's.
    """
    if not _handoff_describes(state, current):
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the evidence handoff does not describe the current evidence",
        )
    presence, found = gh.reread_verification_artifact(pull_request, current.comment_id)
    if presence is ReportPresence.UNCONFIRMED:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the current evidence's artifact could not be re-read",
        )
    if presence is not ReportPresence.PRESENT or not _is_the_settled_artifact(found, current):
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the current evidence's artifact is gone or no longer the one that settled",
        )
    return None


def _handoff_describes(state: PinnedState, current: _records.CurrentEvidence) -> bool:
    """Whether the recorded handoff is the one the current record's settlement wrote."""
    handoff = _settlement.read_evidence_handoff(state)
    return handoff is not None and (
        handoff.receipt,
        handoff.pr_number,
        handoff.revision,
        handoff.target_head,
    ) == (
        current.receipt,
        current.binding.target.publication.pr_number,
        current.revision,
        current.binding.target.target_head,
    )


def _is_the_settled_artifact(found: Any, current: _records.CurrentEvidence) -> bool:
    """Whether an artifact re-read is the one `current` records, commands aside.

    The record keeps no commands, so the identity is compared on an artifact
    built from the record with none, and the commands by their digest.
    """
    recorded = _records.PendingEvidence(
        receipt=current.receipt,
        revision=current.revision,
        binding=current.binding,
        commands=(),
    ).artifact
    return (
        dataclasses.replace(found, commands=()) == recorded
        and found.content_revision == current.content_revision
    )
