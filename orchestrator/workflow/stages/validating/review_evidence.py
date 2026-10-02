# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow verification evidence a reviewer is handed beside its subject.

A reviewer is handed the evidence this issue records as CURRENT, and only
where that evidence answers for the very subject the reviewer is about to be
handed -- the pull request, head, requirements, and developer report, compared
whole as `review_subjects` records them, the report by its revision and the
digest of its complete text. Evidence bound to an earlier report on the same
head, or to requirements the issue has moved past, is evidence about a review
nobody is asking for now; handed over, a reviewer could reuse it for a subject
it never covered.

The record alone is not enough either, since a head, a context, a report, or
the artifact itself can move after a settlement and the record sees none of
it. So the evidence is proved current again first
(`verification_proof.current_evidence_verdict`) -- still the latest revision
this issue spent, its handoff describing it, its artifact on the pull request
exactly as it settled, and the whole binding proved against the world -- and
the artifact is then re-read at the comment it settled as, which is what the
prompt quotes (`review_evidence_prompts`) -- held again to the record exactly
as the proof held its own reading, since an edit landing between the two reads
could otherwise put words the evidence never carried under the revision the
reviewer is told to reuse.

The reviewer round asks it once the launch has recorded the round's subject
(`reviewer`), so evidence this orchestrator executed is held to the subject
this reviewer is handed, and a reviewer's evidence to the subject the last
returned reviewer read, which is this one's only where nothing moved since.

Anything short of that hands no evidence, logged with why, and the reviewer is
told to run the verification itself. A reading nobody could take is no reason to hold the
round: a reviewer handed nothing to reuse still produces fresh evidence.
"""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    review_evidence_prompts as _evidence_prompts,
    review_subjects as _review_subjects,
    verification_current as _current,
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")


def handed_evidence(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    subject: _review_subjects.ReviewSubject,
) -> _evidence_prompts.HandedEvidence | None:
    """The current evidence a reviewer of `subject` is handed, or None for none.

    Every None is logged with why, so an operator can tell a reviewer that
    ran the verification itself for want of evidence from one handed nothing
    because the evidence moved -- and either from a reading nobody could take.
    """
    current = _settlement.read_current_evidence(state)
    if current is None:
        return _hands_none(issue, _no_current_record(state))
    if current.binding.target.subject != subject.recorded():
        return _hands_none(issue, "the current evidence answers for another subject than the one handed")
    proved = _proof.current_evidence_verdict(_proof.ProofReading(gh, spec, issue, state))
    if not proved.proved:
        return _hands_none(issue, proved.refusal)
    presence, found = gh.reread_verification_artifact(proved.pull_request, current.comment_id)
    refusal = _prompt_read_refusal(presence, found, current)
    if refusal:
        return _hands_none(issue, refusal)
    return _evidence_prompts.HandedEvidence(current, found)


def _no_current_record(state: PinnedState) -> str:
    """Why no current record was read: none recorded, or one that will not read."""
    if state.get(_records.CURRENT_EVIDENCE) is None:
        return "this issue records no current verification evidence"
    return "the current verification evidence recorded on the pinned comment will not read"


def _prompt_read_refusal(
    presence: ReportPresence, found: Any, current: _records.CurrentEvidence,
) -> str:
    """Why the artifact read for the prompt cannot be quoted, or "".

    A thread nobody could read is told apart from an artifact deleted or
    edited since the proof read it, as the proof's own reading tells them.
    """
    if presence is ReportPresence.UNCONFIRMED:
        return "the artifact could not be re-read for the prompt"
    if presence is not ReportPresence.PRESENT or not _current._is_the_settled_artifact(found, current):
        return "the artifact re-read for the prompt is gone or no longer the one that settled"
    return ""


def _hands_none(issue: Issue, why: str) -> None:
    """Log why a reviewer of `issue` is handed no verification evidence."""
    log.info("issue=#%d hands its reviewer no verification evidence: %s", issue.number, why)
