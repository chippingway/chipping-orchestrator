# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence an earlier reviewer round left current for the subject the next reviewer is handed.

Settled the way that round leaves it: a reviewer was handed the subject,
returned over it, and declared its run of the suite, which was recorded as a
reviewer-reported transaction and made current by the dispatcher's own
reconciliation -- posted on the pull request and settled on the pinned
comment. The subject is resolved exactly as the next round resolves it, so the
evidence answers for what that round's reviewer is about to be handed.
"""
from __future__ import annotations

from dataclasses import replace
from functools import partial

from orchestrator.github import verification_evidence as _evidence
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.stages.validating import review_report as _review_report
from tests.workflow.repo_values import _FAKE_TREE_SHA
from tests.workflow.stages.validating import (
    review_evidence_readings as _read,
    review_evidence_test_support as _world,
)


def settles_current_evidence(case, *, exit_status: int = 0) -> _records.CurrentEvidence:
    """Record, publish, and settle a run of the suite for the subject `case`'s next reviewer is handed."""
    state = case.github.read_pinned_state(case.issue)
    subject = handed_subject(case, state)
    state.set(_review_subjects.REVIEW_SUBJECT, subject.recorded())
    state.set(_review_subjects.RETURNED_SUBJECT, subject.recorded())
    pending = _record_state.mint_pending_evidence(
        state,
        _world.ISSUE,
        _binding(state, subject),
        (_evidence.VerifiedCommand(_world.SUITE, exit_status, _world.SUITE_OUTPUT),),
    )
    if not _record_state.record_pending_evidence(state, pending):
        raise AssertionError("the earlier round's evidence was refused")
    case.github.write_pinned_state(case.issue, state)
    case._run(partial(case.reconciled, handled=False), run_agent=[])
    return _read.current_evidence(case)


def handed_subject(case, state) -> _review_subjects.ReviewSubject:
    """The subject `case`'s next reviewer is handed, as the round resolves it."""
    requirements = _prompt_context._delivered_thread(
        case.github, case.issue, state,
    ).requirements_revision
    subject, _ = _review_report._reads_the_subject(
        case.github, case.issue, state, _world.PR, requirements,
    )
    return subject


def _binding(state, subject: _review_subjects.ReviewSubject) -> _records.EvidenceBinding:
    """A reviewer's run of the suite on the reviewed head, bound to `subject`."""
    report = _report_settlement.read_current_report(state)
    return _records.EvidenceBinding(
        target=_records.EvidenceTarget(
            publication=replace(
                report.subject, requirements_revision=subject.requirements_revision,
            ),
            subject=subject.recorded(),
        ),
        source=_evidence.EvidenceSource.REVIEWER_REPORTED,
        tested_sha=_world.HEAD,
        tested_tree=_FAKE_TREE_SHA,
        context_revision=_proof.configured_context_revision(),
    )
