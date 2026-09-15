# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Encode late adjudication results and check their pinned-comment size.

Child payloads retain declared estimates and only their persisted fields.
A rationale is cut to its fixed bound before anything is measured, and the
size check uses the actual pinned-state serialization.
"""
from __future__ import annotations

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.stages.decomposition import (
    late_budget as _budget,
    late_run_reading as _late_run_reading,
)
from orchestrator.workflow.stages.decomposition.late_result_models import (
    _RATIONALE_VERDICTS,
    MAX_RATIONALE,
    RATIONALE_TRUNCATION_MARKER,
    _LateAdjudication,
)


def _fits_the_comment(state_data: dict, ceiling: int) -> bool:
    """Whether a pinned comment holding exactly this would fit its ceiling.

    The prospective body is rendered by the owner that writes it, so what is
    measured is the write rather than an estimate of it. The ceiling is the
    caller's, because what has to fit AFTER a write differs by which write it
    is: a hold still owes the comment the record that starts the run, while a
    completed outcome owes it only what other stages add later.
    """
    return len(
        _pinned_state.pinned_state_body(state_data),
    ) <= ceiling


def _result_payload(adjudication: _LateAdjudication) -> dict:
    """The pinned fields one completed adjudication is written as.

    The children are rewritten from the fields a child issue is created out of
    rather than copied, so nothing an agent put beside them travels into the
    pinned comment a human reads and every other stage shares. The declared
    budget is one of them: the child issue states the size its slice was
    proposed at, so a manifest recorded without it would leave a tick that
    crashed between the verdict and the transaction creating children that say
    nothing about their own size -- and the only way back to the number would
    be a second adjudication free to propose a different split entirely.

    The explanation goes only where the reply gave one, and so does the
    budget. What an absent field means is settled on the way back, so writing
    a stand-in here would put this binary's own number in the comment as
    though an agent had estimated it, and spend the comment budget saying
    nothing.

    The rationale is the one field shortened, and it is cut here, before the
    comment is measured, so what the preflight measures is what gets written.
    Only a `single` and a `split` keep one. Every field a verdict is acted on
    through reaches the measurement whole: a truncated question, explanation,
    or manifest would say something nobody did.
    """
    recorded = {_late_run_reading._LATE_RESULT_VERDICT: str(adjudication.verdict)}
    if adjudication.category is not None:
        recorded[_late_run_reading._LATE_RESULT_CATEGORY] = str(adjudication.category)
    if adjudication.question:
        recorded[_late_run_reading._LATE_RESULT_QUESTION] = adjudication.question
    if adjudication.split_blocker:
        recorded[_late_run_reading._LATE_RESULT_SPLIT_BLOCKER] = adjudication.split_blocker
    if adjudication.children:
        recorded[_late_run_reading._LATE_RESULT_CHILDREN] = [
            _recorded_child(child) for child in adjudication.children
        ]
    if adjudication.verdict in _RATIONALE_VERDICTS and adjudication.rationale.strip():
        recorded[_late_run_reading._LATE_RESULT_RATIONALE] = _bounded_rationale(
            adjudication.rationale,
        )
    return recorded


def _bounded_rationale(rationale: str) -> str:
    """The rationale as a record keeps it: whole, or a prefix and the marker.

    Cut on characters of the value rather than on its serialized length, so
    the same argument keeps the same words whatever it escapes to; the marker
    takes its room out of the bound rather than past it.
    """
    if len(rationale) <= MAX_RATIONALE:
        return rationale
    prefix = rationale[:MAX_RATIONALE - len(RATIONALE_TRUNCATION_MARKER)]
    return f"{prefix}{RATIONALE_TRUNCATION_MARKER}"


def _recorded_child(child: dict) -> dict:
    """The fields one proposed child is kept as, and nothing beside them."""
    kept = {
        "title": child.get("title"),
        "body": child.get("body"),
        "depends_on": list(child.get("depends_on") or []),
    }
    estimated = _budget.declared_budget(child)
    if estimated is not None:
        kept[_budget.ESTIMATE] = estimated
    return kept
